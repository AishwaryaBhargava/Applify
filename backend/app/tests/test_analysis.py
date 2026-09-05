"""Tests for the analysis route, the analysis service, and model-output coercion.

Everything runs offline: the two network seams -- ``_call_groq_quick`` and
``_call_azure_detailed`` -- are patched with canned response bodies, including
deliberately malformed ones, so the parsing, coercion, and persistence paths are
all real. ``test_live_detailed_analysis`` is the one exception and is opt-in
behind ``RUN_LIVE=1``.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.analysis import (
    coerce_detailed_breakdown,
    coerce_quick_snapshot,
)
from app.api.routes.analysis import NO_PROFILE
from app.models.analysis import Analysis
from app.models.chat_message import ChatMessage
from app.services import analysis_service
from app.services.analysis_service import AnalysisError, NEXT_STEP_SUGGESTION
from app.tests.conftest import OTHER_USER_ID, FakeSession
from app.tests.test_chat import NOW, make_chat, make_profile

CHAT_ID = "00000000-0000-0000-0000-000000000001"

QUICK_RESPONSE = {
    "fit_score": 74,
    "strengths": [
        "Six years of Python in payments matches the core requirement.",
        "Owned reconciliation at scale, which this role leads with.",
        "PostgreSQL depth lines up with the data volume described.",
    ],
    "gaps": [
        "No Kubernetes experience anywhere in the profile.",
        "The role asks for team leadership; the profile shows none.",
        "No fintech compliance exposure.",
    ],
    "verdict": "Worth applying with a resume tailored to the payments work.",
}

DETAILED_RESPONSE = {
    "skills": [
        {
            "skill": "Python",
            "required_by_jd": True,
            "user_has": True,
            "evidence": "Six years of Python at Kestrel Payments.",
            "gap_reasoning": "",
            "suggestion": "",
        },
        {
            "skill": "Kubernetes",
            "required_by_jd": True,
            "user_has": False,
            "evidence": "",
            "gap_reasoning": "The team runs its own clusters.",
            "suggestion": "Name the Docker work you already have.",
        },
    ],
    "narrative": "A strong backend match held back by the infrastructure ask.",
    "fit_score": 68,
    "strengths": ["Deep Python", "Payments domain", "PostgreSQL"],
    "gaps": ["No Kubernetes", "No leadership", "No cloud certification"],
    "verdict": "Apply, but lead with the payments work.",
}


def make_analysis(
    chat_id: uuid.UUID,
    analysis_type: str = "quick",
    fit_score: int = 55,
) -> Analysis:
    """Build a stored Analysis row."""
    return Analysis(
        id=uuid.uuid4(),
        chat_id=chat_id,
        type=analysis_type,
        fit_score=fit_score,
        strengths=["Stored strength"],
        gaps=["Stored gap"],
        verdict="Stored verdict.",
        full_json={"fit_score": fit_score},
        created_at=NOW,
    )


@pytest.fixture
def mock_quick(monkeypatch: pytest.MonkeyPatch):
    """Patch the Groq quick-analysis call. Returns a setter for the body."""

    def set_response(body: str) -> None:
        monkeypatch.setattr(analysis_service, "_call_groq_quick", lambda prompt: body)

    set_response(json.dumps(QUICK_RESPONSE))
    return set_response


@pytest.fixture
def mock_detailed(monkeypatch: pytest.MonkeyPatch):
    """Patch the Azure detailed-analysis call. Returns a setter for the body."""

    def set_response(body: str) -> None:
        monkeypatch.setattr(
            analysis_service, "_call_azure_detailed", lambda prompt: body
        )

    set_response(json.dumps(DETAILED_RESPONSE))
    return set_response


# ==========================================================================
# Auth guard
# ==========================================================================


def test_analyze_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/analyze is protected by get_current_user."""
    response = client.post("/chats/{}/analyze".format(CHAT_ID), json={"type": "quick"})
    assert response.status_code == 401


def test_analyze_rejects_invalid_type_only_after_auth(client: TestClient) -> None:
    """The auth dependency runs before body validation, so this is still a 401."""
    response = client.post(
        "/chats/{}/analyze".format(CHAT_ID), json={"type": "nonsense"}
    )
    assert response.status_code == 401


