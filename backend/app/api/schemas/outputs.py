"""Schemas for the AI-generated output endpoints."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OutputType(str, Enum):
    """The kinds of document Applify can generate."""

    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    ANSWER = "answer"


class OutputRequest(BaseModel):
    """Ask for a generated resume, cover letter, or application answer."""

    output_type: OutputType
    # Required when output_type is ANSWER: the application question to answer.
    question: str | None = None
    instructions: str | None = Field(
        default=None, description="Optional user steer, e.g. tone or length"
    )
    stream: bool = Field(default=True, description="Return an SSE stream when true")


class OutputResponse(BaseModel):
    """A stored generated output."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    output_type: OutputType
    content: str
    created_at: datetime
