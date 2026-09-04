"""Schemas for the JD analysis endpoint."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisType(str, Enum):
    """Which analysis depth the user asked for."""

    QUICK = "quick"
    DETAILED = "detailed"


class AnalysisRequest(BaseModel):
    """Run an analysis of the stored profile against this chat's JD."""

    type: AnalysisType = AnalysisType.QUICK


class QuickSnapshot(BaseModel):
    """Fast Groq-generated fit snapshot."""

    fit_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: str


class BreakdownSection(BaseModel):
    """One dimension of the detailed breakdown."""

    name: str
    score: int | None = Field(default=None, ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    notes: str | None = None


class DetailedBreakdown(BaseModel):
    """Deeper Azure GPT-4o analysis, section by section."""

    fit_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: str
    sections: list[BreakdownSection] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    """A stored analysis row as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    type: AnalysisType
    fit_score: int | None = None
    strengths: list[Any] = Field(default_factory=list)
    gaps: list[Any] = Field(default_factory=list)
    verdict: str | None = None
    full_json: dict[str, Any] | None = None
    created_at: datetime
