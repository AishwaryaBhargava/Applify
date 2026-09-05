"""Tests for the job chat and message routes, intent detection, and the context
builder.

Everything runs offline. Groq is replaced at the ``llm._open_groq_stream`` /
``_call_groq_classifier`` seam, so the SSE tests exercise the real route, the
real generator, the real provider layer, and the real persistence path with only
the network faked. Patching the raw provider call rather than
``chat_service.stream_chat_reply`` keeps the fallback logic in the path under
test: the failures these tests inject are not rate limits, so they must
propagate rather than reach for Azure -- and ``test_llm.py`` is where the
fallback itself is exercised.

``test_db_roundtrip`` is the one exception: it talks to the local Supabase
Postgres and is opt-in behind ``RUN_DB=1``.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes.chats import CHAT_NOT_FOUND
from app.models.analysis import Analysis
from app.models.chat_message import ChatMessage
from app.models.job_chat import JobChat
from app.models.profile import Profile
from app.models.tracker_entry import TrackerEntry
from app.services import chat_service, llm, output_service
from app.tests.conftest import OTHER_USER_ID, TEST_USER_ID, FakeSession
from app.utils.context_builder import build_context, build_messages

CHAT_ID = "00000000-0000-0000-0000-000000000001"

SAMPLE_PROFILE = {
    "summary": "Backend engineer with six years building payment systems.",
    "skills": ["Python", "PostgreSQL", "Go"],
    "work_experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Kestrel Payments",
            "start_date": "March 2022",
            "current": True,
            "highlights": ["Cut reconciliation from 40 minutes to 6."],
        }
    ],
}

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


# ==========================================================================
# Builders
# ==========================================================================


def make_chat(
    chat_id: uuid.UUID | None = None,
    user_id: str = TEST_USER_ID,
    title: str = "Backend Engineer",
    company: str | None = "Kestrel Payments",
    jd_text: str | None = "We need a backend engineer who writes Python.",
    created_at: datetime = NOW,
    deleted_at: datetime | None = None,
    analysis_type: str | None = None,
) -> JobChat:
    """Build a JobChat row the way the database would hand one back."""
    return JobChat(
        id=chat_id or uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        title=title,
        company=company,
        jd_text=jd_text,
        analysis_type=analysis_type,
        created_at=created_at,
        deleted_at=deleted_at,
    )


def make_message(
    chat_id: uuid.UUID,
    role: str = "user",
    content: str = "hello",
    kind: str = "chat",
    created_at: datetime = NOW,
) -> ChatMessage:
    """Build a ChatMessage row."""
    return ChatMessage(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role=role,
        content=content,
        kind=kind,
        created_at=created_at,
    )


def make_tracker(
    chat_id: uuid.UUID,
    user_id: str = TEST_USER_ID,
    resume_type: str = "unaltered",
    status: str = "not_applied",
) -> TrackerEntry:
    """Build a TrackerEntry row."""
    return TrackerEntry(
        id=uuid.uuid4(),
        chat_id=chat_id,
        user_id=uuid.UUID(user_id),
        status=status,
        resume_type=resume_type,
        created_at=NOW,
        updated_at=NOW,
    )


def make_profile(user_id: str = TEST_USER_ID) -> Profile:
    """Build a Profile row carrying the sample parse."""
    return Profile(
        user_id=uuid.UUID(user_id),
        raw_text="raw resume text",
        parsed_json=dict(SAMPLE_PROFILE),
        created_at=NOW,
        updated_at=NOW,
    )


# ==========================================================================
# Groq stream doubles
# ==========================================================================


class _Delta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.delta = _Delta(content)


class _Chunk:
    """One streamed chunk, shaped like the Groq SDK's."""

    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


def fake_groq_stream(
    monkeypatch: pytest.MonkeyPatch,
    tokens: list[str],
    fail_after: int | None = None,
) -> None:
    """Replace the Groq streaming call with a canned sequence of chunks.

    Args:
        tokens: The chunks to emit, in order.
        fail_after: Raise mid-stream once this many chunks have been emitted.
    """

    def _open(messages: list[dict[str, str]], **kwargs):
        def chunks():
            for index, token in enumerate(tokens):
                if fail_after is not None and index == fail_after:
                    raise RuntimeError("groq connection dropped")
                yield _Chunk(token)

        return chunks()

    monkeypatch.setattr(llm, "_open_groq_stream", _open)


