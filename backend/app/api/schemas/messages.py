"""Schemas for the chat message endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# What produced a message. "chat" is an ordinary turn; "analysis" is the
# rendered fit analysis; the rest are generated documents (Phase 7).
MESSAGE_KINDS: tuple[str, ...] = (
    "chat",
    "analysis",
    "resume",
    "cover_letter",
    "answer",
)


class MessageRequest(BaseModel):
    """A user message posted into a job chat.

    There is no ``stream`` flag: ``POST /chats/{id}/messages`` always answers
    with an SSE stream, so the client has one code path instead of two.
    """

    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    """A stored chat message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    role: str = Field(description="user | assistant")
    content: str
    kind: str = Field(
        default="chat", description="chat | analysis | resume | cover_letter | answer"
    )
    created_at: datetime
