"""Schemas for the chat message endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageRequest(BaseModel):
    """A user message posted into a job chat."""

    content: str = Field(min_length=1)
    stream: bool = Field(default=True, description="Return an SSE stream when true")


class MessageResponse(BaseModel):
    """A stored chat message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    role: str = Field(description="user | assistant")
    content: str
    created_at: datetime
