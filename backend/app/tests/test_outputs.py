"""Tests for output generation: the prompts, the routes, and what they persist.

Everything runs offline. Azure is replaced at exactly one seam --
``output_service._open_output_stream`` -- so the prompt assembly, the delta
extraction, the SSE framing, the three-row commit, and the tracker flip are all
the real code with only the network faked.

Two opt-in checks sit at the bottom: ``test_live_cover_letter`` calls Azure for
real behind ``RUN_LIVE=1``, because every offline test here would pass with a
prompt that produced nothing useful, and ``test_db_resume_roundtrip`` drives the
whole resume path through the real Postgres behind ``RUN_DB=1``.
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.chat_message import ChatMessage
from app.models.generated_output import GeneratedOutput
from app.models.tracker_entry import TrackerEntry
from app.services import chat_service, output_service
from app.tests.conftest import OTHER_USER_ID, FakeSession
from app.tests.test_analysis import make_analysis
from app.tests.test_chat import (
    NOW,
    _Chunk,
    make_chat,
    make_profile,
    make_tracker,
    parse_sse,
)
from app.utils.retry import is_retryable, retry_with_backoff

CHAT_ID = "00000000-0000-0000-0000-000000000001"


# ==========================================================================
# Azure double
# ==========================================================================


def fake_azure_stream(
    monkeypatch: pytest.MonkeyPatch,
    tokens: list[str],
    fail_after: int | None = None,
) -> dict:
    """Replace the Azure streaming call with a canned sequence of chunks.

    Args:
        tokens: The chunks to emit, in order.
        fail_after: Raise once this many chunks have been emitted.

    Returns:
        A dict that captures the ``output_type`` and ``prompt`` the service
        sent, so a test can assert on the prompt without rebuilding it.
    """
    captured: dict = {}

    def _open(output_type: str, prompt: str):
        captured["output_type"] = output_type
        captured["prompt"] = prompt

        def chunks():
            for index, token in enumerate(tokens):
                if fail_after is not None and index == fail_after:
                    raise RuntimeError("azure connection dropped")
                yield _Chunk(token)

        return chunks()

    monkeypatch.setattr(output_service, "_open_output_stream", _open)
    return captured


def seeded_chat(db: FakeSession, **kwargs):
    """Seed a chat with its tracker entry and the sample profile."""
    chat = db.seed(make_chat(**kwargs))
    db.seed(make_tracker(chat.id))
    db.seed(make_profile())
    return chat


def make_output(
    chat_id: uuid.UUID,
    output_type: str = "resume",
    content: str = "# Resume",
    created_at: datetime = NOW,
) -> GeneratedOutput:
    """Build a GeneratedOutput row the way the database would hand one back."""
    return GeneratedOutput(
        id=uuid.uuid4(),
        chat_id=chat_id,
        output_type=output_type,
        content=content,
        created_at=created_at,
    )


# ==========================================================================
# Auth guards
# ==========================================================================


def test_create_output_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/outputs is protected by get_current_user."""
    response = client.post(
        "/chats/{}/outputs".format(CHAT_ID), json={"output_type": "resume"}
    )
    assert response.status_code == 401


def test_list_outputs_requires_auth(client: TestClient) -> None:
    """GET /chats/{id}/outputs is protected by get_current_user."""
    assert client.get("/chats/{}/outputs".format(CHAT_ID)).status_code == 401


# ==========================================================================
# Prompts
# ==========================================================================


def test_every_output_type_has_a_grounded_markdown_prompt() -> None:
    """All three system prompts forbid fabrication and ask for markdown."""
    for output_type in output_service.OUTPUT_TYPES:
        prompt = output_service.system_prompt_for(output_type).lower()
        assert "never invent" in prompt
        assert "markdown" in prompt
        assert "profile" in prompt


def test_resume_prompt_names_every_section_in_order() -> None:
    """The resume prompt fixes the section list the frontend renders."""
    prompt = output_service.RESUME_SYSTEM_PROMPT
    positions = [
        prompt.index(section)
        for section in (
            "Summary",
            "Experience",
            "Skills",
            "Education",
            "Projects",
            "Certifications",
        )
    ]
    assert positions == sorted(positions)
    assert "Omit any section" in prompt


