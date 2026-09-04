"""Tracker routes: list application entries and update a single entry.

Phase 1 scaffolding -- endpoints raise 501 until Phase 8 implements them.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.tracker import TrackerEntry, TrackerUpdateRequest
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/tracker", tags=["tracker"])

NOT_IMPLEMENTED = "Not implemented"


@router.get("", response_model=list[TrackerEntry])
def list_tracker_entries(user_id: CurrentUser, db: DbSession) -> list[TrackerEntry]:
    """Return every tracker entry for the authenticated user."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.patch("/{chat_id}", response_model=TrackerEntry)
def update_tracker_entry(
    chat_id: uuid.UUID,
    payload: TrackerUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> TrackerEntry:
    """Update the status or resume type of one tracker entry."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
