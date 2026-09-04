"""Tests for the analysis route.

Phase 1 covers the auth guard. Behavioural tests arrive with Phase 6.
"""

from fastapi.testclient import TestClient

CHAT_ID = "00000000-0000-0000-0000-000000000001"


def test_analyze_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/analyze is protected by get_current_user."""
    response = client.post(
        "/chats/{}/analyze".format(CHAT_ID), json={"type": "quick"}
    )
    assert response.status_code == 401


def test_analyze_rejects_invalid_type_only_after_auth(client: TestClient) -> None:
    """The auth dependency runs before body validation, so this is still a 401."""
    response = client.post(
        "/chats/{}/analyze".format(CHAT_ID), json={"type": "nonsense"}
    )
    assert response.status_code == 401