def test_unknown_output_type_is_rejected() -> None:
    """A kind with no prompt fails loudly rather than generating something."""
    with pytest.raises(output_service.OutputError):
        output_service.system_prompt_for("linkedin_post")


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "Answer this question: Why do you want to work here?",
            "Why do you want to work here?",
        ),
        (
            "Help me answer this application question: Describe a conflict.",
            "Describe a conflict.",
        ),
        (
            "The question is: What is your greatest weakness?",
            "What is your greatest weakness?",
        ),
        (
            'Answer this application question - "Tell me about yourself"',
            "Tell me about yourself",
        ),
        # No marker at all: the whole message is the question.
        ("Why do you want this role?", "Why do you want this role?"),
        ("", ""),
    ],
)
def test_extract_question(message: str, expected: str) -> None:
    """The lead-in is the user's instruction; what follows it is the question."""
    assert output_service.extract_question(message) == expected


def test_build_output_prompt_carries_profile_jd_analysis_and_history() -> None:
    """Everything the model needs to stay grounded is in one prompt."""
    prompt = output_service.build_output_prompt(
        "cover_letter",
        {"summary": "Backend engineer.", "skills": ["Python"]},
        "Kestrel Payments is hiring a backend engineer.",
        analysis=make_analysis(uuid.uuid4(), fit_score=74),
        history=[{"role": "user", "content": "Write me a cover letter"}],
        user_message="Write me a cover letter, mention my team leadership",
    )

    assert "PROFILE:" in prompt
    assert "JOB DESCRIPTION:" in prompt
    assert "Kestrel Payments" in prompt
    assert "ANALYSIS ALREADY SHOWN TO THE USER" in prompt
    assert "CONVERSATION:" in prompt
    assert "mention my team leadership" in prompt


def test_build_output_prompt_isolates_the_question_for_an_answer() -> None:
    """The answer prompt states the question on its own, not buried in prose."""
    prompt = output_service.build_output_prompt(
        "answer",
        {"summary": "Backend engineer."},
        "A job.",
        user_message="Answer this question: Why us?",
    )

    assert "APPLICATION QUESTION TO ANSWER:\nWhy us?" in prompt
    assert "THE CANDIDATE'S FULL REQUEST:" in prompt


# ==========================================================================
# The intent path: POST /chats/{id}/messages
# ==========================================================================


@pytest.mark.parametrize(
    "message,kind",
    [
        ("Can you tailor my resume for this role?", "resume"),
        ("Please write me a cover letter", "cover_letter"),
        ("Help me answer this application question: why us?", "answer"),
    ],
)
def test_each_intent_generates_and_stores_its_output(
    auth_client: TestClient,
    db: FakeSession,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    kind: str,
) -> None:
    """Every output intent streams from Azure and files a generated_outputs row."""
    chat = seeded_chat(db)
    captured = fake_azure_stream(monkeypatch, ["Dear ", "hiring team"])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": message}
    )

    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "token", "token", "done"]
    assert events[0]["kind"] == kind
    assert captured["output_type"] == kind

    outputs = db.rows(GeneratedOutput)
    assert len(outputs) == 1
    assert outputs[0].output_type == kind
    assert outputs[0].content == "Dear hiring team"
    assert outputs[0].chat_id == chat.id
    assert events[-1]["output_id"] == str(outputs[0].id)

    assistant = [m for m in db.rows(ChatMessage) if m.role == "assistant"]
    assert (assistant[0].kind, assistant[0].content) == (kind, "Dear hiring team")


def test_generating_a_resume_flips_the_tracker(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The done event reports the flip so the tracker store need not refetch."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["# Tailored resume"])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Tailor my resume for this role"},
    )

    done = parse_sse(response.text)[-1]
    assert done["resume_type"] == "tailored"
    assert uuid.UUID(done["output_id"])
    assert db.rows(TrackerEntry)[0].resume_type == "tailored"


def test_a_cover_letter_leaves_the_tracker_alone(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a resume changes resume_type, and only a resume reports it."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["Dear hiring team"])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Please write me a cover letter"},
    )

    done = parse_sse(response.text)[-1]
    assert "resume_type" not in done
    assert "output_id" in done
    assert db.rows(TrackerEntry)[0].resume_type == "unaltered"


