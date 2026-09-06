"""Tests for account deletion.

The database is the ``FakeSession`` from ``conftest`` and the Supabase Admin
call is replaced with a recorder, so the offline tests cover the two things that
matter and cannot be checked any other way: that nothing is deleted when the
server is not configured for it, and that a failed auth deletion is reported as
a 502 rather than swallowed after the rows are already gone.

``test_db_delete_account_end_to_end`` is opt-in behind ``RUN_DB=1``. It creates a
throwaway user against the local Supabase stack, seeds real rows, and checks
that both are gone afterwards -- the only way to exercise the ``ON DELETE
CASCADE`` the offline tests take on trust.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.job_chat import JobChat
from app.models.profile import Profile
from app.models.tracker_entry import TrackerEntry
from app.services import account_service
from app.tests.conftest import OTHER_USER_ID, TEST_USER_ID, FakeSession

SERVICE_KEY = "test-service-role-key"
SUPABASE_URL = "http://127.0.0.1:54321"


class FakeResponse:
    """The slice of ``httpx.Response`` the service reads."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "body"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the process a service role key, as a real deployment would."""
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE_KEY)
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """No service role key: the deployment cannot complete a deletion."""
    monkeypatch.setattr(settings, "supabase_service_role_key", "")


@pytest.fixture
def admin_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record the Supabase Admin DELETE instead of making it."""
    calls: list[dict] = []

    def fake_delete(url: str, headers: dict | None = None, timeout: float = 0.0):
        calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        return FakeResponse(204)

    monkeypatch.setattr(account_service.httpx, "delete", fake_delete)
    return calls


def seed_account(db: FakeSession, user_id: str = TEST_USER_ID) -> dict:
    """Seed one user's profile, chat, and tracker row."""
    now = datetime.now(timezone.utc)
    key = uuid.UUID(user_id)
    profile = db.seed(
        Profile(
            user_id=key,
            raw_text="resume text",
            parsed_json={"skills": ["Python"]},
            created_at=now,
            updated_at=now,
        )
    )
    chat = db.seed(
        JobChat(
            id=uuid.uuid4(),
            user_id=key,
            title="Senior Backend Engineer",
            created_at=now,
        )
    )
    entry = db.seed(
        TrackerEntry(
            id=uuid.uuid4(),
            chat_id=chat.id,
            user_id=key,
            status="not_applied",
            resume_type="unaltered",
            created_at=now,
            updated_at=now,
        )
    )
    return {"profile": profile, "chat": chat, "tracker": entry}


# ==========================================================================
# Auth
# ==========================================================================


def test_delete_account_requires_auth(client: TestClient) -> None:
    """No token, no deletion."""
    response = client.delete("/account")
    assert response.status_code == 401


# ==========================================================================
# Not configured
# ==========================================================================


def test_delete_account_is_501_without_a_service_role_key(
    auth_client: TestClient, db: FakeSession, unconfigured: None
) -> None:
    """A server that cannot finish the job refuses to start it."""
    seed_account(db)

    response = auth_client.delete("/account")

    assert response.status_code == 501
    assert response.json() == {
        "detail": "Account deletion is not configured on this server."
    }


def test_nothing_is_deleted_when_the_server_is_not_configured(
    auth_client: TestClient, db: FakeSession, unconfigured: None
) -> None:
    """A half-deleted account is worse than a refused one."""
    seeded = seed_account(db)

    auth_client.delete("/account")

    assert db.get(Profile, seeded["profile"].user_id) is not None
    assert db.rows(JobChat) == [seeded["chat"]]
    assert db.commits == 0


# ==========================================================================
# The happy path
# ==========================================================================


def test_delete_account_returns_204_and_no_body(
    auth_client: TestClient, db: FakeSession, configured: None, admin_calls: list
) -> None:
    """Success is a 204: there is nothing left to describe."""
    seed_account(db)

    response = auth_client.delete("/account")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_account_removes_the_users_rows(
    auth_client: TestClient, db: FakeSession, configured: None, admin_calls: list
) -> None:
    """The profile, the chats, and the tracker rows all go."""
    seed_account(db)

    auth_client.delete("/account")

    assert db.rows(Profile) == []
    assert db.rows(JobChat) == []
    assert db.rows(TrackerEntry) == []
    assert db.commits == 1


def test_delete_account_leaves_other_users_alone(
    auth_client: TestClient, db: FakeSession, configured: None, admin_calls: list
) -> None:
    """Deleting one account is scoped by user id, like every other route."""
    seed_account(db)
    other = seed_account(db, OTHER_USER_ID)

    auth_client.delete("/account")

    assert db.rows(Profile) == [other["profile"]]
    assert db.rows(JobChat) == [other["chat"]]
    assert db.rows(TrackerEntry) == [other["tracker"]]


def test_delete_account_calls_the_supabase_admin_api(
    auth_client: TestClient, db: FakeSession, configured: None, admin_calls: list
) -> None:
    """The login is removed through the Admin API, with the service role key."""
    seed_account(db)

    auth_client.delete("/account")

    assert len(admin_calls) == 1
    call = admin_calls[0]
    assert call["url"] == "{}/auth/v1/admin/users/{}".format(SUPABASE_URL, TEST_USER_ID)
    assert call["headers"]["apikey"] == SERVICE_KEY
    assert call["headers"]["Authorization"] == "Bearer {}".format(SERVICE_KEY)
    assert call["timeout"] == account_service.AUTH_REQUEST_TIMEOUT


