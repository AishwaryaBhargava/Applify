"""Profile routes: resume upload, read, manual enrichment, and gap detection.

Every route here is thin on purpose. Parsing lives in
:mod:`app.services.resume_parser`, persistence and gap rules in
:mod:`app.services.profile_service`; these functions only translate between HTTP
and those services.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.schemas.profile import (
    ImportSource,
    ProfileGapsResponse,
    ProfileImportApplyRequest,
    ProfileImportResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    validate_section_updates,
)
from app.core.errors import IMPORT_EXTRACTION_FAILED, RESUME_EXTRACTION_FAILED
from app.data.deps import CurrentUser, DbSession
from app.models.profile import Profile
from app.services import import_service, profile_service, resume_parser
from app.services.import_service import (
    DocumentReadError,
    DocumentTooDense,
    DocumentTooLarge,
    EmptyDocumentText,
    ImportProposalError,
    UnsupportedDocumentFormat,
)
from app.services.resume_parser import (
    EmptyResumeText,
    ProfileExtractionError,
    ResumeTextExtractionError,
    UnsupportedResumeFormat,
)

logger = logging.getLogger(__name__)

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
        # rather than blame their resume, and the provider's own text -- a
        # status code and a vendor error code -- is logged rather than shown:
        # every log line carries the request id, so the two can be matched up.
        logger.error("resume extraction failed for a valid upload: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, RESUME_EXTRACTION_FAILED
        ) from exc

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

    Unlike the resume-extraction path, which keeps whatever the model managed to
    read, a user edit is validated strictly first: an entry that is missing a
    required field is a 422 rather than a row that quietly disappears on save.
    Validation runs on the incoming partial *before* the merge, so a rejected
    request writes nothing at all.

    Raises:
        HTTPException: 404 when the user has no profile to enrich.
        ProfileValidationError: 422, with a per-field ``errors`` list, when an
            entry the user filled in is missing a required field.
    """
    profile = _require_profile(db, user_id)
    updated = profile_service.merge_profile(
        db,
        profile,
        validate_section_updates(payload.section_updates()),
        raw_text=payload.raw_text,
    )
    return ProfileResponse.model_validate(updated)


@router.post("/import", response_model=ProfileImportResponse)
async def import_document(
    user_id: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> ProfileImportResponse:
    """Propose what the profile would look like with a document folded in.

    **Nothing is saved.** The response is a proposal plus a per-entry diff for
    the user to review; ``POST /profile/import/apply`` is what writes. A user
    with no profile yet gets a proposal in which everything is an addition.

    The file is read in memory and discarded, exactly like a resume upload --
    no upload is stored and no proposal is cached, which is why
    ``/profile/import/apply`` takes the reviewed proposal back in its body.

    Raises:
        HTTPException: 400 for an unsupported or unreadable file, 413 over
            10MB, 422 when the file holds no importable text or is too dense to
            merge in one go, and 502 when the merge model is unreachable.
    """
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The uploaded file is empty."
        )
    if len(file_bytes) > import_service.MAX_IMPORT_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "The file must be 10MB or smaller."
        )

    try:
        document = import_service.extract_document_text(
            file_bytes, filename=file.filename, content_type=file.content_type
        )
    except DocumentTooLarge as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except UnsupportedDocumentFormat as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DocumentReadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except EmptyDocumentText as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    profile = profile_service.get_profile(db, user_id)
    try:
        result = import_service.propose_import(
            profile.parsed_json if profile is not None else None,
            document["text"],
            file.filename or "document",
        )
    except DocumentTooDense as exc:
        # Not the provider's fault and not a bad file: one section is simply
        # larger than a single answer can hold, and only the user can fix that.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ImportProposalError as exc:
        # The file was fine; the model was not. As with the upload above, the
        # user gets a sentence and the log gets the provider's error.
        logger.error("profile import failed for a valid upload: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, IMPORT_EXTRACTION_FAILED
        ) from exc

    return ProfileImportResponse(
        proposal=result["proposal"],
        changes=result["changes"],
        summary=result["summary"],
        source=ImportSource(
            filename=file.filename,
            kind=document["structure"]["kind"],
            sheets=document["structure"]["sheets"],
        ),
        # Echoed back on apply, where it is appended to raw_text. Nothing about
        # the upload is kept server-side between the two calls, so the client
        # holds it in the meantime.
        document_text=document["text"][: import_service.MAX_RAW_TEXT_CHARS],
        provider=result.get("provider") or None,
    )


@router.post("/import/apply", response_model=ProfileResponse)
def apply_import(
    payload: ProfileImportApplyRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> ProfileResponse:
    """Write the sections of a reviewed import proposal the user chose to keep.

    Each named section replaces that section wholesale; sections the user did
    not tick are untouched. The submitted values go through the **same strict
    validation** as a manual edit -- an import is still a user's decision to
    write something, and a row that vanished on save with a 200 would be data
    loss whether a model or a keyboard produced it. A 422 writes nothing.

    When ``document_text`` is sent it is appended to the profile's ``raw_text``
    under a dated header, so a later re-extraction can see the imported source.
    A user who has no profile row yet gets one created here.

    Raises:
        ProfileValidationError: 422, with a per-field ``errors`` list, when a
            proposed entry is missing a required field.
    """
    profile = profile_service.get_profile(db, user_id)
    updates = validate_section_updates(payload.selected_updates())

    raw_text: str | None = None
    if payload.document_text:
        raw_text = import_service.append_import_to_raw_text(
            profile.raw_text if profile is not None else None,
            payload.document_text,
            payload.filename,
        )

    if profile is None:
        # An import can be the first thing a user does. Creating the row here
        # keeps that path from needing a resume upload first.
        profile = profile_service.upsert_profile(
            db,
            user_id,
            raw_text=raw_text,
            parsed_json=profile_service.merge_profile_updates(None, updates),
        )
        return ProfileResponse.model_validate(profile)

    updated = profile_service.merge_profile(db, profile, updates, raw_text=raw_text)
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
