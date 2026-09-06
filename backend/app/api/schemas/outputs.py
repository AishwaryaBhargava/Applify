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


class ExportFormat(str, Enum):
    """The file formats a generated document can be downloaded as.

    ``docx`` is the one people actually upload to an application form; ``md`` is
    the raw document, for the user who wants to paste it somewhere else without
    a rendering step in between.
    """

    DOCX = "docx"
    MD = "md"


class OutputRequest(BaseModel):
    """Ask for a generated resume, cover letter, or application answer.

    ``user_context`` is whatever the user typed alongside the button: a steer
    ("mention my team leadership"), a length ("keep it to one page"), or -- for
    ``answer`` -- the application question itself. It is appended to the
    synthetic user message the route stores, so the thread reads as though the
    user had asked in chat.
    """

    output_type: OutputType
    user_context: str | None = Field(
        default=None,
        max_length=8000,
        description="Optional steer, or the question to answer",
    )


class OutputResponse(BaseModel):
    """A stored generated output."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    output_type: OutputType
    content: str
    created_at: datetime
