"""Resume, cover letter, and application answer generation via Azure GPT-4o.

All three outputs share one shape: a system prompt that fixes the document type
and the no-fabrication rule, and a user prompt carrying the profile, the JD, the
analysis (when one exists), the conversation so far, and the user's own request.
Only the system prompt differs between kinds -- the grounding material is
identical, because the whole point is that every document says the same true
things about the same person.

Azure GPT-4o is the model for all three: these are the longest, most structured
things the backend writes, and quality matters more than the second or two Groq
would save. The initial call is wrapped in ``utils.retry.retry_with_backoff``
because GPT-4o enforces per-minute token limits and a document request is
expensive enough to be worth retrying rather than failing.

The public seam is :func:`generate_output`, an async generator. Both the intent
path (``POST /chats/{id}/messages``) and the explicit-button path
(``POST /chats/{id}/outputs``) consume it, so there is exactly one place where a
document is written.

:func:`save_output_turn` is the other half of the seam: on a completed stream it
writes the assistant message, the ``generated_outputs`` row, and -- for a resume
-- the tracker's ``resume_type`` flip in a single commit. A document the user can
see in the thread but cannot find in their outputs list, or a tailored resume the
tracker still calls unaltered, would both be worse than no document at all.
"""

import logging
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.models.chat_message import ChatMessage
from app.models.generated_output import GeneratedOutput
from app.models.tracker_entry import TrackerEntry
from app.services.azure_client import get_azure_client, get_deployment_name
from app.utils.context_builder import (
    apply_sliding_window,
    count_words,
    format_analysis,
    format_jd,
    format_messages,
    format_profile,
)
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

OUTPUT_RESUME = "resume"
OUTPUT_COVER_LETTER = "cover_letter"
OUTPUT_ANSWER = "answer"

OUTPUT_TYPES: tuple[str, ...] = (OUTPUT_RESUME, OUTPUT_COVER_LETTER, OUTPUT_ANSWER)

# The tracker's resume_type once a resume has been generated in that chat.
RESUME_TYPE_TAILORED = "tailored"

# Warm but not florid. Low enough that the model keeps rephrasing the profile
# rather than inventing around it; high enough that a cover letter does not read
# like a template.
OUTPUT_TEMPERATURE = 0.4

# A full tailored resume is the longest thing the backend produces.
OUTPUT_MAX_TOKENS = 3000

# Words of context to assemble. Larger than the chat budget: generation is a
# one-shot call with no follow-up turns to pay for, and a resume that misses a
# role because the window clipped it is a bug the user can see.
OUTPUT_MAX_WORDS = 6000


class OutputError(Exception):
    """Raised when Azure is unreachable or returns nothing usable."""


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

# Repeated verbatim in all three system prompts. The rule is the product: an
# application document that invents a credential is worse than no document.
_GROUNDING = """Ground every single statement in the CANDIDATE PROFILE below. \
Never invent or embellish employers, job titles, dates, durations, degrees, \
institutions, certifications, tools, technologies, metrics, or numbers. If the \
job asks for something the profile does not evidence, leave it out -- do not \
imply it, and do not soften it into a claim. You may reword, reorder, \
reprioritise, and choose what to emphasise; you may not add facts.

Write in Markdown. Output only the document itself -- no preamble, no \
commentary about what you did, no closing offer to revise."""

RESUME_SYSTEM_PROMPT = """You are writing a tailored resume for one candidate \
applying to one specific job.

{grounding}

Produce a complete, ready-to-send resume, ordered and worded for this job \
description:

- Start with the candidate's name as an H1 if the profile gives one, followed \
by their contact details on one line if present. Omit anything not in the \
profile.
- Then these sections, in this order, each as an H2: Summary, Experience, \
Skills, Education, Projects, Certifications. Omit any section the profile has \
no content for -- never emit an empty section or a placeholder.
- Summary: three or four lines positioning this candidate for this role, built \
only from what the profile already says.
- Experience: every role in the profile, newest first, with title, employer, \
and dates exactly as the profile records them. Within each role, reorder the \
highlights so the ones this job cares about come first, and rephrase them in \
the job description's own vocabulary -- the same fact, said in the words the \
hiring team uses. A rephrased highlight must remain factually identical to the \
original: same scope, same numbers, same technologies.
- Skills: the profile's skills, grouped sensibly, with the ones the job names \
listed first. Do not add a skill the profile does not list.
- Education, Projects, Certifications: as recorded, with the entries most \
relevant to this job first.

Match the job description's terminology wherever the profile supports it, so \
the resume reads as though it were written for this posting."""

