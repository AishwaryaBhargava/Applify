"""Chat message routes: read history and post a new message.

Phase 1 scaffolding -- endpoints raise 501 until Phase 6 implements them.
POST streams the assistant reply back over SSE once implemented.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.schemas.messages import MessageRequest, MessageResponse
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/chats", tags=["messages"])

NOT_IMPLEMENTED = "Not implemented"


@router.get("/{chat_id}/messages", response_model=list[MessageResponse])
def list_messages(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
) -> list[MessageResponse]:
    """Return the full message history for a chat, oldest first."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.post("/{chat_id}/messages")
def create_message(
    chat_id: uuid.UUID,
    payload: MessageRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """Store the user message and stream the Groq assistant reply over SSE."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
