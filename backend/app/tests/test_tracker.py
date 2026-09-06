"""Tests for the job tracker routes.

A tracker row is assembled from three tables, so most of what can go wrong here
is a join problem: a row that shows the wrong chat's title, a fit score that
leaks from another application, a soft-deleted chat that never leaves the table.
Every test below is aimed at one of those.

Everything runs offline against the ``FakeSession`` -- there is no model call on
either route.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.routes.chats import CHAT_NOT_FOUND
from app.models.tracker_entry import TrackerEntry
from app.tests.conftest import OTHER_USER_ID, TEST_USER_ID, FakeSession
from app.tests.test_analysis import make_analysis
from app.tests.test_chat import NOW, make_chat, make_tracker

TODAY = datetime.now(timezone.utc).date()

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


# ==========================================================================
# The application's own fields
# ==========================================================================


def test_tracker_row_carries_the_application_fields(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Everything the detail panel edits comes back on the row."""
    chat = db.seed(make_chat())
    db.seed(
        make_tracker(
            chat.id,
            status="applied",
            job_url="https://kestrel.example/jobs/42",
            location="Remote (UK)",
            salary="GBP 75,000",
            source="LinkedIn",
            applied_at=datetime.now(timezone.utc) - timedelta(days=3),
            next_action="Follow up with the recruiter",
            next_action_date=TODAY + timedelta(days=2),
            notes="Referred by Priya.",
            priority="high",
        )
    )

    row = auth_client.get("/tracker").json()[0]

    assert row["job_url"] == "https://kestrel.example/jobs/42"
    assert row["location"] == "Remote (UK)"
    assert row["salary"] == "GBP 75,000"
    assert row["source"] == "LinkedIn"
    assert row["next_action"] == "Follow up with the recruiter"
    assert row["next_action_date"] == (TODAY + timedelta(days=2)).isoformat()
    assert row["notes"] == "Referred by Priya."
    assert row["priority"] == "high"