COVER_LETTER_SYSTEM_PROMPT = """You are writing a cover letter for one \
candidate applying to one specific job.

{grounding}

Produce three or four paragraphs:

- Address the letter to the company and the role by name, taken from the job \
description. If the job description does not name the company, address the \
role alone -- never guess a company or a hiring manager's name.
- Open by naming the role and giving the single strongest reason this \
candidate fits it, drawn from their actual experience.
- In the middle paragraphs, connect two or three specific things from the \
profile -- named roles, projects, or results -- to what this job actually asks \
for. Be concrete: name the employer, the project, the number the profile gives.
- If an analysis of this candidate's fit is provided below, let its strengths \
decide which experiences you lead with. Do not mention the analysis, quote it, \
or refer to scores or gaps.
- If the user has given extra context or a steer with their request, work it \
into the letter naturally -- but only as far as the profile supports it. If \
they ask you to emphasise something the profile does not evidence, emphasise \
the nearest thing it does.
- Close with a brief, plain statement of interest and availability. No \
flattery, no filler, no restating the resume line by line.

Keep it under 400 words unless the user asks for a different length."""

ANSWER_SYSTEM_PROMPT = """You are helping one candidate answer a written \
application or screening question for one specific job.

{grounding}

The question the candidate needs answered is given below.

- Answer the question that was actually asked, in the first person, as the \
candidate. No preamble, no restating the question, no "Here is your answer".
- Draw every specific -- employer, project, technology, number, timeframe -- \
from the profile. If the question asks about something the profile does not \
cover, answer from what the profile does support and say plainly what you \
cannot speak to, rather than inventing an example.
- Be concrete and concise. One point, evidenced, beats three asserted.
- Aim for 120 to 250 words unless the candidate asks for a different length, \
in which case follow their instruction.
- If no question can be found in the request, do not guess: say so in one line \
and ask the candidate to paste the question.

Plain prose. Use a short list only if the question genuinely asks for one."""

SYSTEM_PROMPTS: dict[str, str] = {
    OUTPUT_RESUME: RESUME_SYSTEM_PROMPT.format(grounding=_GROUNDING),
    OUTPUT_COVER_LETTER: COVER_LETTER_SYSTEM_PROMPT.format(grounding=_GROUNDING),
    OUTPUT_ANSWER: ANSWER_SYSTEM_PROMPT.format(grounding=_GROUNDING),
}


def system_prompt_for(output_type: str) -> str:
    """Return the system prompt for an output type.

    Raises:
        OutputError: If ``output_type`` is not one of ``OUTPUT_TYPES``.
    """
    try:
        return SYSTEM_PROMPTS[output_type]
    except KeyError:
        raise OutputError("Unknown output type: {!r}".format(output_type)) from None


# --------------------------------------------------------------------------
# The question inside an answer request
# --------------------------------------------------------------------------

# "Answer this question: <question>" -- the marker phrase and the colon are what
# separate the user's instruction from the question they pasted after it.
_QUESTION_MARKER_RE = re.compile(
    r"\b(?:"
    r"answer(?:\s+(?:this|that|the following|the))?(?:\s+\w+){0,2}?\s*question"
    r"|answer\s+(?:this|that|the following)"
    r"|respond\s+to\s+(?:this|that|the following)(?:\s+\w+){0,2}?"
    r"|(?:the\s+|this\s+)?(?:application|screening|interview)\s+question(?:\s+is)?"
    r"|the\s+question(?:\s+is)?"
    r"|help\s+me\s+(?:answer|respond\s+to)(?:\s+\w+){0,2}?"
    r")\s*[:\-—]\s*",
    re.IGNORECASE,
)


def extract_question(user_message: str | None) -> str:
    """Pull the application question out of the message that asked for an answer.

    Users paste questions two ways: with a lead-in ("answer this question: why
    do you want to work here?") or on their own. The lead-in, when present, is
    the user's instruction to us rather than part of the question, so it is
    stripped -- everything after the marker's colon is the question.

    Args:
        user_message: The message that triggered the generation.

    Returns:
        The question text, or the whole message when there is no marker, or an
        empty string when there is nothing at all.
    """
    text = (user_message or "").strip()
    if not text:
        return ""

    match = _QUESTION_MARKER_RE.search(text)
    if match:
        tail = text[match.end() :].strip().strip('"').strip()
        if tail:
            return tail
    return text


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------


def build_output_prompt(
    output_type: str,
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    analysis: Any = None,
    history: list[dict[str, str]] | None = None,
    user_message: str | None = None,
) -> str:
    """Assemble the user-side prompt for the requested output type.

    The profile goes in as raw JSON rather than the chat summary: generation
    reads it field by field, and a resume that drops a role because the summary
    capped the list at six is a defect the user can see. The JD and profile are
    never trimmed; only conversation history is windowed.

    Args:
        output_type: ``resume``, ``cover_letter``, or ``answer``.
        profile_json: The user's structured profile.
        jd_text: This chat's job description.
        analysis: The stored analysis for this chat, if one has been run.
        history: Chat history, oldest first, including the triggering message.
        user_message: The message that triggered the generation.

    Returns:
        The prompt string to send as the user turn.
    """
    blocks = [format_profile(profile_json), format_jd(jd_text)]

    analysis_block = format_analysis(analysis)
    if analysis_block:
        blocks.append(analysis_block)

    fixed = sum(count_words(block) for block in blocks)
    windowed = apply_sliding_window(history or [], OUTPUT_MAX_WORDS - fixed)
    blocks.append(format_messages(windowed))

    request = (user_message or "").strip()
    if output_type == OUTPUT_ANSWER:
        question = extract_question(request)
        blocks.append(
            "APPLICATION QUESTION TO ANSWER:\n{}".format(
                question or "(none supplied)"
            )
        )
        if request and question != request:
            blocks.append("THE CANDIDATE'S FULL REQUEST:\n{}".format(request))
    else:
        blocks.append(
            "THE CANDIDATE'S REQUEST:\n{}".format(
                request or "(no additional instructions)"
            )
        )

    blocks.append(
        "Now write the {}.".format(output_type.replace("_", " "))
    )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# Streaming
