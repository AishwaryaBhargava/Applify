"""Schemas for the ATS keyword-match endpoint.

The response is both the API contract and the storage shape: exactly this object
is written to ``job_chats.keyword_match`` and handed back by ``GET /chats/{id}``,
so there is one shape to reason about rather than a stored one and a rendered
one that can drift.

``aliases`` is carried on every row for that reason. It is what the frontend
shows when a user asks *why* "postgres" counted as "PostgreSQL", and it is what
lets a re-run rescore an existing extraction without paying for the model again.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class KeywordCategory(str, Enum):
    """What kind of thing a JD keyword is.

    The frontend groups the checklist by this, which is the only reason it is an
    enum: an unrecognised category would render as its own orphan group.
    """

    SKILL = "skill"
    TOOL = "tool"
    QUALIFICATION = "qualification"
    RESPONSIBILITY = "responsibility"
    SOFT_SKILL = "soft_skill"
    DOMAIN = "domain"


class KeywordImportance(str, Enum):
    """Whether the posting demands this or merely likes it.

    Drives the score: ``required`` is weighted twice ``preferred``, and only a
    missing ``required`` keyword reaches ``missing_required``.
    """

    REQUIRED = "required"
    PREFERRED = "preferred"


class KeywordMatchEntry(BaseModel):
    """One JD keyword and where the candidate's material says it."""

    model_config = ConfigDict(from_attributes=True)

    keyword: str
    category: KeywordCategory
    importance: KeywordImportance
    # Other spellings that counted as this keyword: the model's, plus the
    # built-in equivalences in ``keyword_service.ALIAS_GROUPS``.
    aliases: list[str] = Field(default_factory=list)
    in_profile: bool
    # Null when the chat has no generated resume to check -- which is different
    # from False, "the resume does not say it".
    in_resume: bool | None = None
    # The first line of the candidate's own material that matched, trimmed to
    # 120 characters. Null when nothing matched.
    evidence: str | None = None


class KeywordMatchResponse(BaseModel):
    """The full ATS keyword match for one chat."""

    model_config = ConfigDict(from_attributes=True)

    # Weighted: required keywords count double. 0-100.
    match_percent: int
    required_matched: int
    required_total: int
    preferred_matched: int
    preferred_total: int
    keywords: list[KeywordMatchEntry] = Field(default_factory=list)
    # The required keywords with no evidence anywhere in the profile -- the
    # actionable half of the whole feature.
    missing_required: list[str] = Field(default_factory=list)
    generated_at: datetime
    # Which provider extracted the keywords; the match itself has no provider,
    # because it is not a model call.
    provider: str = ""
