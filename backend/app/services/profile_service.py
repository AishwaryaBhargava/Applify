"""Profile enrichment and gap detection.

Phase 1 scaffolding. Implemented in Phase 5.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.profile import Profile


def get_profile(db: Session, user_id: uuid.UUID | str) -> Profile | None:
    """Return the stored profile for a user, or None if they have none yet."""
    raise NotImplementedError("Implemented in Phase 5")


def upsert_profile(
    db: Session,
    user_id: uuid.UUID | str,
    raw_text: str | None,
    parsed_json: dict[str, Any] | None,
) -> Profile:
    """Create or replace a user's profile row."""
    raise NotImplementedError("Implemented in Phase 5")


def merge_profile_updates(
    existing: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Merge a manual enrichment into the stored parsed profile."""
    raise NotImplementedError("Implemented in Phase 5")


def detect_gaps(parsed_json: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return nudge suggestions for profile sections that look thin.

    Returns:
        A list of dicts matching ``api.schemas.profile.ProfileGapNudge``.
    """
    raise NotImplementedError("Implemented in Phase 5")
