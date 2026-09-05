"""Job chat routes: create, list, read, and soft-delete job chats.

Thin by design: ownership, soft deletion, and the tracker-entry side effect all
live in :mod:`app.services.chat_service`.

Every lookup goes through :func:`require_chat`, which returns 404 -- never 403 --
for a chat that belongs to someone else. A 403 would confirm the chat exists,
and chat ids are the only thing standing between one user's job search and
another's.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas.analysis import AnalysisResponse
from app.api.schemas.chats import ChatCreateRequest, ChatDetailResponse, ChatResponse
from app.api.schemas.messages import MessageResponse
from app.data.deps import CurrentUser, DbSession
from app.models.job_chat import JobChat
from app.services import analysis_service, chat_service

router = APIRouter(prefix="/chats", tags=["chats"])

# The frontend keys its "chat is gone" handling off this exact 404 body.
CHAT_NOT_FOUND = "Chat not found"

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
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: uuid.UUID, user_id: CurrentUser, db: DbSession) -> None:
    """Soft-delete a job chat by stamping ``deleted_at``."""
    chat = require_chat(db, chat_id, user_id)
    chat_service.soft_delete_chat(db, chat)
