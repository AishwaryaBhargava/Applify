"""Conversational chat with Groq, streamed to the client over SSE.

Phase 1 scaffolding. Implemented in Phase 6.
"""

import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage


def list_messages(db: Session, chat_id: uuid.UUID) -> list[ChatMessage]:
    """Return a chat's message history, oldest first."""
    raise NotImplementedError("Implemented in Phase 6")


def save_message(
    db: Session,
    chat_id: uuid.UUID,
    role: str,
    content: str,
) -> ChatMessage:
    """Persist a single message on a chat."""
    raise NotImplementedError("Implemented in Phase 6")


def stream_reply(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    history: list[dict[str, str]],
    user_message: str,
) -> Iterator[str]:
    """Stream the Groq assistant reply token by token.

    Yields:
        Response text chunks, ready to be wrapped as SSE events by the route.
    """
    raise NotImplementedError("Implemented in Phase 6")
