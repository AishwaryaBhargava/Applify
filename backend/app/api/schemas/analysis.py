"""Schemas for the JD analysis endpoint.

Two shapes come back from the models and both are normalised here before they
reach the database or the client:

* :class:`QuickSnapshot` -- Groq, a few seconds, four fields.
* :class:`DetailedBreakdown` -- Azure GPT-4o, skill by skill, plus a narrative.

The coercion helpers follow the same rule as ``schemas.profile``: a model that
returns a string where a list belongs, a score of ``"85"``, or four strengths
instead of three is normalised rather than rejected. Only output that is not a
JSON object at all is an error, and ``analysis_service`` raises that.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

# Quick snapshots are contracted to exactly three strengths and three gaps: the
# card has three slots, and "top three" is what makes it a snapshot.
SNAPSHOT_POINTS = 3

# A detailed breakdown past this many skills stops being readable.
MAX_SKILLS = 20


class AnalysisType(str, Enum):
    """Which analysis depth the user asked for."""

    QUICK = "quick"
    DETAILED = "detailed"


class AnalysisRequest(BaseModel):
    """Run an analysis of the stored profile against this chat's JD."""

    model_config = ConfigDict(populate_by_name=True)

    # "type" is accepted as an alias so an older client keeps working.
    analysis_type: AnalysisType = Field(
        default=AnalysisType.QUICK,
        validation_alias=AliasChoices("analysis_type", "type"),
    )


class QuickSnapshot(BaseModel):
    """Fast Groq-generated fit snapshot."""

    fit_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: str = ""


class SkillAssessment(BaseModel):
    """One skill, compared between the job description and the profile."""

    model_config = ConfigDict(extra="ignore")

    skill: str
    required_by_jd: bool = False
    user_has: bool = False
    # What in the profile backs this up. Empty when the user does not have it.
    evidence: str = ""
    # Why the gap matters, when there is one.
    gap_reasoning: str = ""
    # What the user could do about it.
    suggestion: str = ""


class DetailedBreakdown(BaseModel):
    """Deeper Azure GPT-4o analysis: skill by skill, plus an overall narrative."""

    fit_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: str = ""
    skills: list[SkillAssessment] = Field(default_factory=list)
    narrative: str = ""


class AnalysisResponse(BaseModel):
    """A stored analysis row as returned to the client.

    ``strengths``, ``gaps``, ``verdict``, and ``fit_score`` are the summary --
    the same four fields whichever depth ran, so the card renders identically.
    ``full_json`` carries the depth-specific detail.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    type: AnalysisType
    fit_score: int = Field(default=0, ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: str = ""
    full_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator(
        "fit_score", "strengths", "gaps", "verdict", "full_json", mode="before"
    )
    @classmethod
    def _null_to_default(cls, value: Any, info: ValidationInfo) -> Any:
        """Read a nullable column as its empty value.

        Every column behind these fields is nullable, and the client contract is
        that they are always present. A row written before this phase, or by
        hand, must not turn into a 500 on read.
        """
        if value is not None:
            return value
        return {
            "fit_score": 0,
            "strengths": [],
            "gaps": [],
            "verdict": "",
            "full_json": {},
        }[info.field_name]


# --------------------------------------------------------------------------
# Defensive coercion of model output
# --------------------------------------------------------------------------


def _clean_str(value: Any) -> str:
    """Return a stripped string for anything scalar, else an empty string."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _clean_str_list(value: Any, limit: int | None = None) -> list[str]:
    """Return non-empty strings from a list, de-duplicated, order preserved."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        # A model sometimes returns [{"strength": "..."}] instead of ["..."].
        if isinstance(item, dict):
            item = next(
                (v for v in item.values() if isinstance(v, str) and v.strip()), None
            )
        cleaned = _clean_str(item)
        if not cleaned or cleaned.casefold() in seen:
            continue
        seen.add(cleaned.casefold())
        out.append(cleaned)
        if limit is not None and len(out) >= limit:
            break
    return out


def _clean_bool(value: Any) -> bool:
    """Coerce a model's idea of a boolean into an actual one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _clean_score(value: Any) -> int:
    """Clamp a fit score into 0-100, reading "85" and 0.85 as 85."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, str):
        stripped = value.strip().rstrip("%").strip()
        try:
            value = float(stripped)
        except ValueError:
            return 0
    if not isinstance(value, (int, float)):
        return 0
    # A model asked for 0-100 occasionally answers with a fraction.
    if isinstance(value, float) and 0 < value <= 1:
        value *= 100
    return max(0, min(100, int(round(value))))


def coerce_quick_snapshot(raw: Any) -> QuickSnapshot:
    """Normalise Groq's quick-analysis output. Never raises.

    Strengths and gaps are trimmed to three; nothing is invented to pad a short
    list, because a fabricated strength is worse than a missing one.
    """
    if not isinstance(raw, dict):
        return QuickSnapshot(fit_score=0)
    return QuickSnapshot(
        fit_score=_clean_score(raw.get("fit_score")),
        strengths=_clean_str_list(raw.get("strengths"), SNAPSHOT_POINTS),
        gaps=_clean_str_list(raw.get("gaps"), SNAPSHOT_POINTS),
        verdict=_clean_str(raw.get("verdict")),
    )


def _coerce_skills(items: Any) -> list[SkillAssessment]:
    """Build skill assessments, dropping any entry that does not name a skill."""
    out: list[SkillAssessment] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            name = _clean_str(item)
            if name:
                out.append(SkillAssessment(skill=name))
        elif isinstance(item, dict):
            name = _clean_str(item.get("skill") or item.get("name"))
            if not name:
                continue
            out.append(
                SkillAssessment(
                    skill=name,
                    required_by_jd=_clean_bool(item.get("required_by_jd")),
                    user_has=_clean_bool(item.get("user_has")),
                    evidence=_clean_str(item.get("evidence")),
                    gap_reasoning=_clean_str(item.get("gap_reasoning")),
                    suggestion=_clean_str(item.get("suggestion")),
                )
            )
        if len(out) >= MAX_SKILLS:
            break
    return out


def coerce_detailed_breakdown(raw: Any) -> DetailedBreakdown:
    """Normalise Azure GPT-4o's detailed output. Never raises.

    When the model gives a narrative but no verdict, the narrative's first
    sentence stands in, so the summary card is never blank.
    """
    if not isinstance(raw, dict):
        return DetailedBreakdown(fit_score=0)

    narrative = _clean_str(raw.get("narrative"))
    verdict = _clean_str(raw.get("verdict"))
    if not verdict and narrative:
        verdict = narrative.split(". ")[0].strip().rstrip(".") + "."

    return DetailedBreakdown(
        fit_score=_clean_score(raw.get("fit_score")),
        strengths=_clean_str_list(raw.get("strengths"), SNAPSHOT_POINTS),
        gaps=_clean_str_list(raw.get("gaps"), SNAPSHOT_POINTS),
        verdict=verdict,
        skills=_coerce_skills(raw.get("skills")),
        narrative=narrative,
    )