def test_tracker_defaults_the_application_fields_to_null(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A new application has facts, not blanks pretending to be facts."""
    seed_entry(db)

    row = auth_client.get("/tracker").json()[0]

    for field in (
        "job_url",
        "location",
        "salary",
        "source",
        "applied_at",
        "next_action",
        "next_action_date",
        "notes",
        "priority",
        "days_since_applied",
    ):
        assert row[field] is None, field
    assert row["next_action_due"] is False


def test_days_since_applied_counts_whole_days(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The "how long has it been" column is derived per request, never stored."""
    chat = db.seed(make_chat())
    db.seed(
        make_tracker(
            chat.id,
            status="applied",
            applied_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
    )

    assert auth_client.get("/tracker").json()[0]["days_since_applied"] == 5


def test_next_action_due_is_true_today_and_in_the_past(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Due means today or earlier -- a task due today is due."""
    for title, day in (
        ("Overdue", TODAY - timedelta(days=1)),
        ("Today", TODAY),
        ("Later", TODAY + timedelta(days=1)),
    ):
        chat = db.seed(make_chat(title=title))
        db.seed(make_tracker(chat.id, next_action_date=day))

    rows = {row["job_title"]: row for row in auth_client.get("/tracker").json()}

    assert rows["Overdue"]["next_action_due"] is True
    assert rows["Today"]["next_action_due"] is True
    assert rows["Later"]["next_action_due"] is False


# ==========================================================================
# PATCH: partial updates
# ==========================================================================


def test_patch_accepts_any_subset_of_the_fields(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A partial update writes what it names and leaves the rest alone."""
    chat, entry = seed_entry(db, notes="Keep me")

    response = auth_client.patch(
        "/tracker/{}".format(chat.id),
        json={
            "job_url": "https://kestrel.example/jobs/42",
            "location": "Remote (UK)",
            "salary": "GBP 75,000",
            "source": "Referral",
            "next_action": "Send the follow-up email",
            "next_action_date": "2026-10-01",
            "priority": "medium",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_url"] == "https://kestrel.example/jobs/42"
    assert body["source"] == "Referral"
    assert body["next_action_date"] == "2026-10-01"
    assert body["priority"] == "medium"
    # Untouched, and still on the row.
    assert body["status"] == "not_applied"
    assert entry.notes == "Keep me"
    assert entry.next_action_date == date(2026, 10, 1)


def test_patch_can_clear_a_field_with_null(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An explicit null clears; an omitted field does not."""
    chat, entry = seed_entry(db, notes="Old note", priority="high")

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"notes": None}
    )

    assert response.status_code == 200
    assert response.json()["notes"] is None
    assert entry.notes is None
    assert entry.priority == "high"


def test_patch_trims_whitespace_only_text_to_null(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A field emptied in the UI arrives as spaces and is stored as nothing."""
    chat, entry = seed_entry(db, notes="Old note")

    auth_client.patch("/tracker/{}".format(chat.id), json={"notes": "   "})

    assert entry.notes is None


def test_patch_rejects_an_empty_body(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Updating nothing is a client bug, not a no-op."""
    chat, _ = seed_entry(db)

    assert auth_client.patch("/tracker/{}".format(chat.id), json={}).status_code == 422
    assert db.commits == 0


# ==========================================================================
# PATCH: validation
# ==========================================================================


def test_patch_rejects_a_non_http_job_url(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Only http(s): a javascript: URL would be a link the frontend renders."""
    chat, entry = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id),
        json={"job_url": "javascript:alert(1)"},
    )

    assert response.status_code == 422
    assert entry.job_url is None
    assert db.commits == 0


def test_patch_accepts_both_http_schemes(
    auth_client: TestClient, db: FakeSession
) -> None:
    """http and https both round-trip; the URL is trimmed on the way in."""
    chat, entry = seed_entry(db)

    for url in ("http://example.com/a", "  https://example.com/b  "):
        response = auth_client.patch(
            "/tracker/{}".format(chat.id), json={"job_url": url}
        )
        assert response.status_code == 200
        assert entry.job_url == url.strip()


def test_patch_rejects_an_unknown_priority(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Priority is an enum, so "urgent" is a 422 and not a stored surprise."""
    chat, entry = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"priority": "urgent"}
    )

    assert response.status_code == 422
    assert entry.priority is None


def test_patch_rejects_over_long_notes_and_next_action(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Free text is bounded: 5000 characters of notes, 300 of next action."""
    chat, _ = seed_entry(db)

    long_notes = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"notes": "x" * 5001}
    )
    long_action = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"next_action": "x" * 301}
    )

    assert long_notes.status_code == 422
    assert long_action.status_code == 422


def test_patch_accepts_text_at_the_limit(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The ceilings are inclusive, so a note of exactly 5000 characters fits."""
    chat, _ = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id),
        json={"notes": "x" * 5000, "next_action": "y" * 300},
    )

    assert response.status_code == 200


def test_patch_rejects_a_malformed_date(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Dates are ISO; "next tuesday" is a 422."""
    chat, _ = seed_entry(db)

    response = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"next_action_date": "next tuesday"}
    )

    assert response.status_code == 422


# ==========================================================================
# PATCH: the applied_at stamp
# ==========================================================================


def test_moving_to_applied_stamps_applied_at(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The one piece of behaviour on this route: when did I send it?"""
    chat, entry = seed_entry(db)
    assert entry.applied_at is None

    body = auth_client.patch(
        "/tracker/{}".format(chat.id), json={"status": "applied"}
    ).json()

    assert entry.applied_at is not None
    assert body["applied_at"] is not None
    assert body["days_since_applied"] == 0


def test_applied_at_survives_moving_back_to_not_applied(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Correcting the status does not unsend the application."""
    chat, entry = seed_entry(db)
    auth_client.patch("/tracker/{}".format(chat.id), json={"status": "applied"})
    stamped = entry.applied_at

    auth_client.patch("/tracker/{}".format(chat.id), json={"status": "not_applied"})

    assert entry.applied_at == stamped


def test_applied_at_is_not_restamped_on_a_later_status_change(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Moving applied to interviewing keeps the original send date."""
    original = datetime.now(timezone.utc) - timedelta(days=9)
    chat = db.seed(make_chat())
    entry = db.seed(make_tracker(chat.id, status="applied", applied_at=original))

    auth_client.patch("/tracker/{}".format(chat.id), json={"status": "interviewing"})

    assert entry.applied_at == original


def test_an_explicit_applied_at_is_not_overwritten(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Back-dating an application the user sent last week must stick."""
    chat, entry = seed_entry(db)

    auth_client.patch(
        "/tracker/{}".format(chat.id),
        json={"status": "applied", "applied_at": "2026-08-20T09:00:00Z"},
    )

    assert entry.applied_at == datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)


# ==========================================================================
# GET /tracker: filtering and sorting
# ==========================================================================


def seed_three(db: FakeSession) -> None:
    """Three applications differing in every sortable and filterable way."""
    alpha = db.seed(
        make_chat(title="Backend Engineer", company="Alpha", created_at=NOW)
    )
    db.seed(
        make_tracker(
            alpha.id,
            status="applied",
            applied_at=datetime.now(timezone.utc) - timedelta(days=1),
            next_action_date=TODAY + timedelta(days=10),
            notes="Great culture",
        )
    )
    db.seed(make_analysis(alpha.id, fit_score=90))

    beta = db.seed(
        make_chat(
            title="Data Engineer", company="Beta", created_at=NOW - timedelta(days=1)
        )
    )
    db.seed(
        make_tracker(
            beta.id,
            status="rejected",
            applied_at=datetime.now(timezone.utc) - timedelta(days=20),
            next_action_date=TODAY + timedelta(days=1),
        )
    )
    db.seed(make_analysis(beta.id, fit_score=50))

    gamma = db.seed(
        make_chat(
            title="Platform Engineer",
            company="Gamma",
            created_at=NOW - timedelta(days=2),
        )
    )
    db.seed(make_tracker(gamma.id, notes="Found on the ALPHA jobs board"))


def test_tracker_filters_by_status(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The status parameter narrows the table to one column of the pipeline."""
    seed_three(db)

    rows = auth_client.get("/tracker?status=applied").json()

    assert [row["company"] for row in rows] == ["Alpha"]


def test_tracker_rejects_an_unknown_status_filter(auth_client: TestClient) -> None:
    """The filter shares the row's enum, so a typo is a 422, not an empty table."""
    assert auth_client.get("/tracker?status=ghosted").status_code == 422


def test_tracker_search_matches_title_company_and_notes(
    auth_client: TestClient, db: FakeSession
) -> None:
    """q searches the three free-text fields a user would type into a search box."""
    seed_three(db)

    by_title = auth_client.get("/tracker?q=data").json()
    by_company = auth_client.get("/tracker?q=beta").json()
    by_notes = auth_client.get("/tracker?q=culture").json()

    assert [row["company"] for row in by_title] == ["Beta"]
    assert [row["company"] for row in by_company] == ["Beta"]
    assert [row["company"] for row in by_notes] == ["Alpha"]


def test_tracker_search_is_case_insensitive(
    auth_client: TestClient, db: FakeSession
) -> None:
    """One query finds both the company Alpha and the note that shouts ALPHA."""
    seed_three(db)

    companies = {
        row["company"] for row in auth_client.get("/tracker?q=AlPhA").json()
    }

    assert companies == {"Alpha", "Gamma"}


def test_tracker_search_and_status_combine(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Both filters apply, rather than the last one winning."""
    seed_three(db)

    rows = auth_client.get("/tracker?q=engineer&status=rejected").json()

    assert [row["company"] for row in rows] == ["Beta"]


def test_tracker_sorts_by_fit_score_with_unscored_last(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Highest score first; a row with no analysis is unanswered, not zero."""
    seed_three(db)

    rows = auth_client.get("/tracker?sort=fit_score").json()

    assert [row["company"] for row in rows] == ["Alpha", "Beta", "Gamma"]
    assert rows[-1]["fit_score"] is None


def test_tracker_sorts_by_applied_at_newest_first(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The most recently sent application leads; the unsent one trails."""
    seed_three(db)

    rows = auth_client.get("/tracker?sort=applied_at").json()

    assert [row["company"] for row in rows] == ["Alpha", "Beta", "Gamma"]


def test_tracker_sorts_by_next_action_date_soonest_first(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The one exception to newest-first: the follow-up due soonest comes first."""
    seed_three(db)

    rows = auth_client.get("/tracker?sort=next_action_date").json()

    assert [row["company"] for row in rows] == ["Beta", "Alpha", "Gamma"]


def test_tracker_defaults_to_created_at_descending(
    auth_client: TestClient, db: FakeSession
) -> None:
    """No sort parameter means the same order the tracker has always had."""
    seed_three(db)

    rows = auth_client.get("/tracker").json()

    assert [row["company"] for row in rows] == ["Alpha", "Beta", "Gamma"]


def test_tracker_rejects_an_unknown_sort(auth_client: TestClient) -> None:
    """Sorting by a column that does not exist is a 422, not a silent default."""
    assert auth_client.get("/tracker?sort=salary").status_code == 422


# ==========================================================================
# POST /chats writes the application fields it is given
# ==========================================================================


def test_create_chat_stores_the_application_fields_on_the_tracker(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The posting's URL is captured once, while the user still has it open."""
    response = auth_client.post(
        "/chats",
        json={
            "title": "Backend Engineer",
            "company": "Kestrel",
            "jd_text": "Python and Postgres.",
            "job_url": "https://kestrel.example/jobs/42",
            "location": "Remote (UK)",
            "source": "LinkedIn",
        },
    )

    assert response.status_code == 201
    entry = db.rows(TrackerEntry)[0]
    assert entry.job_url == "https://kestrel.example/jobs/42"
    assert entry.location == "Remote (UK)"
    assert entry.source == "LinkedIn"

    row = auth_client.get("/tracker").json()[0]
    assert row["job_url"] == "https://kestrel.example/jobs/42"
    assert row["source"] == "LinkedIn"


def test_create_chat_rejects_a_non_http_job_url(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The same URL rule as the tracker's, enforced at the point of entry."""
    response = auth_client.post(
        "/chats",
        json={"title": "Backend Engineer", "job_url": "ftp://example.com/jd"},
    )

    assert response.status_code == 422
    assert db.rows(TrackerEntry) == []


def test_create_chat_still_works_without_the_new_fields(
    auth_client: TestClient, db: FakeSession
) -> None:
    """All three are optional; the old request body is still the whole story."""
    response = auth_client.post("/chats", json={"title": "Backend Engineer"})

    assert response.status_code == 201
    entry = db.rows(TrackerEntry)[0]
    assert entry.job_url is None
    assert entry.location is None
    assert entry.source is None
