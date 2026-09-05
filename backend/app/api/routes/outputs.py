"""Output routes: generate a tailored resume, cover letter, or answer.

``POST /chats/{id}/outputs`` is the explicit-button path. The same three
documents are reachable by simply asking for them in chat -- the intent router
in ``POST /chats/{id}/messages`` classifies the request and streams it under the
matching ``kind`` -- and both paths must behave identically, because the user can
mix them freely inside one thread.

So this route does exactly two things the message route does not: it takes the
document type from the request body instead of inferring it, and it writes the
user turn the button implies ("Generate a tailored resume") so the thread still
reads as a conversation. Everything after that -- the context, the Azure call,
the SSE frames, the persistence, the tracker flip -- is the message route's own
:func:`~app.api.routes.messages.open_token_stream` and
:func:`~app.api.routes.messages.assistant_event_stream`, reused verbatim.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.routes.chats import require_chat
from app.api.routes.messages import (
    SSE_HEADERS,
    assistant_event_stream,
    open_token_stream,
)
from app.api.schemas.outputs import OutputRequest, OutputResponse
from app.data.deps import CurrentUser, DbSession
from app.services import chat_service, output_service

router = APIRouter(prefix="/chats", tags=["outputs"])

# The user turn each button stands for. Written into the thread so a document
# never appears as an assistant message answering nothing.
BUTTON_MESSAGES: dict[str, str] = {
    output_service.OUTPUT_RESUME: "Generate a tailored resume for this role",
    output_service.OUTPUT_COVER_LETTER: "Write a cover letter for this role",
    output_service.OUTPUT_ANSWER: "Answer this application question",
}


def button_message(output_type: str, user_context: str | None) -> str:
    """Compose the user message an output button stands for.

    The context is joined with a colon rather than a full stop so an ``answer``
    request comes out as "Answer this application question: <question>" -- the
    exact shape ``output_service.extract_question`` reads, and the same shape a
    user typing the request by hand would produce.
    """
    base = BUTTON_MESSAGES[output_type]
    context = (user_context or "").strip()
    return "{}: {}".format(base, context) if context else base


@router.post("/{chat_id}/outputs")
def create_output(
    chat_id: uuid.UUID,
    payload: OutputRequest,
    user_id: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """Generate a resume, cover letter, or application answer via Azure GPT-4o.

    Answers with the same SSE stream as ``POST /chats/{id}/messages``, with
    ``kind`` fixed to the requested ``output_type``. On ``done`` the event also
    carries ``output_id``, and for a resume the tracker's new ``resume_type``.

    Raises:
        HTTPException: 404 when the chat is not the caller's. An unknown
            ``output_type`` is a 422 from the schema.
    """
    chat = require_chat(db, chat_id, user_id)

    kind = payload.output_type.value
    content = button_message(kind, payload.user_context)

    # Persisted before the stream opens, exactly as the message route does, so
    # the generation reads it as the latest turn of the conversation.
    chat_service.save_message(db, chat.id, "user", content, kind="chat")

    state: dict[str, Any] = {}
    tokens = open_token_stream(db, chat, user_id, kind, content, state)

    return StreamingResponse(
        assistant_event_stream(db, chat.id, kind, tokens, state=state),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/{chat_id}/outputs", response_model=list[OutputResponse])
def list_outputs(
    chat_id: uuid.UUID,
    user_id: CurrentUser,
    db: DbSession,
) -> list[OutputResponse]:
    """List the outputs already generated for this chat, newest first.

    Raises:
        HTTPException: 404 when the chat is not the caller's.
    """
    chat = require_chat(db, chat_id, user_id)
    return [
        OutputResponse.model_validate(output)
        for output in output_service.list_outputs(db, chat.id)
    ]
