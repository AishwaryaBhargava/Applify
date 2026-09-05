"""Tests for the job tracker routes.

A tracker row is assembled from three tables, so most of what can go wrong here
is a join problem: a row that shows the wrong chat's title, a fit score that
leaks from another application, a soft-deleted chat that never leaves the table.
Every test below is aimed at one of those.

Everything runs offline against the ``FakeSession`` -- there is no model call on
either route.
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.api.routes.chats import CHAT_NOT_FOUND
from app.models.tracker_entry import TrackerEntry
from app.tests.conftest import OTHER_USER_ID, TEST_USER_ID, FakeSession
from app.tests.test_analysis import make_analysis
from app.tests.test_chat import NOW, make_chat, make_tracker

CHAT_ID = "00000000-0000-0000-0000-000000000001"


def seed_entry(db: FakeSession, **tracker_kwargs):
    """Seed a chat and its tracker entry together, as ``POST /chats`` does."""
    chat = db.seed(make_chat())
    entry = db.seed(make_tracker(chat.id, **tracker_kwargs))
    return chat, entry


# ==========================================================================
# Auth guards
# ==========================================================================


def test_list_tracker_requires_auth(client: TestClient) -> None:
    """GET /tracker is protected by get_current_user."""
    assert client.get("/tracker").status_code == 401


def test_update_tracker_requires_auth(client: TestClient) -> None:
    """PATCH /tracker/{chat_id} is protected by get_current_user."""
    response = client.patch(
        "/tracker/{}".format(CHAT_ID), json={"status": "applied"}
    )
    assert response.status_code == 401


# ==========================================================================
# GET /tracker
# ==========================================================================


def test_tracker_row_carries_everything_the_table_renders(
    auth_client: TestClient, db: FakeSession
) -> None:
    """One row holds the chat's metadata, the tracker's state, and the score."""
    chat = db.seed(
        make_chat(
            title="Senior Backend Engineer",
            company="Kestrel Payments",
            analysis_type="detailed",
        )
    )
    entry = db.seed(make_tracker(chat.id, status="applied"))
    db.seed(make_analysis(chat.id, analysis_type="detailed", fit_score=74))

    body = auth_client.get("/tracker").json()

    assert len(body) == 1
    row = body[0]
    assert row["id"] == str(entry.id)
    assert row["chat_id"] == str(chat.id)
    assert row["user_id"] == TEST_USER_ID
    assert row["job_title"] == "Senior Backend Engineer"
    assert row["title"] == "Senior Backend Engineer"
    assert row["company"] == "Kestrel Payments"
    assert row["date_added"].startswith("2026-09-01")
    assert row["analysis_type"] == "detailed"
    assert row["resume_type"] == "unaltered"
    assert row["status"] == "applied"
    assert row["fit_score"] == 74
    assert row["created_at"] and row["updated_at"]


def test_tracker_fit_score_is_null_without_an_analysis(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A chat that has not been analysed has no score, not a zero."""
    seed_entry(db)

    assert auth_client.get("/tracker").json()[0]["fit_score"] is None


def test_tracker_joins_each_score_to_its_own_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Two applications, two analyses -- neither score lands on the wrong row."""
    scored = db.seed(make_chat(title="Scored", created_at=NOW))
    unscored = db.seed(
        make_chat(title="Unscored", created_at=NOW - timedelta(days=1))
    )
    db.seed(make_tracker(scored.id))
    db.seed(make_tracker(unscored.id))
    db.seed(make_analysis(scored.id, fit_score=81))

    rows = {row["job_title"]: row for row in auth_client.get("/tracker").json()}

    assert rows["Scored"]["fit_score"] == 81
    assert rows["Unscored"]["fit_score"] is None


def test_tracker_is_newest_first(auth_client: TestClient, db: FakeSession) -> None:
    """The table order is created_at descending."""
    for title, offset in (("Oldest", 2), ("Newest", 0), ("Middle", 1)):
        chat = db.seed(
            make_chat(title=title, created_at=NOW - timedelta(days=offset))
        )
        entry = make_tracker(chat.id)
        entry.created_at = chat.created_at
        db.seed(entry)

    titles = [row["job_title"] for row in auth_client.get("/tracker").json()]

    assert titles == ["Newest", "Middle", "Oldest"]


def test_tracker_excludes_soft_deleted_chats(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Deleting a chat removes its application from the tracker."""
    live = db.seed(make_chat(title="Live"))
    gone = db.seed(make_chat(title="Deleted", deleted_at=NOW))
    db.seed(make_tracker(live.id))
    db.seed(make_tracker(gone.id))

    titles = [row["job_title"] for row in auth_client.get("/tracker").json()]

    assert titles == ["Live"]
    # The row itself survives: it is application history, not garbage.
    assert len(db.rows(TrackerEntry)) == 2