def parse_sse(body: str) -> list[dict]:
    """Parse an SSE body into the list of JSON objects it carried."""
    return [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


# ==========================================================================
# Auth guards
# ==========================================================================


def test_list_chats_requires_auth(client: TestClient) -> None:
    """GET /chats is protected by get_current_user."""
    assert client.get("/chats").status_code == 401


def test_create_chat_requires_auth(client: TestClient) -> None:
    """POST /chats is protected by get_current_user."""
    assert client.post("/chats", json={"title": "Backend Engineer"}).status_code == 401


def test_get_chat_requires_auth(client: TestClient) -> None:
    """GET /chats/{id} is protected by get_current_user."""
    assert client.get("/chats/{}".format(CHAT_ID)).status_code == 401


def test_delete_chat_requires_auth(client: TestClient) -> None:
    """DELETE /chats/{id} is protected by get_current_user."""
    assert client.delete("/chats/{}".format(CHAT_ID)).status_code == 401


def test_list_messages_requires_auth(client: TestClient) -> None:
    """GET /chats/{id}/messages is protected by get_current_user."""
    assert client.get("/chats/{}/messages".format(CHAT_ID)).status_code == 401


def test_post_message_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/messages is protected by get_current_user."""
    response = client.post(
        "/chats/{}/messages".format(CHAT_ID), json={"content": "hi"}
    )
    assert response.status_code == 401


# ==========================================================================
# POST /chats
# ==========================================================================


def test_create_chat_returns_201_and_the_new_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A new chat comes back fully formed, with no analysis yet."""
    response = auth_client.post(
        "/chats",
        json={
            "title": "Backend Engineer",
            "company": "Kestrel Payments",
            "jd_text": "Python, Postgres, payments.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Backend Engineer"
    assert body["company"] == "Kestrel Payments"
    assert body["jd_text"] == "Python, Postgres, payments."
    assert body["analysis_type"] is None
    assert body["has_analysis"] is False
    assert body["resume_type"] == "unaltered"
    assert uuid.UUID(body["id"])


def test_create_chat_auto_creates_the_tracker_entry(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The tracker row is opened in the same transaction as the chat."""
    response = auth_client.post("/chats", json={"title": "Backend Engineer"})

    chats = db.rows(JobChat)
    entries = db.rows(TrackerEntry)
    assert len(chats) == 1
    assert len(entries) == 1
    assert entries[0].chat_id == chats[0].id == uuid.UUID(response.json()["id"])
    assert entries[0].user_id == uuid.UUID(TEST_USER_ID)
    assert entries[0].status == "not_applied"
    assert entries[0].resume_type == "unaltered"
    # One commit: the chat and its tracker entry land together or not at all.
    assert db.commits == 1


def test_create_chat_rejects_an_empty_title(auth_client: TestClient) -> None:
    """Title is required -- an untitled chat is unusable in the sidebar."""
    assert auth_client.post("/chats", json={"title": ""}).status_code == 422


# ==========================================================================
# GET /chats
# ==========================================================================


def test_list_chats_is_newest_first(auth_client: TestClient, db: FakeSession) -> None:
    """The sidebar order is created_at descending."""
    db.seed(make_chat(title="Oldest", created_at=NOW - timedelta(days=2)))
    db.seed(make_chat(title="Newest", created_at=NOW))
    db.seed(make_chat(title="Middle", created_at=NOW - timedelta(days=1)))

    titles = [chat["title"] for chat in auth_client.get("/chats").json()]

    assert titles == ["Newest", "Middle", "Oldest"]


def test_list_chats_excludes_soft_deleted_and_other_users(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Deleted chats and other people's chats never appear."""
    db.seed(make_chat(title="Mine"))
    db.seed(make_chat(title="Deleted", deleted_at=NOW))
    db.seed(make_chat(title="Theirs", user_id=OTHER_USER_ID))

    titles = [chat["title"] for chat in auth_client.get("/chats").json()]

    assert titles == ["Mine"]


def test_list_chats_reports_analysis_and_resume_type(
    auth_client: TestClient, db: FakeSession
) -> None:
    """has_analysis and resume_type are joined in from the other two tables."""
    analysed = make_chat(title="Analysed", analysis_type="quick", created_at=NOW)
    plain = make_chat(title="Plain", created_at=NOW - timedelta(days=1))
    db.seed(analysed)
    db.seed(plain)
    db.seed(make_tracker(analysed.id, resume_type="tailored"))
    db.seed(make_tracker(plain.id))
    db.seed(
        Analysis(
            id=uuid.uuid4(),
            chat_id=analysed.id,
            type="quick",
            fit_score=71,
            strengths=["Python"],
            gaps=["Kubernetes"],
            verdict="Worth applying.",
            full_json={},
            created_at=NOW,
        )
    )

    body = {chat["title"]: chat for chat in auth_client.get("/chats").json()}

    assert body["Analysed"]["has_analysis"] is True
    assert body["Analysed"]["analysis_type"] == "quick"
    assert body["Analysed"]["resume_type"] == "tailored"
    assert body["Plain"]["has_analysis"] is False
    assert body["Plain"]["resume_type"] == "unaltered"


# ==========================================================================
# GET /chats/{id}
# ==========================================================================


def test_get_chat_returns_messages_and_analysis(
    auth_client: TestClient, db: FakeSession
) -> None:
    """One request carries everything the chat page needs to re-render."""
    chat = db.seed(make_chat(analysis_type="quick"))
    db.seed(make_tracker(chat.id))
    db.seed(make_message(chat.id, "user", "First", created_at=NOW))
    db.seed(
        make_message(
            chat.id,
            "assistant",
            "## Quick snapshot",
            kind="analysis",
            created_at=NOW + timedelta(seconds=5),
        )
    )
    db.seed(
        Analysis(
            id=uuid.uuid4(),
            chat_id=chat.id,
            type="quick",
            fit_score=71,
            strengths=["Python"],
            gaps=["Kubernetes"],
            verdict="Worth applying.",
            full_json={"fit_score": 71},
            created_at=NOW,
        )
    )

    body = auth_client.get("/chats/{}".format(chat.id)).json()

    assert body["has_analysis"] is True
    assert [m["content"] for m in body["messages"]] == ["First", "## Quick snapshot"]
    assert [m["kind"] for m in body["messages"]] == ["chat", "analysis"]
    assert body["analysis"]["fit_score"] == 71
    assert body["analysis"]["verdict"] == "Worth applying."


def test_get_chat_404s_for_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Existence is never leaked across users: 404, not 403."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))

    response = auth_client.get("/chats/{}".format(chat.id))

    assert response.status_code == 404
    assert response.json()["detail"] == CHAT_NOT_FOUND


def test_get_chat_404s_for_a_soft_deleted_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A deleted chat is gone as far as the API is concerned."""
    chat = db.seed(make_chat(deleted_at=NOW))

    assert auth_client.get("/chats/{}".format(chat.id)).status_code == 404


def test_get_chat_404s_for_an_unknown_id(auth_client: TestClient) -> None:
    """An id that was never a chat is a 404, not a 500."""
    assert auth_client.get("/chats/{}".format(uuid.uuid4())).status_code == 404


# ==========================================================================
# DELETE /chats/{id}
# ==========================================================================


def test_delete_chat_soft_deletes(auth_client: TestClient, db: FakeSession) -> None:
    """DELETE stamps deleted_at and the chat drops out of every read."""
    chat = db.seed(make_chat())

    assert auth_client.delete("/chats/{}".format(chat.id)).status_code == 204

    assert chat.deleted_at is not None
    assert auth_client.get("/chats").json() == []
    assert auth_client.get("/chats/{}".format(chat.id)).status_code == 404


def test_delete_chat_404s_for_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Deleting someone else's chat is a 404 and changes nothing."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))

    assert auth_client.delete("/chats/{}".format(chat.id)).status_code == 404
    assert chat.deleted_at is None


# ==========================================================================
# GET /chats/{id}/messages
# ==========================================================================


def test_list_messages_is_oldest_first(
    auth_client: TestClient, db: FakeSession
) -> None:
    """History renders top to bottom, so it is returned created_at ascending."""
    chat = db.seed(make_chat())
    db.seed(make_message(chat.id, "assistant", "second", created_at=NOW))
    db.seed(make_message(chat.id, "user", "first", created_at=NOW - timedelta(minutes=1)))

    body = auth_client.get("/chats/{}/messages".format(chat.id)).json()

    assert [m["content"] for m in body] == ["first", "second"]
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert all(m["kind"] == "chat" for m in body)


def test_list_messages_404s_for_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Message history is behind the same ownership check as the chat."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))
    db.seed(make_message(chat.id, "user", "secret"))

    assert auth_client.get("/chats/{}/messages".format(chat.id)).status_code == 404


# ==========================================================================
# POST /chats/{id}/messages -- SSE
# ==========================================================================


def test_post_message_streams_start_tokens_and_done(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path emits exactly start, one event per token, then done."""
    chat = db.seed(make_chat())
    db.seed(make_profile())
    fake_groq_stream(monkeypatch, ["Your ", "Python ", "experience fits."])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "How well do I fit this role?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "token", "token", "token", "done"]
    assert events[0]["kind"] == "chat"
    assert [event["content"] for event in events[1:4]] == [
        "Your ",
        "Python ",
        "experience fits.",
    ]
    assert events[-1]["content"] == "Your Python experience fits."
    # start and done name the same message.
    assert events[0]["message_id"] == events[-1]["message_id"]


def test_post_message_persists_both_turns(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user message and the completed reply are both stored, in order."""
    chat = db.seed(make_chat())
    fake_groq_stream(monkeypatch, ["Sure", ", here goes."])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "Hi there"}
    )
    done = parse_sse(response.text)[-1]

    stored = sorted(db.rows(ChatMessage), key=lambda m: m.created_at)
    assert [(m.role, m.content, m.kind) for m in stored] == [
        ("user", "Hi there", "chat"),
        ("assistant", "Sure, here goes.", "chat"),
    ]
    assert str(stored[1].id) == done["message_id"]


def test_post_message_error_persists_the_partial_reply(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mid-stream failure keeps what arrived and says so on the wire."""
    chat = db.seed(make_chat())
    fake_groq_stream(monkeypatch, ["Half ", "a reply", " never sent"], fail_after=2)

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "Tell me more"}
    )

    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "token", "token", "error"]
    error = events[-1]
    assert error["partial"] is True
    assert error["content"] == "Half a reply"
    assert error["message_id"] == events[0]["message_id"]

    assistant = [m for m in db.rows(ChatMessage) if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].content == "Half a reply"
    assert str(assistant[0].id) == error["message_id"]


def test_post_message_reports_an_empty_reply_without_storing_it(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream that yields nothing is an error, not an empty message bubble."""
    chat = db.seed(make_chat())
    fake_groq_stream(monkeypatch, [])

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "Anything there?"}
    )

    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "error"]
    assert events[-1]["partial"] is False
    assert [m for m in db.rows(ChatMessage) if m.role == "assistant"] == []


def test_post_message_404s_for_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Ownership is checked before anything is written or streamed."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "hello"}
    )

    assert response.status_code == 404
    assert db.rows(ChatMessage) == []


def test_post_message_rejects_a_blank_message(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Whitespace is not a message."""
    chat = db.seed(make_chat())

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "   "}
    )

    assert response.status_code == 422
    assert db.rows(ChatMessage) == []


def test_post_message_with_output_intent_delegates_to_output_service(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume request streams from output_service, not the chat model.

    The seam itself: Groq must not be touched, and the assistant message is
    stored under the detected ``kind``. What the document says is
    ``test_outputs.py``'s problem.
    """
    chat = db.seed(make_chat())
    db.seed(make_tracker(chat.id))
    db.seed(make_profile())

    def explode(messages, **kwargs):  # pragma: no cover - the chat model is unused
        raise AssertionError("chat model must not run for an output intent")

    monkeypatch.setattr(llm, "_open_groq_stream", explode)
    monkeypatch.setattr(
        output_service,
        "_open_output_stream",
        lambda output_type, prompt: iter([_Chunk("# Tailored "), _Chunk("Resume")]),
    )

    response = auth_client.post(
        "/chats/{}/messages".format(chat.id),
        json={"content": "Can you tailor my resume for this role?"},
    )

    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["start", "token", "token", "done"]
    assert events[0]["kind"] == "resume"
    assert events[-1]["content"] == "# Tailored Resume"

    assistant = [m for m in db.rows(ChatMessage) if m.role == "assistant"]
    assert assistant[0].kind == "resume"
    assert assistant[0].content == "# Tailored Resume"


def test_post_message_sends_profile_jd_and_analysis_to_the_model(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The context the model receives is grounded in the stored rows."""
    chat = db.seed(make_chat(jd_text="Must know Kubernetes and Python."))
    db.seed(make_profile())
    db.seed(
        Analysis(
            id=uuid.uuid4(),
            chat_id=chat.id,
            type="quick",
            fit_score=64,
            strengths=["Deep Python experience"],
            gaps=["No Kubernetes"],
            verdict="Worth applying with tailoring.",
            full_json={},
            created_at=NOW,
        )
    )
    captured: dict = {}

    def _open(messages, **kwargs):
        captured["messages"] = messages
        return iter([_Chunk("ok")])

    monkeypatch.setattr(llm, "_open_groq_stream", _open)

    auth_client.post(
        "/chats/{}/messages".format(chat.id), json={"content": "What should I stress?"}
    )

    system = captured["messages"][0]
    assert system["role"] == "system"
    assert "Kestrel Payments" in system["content"]
    assert "Kubernetes" in system["content"]
    assert "64/100" in system["content"]
    assert captured["messages"][-1] == {
        "role": "user",
        "content": "What should I stress?",
    }


# ==========================================================================
# Intent detection
# ==========================================================================


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Tailor my resume for this role", chat_service.INTENT_RESUME),
        ("can you rewrite my CV to match this JD?", chat_service.INTENT_RESUME),
        ("Please generate a tailored resume", chat_service.INTENT_RESUME),
        ("Write me a cover letter", chat_service.INTENT_COVER_LETTER),
        ("draft a covering letter for this job", chat_service.INTENT_COVER_LETTER),
        (
            "Use my resume to write a cover letter",
            chat_service.INTENT_COVER_LETTER,
        ),
        ("How should I answer this question?", chat_service.INTENT_ANSWER),
        ("help me answer their application question", chat_service.INTENT_ANSWER),
        ("What should I say about my notice period?", chat_service.INTENT_ANSWER),
        ("What do you think of this job?", chat_service.INTENT_CHAT),
        ("Is the salary range reasonable for Bengaluru?", chat_service.INTENT_CHAT),
        ("", chat_service.INTENT_CHAT),
    ],
)
def test_intent_rules_decide_the_clear_cases(message: str, expected: str) -> None:
    """The rules classify unambiguous phrasings with no model call."""
    assert chat_service.detect_intent_rules(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "Should I mention my resume gap?",
        "Do they want a cover letter with the application?",
        "Is this question worth answering in detail?",
    ],
)
def test_intent_rules_defer_when_ambiguous(message: str) -> None:
    """Mentioning an output type is not the same as asking for one."""
    assert chat_service.detect_intent_rules(message) is None


