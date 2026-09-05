"""Quick snapshot and detailed breakdown analysis.

Quick snapshots run on Groq (``settings.groq_model``) because the user is
watching a spinner and three seconds is the budget. Detailed breakdowns run on
Azure GPT-4o (``settings.azure_gpt4o_deployment``) because a skill-by-skill
comparison is a judgement task and depth is worth the latency.

Both calls ask for JSON mode, are wrapped in ``utils.retry.retry_with_backoff``,
and have their output normalised by the coercion helpers in
``api.schemas.analysis`` before anything is persisted. A model that returns four
strengths, a score as a string, or a missing field produces a slightly poorer
analysis -- never a 500.

An analysis is written once per chat and read from the database forever after.
Re-running is an explicit user action (``?force=true``), never a side effect of
opening a chat.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.api.schemas.analysis import (
    AnalysisType,
    DetailedBreakdown,
    QuickSnapshot,
    coerce_detailed_breakdown,
    coerce_quick_snapshot,
)
from app.models.analysis import Analysis
from app.models.chat_message import ChatMessage
from app.models.job_chat import JobChat
from app.services.azure_client import get_azure_client, get_deployment_name
from app.services.groq_client import get_groq_client, get_groq_model
from app.utils.context_builder import format_jd, format_profile
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Analysis is a judgement call, not a creative one: the same profile against the
# same JD should score about the same twice running.
ANALYSIS_TEMPERATURE = 0.2

# Quick returns four small fields, but gpt-oss spends a chunk of its budget
# reasoning before it emits any of them.
QUICK_MAX_TOKENS = 2048

# Detailed returns a skill table plus a narrative.
DETAILED_MAX_TOKENS = 4096

# The single proactive next step offered after an analysis. One suggestion, once
# -- the system prompt tells the model not to repeat it if the user moves on.
NEXT_STEP_SUGGESTION = "Want me to tailor your resume for this role?"


class AnalysisError(Exception):
    """Raised when the model is unreachable or returns nothing usable."""


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

_NO_FABRICATION = (
    "Ground every statement in the candidate profile. Never invent experience, "
    "employers, dates, degrees, certifications, tools, or numbers that are not "
    "in the profile. If the profile does not evidence something the job asks "
    "for, that is a gap -- say so."
)

QUICK_SYSTEM_PROMPT = """You are a hiring-side reviewer assessing how well one \
candidate fits one job description.

{no_fabrication}

Return a JSON object with exactly these keys:
  "fit_score": integer 0-100, how well this candidate matches this specific role
  "strengths": array of exactly 3 strings, the strongest matches, each naming
               concrete evidence from the profile
  "gaps":      array of exactly 3 strings, the most significant gaps against
               this job description
  "verdict":   one sentence, a plain recommendation on whether to apply

Scoring guide: 80-100 a strong match, 60-79 worth applying with tailoring,
40-59 a stretch, below 40 a poor fit. Be honest -- an inflated score costs the
candidate an application they cannot win.

Each strength and each gap is one sentence. No preamble, no markdown, JSON only.
""".format(no_fabrication=_NO_FABRICATION)

QUICK_USER_TEMPLATE = """{profile}

{jd}

Assess this candidate against this job description and return the JSON object."""

DETAILED_SYSTEM_PROMPT = """You are a hiring-side reviewer producing a detailed, \
skill-by-skill fit assessment of one candidate against one job description.

{no_fabrication}

Return a JSON object with exactly these keys:
  "skills": array of 6-12 objects, one per meaningful requirement in the job
            description, most important first. Each object has:
              "skill":          the requirement, named as the job description
                                names it
              "required_by_jd": boolean, true when the job description asks for
                                it explicitly
              "user_has":       boolean, true only when the profile evidences it
              "evidence":       the specific role, project, or line in the
                                profile that demonstrates it; empty string when
                                user_has is false
              "gap_reasoning":  why this gap matters for this role; empty string
                                when user_has is true
              "suggestion":     one concrete, honest thing the candidate can do
                                about the gap -- reframing real experience they
                                already have, or naming what they would need to
                                learn. Empty string when user_has is true.
  "narrative":  2-4 sentences on the overall fit, referring to the candidate's
                actual background
  "fit_score":  integer 0-100
  "strengths":  array of exactly 3 strings summarising the strongest matches
  "gaps":       array of exactly 3 strings summarising the most significant gaps
  "verdict":    one sentence, a plain recommendation on whether to apply