def test_deleting_a_chat_hides_its_tracker_row(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The DELETE /chats/{id} soft delete propagates to the tracker."""
    chat, _ = seed_entry(db)
    assert len(auth_client.get("/tracker").json()) == 1

    assert auth_client.delete("/chats/{}".format(chat.id)).status_code == 204

    assert auth_client.get("/tracker").json() == []


def test_tracker_excludes_other_users(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Another user's applications are not in this user's tracker."""
    mine = db.seed(make_chat(title="Mine"))
    theirs = db.seed(make_chat(title="Theirs", user_id=OTHER_USER_ID))
    db.seed(make_tracker(mine.id))
    db.seed(make_tracker(theirs.id, user_id=OTHER_USER_ID))

    titles = [row["job_title"] for row in auth_client.get("/tracker").json()]

    assert titles == ["Mine"]


def test_tracker_is_empty_for_a_new_user(auth_client: TestClient) -> None:
    """No chats means an empty list, which is what drives the empty state."""
    assert auth_client.get("/tracker").json() == []


def test_tracker_reports_a_generated_resume(
    auth_client: TestClient, db: FakeSession
) -> None:
    """resume_type is what the resume generation wrote, not a default."""
    seed_entry(db, resume_type="tailored")

    assert auth_client.get("/tracker").json()[0]["resume_type"] == "tailored"


# ==========================================================================
# PATCH /tracker/{chat_id}
# ==========================================================================


def test_status_update_persists_and_returns_the_row(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The updated row comes straight back, so the store needs no refetch."""
    chat, entry = seed_entry(db)
    db.seed(make_analysis(chat.id, fit_score=64))

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"status": "interviewing"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "interviewing"
    assert body["chat_id"] == str(chat.id)
    assert body["job_title"] == chat.title
    assert body["fit_score"] == 64
    assert entry.status == "interviewing"
    assert db.commits == 1


def test_status_update_stamps_updated_at(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A status change moves updated_at; created_at is left alone."""
    chat, entry = seed_entry(db)

    auth_client.patch("/tracker/{}".format(chat.id), json={"status": "offer"})

    assert entry.updated_at > entry.created_at


def test_every_valid_status_is_accepted(
    auth_client: TestClient, db: FakeSession
) -> None:
    """All five statuses the picker offers round-trip."""
    chat, _ = seed_entry(db)

    for value in ("not_applied", "applied", "interviewing", "offer", "rejected"):
        response = auth_client.patch(
            "/tracker/{}".format(chat.id), json={"status": value}
        )
        assert response.status_code == 200
        assert response.json()["status"] == value


def test_an_unknown_status_is_rejected(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The enum is the validation: anything else is a 422 and no write."""
    chat, entry = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"status": "ghosted"}
    )

    assert response.status_code == 422
    assert entry.status == "not_applied"
    assert db.commits == 0


def test_a_missing_status_is_rejected(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Status is the only field and it is required."""
    chat, _ = seed_entry(db)

    assert auth_client.patch("/tracker/{}".format(chat.id), json={}).status_code == 422


def test_resume_type_cannot_be_set_by_the_client(
    auth_client: TestClient, db: FakeSession
) -> None:
    """resume_type follows from generating a resume; the client cannot claim it."""
    chat, entry = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id),
        json={"status": "applied", "resume_type": "tailored"},
    )

    assert response.status_code == 200
    assert entry.resume_type == "unaltered"
    assert response.json()["resume_type"] == "unaltered"


def test_status_update_404s_on_another_users_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Someone else's application does not exist, and is not modified."""
    chat = db.seed(make_chat(user_id=OTHER_USER_ID))
    entry = db.seed(make_tracker(chat.id, user_id=OTHER_USER_ID))

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"status": "offer"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == CHAT_NOT_FOUND
    assert entry.status == "not_applied"


def test_status_update_404s_on_a_deleted_chat(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A soft-deleted application cannot be moved along either."""
    chat = db.seed(make_chat(deleted_at=NOW))
    db.seed(make_tracker(chat.id))

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"status": "applied"}
    )

    assert response.status_code == 404


def test_status_update_404s_on_an_unknown_chat(auth_client: TestClient) -> None:
    """A chat id that was never issued is a 404, not a 500."""
    response = auth_client.patch(
        "/tracker/{}".format(uuid.uuid4()), json={"status": "applied"}
    )

    assert response.status_code == 404