# ==========================================================================
# Route behaviour
# ==========================================================================


def test_quick_analysis_returns_the_snapshot(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """A quick run comes back validated and in the documented shape."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "quick"
    assert body["chat_id"] == str(chat.id)
    assert body["fit_score"] == 74
    assert len(body["strengths"]) == 3
    assert len(body["gaps"]) == 3
    assert body["verdict"].startswith("Worth applying")
    assert body["full_json"]["fit_score"] == 74


def test_quick_analysis_persists_everything_together(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """The analysis, the chat's analysis_type, and one assistant message land."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    auth_client.post("/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"})

    assert chat.analysis_type == "quick"
    assert len(db.rows(Analysis)) == 1

    messages = db.rows(ChatMessage)
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].kind == "analysis"
    assert "74/100" in messages[0].content
    # Exactly one proactive suggestion, and it closes the message.
    assert messages[0].content.strip().endswith(NEXT_STEP_SUGGESTION)
    assert messages[0].content.count(NEXT_STEP_SUGGESTION) == 1


def test_detailed_analysis_keeps_the_skill_table(
    auth_client: TestClient, db: FakeSession, mock_detailed
) -> None:
    """The detailed breakdown is summarised at the top level, detailed in full_json."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    body = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "detailed"}
    ).json()

    assert body["type"] == "detailed"
    assert body["fit_score"] == 68
    assert body["strengths"] == ["Deep Python", "Payments domain", "PostgreSQL"]
    assert body["verdict"] == "Apply, but lead with the payments work."

    skills = body["full_json"]["skills"]
    assert [skill["skill"] for skill in skills] == ["Python", "Kubernetes"]
    assert skills[1]["user_has"] is False
    assert skills[1]["suggestion"].startswith("Name the Docker work")
    assert body["full_json"]["narrative"].startswith("A strong backend match")


def test_existing_analysis_is_returned_without_re_running(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-opening a chat reads the stored analysis; it never spends a model call."""
    chat = db.seed(make_chat(analysis_type="quick"))
    db.seed(make_profile())
    stored = db.seed(make_analysis(chat.id, fit_score=55))

    def explode(prompt: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("the model must not be called for a stored analysis")

    monkeypatch.setattr(analysis_service, "_call_groq_quick", explode)
    monkeypatch.setattr(analysis_service, "_call_azure_detailed", explode)

    body = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    ).json()

    assert body["id"] == str(stored.id)
    assert body["fit_score"] == 55
    assert len(db.rows(Analysis)) == 1
    assert db.rows(ChatMessage) == []