# --------------------------------------------------------------------------


@retry_with_backoff(max_attempts=4, base_delay=1.0)
def _open_output_stream(output_type: str, prompt: str) -> Any:
    """Open the Azure streaming completion for one document.

    Separate from the generator below so the retry decorator wraps the network
    call itself: decorating a generator function would only retry building the
    generator object, which never fails.
    """
    return get_azure_client().chat.completions.create(
        model=get_deployment_name(),
        messages=[
            {"role": "system", "content": system_prompt_for(output_type)},
            {"role": "user", "content": prompt},
        ],
        temperature=OUTPUT_TEMPERATURE,
        max_tokens=OUTPUT_MAX_TOKENS,
        stream=True,
    )


def stream_output(
    output_type: str,
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    analysis: Any = None,
    history: list[dict[str, str]] | None = None,
    user_message: str | None = None,
) -> Iterator[str]:
    """Stream generated document text from Azure GPT-4o.

    Blocking: the OpenAI SDK's stream is a synchronous iterator.
    :func:`generate_output` pumps it on a worker thread.

    Yields:
        Non-empty text chunks, ready to be wrapped as SSE events by the route.
    """
    prompt = build_output_prompt(
        output_type,
        profile_json,
        jd_text,
        analysis=analysis,
        history=history,
        user_message=user_message,
    )
    for chunk in _open_output_stream(output_type, prompt):
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            # Azure's content filter emits a leading chunk with no choices.
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if content:
            yield content


async def generate_output(
    kind: str,
    profile_json: dict[str, Any] | None = None,
    jd_text: str | None = None,
    analysis: Any = None,
    history: list[dict[str, str]] | None = None,
    user_message: str | None = None,
) -> AsyncIterator[str]:
    """Stream a generated document, token by token.

    The seam both output routes delegate to. The blocking Azure iterator is
    opened and drained on worker threads, so a slow first token never stalls the
    event loop that is serving every other request.

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

    Raises:
        OutputError: If ``kind`` is not a known output type.
    """
    system_prompt_for(kind)  # fail fast, before anything is streamed
    tokens = await run_in_threadpool(
        stream_output,
        kind,
        profile_json,
        jd_text,
        analysis,
        history,
        user_message,
    )
    async for chunk in iterate_in_threadpool(tokens):
        yield chunk


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def save_output_turn(
    db: Session,
    chat_id: uuid.UUID,
    output_type: str,
    content: str,
    message_id: uuid.UUID | None = None,
) -> tuple[ChatMessage, GeneratedOutput, TrackerEntry | None]:
    """Persist a finished document: the message, the output row, and the flip.

    One commit covers all three. A user who can see a tailored resume in the
    thread but not in their outputs list, or whose tracker still says
    "unaltered" after one was generated, is looking at a database that
    contradicts their screen.

    Args:
        db: The active session.
        chat_id: The chat the document belongs to.
        output_type: ``resume``, ``cover_letter``, or ``answer``.
        content: The full generated document.
        message_id: The id announced in the SSE ``start`` event, so the stored
            message is the one the frontend has been streaming into.

    Returns:
        ``(message, output, tracker_entry)``. The tracker entry is None unless
        this was a resume and the chat has one.
    """
    now = datetime.now(timezone.utc)

    message = ChatMessage(
        id=message_id or uuid.uuid4(),
        chat_id=chat_id,
        role="assistant",
        content=content,
        kind=output_type,
        created_at=now,
    )
    output = GeneratedOutput(
        id=uuid.uuid4(),
        chat_id=chat_id,
        output_type=output_type,
        content=content,
        created_at=now,
    )
    db.add(message)
    db.add(output)

    entry: TrackerEntry | None = None
    if output_type == OUTPUT_RESUME:
        entry = (
            db.query(TrackerEntry).filter(TrackerEntry.chat_id == chat_id).first()
        )
        if entry is not None:
            entry.resume_type = RESUME_TYPE_TAILORED
            entry.updated_at = now
        else:
            logger.warning("No tracker entry for chat %s; resume_type not set", chat_id)

    db.commit()
    return message, output, entry


def list_outputs(db: Session, chat_id: uuid.UUID) -> list[GeneratedOutput]:
    """Return the outputs already generated for a chat, newest first."""
    return (
        db.query(GeneratedOutput)
        .filter(GeneratedOutput.chat_id == chat_id)
        .order_by(GeneratedOutput.created_at.desc())
        .all()
    )
