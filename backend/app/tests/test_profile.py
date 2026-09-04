"""Tests for the profile routes.

Phase 1 covers the auth guard only. Behavioural tests arrive with Phases 4-5.
"""

from fastapi.testclient import TestClient


def test_get_profile_requires_auth(client: TestClient) -> None:
    """GET /profile is protected by get_current_user."""
    assert client.get("/profile").status_code == 401


def test_patch_profile_requires_auth(client: TestClient) -> None:
    """PATCH /profile is protected by get_current_user."""
    assert client.patch("/profile", json={}).status_code == 401


def test_upload_profile_requires_auth(client: TestClient) -> None:
    """POST /profile/upload is protected by get_current_user."""
    assert client.post("/profile/upload").status_code == 401
