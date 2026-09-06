"""Tracker routes: list application entries and update a single entry.

A tracker row is a view over three tables. The ``tracker_entries`` row holds
everything the user edits by hand -- status, the posting's URL, location,
salary, source, when they applied, what they have to do next, notes, priority --
and the rest of what the table renders is copied from the chat it belongs to
(title, company, when it was started, which analysis was run) and from that
chat's analysis (the fit score).

Soft deletion is inherited rather than duplicated: the listing starts from the
user's *live* chats, so deleting a chat drops its tracker row without the
tracker knowing anything about ``deleted_at``.

Three queries serve the whole page -- chats, tracker rows, analyses -- and the
join, the filtering, and the sort all happen in Python. That keeps every
ownership rule expressed as an ordinary SQLAlchemy criterion, lets ``q`` search
across two tables in one pass, and costs nothing at the scale a single user's
job search runs at.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status as http_status

from app.api.routes.chats import require_chat
from app.api.schemas.tracker import (
    ApplicationStatus,
    TrackerEntry,
    TrackerSort,
    TrackerUpdateRequest,
)
from app.data.deps import CurrentUser, DbSession
from app.models.analysis import Analysis
from app.models.job_chat import JobChat
from app.models.tracker_entry import TrackerEntry as TrackerEntryRow
from app.services import analysis_service, chat_service

router = APIRouter(prefix="/tracker", tags=["tracker"])

ENTRY_NOT_FOUND = "Tracker entry not found"

# Fields the client may write straight through, once the schema has validated
# and trimmed them. ``status`` and ``priority`` are handled separately: one
# drives the ``applied_at`` stamp, and both arrive as enum members.
PASSTHROUGH_FIELDS: tuple[str, ...] = (
    "job_url",
    "location",
    "salary",
    "source",
    "applied_at",
    "next_action",
    "next_action_date",
    "notes",
)


def _today() -> date:
    """Today in UTC.

    The tracker's two derived fields are answers about "now", and UTC is the
    only clock the server can agree with itself on.
    """
    return datetime.now(timezone.utc).date()


def _as_date(value: datetime | None) -> date | None:
    """Return the calendar date of a timestamp, tolerating a naive one."""
    if value is None:
        return None
    return value.date()


def to_tracker_entry(
    entry: TrackerEntryRow,
    chat: JobChat,
    analysis: Analysis | None = None,
    today: date | None = None,
) -> TrackerEntry:
    """Build one table-ready tracker row from its three sources.

    Args:
        entry: The ``tracker_entries`` row.
        chat: The chat it belongs to.
        analysis: That chat's analysis, when it has one.
        today: The date to measure ``days_since_applied`` and
            ``next_action_due`` against. Defaults to today in UTC; passed in by
            the listing so every row in one response shares a single clock.
    """
    now = today or _today()
    applied_on = _as_date(entry.applied_at)
    due_on = entry.next_action_date

    return TrackerEntry(
        id=entry.id,
        chat_id=entry.chat_id,
        user_id=entry.user_id,
        job_title=chat.title,
        title=chat.title,
        company=chat.company,
        date_added=chat.created_at,
        analysis_type=chat.analysis_type,
        resume_type=entry.resume_type,
        status=entry.status,
        fit_score=analysis.fit_score if analysis is not None else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        job_url=entry.job_url,
        location=entry.location,
        salary=entry.salary,
        source=entry.source,
        applied_at=entry.applied_at,
        next_action=entry.next_action,
        next_action_date=due_on,
        notes=entry.notes,
        priority=entry.priority,
        days_since_applied=(
            (now - applied_on).days if applied_on is not None else None
        ),
        next_action_due=due_on is not None and due_on <= now,
    )


def matches_query(row: TrackerEntry, needle: str) -> bool:
    """Return True when a row mentions ``needle`` anywhere the user can see it.

    Job title, company, and notes -- the three free-text fields a user would
    actually type into a search box looking for one application.
    """
    haystack = " ".join(
        part for part in (row.job_title, row.company, row.notes) if part
    )
    return needle in haystack.lower()


def sort_rows(rows: list[TrackerEntry], sort: TrackerSort) -> list[TrackerEntry]:
    """Order the tracker table, keeping rows with no value for the key last.

    ``next_action_date`` runs ascending -- the follow-up due today is the one
    that matters -- and everything else runs newest or highest first. A row that
    has no value for the chosen key is not "oldest", it is unanswered, so it
    sorts after every row that has one regardless of direction.
    """
    if sort is TrackerSort.CREATED_AT:
        return sorted(rows, key=lambda row: row.created_at, reverse=True)

    key = sort.value
    ascending = sort is TrackerSort.NEXT_ACTION_DATE

    present = [row for row in rows if getattr(row, key) is not None]
    absent = [row for row in rows if getattr(row, key) is None]

    present.sort(key=lambda row: getattr(row, key), reverse=not ascending)
    absent.sort(key=lambda row: row.created_at, reverse=True)
    return present + absent


@router.get("", response_model=list[TrackerEntry])
def list_tracker_entries(
    user_id: CurrentUser,
    db: DbSession,
    status: ApplicationStatus | None = Query(
        default=None, description="Keep only applications in this status."
    ),
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Case-insensitive search over job title, company, and notes.",
    ),
    sort: TrackerSort = Query(
        default=TrackerSort.CREATED_AT, description="Ordering for the table."
    ),
) -> list[TrackerEntry]:
    """Return the authenticated user's tracker entries.

    Rows whose chat has been soft-deleted are excluded, because the listing is
    driven by the live chats rather than by the tracker table.

    Filtering and ordering are applied after the join, so ``q`` can match a job
    title from ``job_chats`` and a note from ``tracker_entries`` in one pass.
    """
    chats = chat_service.list_chats_for_user(db, user_id)
    entries = chat_service.tracker_entries_by_chat(db, user_id)
    analyses = analysis_service.analyses_by_chat(db, [chat.id for chat in chats])
    today = _today()

    rows = [
        to_tracker_entry(entries[chat.id], chat, analyses.get(chat.id), today)
        for chat in chats
        if chat.id in entries
    ]

    if status is not None:
        rows = [row for row in rows if row.status is status]

    needle = (q or "").strip().lower()
    if needle:
        rows = [row for row in rows if matches_query(row, needle)]

    return sort_rows(rows, sort)


def apply_update(entry: TrackerEntryRow, payload: TrackerUpdateRequest) -> None:
    """Write one partial update onto a tracker row.

    Only the fields the client actually named are touched: ``model_fields_set``
    is what separates "clear my notes" from "I did not mention notes". The
    ``applied_at`` stamp is the one piece of behaviour here rather than
    storage -- moving an application into ``applied`` for the first time records
    *when*, and moving it back out later never unrecords it, because the
    application really was sent.
    """
    changes = payload.model_dump(exclude_unset=True)
    was_applied = entry.status == ApplicationStatus.APPLIED.value

    # A null status is meaningless -- the row always has one -- so it is
    # ignored rather than treated as a clear.
    new_status = changes.pop("status", None)
    if new_status is not None:
        entry.status = new_status.value

    if "priority" in changes:
        priority = changes.pop("priority")
        entry.priority = priority.value if priority is not None else None

    for field in PASSTHROUGH_FIELDS:
        if field in changes:
            setattr(entry, field, changes[field])

    now = datetime.now(timezone.utc)
    if (
        entry.status == ApplicationStatus.APPLIED.value
        and not was_applied
        and entry.applied_at is None
    ):
        entry.applied_at = now

    entry.updated_at = now


@router.patch("/{chat_id}", response_model=TrackerEntry)
def update_tracker_entry(
    chat_id: uuid.UUID,
    payload: TrackerUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> TrackerEntry:
    """Update any subset of one application's editable fields.

    Addressed by ``chat_id`` rather than the tracker row's own id: the chat is
    what the user is looking at, and it is what ownership is checked against.

    Raises:
        HTTPException: 404 when the chat is not the caller's live chat, or has
            no tracker row. An empty body, a status or priority outside its
            enum, a ``job_url`` that is not http(s), an over-long note, or a
            malformed date are all 422s from the schema.
    """
    chat = require_chat(db, chat_id, user_id)

    entry = chat_service.get_tracker_entry(db, chat.id)
    if entry is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, ENTRY_NOT_FOUND)

    apply_update(entry, payload)
    db.commit()

    return to_tracker_entry(entry, chat, analysis_service.get_analysis(db, chat.id))
