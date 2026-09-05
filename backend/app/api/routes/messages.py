"""Chat message routes: read history and post a new message.

``POST /chats/{id}/messages`` answers with Server-Sent Events. The wire format
is one JSON object per ``data:`` line:

    {"type": "start", "message_id": "<uuid>", "kind": "chat"}
    {"type": "token", "content": "..."}          (repeated)
    {"type": "done",  "message_id": "<uuid>", "content": "<full text>"}
    {"type": "error", "message": "...", "message_id": "<uuid>", "partial": true}

``start`` announces the assistant message's id before there is anything to
store, so the frontend can render an empty bubble immediately and the id it
streams into is the id the message is finally saved under.

``kind`` on the ``start`` event is the detected intent. When it is not ``chat``,
the tokens come from ``output_service`` instead of the conversational model, and
the ``done`` event carries the stored document's ``output_id`` as well -- plus
``resume_type`` when the document was a resume, so the tracker updates without a
refetch.

Whatever streamed before a failure is persisted, and the ``error`` event names
the same ``message_id`` with ``partial: true``, so the frontend can leave the
partial text on screen and offer a retry rather than losing it.

:func:`open_token_stream` and :func:`assistant_event_stream` are the two halves
this module exports to ``routes.outputs``. The explicit-button path posts a
different user message but must produce byte-identical SSE, so it reuses both
rather than restating them.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.api.routes.chats import require_chat
from app.api.schemas.messages import MessageRequest, MessageResponse
from app.data.deps import CurrentUser, DbSession
from app.models.job_chat import JobChat
from app.services import analysis_service, chat_service, output_service, profile_service
from app.utils.context_builder import build_messages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["messages"])

# Proxies buffer text/event-stream by default, which turns a live stream into
# one delivery at the end. X-Accel-Buffering is the nginx opt-out Render honours.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

EMPTY_MESSAGE = "A message cannot be empty."
STREAM_FAILED = "The assistant could not finish this reply. Please try again."
EMPTY_REPLY = "The assistant returned an empty reply. Please try again."


def sse_event(payload: dict[str, Any]) -> str:
    """Render one SSE event: a single ``data:`` line holding a JSON object."""
    return "data: {}\n\n".format(json.dumps(payload, ensure_ascii=False))


# --------------------------------------------------------------------------
# The shared streaming turn
# --------------------------------------------------------------------------


def open_token_stream(
    db: Session,
    chat: JobChat,
    user_id: str,
    kind: str,
    user_message: str,
) -> AsyncIterator[str]:
    """Open the token stream for one assistant turn.

    The grounding material -- profile, analysis, history -- is read here rather
    than inside the SSE generator, so a database problem surfaces while the
    status code is still negotiable.

    Args:
        db: The active session.
        chat: The chat being answered, already ownership-checked.
        user_id: The caller, for the profile lookup.
        kind: ``chat`` for a conversational reply, otherwise the document type.
        user_message: The message that triggered this turn, already persisted.

    Returns:
        An async iterator of text chunks.
    """
    profile = profile_service.get_profile(db, user_id)
    profile_json = profile.parsed_json if profile else None
    analysis = analysis_service.get_analysis(db, chat.id)
    history = chat_service.history_for_context(db, chat.id)

    if kind == chat_service.INTENT_CHAT:
        # The blocking Groq iterator is pumped on a worker thread so it never
        # stalls the event loop mid-stream.
        return iterate_in_threadpool(
            chat_service.stream_chat_reply(
                build_messages(profile_json, chat.jd_text, analysis, history)
            )
        )

    return output_service.generate_output(
        kind,
        profile_json=profile_json,
        jd_text=chat.jd_text,
        analysis=analysis,
        history=history,
        user_message=user_message,
    )


async def assistant_event_stream(
    db: Session,
    chat_id: uuid.UUID,
    kind: str,
    tokens: AsyncIterator[str],
    assistant_id: uuid.UUID | None = None,
) -> AsyncIterator[str]:
    """Yield the SSE events for one assistant reply, and persist it.

    Shared by the intent path and the explicit ``/outputs`` path, so the wire
    format has exactly one definition.

    A document kind persists three things in one commit -- the message, the
    ``generated_outputs`` row, and the resume flip -- and reports the new
    output's id on ``done``. A stream that failed part-way persists only the
    message: half a resume is worth leaving on screen, but not worth filing in
    the user's outputs as a finished document.

    Args:
        db: The active session.
        chat_id: The chat being answered.
        kind: ``chat`` or one of the output types.
        tokens: The chunks to stream.
        assistant_id: Pre-chosen message id, generated here when omitted. It is
            announced on ``start`` before there is anything to store, so the id
            the frontend streams into is the id the row is saved under.

    Yields:
        Rendered SSE events.
    """
    message_id = assistant_id or uuid.uuid4()

    yield sse_event({"type": "start", "message_id": str(message_id), "kind": kind})

    parts: list[str] = []
    try:
        async for token in tokens:
            parts.append(token)
            yield sse_event({"type": "token", "content": token})
    except Exception:  # noqa: BLE001 - reported to the client as an error event
        logger.exception("Streaming reply failed for chat %s", chat_id)
        text = "".join(parts)
        if text:
            await run_in_threadpool(
                chat_service.save_message,
                db,
                chat_id,
                "assistant",
                text,
                kind,
                message_id,
            )
        yield sse_event(
            {
                "type": "error",
                "message": STREAM_FAILED,
                "message_id": str(message_id),
                "partial": bool(text),
                "content": text,
            }
        )
        return

    text = "".join(parts)
    if not text:
        yield sse_event(
            {
                "type": "error",
                "message": EMPTY_REPLY,
                "message_id": str(message_id),
                "partial": False,
                "content": "",
            }
        )
        return

    done: dict[str, Any] = {
        "type": "done",
        "message_id": str(message_id),
        "content": text,
    }

    if kind in chat_service.OUTPUT_INTENTS:
        _, output, entry = await run_in_threadpool(
            output_service.save_output_turn, db, chat_id, kind, text, message_id
        )
        done["output_id"] = str(output.id)
        if kind == chat_service.INTENT_RESUME:
            done["resume_type"] = (
                entry.resume_type
                if entry is not None
                else output_service.RESUME_TYPE_TAILORED
            )
    else:
        await run_in_threadpool(
            chat_service.save_message,
            db,
            chat_id,
            "assistant",
            text,
            kind,
            message_id,
        )

    yield sse_event(done)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("/{chat_id}/messages", response_model=list[MessageResponse])
def list_messages(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
) -> list[MessageResponse]:
    """Return the full message history for a chat, oldest first."""
    chat = require_chat(db, chat_id, user_id)
    return [
        MessageResponse.model_validate(message)
        for message in chat_service.list_messages(db, chat.id)
    ]


@router.post("/{chat_id}/messages")
def create_message(
    chat_id: uuid.UUID,
    payload: MessageRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """Store the user message and stream the assistant reply over SSE.

    Ownership, the user message, and the intent classification are all resolved
    *before* the response starts: once the first byte is on the wire the status
    code is fixed at 200, so a 404 has to happen here or not at all.

    Raises:
        HTTPException: 404 when the chat is not the caller's, 422 when the
            message is blank.
    """
    chat = require_chat(db, chat_id, user_id)

    content = payload.content.strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, EMPTY_MESSAGE)

    # Persisted first: the user's own words survive even if the model call fails
    # a moment later, and the history the model reads includes this turn.
    chat_service.save_message(db, chat.id, "user", content, kind="chat")

    kind = chat_service.detect_intent(content)
    tokens = open_token_stream(db, chat, user_id, kind, content)

    return StreamingResponse(
        assistant_event_stream(db, chat.id, kind, tokens),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
