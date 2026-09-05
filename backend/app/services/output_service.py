"""Resume, cover letter, and application answer generation via Azure GPT-4o.

All output generation streams. Every Azure call is wrapped in
``utils.retry.retry_with_backoff`` because these are the longest calls the
backend makes and GPT-4o enforces per-minute token limits.

Phase 6 wired the seam: when ``chat_service.detect_intent`` classifies a message
as ``resume``, ``cover_letter``, or ``answer``, the streaming message route
delegates to :func:`generate_output` instead of answering conversationally.
Everything around that delegation -- intent, SSE framing, persistence with the
right ``kind`` -- is finished and tested. Phase 7 only has to replace the body of
:func:`generate_output` with the real Azure calls.

The rest of this module is Phase 1 scaffolding, implemented in Phase 7.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.models.generated_output import GeneratedOutput

# What the stub streams until Phase 7 lands. Kept as a constant so the test that
# pins the seam and the placeholder itself cannot drift apart.
PLACEHOLDER_TOKEN = "Output generation coming in Phase 7."


async def generate_output(
    kind: str,
    profile_json: dict[str, Any] | None = None,
    jd_text: str | None = None,
    analysis: Any = None,
    history: list[dict[str, str]] | None = None,
    user_message: str | None = None,
) -> AsyncIterator[str]:
    """Stream a generated document, token by token.

    This is the seam the chat route delegates to. It is an async generator
    because the route consumes it inside its SSE generator with ``async for``;
    Phase 7 replaces the body with the Azure streaming call and nothing above it
    changes.

    Args:
        kind: ``resume``, ``cover_letter``, or ``answer``.
        profile_json: The user's structured profile.
        jd_text: This chat's job description.
        analysis: The stored analysis for this chat, if one has been run.
        history: Chat history, oldest first.
        user_message: The message that triggered the generation -- it carries
            the user's steer ("keep it to one page", or the question to answer).

    Yields:
        Text chunks.
    """
    yield PLACEHOLDER_TOKEN


def build_output_prompt(
    output_type: str,
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    question: str | None = None,
    instructions: str | None = None,
) -> str:
    """Assemble the generation prompt for the requested output type."""
    raise NotImplementedError("Implemented in Phase 7")


def stream_output(
    output_type: str,
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    question: str | None = None,
    instructions: str | None = None,
) -> Iterator[str]:
    """Stream generated document text from Azure GPT-4o.

    Yields:
        Text chunks, ready to be wrapped as SSE events by the route.
    """
    raise NotImplementedError("Implemented in Phase 7")


def save_output(
    db: Session,
    chat_id: uuid.UUID,
    output_type: str,
    content: str,
) -> GeneratedOutput:
    """Persist a completed generated output against its chat."""
    raise NotImplementedError("Implemented in Phase 7")


def list_outputs(db: Session, chat_id: uuid.UUID) -> list[GeneratedOutput]:
    """Return the outputs already generated for a chat, newest first."""
    raise NotImplementedError("Implemented in Phase 7")
