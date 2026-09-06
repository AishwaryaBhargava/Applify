"""Job chats: persistence, intent detection, and the streamed Groq reply.

Three responsibilities, in the order a request meets them:

1. **Persistence.** Every read and write of a chat, its messages, and its
   tracker entry goes through the thin helpers here, so the routes stay
   translation-only. Every query filters on ``user_id`` and, for chats,
   ``deleted_at IS NULL`` -- a chat that is not yours does not exist.
2. **Intent detection.** A user message is classified as ``chat``, ``resume``,
   ``cover_letter``, or ``answer``. Rules first, a one-line Groq call only when
   the rules are genuinely unsure. Most turns cost nothing.
3. **Streaming.** The conversational reply is streamed through
   ``services.llm``, which prefers Groq and falls back to Azure GPT-4o when
   Groq is capped before the first token; the route wraps the chunks as SSE
   events.

Ids and timestamps are assigned here rather than left to the column defaults, so
a freshly created row is complete without a post-commit refresh round trip --
the same convention ``profile_service`` uses.
"""

import logging
import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.job_chat import JobChat
from app.models.tracker_entry import TrackerEntry
from app.services import llm
from app.services.groq_client import MIN_MAX_TOKENS, get_groq_client, get_groq_model
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Conversational, not creative. High enough not to read like a form letter, low
# enough that it keeps answering the question it was asked.
CHAT_TEMPERATURE = 0.6

# gpt-oss spends part of its budget reasoning before it emits a token, so a
# chat reply needs real headroom or it arrives truncated.
CHAT_MAX_TOKENS = 2048

# --------------------------------------------------------------------------
# Intent
# --------------------------------------------------------------------------

INTENT_CHAT = "chat"
INTENT_RESUME = "resume"
INTENT_COVER_LETTER = "cover_letter"
INTENT_ANSWER = "answer"

INTENTS: tuple[str, ...] = (INTENT_CHAT, INTENT_RESUME, INTENT_COVER_LETTER, INTENT_ANSWER)

# Intents that are handed to output_service instead of being answered in chat.
OUTPUT_INTENTS: tuple[str, ...] = (INTENT_RESUME, INTENT_COVER_LETTER, INTENT_ANSWER)

# Naming a document is a topic ("should I mention my resume gap?"); naming one
# next to a generation verb or a request marker is an ask.
_COVER_LETTER_RE = re.compile(
    r"\b(cover|covering|motivation)\s*-?\s*letter\b|\bcoverletter\b"
)
_RESUME_NOUN_RE = re.compile(r"\b(resume|resum[eé]|cv)\b")
_ACTION_RE = re.compile(
    r"\b(tailor|tailored|tailoring|customi[sz]e|customi[sz]ed|optimi[sz]e|optimi[sz]ed"
    r"|rewrite|rewriting|rework|revamp|adapt|adjust|update|write|draft|generate"
    r"|create|build|make|produce|prepare|compose)\b"
)
# "I need", not "they need": whose need it is decides whether this is a request.
_REQUEST_MARKER_RE = re.compile(
    r"\b(can you|could you|would you|will you|please|i need|i want|i'd like"
    r"|give me|send me|help me with)\b"
)

_ANSWER_RE = re.compile(
    r"\b(answer|respond)\s+(this|that|the|these|those|it)\b"
    r"|\bhow (should|do|would|can) i (answer|respond)\b"
    r"|\bhelp me (answer|respond)\b"
    r"|\b(application|screening|interview) question\b"
    r"|\b(draft|write|give me) (an?|my) (answer|response)\b"
    r"|\bwhat should i (say|write|put)\b"
)

# Words that mean the message is *about* one of the output types even when the
# phrasing does not match a rule. Their presence is what makes a message
# ambiguous rather than plainly conversational.
_AMBIGUOUS_RE = re.compile(
    r"\b(resume|resum[eé]|cv|cover letter|letter|answer|answering|question|apply|application)\b"
)

INTENT_CLASSIFIER_PROMPT = """Classify the user's message by what they are \
asking for in a job-application assistant. Reply with exactly one word:

chat - a question, a comment, or a request for advice or discussion
resume - they want a resume written, tailored, or rewritten
cover_letter - they want a cover letter written
answer - they want help answering a specific application or interview question

One word, nothing else."""


