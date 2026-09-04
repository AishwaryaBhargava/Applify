"""Output routes: generate a tailored resume, cover letter, or answer.

Phase 1 scaffolding -- endpoints raise 501 until Phase 7 implements them.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.schemas.outputs import OutputRequest, OutputResponse
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/chats", tags=["outputs"])

NOT_IMPLEMENTED = "Not implemented"


@router.post("/{chat_id}/outputs")
def create_output(
    chat_id: uuid.UUID,
    payload: OutputRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """Generate a resume, cover letter, or application answer via Azure GPT-4o."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)


@router.get("/{chat_id}/outputs", response_model=list[OutputResponse])
def list_outputs(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
) -> list[OutputResponse]:
    """List the outputs already generated for this chat."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