Scoring guide: 80-100 a strong match, 60-79 worth applying with tailoring,
40-59 a stretch, below 40 a poor fit.

No preamble, no markdown, JSON only.
""".format(no_fabrication=_NO_FABRICATION)

DETAILED_USER_TEMPLATE = """{profile}

{jd}

Produce the detailed assessment and return the JSON object."""


# --------------------------------------------------------------------------
# Model calls
# --------------------------------------------------------------------------


def build_analysis_prompt(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    analysis_type: str,
) -> str:
    """Assemble the user-turn prompt from profile and JD context.

    Args:
        profile_json: The user's stored ``parsed_json``.
        jd_text: This chat's job description.
        analysis_type: ``"quick"`` or ``"detailed"``.

    Returns:
        The filled user-message template for that depth.
    """
    template = (
        DETAILED_USER_TEMPLATE
        if analysis_type == AnalysisType.DETAILED.value
        else QUICK_USER_TEMPLATE
    )
    return template.format(profile=format_profile(profile_json), jd=format_jd(jd_text))


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse a model response that is supposed to be a JSON object.

    Tries the whole response first, then the outermost ``{...}`` span, which
    rescues a response with a stray sentence wrapped around the object.

    Raises:
        AnalysisError: If no JSON object can be recovered.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    for candidate in (text, _outermost_object(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise AnalysisError("The analysis model did not return valid JSON.")


def _outermost_object(text: str) -> str:
    """Return the outermost ``{...}`` span in a string, or an empty string."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return ""
    return text[start : end + 1]


