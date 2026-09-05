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
from app.api.routes.chats import require_chat
from app.data.deps import CurrentUser, DbSession
from app.services import analysis_service, profile_service
from app.services.analysis_service import AnalysisError

router = APIRouter(prefix="/chats", tags=["analysis"])

# The frontend turns this exact body into its "upload a resume" prompt.
NO_PROFILE = "Upload your resume first"

NO_JD = "This chat has no job description to analyse."


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

    profile = profile_service.get_profile(db, user_id)
    if profile is None or not profile.parsed_json:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_PROFILE)

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
