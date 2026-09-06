"""Job chat routes: create, list, read, soft-delete, and ATS keyword match.

Thin by design: ownership, soft deletion, and the tracker-entry side effect all
live in :mod:`app.services.chat_service`; the keyword match lives in
:mod:`app.services.keyword_service`.

Every lookup goes through :func:`require_chat`, which returns 404 -- never 403 --
for a chat that belongs to someone else. A 403 would confirm the chat exists,
and chat ids are the only thing standing between one user's job search and
another's.

This module is also where the two error strings every chat-scoped route shares
are defined. It is the one module all of them already import, so putting them
here is what keeps ``routes.analysis`` and ``routes.chats`` from importing each
other in a circle.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas.analysis import AnalysisResponse
from app.api.schemas.chats import ChatCreateRequest, ChatDetailResponse, ChatResponse
from app.api.schemas.keywords import KeywordMatchResponse
from app.api.schemas.messages import MessageResponse
from app.data.deps import CurrentUser, DbSession
from app.models.job_chat import JobChat
from app.services import (
    analysis_service,
    chat_service,
    keyword_service,
    output_service,
    profile_service,
)
from app.services.keyword_service import KeywordError

router = APIRouter(prefix="/chats", tags=["chats"])

# The frontend keys its "chat is gone" handling off this exact 404 body.
CHAT_NOT_FOUND = "Chat not found"

# The frontend turns this exact body into its "upload a resume" prompt. Shared
# by every route that needs a profile to work from.
NO_PROFILE = "Upload your resume first"

NO_JD = "This chat has no job description to analyse."

DEFAULT_RESUME_TYPE = "unaltered"


def require_chat(db: Session, chat_id: uuid.UUID, user_id: str) -> JobChat:
    """Return the caller's live chat or raise the 404 every route shares.

    Imported by the message and analysis routes too, so the ownership rule is
    written once.
    """
    chat = chat_service.get_chat_for_user(db, chat_id, user_id)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CHAT_NOT_FOUND)
    return chat


def to_chat_response(
    chat: JobChat,
    has_analysis: bool,
    resume_type: str = DEFAULT_RESUME_TYPE,
) -> ChatResponse:
    """Build the sidebar-ready response for one chat."""
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        company=chat.company,
        jd_text=chat.jd_text,
        analysis_type=chat.analysis_type,
        created_at=chat.created_at,
        has_analysis=has_analysis,
        resume_type=resume_type,
    )


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> ChatResponse:
    """Create a job chat from a job description and open its tracker entry.

    The tracker entry is created in the same transaction, so the tracker and the
    sidebar can never disagree about which applications exist.
    """
    chat, entry = chat_service.create_chat(
        db,
        user_id=user_id,
        title=payload.title.strip(),
        company=(payload.company or None),
        jd_text=(payload.jd_text or None),
        job_url=(payload.job_url or None),
        location=(payload.location or None),
        source=(payload.source or None),
    )
    return to_chat_response(chat, has_analysis=False, resume_type=entry.resume_type)


@router.get("", response_model=list[ChatResponse])
def list_chats(user_id: CurrentUser, db: DbSession) -> list[ChatResponse]:
    """List the authenticated user's job chats, newest first.

    Soft-deleted chats are excluded. Analysis presence and resume type are
    fetched in one query each rather than per chat.
    """
    chats = chat_service.list_chats_for_user(db, user_id)
    analysed = analysis_service.chat_ids_with_analysis(db, [c.id for c in chats])
    trackers = chat_service.tracker_entries_by_chat(db, user_id)

    return [
        to_chat_response(
            chat,
            has_analysis=chat.id in analysed,
            resume_type=(
                trackers[chat.id].resume_type
                if chat.id in trackers
                else DEFAULT_RESUME_TYPE
            ),
        )
        for chat in chats
    ]


@router.get("/{chat_id}", response_model=ChatDetailResponse)
def get_chat(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
) -> ChatDetailResponse:
    """Return one chat with its full message history and its analysis.

    One request rebuilds the whole chat page after a reload, which is why the
    messages and the analysis come along rather than being fetched separately.
    """
    chat = require_chat(db, chat_id, user_id)
    analysis = analysis_service.get_analysis(db, chat.id)
    entry = chat_service.get_tracker_entry(db, chat.id)

    return ChatDetailResponse(
        **to_chat_response(
            chat,
            has_analysis=analysis is not None,
            resume_type=entry.resume_type if entry else DEFAULT_RESUME_TYPE,
        ).model_dump(),
        messages=[
            MessageResponse.model_validate(message)
            for message in chat_service.list_messages(db, chat.id)
        ],
        analysis=AnalysisResponse.model_validate(analysis) if analysis else None,
        keyword_match=chat.keyword_match,
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: uuid.UUID, user_id: CurrentUser, db: DbSession) -> None:
    """Soft-delete a job chat by stamping ``deleted_at``."""
    chat = require_chat(db, chat_id, user_id)
    chat_service.soft_delete_chat(db, chat)


def require_profile(db: Session, user_id: str):
    """Return the caller's profile, or raise the 409 every grounded route shares.

    A 409 rather than a 404: the request is well formed and the chat exists, but
    the account is not in a state where it can be answered. The frontend turns
    it into "upload your resume first".
    """
    profile = profile_service.get_profile(db, user_id)
    if profile is None or not profile.parsed_json:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_PROFILE)
    return profile


@router.post("/{chat_id}/keywords", response_model=KeywordMatchResponse)
def match_keywords(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
    force: bool = Query(
        default=False,
        description="Re-read the job description instead of reusing its keywords.",
    ),
) -> KeywordMatchResponse:
    """Score this chat's job description against the user's profile.

    The keyword list is extracted from the JD once and cached on the chat; the
    *match* is recomputed on every call. That split is the contract: calling
    this again after editing the profile costs nothing and shows the new score,
    while ``?force=true`` is the only way to spend a model call re-reading a JD
    that has not changed.

    When the chat has a generated resume, it is searched as a second corpus, so
    a keyword the profile has but the resume dropped shows up as
    ``in_profile: true, in_resume: false``.

    Raises:
        HTTPException: 404 when the chat is not the caller's, 409 when the user
            has no profile, 422 when the chat has no job description, and 502
            when the extraction model is unreachable or returns nothing usable.
    """
    chat = require_chat(db, chat_id, user_id)
    profile = require_profile(db, user_id)

    if not (chat.jd_text or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_JD)

    resume = output_service.latest_resume(db, chat.id)

    try:
        result = keyword_service.run_keyword_match(
            chat.jd_text,
            profile.parsed_json,
            resume_content=resume.content if resume is not None else None,
            existing=chat.keyword_match,
            force=force,
        )
    except KeywordError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    chat_service.save_keyword_match(db, chat, result)
    return KeywordMatchResponse.model_validate(result)
