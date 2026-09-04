"""Job chat routes: create, list, read, and soft-delete job chats.

Phase 1 scaffolding -- endpoints raise 501 until Phase 6 implements them.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.chats import ChatCreateRequest, ChatResponse
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/chats", tags=["chats"])

NOT_IMPLEMENTED = "Not implemented"


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreateRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> ChatResponse:
    """Create a job chat from a job description and open its tracker entry."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.get("", response_model=list[ChatResponse])
def list_chats(user_id: CurrentUser, db: DbSession) -> list[ChatResponse]:
    """List the authenticated user's job chats, newest first."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: uuid.UUID, user_id: CurrentUser, db: DbSession) -> ChatResponse:
    """Return a single job chat owned by the authenticated user."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: uuid.UUID, user_id: CurrentUser, db: DbSession) -> None:
    """Soft-delete a job chat by stamping ``deleted_at``."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