def test_the_output_turn_is_one_commit(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Message, output row, and tracker flip land together or not at all."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["# Resume"])
    before = db.commits

    auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Tailor my resume"},
    )

    # One for the user message, one for the whole assistant turn.
    assert db.commits - before == 2


def test_a_failed_stream_keeps_the_partial_but_files_nothing(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a resume stays on screen; it is not filed as a finished document."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["# Resume", "\n\nSummary"], fail_after=1)

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Tailor my resume"},
    )

    error = parse_sse(response.text)[-1]
    assert error["type"] == "error"
    assert error["partial"] is True
    assert error["content"] == "# Resume"

    assistant = [m for m in db.rows(ChatMessage) if m.role == "assistant"]
    assert assistant[0].content == "# Resume"
    assert db.rows(GeneratedOutput) == []
    assert db.rows(TrackerEntry)[0].resume_type == "unaltered"


def test_generation_reads_the_profile_the_jd_and_the_analysis(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt Azure receives is built from the stored rows, not from air."""
    chat = seeded_chat(db, jd_text="Kestrel Payments needs Kubernetes and Python.")
    db.seed(make_analysis(chat.id, fit_score=74))
    captured = fake_azure_stream(monkeypatch, ["# Resume"])

    auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Tailor my resume for this role"},
    )

    prompt = captured["prompt"]
    assert "Kestrel Payments needs Kubernetes" in prompt
    assert "Senior Backend Engineer" in prompt  # from the sample profile
    assert "ANALYSIS ALREADY SHOWN TO THE USER" in prompt
    assert "Tailor my resume for this role" in prompt


# ==========================================================================
# The explicit path: POST /chats/{id}/outputs
# ==========================================================================


def test_output_route_persists_the_user_message_it_stands_for(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button writes the turn it implies, so the thread stays coherent."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["# Resume"])

    auth_client.post(
        "/chats/{}/outputs".format(chat.id), json={"output_type": "resume"}
    )

    user = [m for m in db.rows(ChatMessage) if m.role == "user"]
    assert len(user) == 1
    assert user[0].content == "Generate a tailored resume for this role"
    assert user[0].kind == "chat"


def test_output_route_appends_the_user_context(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The steer is stored in the thread and reaches the model."""
    chat = seeded_chat(db)
    captured = fake_azure_stream(monkeypatch, ["Dear hiring team"])

    auth_client.post(
        "/chats/{}/outputs".format(chat.id),
        json={
            "output_type": "cover_letter",
            "user_context": "mention my team leadership",
        },
    )

    user = [m for m in db.rows(ChatMessage) if m.role == "user"]
    assert user[0].content == (
        "Write a cover letter for this role: mention my team leadership"
    )
    assert "mention my team leadership" in captured["prompt"]


def test_output_route_treats_the_context_as_the_question_for_an_answer(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An answer's user_context is the question, and it is isolated as one."""
    chat = seeded_chat(db)
    captured = fake_azure_stream(monkeypatch, ["I led"])

    auth_client.post(
        "/chats/{}/outputs".format(chat.id),
        json={
            "output_type": "answer",
            "user_context": "Describe a time you led a project.",
        },
    )

    assert (
        "APPLICATION QUESTION TO ANSWER:\nDescribe a time you led a project."
        in captured["prompt"]
    )


def test_output_route_streams_the_same_events_as_the_message_route(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One SSE contract, whichever path asked for the document."""
    chat = seeded_chat(db)
    fake_azure_stream(monkeypatch, ["# Tailored ", "resume"])

    response = auth_client.post(
        "/chats/{}/outputs".format(chat.id), json={"output_type": "resume"}
    )

    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "token", "token", "done"]
    assert events[0]["kind"] == "resume"
    assert events[-1]["content"] == "# Tailored resume"
    assert events[-1]["resume_type"] == "tailored"
    assert events[-1]["output_id"] == str(db.rows(GeneratedOutput)[0].id)
    assert db.rows(TrackerEntry)[0].resume_type == "tailored"


def test_output_route_rejects_an_unknown_type(
    auth_client: TestClient, db: FakeSession
) -> None:
    """output_type is an enum, so anything else is a 422 before any work."""
    chat = seeded_chat(db)

    response = auth_client.post(
        "/chats/{}/outputs".format(chat.id), json={"output_type": "linkedin_post"}
    )

    assert response.status_code == 422
    assert db.rows(ChatMessage) == []


def test_output_route_404s_on_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A chat that is not yours does not exist, and nothing is written."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))

    response = auth_client.post(
        "/chats/{}/outputs".format(chat.id), json={"output_type": "resume"}
    )

    assert response.status_code == 404
    assert db.rows(ChatMessage) == []
    assert db.rows(GeneratedOutput) == []


def test_output_route_404s_on_a_deleted_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A soft-deleted chat cannot generate anything either."""
    chat = db.seed(make_chat(deleted_at=NOW))

    response = auth_client.post(
        "/chats/{}/outputs".format(chat.id), json={"output_type": "resume"}
    )

    assert response.status_code == 404


# ==========================================================================
# GET /chats/{id}/outputs
# ==========================================================================


def test_list_outputs_is_newest_first(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The outputs list is ordered created_at descending."""
    chat = db.seed(make_chat())
    db.seed(make_output(chat.id, "resume", "oldest", NOW - timedelta(days=2)))
    db.seed(make_output(chat.id, "answer", "newest", NOW))
    db.seed(make_output(chat.id, "cover_letter", "middle", NOW - timedelta(days=1)))

    body = auth_client.get("/chats/{}/outputs".format(chat.id)).json()

    assert [row["content"] for row in body] == ["newest", "middle", "oldest"]
    assert body[0].keys() == {
        "id",
        "chat_id",
        "output_type",
        "content",
        "created_at",
    }
    assert body[0]["chat_id"] == str(chat.id)


def test_list_outputs_is_scoped_to_one_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Another chat's documents never appear in this one's list."""
    mine = db.seed(make_chat(title="Mine"))
    other = db.seed(make_chat(title="Other"))
    db.seed(make_output(mine.id, content="mine"))
    db.seed(make_output(other.id, content="theirs"))

    body = auth_client.get("/chats/{}/outputs".format(mine.id)).json()

    assert [row["content"] for row in body] == ["mine"]


def test_list_outputs_404s_on_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Ownership is checked before anything is read."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))
    db.seed(make_output(chat.id))

    assert auth_client.get("/chats/{}/outputs".format(chat.id)).status_code == 404


def test_list_outputs_is_empty_before_anything_is_generated(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An empty list, not a 404 -- the chat exists, it just has no documents."""
    chat = db.seed(make_chat())

    response = auth_client.get("/chats/{}/outputs".format(chat.id))

    assert response.status_code == 200
    assert response.json() == []


# ==========================================================================
# utils.retry
# ==========================================================================


class _RateLimitError(Exception):
    """Stands in for the SDK rate limit classes, matched by name."""

    status_code = 429


def test_is_retryable_matches_rate_limits() -> None:
    """429s and 5xxs are retryable; a plain ValueError is not."""
    assert is_retryable(_RateLimitError())
    assert not is_retryable(ValueError("bad input"))


def test_retry_with_backoff_retries_then_succeeds() -> None:
    """The decorator retries a 429 and returns the eventual success."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base_delay=0.01, jitter=False)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimitError("rate limited")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_does_not_retry_other_errors() -> None:
    """Non-retryable exceptions propagate on the first attempt."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base_delay=0.01, jitter=False)
    def broken() -> None:
        calls["n"] += 1
        raise ValueError("bad input")

    try:
        broken()
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    assert calls["n"] == 1


def test_the_azure_call_is_wrapped_in_retry() -> None:
    """The initial generation call retries rate limits rather than failing."""
    assert hasattr(output_service._open_output_stream, "__wrapped__")


# ==========================================================================
# Opt-in live check of the cover letter prompt
# ==========================================================================


LIVE_PROFILE = {
    "name": "Priya Raman",
    "summary": "Backend engineer with six years building payment systems.",
    "skills": ["Python", "PostgreSQL", "Go", "Docker"],
    "work_experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Kestrel Payments",
            "start_date": "March 2022",
            "current": True,
            "highlights": [
                "Cut reconciliation from 40 minutes to 6.",
                "Owned the ledger service end to end.",
                "Led a team of three through a payments migration.",
            ],
        }
    ],
    "education": [{"degree": "M.Tech", "institution": "IIT Hyderabad"}],
}

LIVE_JD = (
    "Northwind Logistics is hiring a Senior Backend Engineer. You will own our "
    "settlement and reconciliation services, write Python and Go, and work "
    "closely with the finance team. Payments experience strongly preferred."
)


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Azure GPT-4o test. Set RUN_LIVE=1 to run it.",
)
def test_live_cover_letter() -> None:
    """Generate a real cover letter and check it is addressed to the company.

    Guards the prompt itself: every offline test above fakes the response and
    would pass with a prompt that returned a generic template.
    """
    started = time.perf_counter()
    first_token_at: float | None = None
    parts: list[str] = []

    for chunk in output_service.stream_output(
        output_service.OUTPUT_COVER_LETTER,
        LIVE_PROFILE,
        LIVE_JD,
        user_message="Write a cover letter, mention my team leadership",
    ):
        if first_token_at is None:
            first_token_at = time.perf_counter()
        parts.append(chunk)

    letter = "".join(parts)
    total = time.perf_counter() - started
    print(
        "\ncover letter: first token {:.2f}s, total {:.2f}s, {} words".format(
            (first_token_at or started) - started, total, len(letter.split())
        )
    )

    assert "Northwind" in letter
    assert "Kestrel Payments" in letter
    assert len(letter.split()) > 120
    # Grounded: the profile has no AWS certification, so the letter must not
    # claim one.
    assert "AWS" not in letter


# ==========================================================================
# Opt-in resume roundtrip against the local Supabase Postgres
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_DB") != "1",
    reason="Live database test. Set RUN_DB=1 to run it.",
)
def test_db_resume_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive the whole resume path through real SQLAlchemy, faking only Azure.

    The offline suite proves the logic against FakeSession; this proves the
    ``generated_outputs`` insert and the tracker update actually commit against
    the real columns and constraints.
    """
    from app.data.database import SessionLocal
    from app.data.deps import get_current_user, get_db
    from app.main import app
    from app.models.job_chat import JobChat

    user_id = uuid.uuid4()
    session = SessionLocal()
    chat = None
    try:
        chat, entry = chat_service.create_chat(
            session, user_id, "Resume Roundtrip", "Northwind", LIVE_JD
        )
        assert entry.resume_type == "unaltered"

        fake_azure_stream(monkeypatch, ["# Priya Raman\n\n", "## Summary\n\nX"])
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: str(user_id)

        with TestClient(app) as db_client:
            response = db_client.post(
                "/chats/{}/outputs".format(chat.id),
                json={"output_type": "resume", "user_context": "one page"},
            )
            events = parse_sse(response.text)

            done = events[-1]
            assert done["type"] == "done"
            assert done["resume_type"] == "tailored"

            listed = db_client.get("/chats/{}/outputs".format(chat.id)).json()
            assert [row["output_type"] for row in listed] == ["resume"]
            assert listed[0]["id"] == done["output_id"]

            tracker = db_client.get("/tracker").json()
            row = next(r for r in tracker if r["chat_id"] == str(chat.id))
            assert row["resume_type"] == "tailored"
            assert row["job_title"] == "Resume Roundtrip"
            assert row["status"] == "not_applied"

            patched = db_client.patch(
                "/tracker/{}".format(chat.id), json={"status": "applied"}
            )
            assert patched.status_code == 200
            assert patched.json()["status"] == "applied"

        stored = session.get(GeneratedOutput, uuid.UUID(done["output_id"]))
        assert stored is not None
        assert stored.content == "# Priya Raman\n\n## Summary\n\nX"
        assert (
            chat_service.get_tracker_entry(session, chat.id).resume_type == "tailored"
        )
    finally:
        app.dependency_overrides.clear()
        if chat is not None:
            row = session.get(JobChat, chat.id)
            if row is not None:
                session.delete(row)  # cascades to messages, outputs, tracker
                session.commit()
        session.close()


def test_sse_payloads_are_json_objects() -> None:
    """Sanity check on the helper the SSE tests parse with."""
    from app.api.routes.messages import sse_event

    rendered = sse_event({"type": "done", "output_id": "x"})
    assert rendered.endswith("\n\n")
    assert json.loads(rendered[len("data: ") :]) == {"type": "done", "output_id": "x"}
