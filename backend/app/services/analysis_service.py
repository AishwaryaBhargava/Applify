"""Quick snapshot and detailed breakdown analysis.

Quick snapshots run on Groq (model from ``settings.groq_model``); detailed
breakdowns run on Azure GPT-4o. Both build their prompt through
``utils.context_builder`` and wrap the model call in
``utils.retry.retry_with_backoff``.

Phase 1 scaffolding. Implemented in Phase 6.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.analysis import Analysis


def build_analysis_prompt(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    analysis_type: str,
) -> str:
    """Assemble the analysis prompt from profile and JD context."""
    raise NotImplementedError("Implemented in Phase 6")


def run_quick_snapshot(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
) -> dict[str, Any]:
    """Call Groq for a fast fit snapshot.

    Returns:
        A dict matching ``api.schemas.analysis.QuickSnapshot``.
    """
    raise NotImplementedError("Implemented in Phase 6")


def run_detailed_breakdown(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
) -> dict[str, Any]:
    """Call Azure GPT-4o for a section-by-section breakdown.

    Returns:
        A dict matching ``api.schemas.analysis.DetailedBreakdown``.
    """
    raise NotImplementedError("Implemented in Phase 6")


def save_analysis(
    db: Session,
    chat_id: uuid.UUID,
    analysis_type: str,
    result: dict[str, Any],
) -> Analysis:
    """Persist an analysis result against its chat."""
    raise NotImplementedError("Implemented in Phase 6")
