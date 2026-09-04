"""Analysis route: run a quick snapshot or detailed breakdown for a chat.

Phase 1 scaffolding -- the endpoint raises 501 until Phase 6 implements it.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.data.deps import CurrentUser, DbSession

router = APIRouter(prefix="/chats", tags=["analysis"])

NOT_IMPLEMENTED = "Not implemented"


@router.post("/{chat_id}/analyze", response_model=AnalysisResponse)
def analyze_chat(
    chat_id: uuid.UUID,
    payload: AnalysisRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> AnalysisResponse:
    """Analyse the stored profile against this chat's JD and persist the result.

    Quick snapshots run on Groq; detailed breakdowns run on Azure GPT-4o.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_IMPLEMENTED)
