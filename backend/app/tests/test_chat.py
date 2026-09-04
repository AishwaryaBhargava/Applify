"""Tests for the job chat and message routes, plus the AI context builder.

Phase 1 covers the auth guard and context_builder. Behavioural tests for the
chat endpoints arrive with Phase 6.
"""

from fastapi.testclient import TestClient

from app.utils.context_builder import build_context

CHAT_ID = "00000000-0000-0000-0000-000000000001"


def test_list_chats_requires_auth(client: TestClient) -> None:
    """GET /chats is protected by get_current_user."""
    assert client.get("/chats").status_code == 401


def test_create_chat_requires_auth(client: TestClient) -> None:
    """POST /chats is protected by get_current_user."""
    assert client.post("/chats", json={"title": "Backend Engineer"}).status_code == 401


def test_list_messages_requires_auth(client: TestClient) -> None:
    """GET /chats/{id}/messages is protected by get_current_user."""
    assert client.get("/chats/{}/messages".format(CHAT_ID)).status_code == 401


def test_build_context_always_keeps_profile_and_jd() -> None:
    """Profile and JD survive even when the word budget is tiny."""
    context = build_context(
        profile_json={"full_name": "Ada Lovelace", "skills": ["python"]},
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
