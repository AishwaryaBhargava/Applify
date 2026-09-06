"""Analysis route: run a quick snapshot or detailed breakdown for a chat.

The response is plain JSON, not a stream. The frontend shows a skeleton card
while it runs, and an analysis is only useful once it is complete and validated
-- a half-parsed fit score on screen would be worse than a spinner.

An analysis is written once per chat. Re-opening a chat reads it back from the
database; re-running is an explicit ``?force=true``.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas.analysis import AnalysisRequest, AnalysisResponse

# NO_PROFILE and NO_JD are defined in routes.chats -- the module every
# chat-scoped route already imports -- and re-exported here because they are
# part of this route's contract too.
from app.api.routes.chats import NO_JD, NO_PROFILE, require_chat, require_profile
from app.data.deps import CurrentUser, DbSession
from app.services import analysis_service
from app.services.analysis_service import AnalysisError

router = APIRouter(prefix="/chats", tags=["analysis"])

__all__ = ["NO_JD", "NO_PROFILE", "analyze_chat", "router"]


@router.post("/{chat_id}/analyze", response_model=AnalysisResponse)
def analyze_chat(
    chat_id: uuid.UUID,
    payload: AnalysisRequest,
    user_id: CurrentUser,
    db: DbSession,
    force: bool = Query(
        default=False,
        description="Re-run the analysis and replace the stored one.",
    ),
) -> AnalysisResponse:
    """Analyse the stored profile against this chat's JD and persist the result.

    Quick snapshots run on Groq; detailed breakdowns run on Azure GPT-4o. On
    success the analysis is saved, ``job_chats.analysis_type`` is set, and one
    assistant message rendering the analysis is appended to the thread.

    Raises:
        HTTPException: 404 when the chat is not the caller's, 409 when the user
            has no profile to analyse, 422 when the chat has no job description,
            and 502 when the model is unreachable or returns nothing usable.
    """
    chat = require_chat(db, chat_id, user_id)

    existing = analysis_service.get_analysis(db, chat.id)
    if existing is not None and not force:
        # Never re-run on a revisit: it costs a model call and would show the
        # user a different score for the same profile and the same JD.
        return AnalysisResponse.model_validate(existing)

    profile = require_profile(db, user_id)

    if not (chat.jd_text or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_JD)

    analysis_type = payload.analysis_type.value
    try:
        result = analysis_service.run_analysis(
            analysis_type, profile.parsed_json, chat.jd_text
        )
    except AnalysisError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if existing is not None:
        analysis_service.delete_analysis(db, existing)

    analysis = analysis_service.save_analysis(db, chat, analysis_type, result)
    return AnalysisResponse.model_validate(analysis)
