"""Tracker routes: list application entries and update a single entry.

A tracker row is a view over three tables. The ``tracker_entries`` row holds the
two mutable facts -- status and resume type -- and everything else the table
renders is copied from the chat it belongs to (title, company, when it was
started, which analysis was run) and from that chat's analysis (the fit score).

Soft deletion is inherited rather than duplicated: the listing starts from the
user's *live* chats, so deleting a chat drops its tracker row without the
tracker knowing anything about ``deleted_at``.

Three queries serve the whole page -- chats, tracker rows, analyses -- and the
join happens in Python. That keeps every filter expressed as an ordinary
SQLAlchemy criterion and costs nothing at the scale a single user's job search
runs at.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status as http_status

from app.api.routes.chats import require_chat
from app.api.schemas.tracker import TrackerEntry, TrackerUpdateRequest
from app.data.deps import CurrentUser, DbSession
from app.models.analysis import Analysis
from app.models.job_chat import JobChat
from app.models.tracker_entry import TrackerEntry as TrackerEntryRow
from app.services import analysis_service, chat_service

router = APIRouter(prefix="/tracker", tags=["tracker"])

ENTRY_NOT_FOUND = "Tracker entry not found"


def to_tracker_entry(
    entry: TrackerEntryRow,
    chat: JobChat,
    analysis: Analysis | None = None,
) -> TrackerEntry:
    """Build one table-ready tracker row from its three sources."""
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
    )


@router.get("", response_model=list[TrackerEntry])
def list_tracker_entries(user_id: CurrentUser, db: DbSession) -> list[TrackerEntry]:
    """Return every tracker entry for the authenticated user, newest first.

    Rows whose chat has been soft-deleted are excluded, because the listing is
    driven by the live chats rather than by the tracker table.
    """
    chats = chat_service.list_chats_for_user(db, user_id)
    entries = chat_service.tracker_entries_by_chat(db, user_id)
    analyses = analysis_service.analyses_by_chat(db, [chat.id for chat in chats])

    rows = [
        to_tracker_entry(entries[chat.id], chat, analyses.get(chat.id))
        for chat in chats
        if chat.id in entries
    ]
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows


@router.patch("/{chat_id}", response_model=TrackerEntry)
def update_tracker_entry(
    chat_id: uuid.UUID,
    payload: TrackerUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> TrackerEntry:
    """Move one application to a new status.

    Addressed by ``chat_id`` rather than the tracker row's own id: the chat is
    what the user is looking at, and it is what ownership is checked against.

    Raises:
        HTTPException: 404 when the chat is not the caller's live chat, or has
            no tracker row. A status outside the enum is a 422 from the schema.
    """
    chat = require_chat(db, chat_id, user_id)

    entry = chat_service.get_tracker_entry(db, chat.id)
    if entry is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, ENTRY_NOT_FOUND)

    entry.status = payload.status.value
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()

    return to_tracker_entry(entry, chat, analysis_service.get_analysis(db, chat.id))
