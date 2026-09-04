"""Resume, cover letter, and application answer generation via Azure GPT-4o.

All output generation streams. Every Azure call is wrapped in
``utils.retry.retry_with_backoff`` because these are the longest calls the
backend makes and GPT-4o enforces per-minute token limits.

Phase 1 scaffolding. Implemented in Phase 7.
"""

import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.models.generated_output import GeneratedOutput


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