def test_detect_intent_falls_back_to_groq_when_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an ambiguous message reaches the classifier, and its label is used."""
    calls: list[str] = []

    def fake_classifier(message: str) -> str:
        calls.append(message)
        return "cover_letter\n"

    monkeypatch.setattr(chat_service, "_call_groq_classifier", fake_classifier)

    assert chat_service.detect_intent("Do they want a cover letter with the application?") == (
        chat_service.INTENT_COVER_LETTER
    )
    assert len(calls) == 1

    # A clear message never spends the call.
    assert chat_service.detect_intent("What do you think of this job?") == (
        chat_service.INTENT_CHAT
    )
    assert len(calls) == 1


def test_detect_intent_defaults_to_chat_when_the_classifier_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A classifier outage answers conversationally rather than guessing."""

    def broken(message: str) -> str:
        raise RuntimeError("groq is down")

    monkeypatch.setattr(chat_service, "_call_groq_classifier", broken)

    assert chat_service.detect_intent("Should I mention my resume gap?") == (
        chat_service.INTENT_CHAT
    )


def test_detect_intent_ignores_an_unrecognised_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A classifier that invents a label is treated as chat."""
    monkeypatch.setattr(chat_service, "_call_groq_classifier", lambda message: "banana")

    assert chat_service.detect_intent("Should I mention my resume gap?") == (
        chat_service.INTENT_CHAT
    )


# ==========================================================================
# Context builder
# ==========================================================================


def test_build_context_always_keeps_profile_and_jd() -> None:
    """Profile and JD survive even when the word budget is tiny."""
    context = build_context(
        profile_json={"summary": "Ada Lovelace writes Python.", "skills": ["python"]},
        jd_text="We need a backend engineer who writes Python.",
        messages=[{"role": "user", "content": "word " * 500}],
        max_words=50,
    )
    assert "Ada Lovelace" in context
    assert "backend engineer" in context


def test_build_context_windows_oldest_messages_out() -> None:
    """The sliding window drops the oldest messages and keeps the newest."""
    messages = [
        {"role": "user", "content": "oldest " * 200},
        {"role": "assistant", "content": "middle " * 200},
        {"role": "user", "content": "newest question"},
    ]
    context = build_context({}, "short jd", messages, max_words=100)
    assert "newest question" in context
    assert "oldest" not in context


def test_build_messages_puts_grounding_in_the_system_turn() -> None:
    """Persona, profile, and JD are one system message; history follows it."""
    messages = build_messages(
        SAMPLE_PROFILE,
        "We need Python and Kubernetes.",
        None,
        [{"role": "user", "content": "Where do I stand?"}],
    )

    assert messages[0]["role"] == "system"
    assert "Applify" in messages[0]["content"]
    assert "Kestrel Payments" in messages[0]["content"]
    assert "Kubernetes" in messages[0]["content"]
    assert messages[1:] == [{"role": "user", "content": "Where do I stand?"}]


def test_build_messages_includes_the_analysis_summary() -> None:
    """A completed analysis is carried as its summary, not its full breakdown."""
    analysis = {
        "type": "detailed",
        "fit_score": 78,
        "strengths": ["Payments domain depth"],
        "gaps": ["No Kubernetes"],
        "verdict": "Apply with a tailored resume.",
        "full_json": {"narrative": "a" * 5000},
    }

    system = build_messages(SAMPLE_PROFILE, "jd text", analysis, [])[0]["content"]

    assert "78/100" in system
    assert "Payments domain depth" in system
    assert "Apply with a tailored resume." in system
    assert "aaaa" not in system


def test_build_messages_drops_oldest_history_first() -> None:
    """Windowing sheds the oldest turns and never the system turn."""
    history = [
        {"role": "user", "content": "oldest " * 300},
        {"role": "assistant", "content": "middle " * 300},
        {"role": "user", "content": "newest question"},
    ]

    messages = build_messages(SAMPLE_PROFILE, "short jd", None, history, max_words=200)

    assert messages[0]["role"] == "system"
    assert "Applify" in messages[0]["content"]
    assert [m["content"] for m in messages[1:]] == ["newest question"]


def test_build_messages_keeps_the_newest_turn_even_when_it_overflows() -> None:
    """The message being answered is never the one that gets dropped."""
    history = [{"role": "user", "content": "word " * 5000}]

    messages = build_messages(SAMPLE_PROFILE, "jd", None, history, max_words=100)

    assert len(messages) == 2
    assert messages[1]["content"].startswith("word")


# ==========================================================================
# Opt-in integration check against the local Supabase Postgres
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_DB") != "1",
    reason="Live database test. Set RUN_DB=1 to run it.",
)
def test_db_roundtrip() -> None:
    """Create a chat, add messages, read them back, then clean up.

    The offline suite proves the query logic; this proves the columns, the
    ``kind`` migration, and the tracker foreign key exist as the models expect.
    """
    from app.data.database import SessionLocal

    user_id = uuid.uuid4()
    session = SessionLocal()
    try:
        chat, entry = chat_service.create_chat(
            session, user_id, "Integration Check", "Kestrel", "Python and Postgres."
        )
        chat_service.save_message(session, chat.id, "user", "hello there")
        chat_service.save_message(
            session, chat.id, "assistant", "## Quick snapshot", kind="analysis"
        )

        assert chat_service.get_chat_for_user(session, chat.id, user_id) is not None
        stored = chat_service.list_messages(session, chat.id)
        assert [(m.role, m.kind) for m in stored] == [
            ("user", "chat"),
            ("assistant", "analysis"),
        ]
        assert chat_service.get_tracker_entry(session, chat.id).id == entry.id

        chat_service.soft_delete_chat(session, chat)
        assert chat_service.get_chat_for_user(session, chat.id, user_id) is None

        session.delete(chat)  # cascades to messages and the tracker entry
        session.commit()
        assert session.get(JobChat, chat.id) is None
    finally:
        session.close()