def test_force_re_runs_and_replaces_the_stored_analysis(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """?force=true is the only way to re-run, and it leaves one analysis behind."""
    chat = db.seed(make_chat(analysis_type="quick"))
    db.seed(make_profile())
    stored = db.seed(make_analysis(chat.id, fit_score=55))

    body = auth_client.post(
        "/chats/{}/analyze?force=true".format(chat.id),
        json={"analysis_type": "quick"},
    ).json()

    assert body["fit_score"] == 74
    assert body["id"] != str(stored.id)
    rows = db.rows(Analysis)
    assert len(rows) == 1
    assert rows[0].fit_score == 74


def test_force_can_switch_depth(
    auth_client: TestClient, db: FakeSession, mock_detailed
) -> None:
    """A forced re-run at a different depth updates the chat's analysis_type."""
    chat = db.seed(make_chat(analysis_type="quick"))
    db.seed(make_profile())
    db.seed(make_analysis(chat.id, fit_score=55))

    body = auth_client.post(
        "/chats/{}/analyze?force=true".format(chat.id),
        json={"analysis_type": "detailed"},
    ).json()

    assert body["type"] == "detailed"
    assert chat.analysis_type == "detailed"


def test_analyze_409s_without_a_profile(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """There is nothing to compare a JD against until a resume is uploaded."""
    chat = db.seed(make_chat())

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == NO_PROFILE


def test_analyze_409s_on_an_empty_profile(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """A profile row with nothing parsed into it is no profile at all."""
    profile = make_profile()
    profile.parsed_json = {}
    chat = db.seed(make_chat())
    db.seed(profile)

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 409


def test_analyze_422s_without_a_job_description(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """A chat with no JD has nothing to analyse against."""
    chat = db.seed(make_chat(jd_text=None))
    db.seed(make_profile())

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 422


def test_analyze_404s_for_another_users_chat(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """Analysis is behind the same ownership check as everything else."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))
    db.seed(make_profile())

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 404
    assert db.rows(Analysis) == []


def test_analyze_502s_when_the_model_is_unreachable(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider outage is reported as a bad gateway, and nothing is stored."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    def broken(prompt: str) -> str:
        raise RuntimeError("groq is down")

    monkeypatch.setattr(analysis_service, "_call_groq_quick", broken)

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 502
    assert db.rows(Analysis) == []
    assert db.rows(ChatMessage) == []


def test_analyze_502s_on_unparseable_model_output(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """Prose where JSON was asked for is a failure, not a blank analysis."""
    chat = db.seed(make_chat())
    db.seed(make_profile())
    mock_quick("I am afraid I cannot help with that.")

    response = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    )

    assert response.status_code == 502
    assert db.rows(Analysis) == []


def test_analyze_accepts_the_type_alias(
    auth_client: TestClient, db: FakeSession, mock_detailed
) -> None:
    """``{"type": ...}`` is accepted alongside ``{"analysis_type": ...}``."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    body = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"type": "detailed"}
    ).json()

    assert body["type"] == "detailed"


def test_analyze_normalises_malformed_model_output(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """A sloppy but recoverable response is normalised rather than rejected."""
    chat = db.seed(make_chat())
    db.seed(make_profile())
    mock_quick(
        "```json\n"
        + json.dumps(
            {
                "fit_score": "132",
                "strengths": "Only one strength, as a string",
                "gaps": ["a", "a", "b", "c", "d"],
                "verdict": 42,
            }
        )
        + "\n```"
    )

    body = auth_client.post(
        "/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"}
    ).json()

    assert body["fit_score"] == 100
    assert body["strengths"] == ["Only one strength, as a string"]
    assert body["gaps"] == ["a", "b", "c"]
    assert body["verdict"] == "42"


# ==========================================================================
# Service: parsing, coercion, rendering
# ==========================================================================


def test_parse_json_object_recovers_a_wrapped_object() -> None:
    """A stray sentence around the object does not lose the analysis."""
    parsed = analysis_service._parse_json_object(
        'Here you go: {"fit_score": 70} -- hope that helps.'
    )
    assert parsed == {"fit_score": 70}


def test_parse_json_object_raises_on_prose() -> None:
    """No JSON object at all is an AnalysisError."""
    with pytest.raises(AnalysisError):
        analysis_service._parse_json_object("no json here")


def test_coerce_quick_snapshot_clamps_and_trims() -> None:
    """Scores are clamped, lists de-duplicated and capped at three."""
    snapshot = coerce_quick_snapshot(
        {
            "fit_score": -5,
            "strengths": ["a", "A", "b", "c", "d"],
            "gaps": [{"gap": "missing kubernetes"}],
            "verdict": "  Apply.  ",
        }
    )

    assert snapshot.fit_score == 0
    assert snapshot.strengths == ["a", "b", "c"]
    assert snapshot.gaps == ["missing kubernetes"]
    assert snapshot.verdict == "Apply."


def test_coerce_quick_snapshot_survives_nonsense() -> None:
    """Anything that is not an object degrades to an empty snapshot."""
    snapshot = coerce_quick_snapshot(["not", "an", "object"])
    assert snapshot.fit_score == 0
    assert snapshot.strengths == []


def test_coerce_detailed_breakdown_fills_a_missing_verdict() -> None:
    """A missing verdict falls back to the narrative's first sentence."""
    breakdown = coerce_detailed_breakdown(
        {
            "fit_score": 0.68,
            "narrative": "A strong match on backend depth. Infrastructure is thin.",
            "skills": [{"skill": "Python", "user_has": "yes", "required_by_jd": 1}],
        }
    )

    assert breakdown.fit_score == 68
    assert breakdown.verdict == "A strong match on backend depth."
    assert breakdown.skills[0].user_has is True
    assert breakdown.skills[0].required_by_jd is True


def test_render_analysis_markdown_ends_with_one_suggestion() -> None:
    """The thread message closes with a single proactive next step."""
    markdown = analysis_service.render_analysis_markdown(
        "detailed", coerce_detailed_breakdown(DETAILED_RESPONSE)
    )

    assert markdown.startswith("## Detailed breakdown")
    assert "68/100" in markdown
    assert "Kubernetes" in markdown
    assert markdown.count(NEXT_STEP_SUGGESTION) == 1
    assert markdown.strip().endswith(NEXT_STEP_SUGGESTION)


def test_prompts_forbid_fabrication() -> None:
    """The no-fabrication rule is stated in both prompts, not just implied."""
    for prompt in (
        analysis_service.QUICK_SYSTEM_PROMPT,
        analysis_service.DETAILED_SYSTEM_PROMPT,
    ):
        assert "Never invent" in prompt
        assert "profile" in prompt


def test_build_analysis_prompt_carries_profile_and_jd() -> None:
    """Both halves of the comparison reach the model."""
    prompt = analysis_service.build_analysis_prompt(
        {"skills": ["Python"]}, "We need Python.", "quick"
    )
    assert "Python" in prompt
    assert "JOB DESCRIPTION" in prompt


# ==========================================================================
# Opt-in live check of the detailed prompt
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Azure GPT-4o test. Set RUN_LIVE=1 to run it.",
)
def test_live_detailed_analysis() -> None:
    """Run the real detailed prompt against Azure GPT-4o.

    Guards the prompt itself: every offline test mocks the response and would
    pass with a prompt that returns nothing useful.
    """
    profile = {
        "summary": "Backend engineer, six years, payments.",
        "skills": ["Python", "PostgreSQL", "Docker", "Go"],
        "work_experience": [
            {
                "title": "Senior Backend Engineer",
                "company": "Kestrel Payments",
                "start_date": "March 2022",
                "current": True,
                "highlights": [
                    "Cut reconciliation from 40 minutes to 6.",
                    "Owned the ledger service end to end.",
                ],
            }
        ],
        "education": [{"degree": "M.Tech", "institution": "IIT Hyderabad"}],
    }
    jd = (
        "Senior Platform Engineer. You will run Kubernetes clusters, write Go "
        "services, own on-call, and lead a team of three. Payments experience "
        "is a plus. AWS certification preferred."
    )

    result = analysis_service.run_detailed_analysis(profile, jd)

    assert 0 <= result.fit_score <= 100
    assert len(result.skills) >= 4
    assert result.narrative and len(result.narrative.split()) > 15
    assert result.verdict

    named = " ".join(skill.skill.lower() for skill in result.skills)
    assert "kubernetes" in named

    # Gaps must be reasoned, not asserted, and matched skills must cite the
    # profile rather than repeating the job description.
    gaps = [skill for skill in result.skills if not skill.user_has]
    assert gaps and all(skill.gap_reasoning for skill in gaps)
    matched = [skill for skill in result.skills if skill.user_has]
    assert matched and all(skill.evidence for skill in matched)


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Groq test. Set RUN_LIVE=1 to run it.",
)
def test_live_quick_analysis() -> None:
    """Run the real quick prompt against Groq."""
    result = analysis_service.run_quick_analysis(
        {"summary": "Backend engineer.", "skills": ["Python", "PostgreSQL"]},
        "Senior Python engineer. Postgres, payments, Kubernetes.",
    )

    assert 0 <= result.fit_score <= 100
    assert len(result.strengths) == 3
    assert len(result.gaps) == 3
    assert result.verdict


def test_analysis_row_timestamps_are_timezone_aware(
    auth_client: TestClient, db: FakeSession, mock_quick
) -> None:
    """created_at is stamped in UTC here, not left to the column default."""
    chat = db.seed(make_chat())
    db.seed(make_profile())

    auth_client.post("/chats/{}/analyze".format(chat.id), json={"analysis_type": "quick"})

    stored = db.rows(Analysis)[0]
    assert stored.created_at.tzinfo is not None
    assert stored.created_at <= datetime.now(timezone.utc)
