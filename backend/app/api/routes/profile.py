"""Profile routes: resume upload, read, and manual enrichment.

Phase 1 scaffolding -- endpoints are declared with their real signatures but
raise 501 until Phases 4 and 5 implement them.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.schemas.profile import ProfileResponse, ProfileUpdateRequest
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/profile", tags=["profile"])

NOT_IMPLEMENTED = "Not implemented"


@router.post("/upload", response_model=ProfileResponse)
def upload_resume(
    user_id: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> ProfileResponse:
    """Parse an uploaded PDF or DOCX resume in memory and store the profile."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.get("", response_model=ProfileResponse)
def get_profile(user_id: CurrentUser, db: DbSession) -> ProfileResponse:
    """Return the authenticated user's stored profile."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.patch("", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> ProfileResponse:
    """Apply a manual enrichment to the stored profile."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