@retry_with_backoff(max_attempts=4, base_delay=1.0)
def _call_groq_quick(prompt: str) -> str:
    """Send the quick-analysis prompt to Groq and return the raw content."""
    completion = get_groq_client().chat.completions.create(
        model=get_groq_model(),
        messages=[
            {"role": "system", "content": QUICK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=ANALYSIS_TEMPERATURE,
        max_tokens=QUICK_MAX_TOKENS,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content or ""


@retry_with_backoff(max_attempts=4, base_delay=1.0)
def _call_azure_detailed(prompt: str) -> str:
    """Send the detailed-analysis prompt to Azure GPT-4o and return the content."""
    completion = get_azure_client().chat.completions.create(
        model=get_deployment_name(),
        messages=[
            {"role": "system", "content": DETAILED_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=ANALYSIS_TEMPERATURE,
        max_tokens=DETAILED_MAX_TOKENS,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content or ""


def run_quick_analysis(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
) -> QuickSnapshot:
    """Call Groq for a fast fit snapshot.

    Returns:
        A validated :class:`QuickSnapshot`.

    Raises:
        AnalysisError: If Groq is unreachable or returns no JSON object.
    """
    prompt = build_analysis_prompt(profile_json, jd_text, AnalysisType.QUICK.value)
    try:
        content = _call_groq_quick(prompt)
    except Exception as exc:
        logger.exception("Groq quick analysis failed")
        raise AnalysisError("Quick analysis failed: {}".format(exc)) from exc
    return coerce_quick_snapshot(_parse_json_object(content))


def run_detailed_analysis(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
) -> DetailedBreakdown:
    """Call Azure GPT-4o for a skill-by-skill breakdown.

    Returns:
        A validated :class:`DetailedBreakdown`.

    Raises:
        AnalysisError: If Azure is unreachable or returns no JSON object.
    """
    prompt = build_analysis_prompt(profile_json, jd_text, AnalysisType.DETAILED.value)
    try:
        content = _call_azure_detailed(prompt)
    except Exception as exc:
        logger.exception("Azure detailed analysis failed")
        raise AnalysisError("Detailed analysis failed: {}".format(exc)) from exc
    return coerce_detailed_breakdown(_parse_json_object(content))


def run_analysis(
    analysis_type: str,
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
) -> QuickSnapshot | DetailedBreakdown:
    """Run the analysis of the requested depth.

    Args:
        analysis_type: ``"quick"`` or ``"detailed"``.
        profile_json: The user's stored ``parsed_json``.
        jd_text: This chat's job description.

    Raises:
        AnalysisError: If the model is unreachable or returns nothing usable.
    """
    if analysis_type == AnalysisType.DETAILED.value:
        return run_detailed_analysis(profile_json, jd_text)
    return run_quick_analysis(profile_json, jd_text)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_analysis_markdown(
    analysis_type: str,
    result: QuickSnapshot | DetailedBreakdown,
) -> str:
    """Render a completed analysis as the assistant message shown in the thread.

    The analysis card is its own UI component, but the thread needs a message
    too -- otherwise the conversation starts with a reply to nothing. This
    message closes with the one proactive suggestion the phase calls for.

    Args:
        analysis_type: ``"quick"`` or ``"detailed"``.
        result: The validated analysis.

    Returns:
        Markdown, ending with a single next-step question.
    """
    heading = (
        "## Detailed breakdown"
        if analysis_type == AnalysisType.DETAILED.value
        else "## Quick snapshot"
    )
    lines = [heading, "", "**Fit score: {}/100**".format(result.fit_score)]

    if result.verdict:
        lines += ["", result.verdict]

    if result.strengths:
        lines += ["", "**Where you match**"]
        lines += ["- {}".format(item) for item in result.strengths]

    if result.gaps:
        lines += ["", "**Where you fall short**"]
        lines += ["- {}".format(item) for item in result.gaps]

    if isinstance(result, DetailedBreakdown):
        if result.skills:
            lines += ["", "**Skill by skill**"]
            for skill in result.skills:
                mark = "yes" if skill.user_has else "no"
                detail = skill.evidence if skill.user_has else skill.gap_reasoning
                line = "- **{}** ({}){}".format(
                    skill.skill, mark, ": {}".format(detail) if detail else ""
                )
                if not skill.user_has and skill.suggestion:
                    line += " _{}_".format(skill.suggestion)
                lines.append(line)
        if result.narrative:
            lines += ["", result.narrative]

    lines += ["", NEXT_STEP_SUGGESTION]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def get_analysis(db: Session, chat_id: uuid.UUID) -> Analysis | None:
    """Return the stored analysis for a chat, or None if it has not been run."""
    return (
        db.query(Analysis)
        .filter(Analysis.chat_id == chat_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )


def chat_ids_with_analysis(
    db: Session,
    chat_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    """Return which of ``chat_ids`` already have an analysis.

    One query for the whole sidebar rather than one per chat.
    """
    if not chat_ids:
        return set()
    rows = db.query(Analysis).filter(Analysis.chat_id.in_(chat_ids)).all()
    return {row.chat_id for row in rows}


def save_analysis(
    db: Session,
    chat: JobChat,
    analysis_type: str,
    result: QuickSnapshot | DetailedBreakdown,
    message_content: str | None = None,
) -> Analysis:
    """Persist an analysis, its chat message, and the chat's analysis type.

    One commit covers all three: an analysis the user can see in the card but
    not in the thread (or a chat whose ``analysis_type`` disagrees with its
    stored analysis) would be a confusing half-state.

    Args:
        db: The active session.
        chat: The chat being analysed.
        analysis_type: ``"quick"`` or ``"detailed"``.
        result: The validated analysis.
        message_content: The rendered assistant message. Defaults to the
            markdown rendering of ``result``.

    Returns:
        The stored :class:`Analysis` row.
    """
    now = datetime.now(timezone.utc)
    full_json = result.model_dump()

    analysis = Analysis(
        id=uuid.uuid4(),
        chat_id=chat.id,
        type=analysis_type,
        fit_score=result.fit_score,
        strengths=list(result.strengths),
        gaps=list(result.gaps),
        verdict=result.verdict,
        full_json=full_json,
        created_at=now,
    )
    db.add(analysis)

    db.add(
        ChatMessage(
            id=uuid.uuid4(),
            chat_id=chat.id,
            role="assistant",
            content=(
                message_content
                if message_content is not None
                else render_analysis_markdown(analysis_type, result)
            ),
            kind="analysis",
            created_at=now,
        )
    )

    chat.analysis_type = analysis_type
    db.commit()
    return analysis


def delete_analysis(db: Session, analysis: Analysis) -> None:
    """Remove a stored analysis so a forced re-run can replace it."""
    db.delete(analysis)
