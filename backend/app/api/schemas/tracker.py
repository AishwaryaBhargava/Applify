"""Schemas for the job application tracker endpoints."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ApplicationStatus(str, Enum):
    """Where an application currently stands."""

    NOT_APPLIED = "not_applied"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"


class ResumeType(str, Enum):
    """Whether the user sent the base resume or a tailored one."""

    UNALTERED = "unaltered"
    TAILORED = "tailored"


class TrackerEntry(BaseModel):
    """A tracker row as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    status: ApplicationStatus
    resume_type: ResumeType
    created_at: datetime
    updated_at: datetime
    # Denormalised from the job chat for table rendering.
    title: str | None = None
    company: str | None = None


class TrackerUpdateRequest(BaseModel):
    """Partial update to a tracker row."""

    status: ApplicationStatus | None = None
    resume_type: ResumeType | None = None
