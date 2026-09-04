"""Builds the AI context sent with every chat, analysis, and generation call.

This is the most important utility in the backend: it decides what the model
sees. The contract is deliberately narrow --

    profile + JD are always included, in full.
    Chat history is trimmed from the oldest end until the whole context fits
    ``max_words``.

Per the tech stack doc, the sliding window kicks in above 4000 words.
"""

import json
from typing import Any

# Words to keep in reserve for the system prompt and the model's own reply.
DEFAULT_MAX_WORDS = 4000


def count_words(text: str) -> int:
    """Rough word count used as a cheap proxy for token budget."""
    return len(text.split())


def format_profile(profile_json: dict[str, Any] | None) -> str:
    """Render the structured profile as a readable block for the prompt.

    Args:
        profile_json: The stored ``parsed_json`` for the user, or None.

    Returns:
        A ``PROFILE:``-prefixed block, or a placeholder when no profile exists.
    """
    if not profile_json:
        return "PROFILE:\n(no profile on file)"
    return "PROFILE:\n" + json.dumps(profile_json, indent=2, ensure_ascii=False)


def format_jd(jd_text: str | None) -> str:
    """Render the job description as a labelled block for the prompt."""
    if not jd_text:
        return "JOB DESCRIPTION:\n(no job description provided)"
    return "JOB DESCRIPTION:\n" + jd_text.strip()


def format_messages(messages: list[dict[str, str]]) -> str:
    """Render chat history as ``role: content`` lines."""
    if not messages:
        return "CONVERSATION:\n(no messages yet)"
    lines = [
        "{}: {}".format(m.get("role", "user").upper(), m.get("content", "").strip())
        for m in messages
    ]
    return "CONVERSATION:\n" + "\n".join(lines)


def apply_sliding_window(
    messages: list[dict[str, str]],
    budget_words: int,
) -> list[dict[str, str]]:
    """Drop the oldest messages until the history fits ``budget_words``.

    The most recent messages are always the ones kept: they carry the live
    thread of the conversation. At least the final message survives even if it
    alone exceeds the budget.

    Args:
        messages: Full history, oldest first.
        budget_words: Words available for history after profile and JD are counted.

    Returns:
        The trimmed history, still oldest first.
    """
    if budget_words <= 0:
        return messages[-1:] if messages else []

    kept: list[dict[str, str]] = []
    used = 0
    for message in reversed(messages):
        cost = count_words(message.get("content", "")) + 2  # + role label
        if kept and used + cost > budget_words:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    return kept


def build_context(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    messages: list[dict[str, str]] | None = None,
    max_words: int = DEFAULT_MAX_WORDS,
) -> str:
    """Assemble the full AI context string for a chat turn.

    Profile and JD are never trimmed. Chat history is windowed to whatever word
    budget remains under ``max_words``.

    Args:
        profile_json: The user's structured profile, or None.
        jd_text: The job description text for this chat, or None.
        messages: Chat history as ``{"role": ..., "content": ...}``, oldest first.
        max_words: Soft ceiling on the assembled context.

    Returns:
        The context string to prepend to the user's current message.
    """
    profile_block = format_profile(profile_json)
    jd_block = format_jd(jd_text)

    fixed_words = count_words(profile_block) + count_words(jd_block)
    history = apply_sliding_window(messages or [], max_words - fixed_words)

    return "\n\n".join([profile_block, jd_block, format_messages(history)])
