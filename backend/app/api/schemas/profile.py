"""Schemas for the profile endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkExperience(BaseModel):
    """A single role in the user's work history."""

    company: str | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class Education(BaseModel):
    """A single education entry."""

    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ParsedProfile(BaseModel):
    """The structured profile extracted from a resume and enriched by the user."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)


class ProfileUploadRequest(BaseModel):
    """Optional metadata sent alongside the multipart resume upload.

    The file itself arrives as an ``UploadFile``, not through this model.
    """

    filename: str | None = None


class ProfileResponse(BaseModel):
    """A user's stored profile."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    raw_text: str | None = None
    parsed_json: ParsedProfile | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Partial update to the stored profile (manual enrichment)."""

    parsed_json: ParsedProfile | None = None
    raw_text: str | None = None


class ProfileGapNudge(BaseModel):
    """A suggestion surfaced when a profile section looks thin."""

    section: str
    message: str
    severity: str = "info"
