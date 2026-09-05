"""Profile routes: resume upload, read, manual enrichment, and gap detection.

Every route here is thin on purpose. Parsing lives in
:mod:`app.services.resume_parser`, persistence and gap rules in
:mod:`app.services.profile_service`; these functions only translate between HTTP
and those services.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.schemas.profile import (
    ProfileGapsResponse,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.data.deps import CurrentUser, DbSession
from app.models.profile import Profile
from app.services import profile_service, resume_parser
from app.services.resume_parser import (
    EmptyResumeText,
    ProfileExtractionError,
    ResumeTextExtractionError,
    UnsupportedResumeFormat,
)

router = APIRouter(prefix="/profile", tags=["profile"])

# Matches the 10MB cap the upload component enforces client side. Checked again
# here because a client-side limit is a courtesy, not a control.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# The frontend keys its onboarding redirect off this exact 404 body, so it is a
# contract, not just a message.
PROFILE_NOT_FOUND = "Profile not found"


def _require_profile(db: Session, user_id: str) -> Profile:
    """Return the user's profile row or raise the 404 the frontend expects."""
    profile = profile_service.get_profile(db, user_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROFILE_NOT_FOUND)
    return profile


@router.post("/upload", response_model=ProfileResponse)
async def upload_resume(
    user_id: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> ProfileResponse:
    """Parse an uploaded PDF or DOCX resume in memory and store the profile.

    The file itself is never written to disk or object storage -- only the
    extracted text and its structured parse are persisted.

    Raises:
        HTTPException: 400 for a non-PDF/DOCX or unreadable file, 413 when the
            upload exceeds 10MB, 422 when the file holds no readable text, and
            502 when the extraction model is unreachable.
    """
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The uploaded file is empty."
        )
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "Resume must be 10MB or smaller.",
        )

    try:
        parsed = resume_parser.parse_resume(
            file_bytes,
            filename=file.filename,
            content_type=file.content_type,
        )
    except UnsupportedResumeFormat as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ResumeTextExtractionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except EmptyResumeText as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ProfileExtractionError as exc:
        # The file was fine; the model was not. A 502 tells the user to retry
        # rather than blame their resume.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    profile = profile_service.upsert_profile(
        db,
        user_id,
        raw_text=parsed["raw_text"],
        parsed_json=parsed["parsed_json"],
    )
    return ProfileResponse.model_validate(profile)


@router.get("", response_model=ProfileResponse)
def get_profile(user_id: CurrentUser, db: DbSession) -> ProfileResponse:
    """Return the authenticated user's stored profile.

    Raises:
        HTTPException: 404 when the user has not uploaded a resume yet. The
            frontend redirects to onboarding on this.
    """
    return ProfileResponse.model_validate(_require_profile(db, user_id))


@router.patch("", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> ProfileResponse:
    """Apply a manual enrichment to the stored profile.

    Any subset of the profile sections may be sent. A section that is present
    replaces that section wholesale; omitted sections are untouched.

    Raises:
        HTTPException: 404 when the user has no profile to enrich.
    """
    profile = _require_profile(db, user_id)
    updated = profile_service.merge_profile(
        db,
        profile,
        payload.section_updates(),
        raw_text=payload.raw_text,
    )
    return ProfileResponse.model_validate(updated)


@router.get("/gaps", response_model=ProfileGapsResponse)
def get_profile_gaps(user_id: CurrentUser, db: DbSession) -> ProfileGapsResponse:
    """Return the missing and thin sections of the user's profile.

    Raises:
        HTTPException: 404 when the user has no profile, matching ``GET
            /profile`` so the onboarding redirect works from either call.
    """
    profile = _require_profile(db, user_id)
    return ProfileGapsResponse(gaps=profile_service.detect_gaps(profile.parsed_json))
