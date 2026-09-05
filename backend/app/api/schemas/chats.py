"""Schemas for the job chat endpoints.

``ChatResponse`` is the shape the sidebar renders from, so it carries the two
pieces of state the list needs but the ``job_chats`` row does not hold:
``has_analysis`` (has this chat been analysed yet?) and ``resume_type`` (from
the chat's tracker entry). Both are computed by the route; keeping them here
means the frontend never has to fan out to /tracker just to draw the list.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.analysis import AnalysisResponse
from app.api.schemas.messages import MessageResponse


class ChatCreateRequest(BaseModel):
    """Create a new job chat from a job description.

    ``analysis_type`` is deliberately not accepted here: it is set by
    ``POST /chats/{id}/analyze`` when the user actually picks a depth, so a chat
    can never claim an analysis it does not have.
    """

    title: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = None


class ChatUpdateRequest(BaseModel):
    """Partial update to an existing job chat."""

    title: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    jd_text: str | None = None


class ChatResponse(BaseModel):
    """A job chat as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str | None = None
    jd_text: str | None = None
    # null until an analysis has been run; then "quick" or "detailed".
    analysis_type: str | None = None
    created_at: datetime
    # True once an analysis row exists for this chat.
    has_analysis: bool = False
    # From the chat's tracker entry: "unaltered" until a resume is generated.
    resume_type: str = "unaltered"


class ChatDetailResponse(ChatResponse):
    """A single chat with everything needed to render it: history and analysis."""

    messages: list[MessageResponse] = Field(default_factory=list)
    analysis: AnalysisResponse | None = None