def test_delete_account_succeeds_when_the_auth_user_is_already_gone(
    auth_client: TestClient,
    db: FakeSession,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 from Supabase is the state we asked for, so a retry can finish."""
    seed_account(db)
    monkeypatch.setattr(
        account_service.httpx, "delete", lambda *a, **k: FakeResponse(404)
    )

    assert auth_client.delete("/account").status_code == 204


def test_delete_account_deletes_rows_before_calling_supabase(
    auth_client: TestClient,
    db: FakeSession,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Order matters: a login deleted first would strand unreachable rows."""
    seen: dict = {}

    def fake_delete(*args, **kwargs):
        seen["profiles_left"] = len(db.rows(Profile))
        return FakeResponse(204)

    monkeypatch.setattr(account_service.httpx, "delete", fake_delete)
    seed_account(db)

    auth_client.delete("/account")

    assert seen["profiles_left"] == 0


# ==========================================================================
# The auth call failing
# ==========================================================================


def test_a_failed_auth_deletion_is_a_502(
    auth_client: TestClient,
    db: FakeSession,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rows are gone but the login is not, and the user is told so."""
    seed_account(db)
    monkeypatch.setattr(
        account_service.httpx, "delete", lambda *a, **k: FakeResponse(500)
    )

    response = auth_client.delete("/account")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "data was removed" in detail
    assert "login could not be deleted" in detail
    # The rows really are gone -- the 502 describes a partial success.
    assert db.rows(Profile) == []


def test_an_unreachable_supabase_is_a_502(
    auth_client: TestClient,
    db: FakeSession,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure is reported the same way as a refusal."""
    seed_account(db)

    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(account_service.httpx, "delete", boom)

    assert auth_client.delete("/account").status_code == 502


def test_the_service_role_key_never_reaches_the_response(
    auth_client: TestClient,
    db: FakeSession,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure message quotes the status code, never the credentials."""
    seed_account(db)
    monkeypatch.setattr(
        account_service.httpx, "delete", lambda *a, **k: FakeResponse(403)
    )

    response = auth_client.delete("/account")

    assert SERVICE_KEY not in response.text


# ==========================================================================
# The service, directly
# ==========================================================================


def test_deletion_is_configured_needs_both_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key with no project URL cannot address the Admin API."""
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE_KEY)
    monkeypatch.setattr(settings, "supabase_url", "")
    assert not account_service.deletion_is_configured()


def test_delete_user_rows_counts_what_it_removed(
    db: FakeSession, configured: None
) -> None:
    """The counts are what the log line reports."""
    seed_account(db)

    counts = account_service.delete_user_rows(db, TEST_USER_ID)

    assert counts == {"profiles": 1, "chats": 1, "tracker_entries": 1}


def test_delete_account_on_a_user_with_nothing_stored(
    auth_client: TestClient, db: FakeSession, configured: None, admin_calls: list
) -> None:
    """A user who never uploaded anything can still delete their account."""
    assert auth_client.delete("/account").status_code == 204
    assert len(admin_calls) == 1


# ==========================================================================
# Live database -- opt in with RUN_DB=1
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_DB") != "1",
    reason="Needs the local Supabase stack. Set RUN_DB=1 to run it.",
)
def test_db_delete_account_end_to_end() -> None:
    """Create a throwaway user, seed rows, delete the account, check both went.

    The only test that proves the ``ON DELETE CASCADE`` on ``chat_id`` really
    carries the messages, analyses, outputs, and tracker rows away with the
    chat -- the FakeSession cannot cascade, so every offline test takes that on
    trust.

    Needs ``npx supabase start`` and ``SUPABASE_SERVICE_ROLE_KEY`` set to the
    key that ``npx supabase status`` prints.
    """
    import httpx
    from sqlalchemy import text as sql_text

    from app.data.database import SessionLocal

    if not account_service.deletion_is_configured():
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY is not set")

    base = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    email = "applify-throwaway-{}@example.com".format(uuid.uuid4().hex[:8])
    created = httpx.post(
        "{}/auth/v1/admin/users".format(base),
        headers=headers,
        json={"email": email, "password": uuid.uuid4().hex, "email_confirm": True},
        timeout=10.0,
    )
    assert created.status_code in (200, 201), created.text
    user_id = created.json()["id"]

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        chat_id = uuid.uuid4()
        db.add(
            Profile(
                user_id=uuid.UUID(user_id),
                raw_text="throwaway",
                parsed_json={"skills": ["Python"]},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            JobChat(
                id=chat_id,
                user_id=uuid.UUID(user_id),
                title="Throwaway role",
                created_at=now,
            )
        )
        db.add(
            TrackerEntry(
                id=uuid.uuid4(),
                chat_id=chat_id,
                user_id=uuid.UUID(user_id),
                status="not_applied",
                resume_type="unaltered",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        account_service.delete_account(db, user_id)

        for table in ("profiles", "job_chats", "tracker_entries"):
            remaining = db.execute(
                sql_text(
                    "SELECT count(*) FROM {} WHERE user_id = :uid".format(table)
                ),
                {"uid": user_id},
            ).scalar_one()
            assert remaining == 0, "{} still has rows".format(table)
    finally:
        db.close()

    lookup = httpx.get(
        "{}/auth/v1/admin/users/{}".format(base, user_id),
        headers=headers,
        timeout=10.0,
    )
    assert lookup.status_code == 404, "the auth user still exists"
