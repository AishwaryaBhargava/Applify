"""Schemas for the job chat endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatCreateRequest(BaseModel):
    """Create a new job chat from a job description."""

    title: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = None
    analysis_type: str | None = Field(default=None, description="quick | detailed")


class ChatUpdateRequest(BaseModel):
    """Partial update to an existing job chat."""

    title: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = None
    analysis_type: str | None = None


class ChatResponse(BaseModel):
    """A job chat as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    company: str | None = None
    jd_text: str | None = None
    analysis_type: str | None = None
    created_at: datetime