def detect_intent_rules(message: str) -> str | None:
    """Classify a message using cheap deterministic rules.

    Returns:
        One of ``INTENTS`` when the rules are confident, or None when the
        message mentions an output type without clearly asking for one -- the
        only case worth spending a model call on.
    """
    text = " ".join((message or "").lower().split())
    if not text:
        return INTENT_CHAT

    asking = bool(_ACTION_RE.search(text) or _REQUEST_MARKER_RE.search(text))

    # Checked first: "write a cover letter using my resume" is a cover letter
    # request, not a resume request.
    if asking and _COVER_LETTER_RE.search(text):
        return INTENT_COVER_LETTER

    if asking and _RESUME_NOUN_RE.search(text):
        return INTENT_RESUME

    if _ANSWER_RE.search(text):
        return INTENT_ANSWER

    # No output vocabulary at all -- plainly a conversational turn.
    if not _AMBIGUOUS_RE.search(text):
        return INTENT_CHAT

    return None


@retry_with_backoff(max_attempts=2, base_delay=0.5)
def _call_groq_classifier(message: str) -> str:
    """Ask Groq for a one-word intent label."""
    completion = get_groq_client().chat.completions.create(
        model=get_groq_model(),
        messages=[
            {"role": "system", "content": INTENT_CLASSIFIER_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0,
        max_tokens=MIN_MAX_TOKENS,
    )
    return completion.choices[0].message.content or ""


def detect_intent(message: str) -> str:
    """Classify a user message as chat, resume, cover_letter, or answer.

    Rules decide the clear cases for free. Only a message that mentions an
    output type without clearly requesting one reaches the model, and if that
    call fails the message is treated as chat -- answering conversationally when
    the user wanted a document is a far cheaper mistake than generating a
    document they did not ask for.
    """
    ruled = detect_intent_rules(message)
    if ruled is not None:
        return ruled

    try:
        raw = _call_groq_classifier(message)
    except Exception:
        logger.exception("Groq intent classification failed; defaulting to chat")
        return INTENT_CHAT

    label = raw.strip().strip(".").strip('"').lower().replace(" ", "_").replace("-", "_")
    for intent in OUTPUT_INTENTS:
        if intent in label:
            return intent
    return INTENT_CHAT


# --------------------------------------------------------------------------
# Streaming
# --------------------------------------------------------------------------


def chat_provider() -> str:
    """Return the provider chat should try first.

    Read per call rather than at import so flipping ``LLM_PREFER_AZURE_FOR_CHAT``
    takes effect on a restart with no code change -- the escape hatch for a day
    when Groq is capped from the first message and paying the fallback's failed
    first attempt on every turn is not worth it.
    """
    return llm.AZURE if settings.llm_prefer_azure_for_chat else llm.GROQ


def stream_chat_reply(messages: list[dict[str, str]]) -> Iterator[str]:
    """Stream the assistant reply token by token.

    Groq serves chat by default; ``services.llm`` falls back to Azure GPT-4o if
    Groq is rate-limited *before the first token*. After the first token the
    error stands: switching models mid-reply would splice two different answers
    together in front of the user.

    Args:
        messages: An OpenAI-style messages list, as built by
            ``utils.context_builder.build_messages``.

    Returns:
        A ``llm.ProviderStream`` of non-empty text chunks -- an iterator the
        route wraps as SSE events, whose ``provider`` attribute names whoever
        served it once the first chunk has arrived.
    """
    return llm.stream_text(
        messages,
        max_tokens=CHAT_MAX_TOKENS,
        temperature=CHAT_TEMPERATURE,
        prefer=chat_provider(),
        purpose="chat",
        max_attempts=3,
        base_delay=1.0,
    )


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    """Coerce a Supabase ``sub`` claim (a string) into a UUID."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def create_chat(
    db: Session,
    user_id: uuid.UUID | str,
    title: str,
    company: str | None = None,
    jd_text: str | None = None,
    job_url: str | None = None,
    location: str | None = None,
    source: str | None = None,
) -> tuple[JobChat, TrackerEntry]:
    """Create a job chat and open its tracker entry in one transaction.

    The tracker entry is never created by hand: a chat is an application the
    user is considering, so the row exists from the moment the chat does. Both
    inserts share one commit -- a chat without a tracker entry would be invisible
    in the tracker forever.

    ``job_url``, ``location`` and ``source`` describe the *application* rather
    than the conversation, so they are written onto the tracker row even though
    they arrive with the chat. Capturing them at creation is the whole point:
    the user has the posting open in the next tab exactly once.

    Returns:
        The new ``(chat, tracker_entry)`` pair.
    """
    now = datetime.now(timezone.utc)
    owner = _as_uuid(user_id)

    chat = JobChat(
        id=uuid.uuid4(),
        user_id=owner,
        title=title,
        company=company,
        jd_text=jd_text,
        analysis_type=None,
        created_at=now,
        deleted_at=None,
        keyword_match=None,
    )
    entry = TrackerEntry(
        id=uuid.uuid4(),
        chat_id=chat.id,
        user_id=owner,
        status="not_applied",
        resume_type="unaltered",
        job_url=job_url,
        location=location,
        source=source,
        created_at=now,
        updated_at=now,
    )

    db.add(chat)
    db.add(entry)
    db.commit()
    return chat, entry


def get_chat_for_user(
    db: Session,
    chat_id: uuid.UUID,
    user_id: uuid.UUID | str,
) -> JobChat | None:
    """Return a chat only if it belongs to this user and is not deleted.

    Ownership and soft deletion are checked in the query, not afterwards, so
    there is no code path where a row belonging to someone else is loaded and
    then discarded. Callers turn a None into a 404 -- never a 403, which would
    confirm the chat exists.
    """
    return (
        db.query(JobChat)
        .filter(
            JobChat.id == chat_id,
            JobChat.user_id == _as_uuid(user_id),
            JobChat.deleted_at.is_(None),
        )
        .first()
    )


def list_chats_for_user(db: Session, user_id: uuid.UUID | str) -> list[JobChat]:
    """Return a user's live chats, newest first."""
    return (
        db.query(JobChat)
        .filter(JobChat.user_id == _as_uuid(user_id), JobChat.deleted_at.is_(None))
        .order_by(JobChat.created_at.desc())
        .all()
    )


def soft_delete_chat(db: Session, chat: JobChat) -> JobChat:
    """Stamp ``deleted_at`` so the chat drops out of every list.

    The row stays: its tracker entry is part of the user's application history,
    and a hard delete would cascade it away.
    """
    chat.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return chat


def save_keyword_match(
    db: Session,
    chat: JobChat,
    result: dict,
) -> JobChat:
    """Store the latest ATS keyword match on a chat, replacing any previous one.

    There is only ever one live result per chat: a re-run answers the same
    question with fresher inputs, and keeping the stale answer next to it would
    only ever be read by mistake.
    """
    chat.keyword_match = result
    db.commit()
    return chat


def get_tracker_entry(db: Session, chat_id: uuid.UUID) -> TrackerEntry | None:
    """Return the tracker entry for a chat, if one exists."""
    return db.query(TrackerEntry).filter(TrackerEntry.chat_id == chat_id).first()


def tracker_entries_by_chat(
    db: Session,
    user_id: uuid.UUID | str,
) -> dict[uuid.UUID, TrackerEntry]:
    """Return this user's tracker entries keyed by chat id.

    One query for the whole sidebar rather than one per chat.
    """
    rows = (
        db.query(TrackerEntry).filter(TrackerEntry.user_id == _as_uuid(user_id)).all()
    )
    return {row.chat_id: row for row in rows}


def list_messages(db: Session, chat_id: uuid.UUID) -> list[ChatMessage]:
    """Return a chat's message history, oldest first."""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


def save_message(
    db: Session,
    chat_id: uuid.UUID,
    role: str,
    content: str,
    kind: str = "chat",
    message_id: uuid.UUID | None = None,
) -> ChatMessage:
    """Persist a single message on a chat.

    Args:
        db: The active session.
        chat_id: The chat the message belongs to.
        role: ``"user"`` or ``"assistant"``.
        content: The message text.
        kind: What produced it -- ``chat``, ``analysis``, ``resume``,
            ``cover_letter``, or ``answer``.
        message_id: Pre-assigned id. The streaming route announces the assistant
            message's id in its ``start`` event, before there is anything to
            store, so it has to choose the id up front.

    Returns:
        The stored message.
    """
    message = ChatMessage(
        id=message_id or uuid.uuid4(),
        chat_id=chat_id,
        role=role,
        content=content,
        kind=kind,
        created_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    return message


def history_for_context(db: Session, chat_id: uuid.UUID) -> list[dict[str, str]]:
    """Return the chat history in the ``{"role", "content"}`` shape the context
    builder takes, oldest first.

    Analysis and generated-document messages are included: they are part of what
    the user can see on screen, so the model has to know it already said them.
    """
    return [
        {"role": message.role, "content": message.content}
        for message in list_messages(db, chat_id)
    ]
