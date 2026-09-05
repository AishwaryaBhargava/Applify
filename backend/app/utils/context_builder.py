"""Builds the AI context sent with every chat, analysis, and generation call.

This is the most important utility in the backend: it decides what the model
sees. The contract is deliberately narrow --

    profile + JD (+ the analysis summary, once one exists) are always included.
    Chat history is trimmed from the oldest end until the whole context fits
    ``max_words``.

Per the tech stack doc, the sliding window kicks in above 4000 words.

Two renderings are offered:

* :func:`build_messages` -- an OpenAI-style ``messages`` list, which is what the
  chat endpoint sends to Groq. The fixed context lives in the system message, so
  windowing can only ever drop conversation turns.
* :func:`build_context` -- the same material as one string, for the prompt-shaped
  calls (analysis, generation) that are not multi-turn.

The profile is rendered as a compact summary rather than raw JSON: the JSON dump
of a full profile is mostly punctuation and key names, and every word of it
competes with the conversation for the window.
"""

import json
from typing import Any

from app.api.schemas.profile import ParsedProfile

# Words to keep in reserve for the system prompt and the model's own reply.
DEFAULT_MAX_WORDS = 4000

# How much of a long profile survives into the summary. A resume with 12 roles
# is real, but the oldest ones stop informing a fit judgement.
MAX_ROLES = 6
MAX_HIGHLIGHTS_PER_ROLE = 4
MAX_LIST_ITEMS = 12

# The persona. Proactive but not overwhelming: it offers the obvious next step
# once, and then follows the user. Grounding is stated as a hard rule because
# every downstream feature -- resume, cover letter, answers -- inherits it.
SYSTEM_PROMPT = """You are Applify, a job application co-pilot.

You are working with one user on one specific job opening. Their career profile
and the job description are given below and are the only facts you have about
them.

How you work:
- Ground every claim in the profile. Never invent experience, employers, dates,
  degrees, certifications, or numbers. If something is not in the profile, say
  so plainly and suggest how the user could supply it.
- Be direct and specific. Reference the user's actual roles, projects, and
  skills by name instead of speaking in generalities.
- Be proactive, but only once. After an analysis, offer the single most useful
  next step -- tailoring their resume, drafting a cover letter, or working
  through an application question. If the user does not take it up, drop it and
  follow where they lead. Never repeat an offer they have already passed on.
- Keep replies tight. A few short paragraphs or a short list, not an essay.
  Markdown is fine.
- You cannot browse, apply on the user's behalf, or contact anyone. Say so if
  asked.
"""


def count_words(text: str) -> int:
    """Rough word count used as a cheap proxy for token budget."""
    return len(text.split())


# --------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------


def _join(values: list[str], limit: int = MAX_LIST_ITEMS) -> str:
    """Render a list of short strings as a comma-separated line."""
    kept = [v for v in values if v][:limit]
    return ", ".join(kept)


def summarize_profile(profile_json: dict[str, Any] | None) -> str:
    """Render the structured profile as a compact, readable block.

    Args:
        profile_json: The stored ``parsed_json`` for the user, or None.

    Returns:
        A ``PROFILE:``-prefixed block, or a placeholder when no profile exists.
    """
    if not profile_json:
        return "PROFILE:\n(no profile on file)"

    profile = ParsedProfile.model_validate(profile_json)
    lines: list[str] = ["PROFILE:"]

    if profile.summary:
        lines.append("Summary: {}".format(profile.summary.strip()))

    if profile.skills:
        lines.append("Skills: {}".format(_join(profile.skills, limit=40)))

    if profile.work_experience:
        lines.append("Experience:")
        for role in profile.work_experience[:MAX_ROLES]:
            header = " - {} at {}".format(
                role.title or "Role", role.company or "an unnamed employer"
            )
            span = " to ".join(
                part
                for part in (
                    role.start_date,
                    "Present" if role.current else role.end_date,
                )
                if part
            )
            if span:
                header += " ({})".format(span)
            lines.append(header)
            for highlight in role.highlights[:MAX_HIGHLIGHTS_PER_ROLE]:
                if highlight.strip():
                    lines.append("   * {}".format(highlight.strip()))

    if profile.education:
        lines.append("Education:")
        for entry in profile.education[:MAX_LIST_ITEMS]:
            parts = [p for p in (entry.degree, entry.field, entry.institution) if p]
            tail = entry.end_date or entry.start_date
            line = " - {}".format(", ".join(parts) or "Education entry")
            if tail:
                line += " ({})".format(tail)
            lines.append(line)

    if profile.certifications:
        lines.append(
            "Certifications: {}".format(
                _join(
                    [
                        "{}{}".format(
                            cert.name or "",
                            " ({})".format(cert.year) if cert.year else "",
                        )
                        for cert in profile.certifications
                    ]
                )
            )
        )

    if profile.projects:
        lines.append("Projects:")
        for project in profile.projects[:MAX_LIST_ITEMS]:
            line = " - {}".format(project.name or "Project")
            if project.description:
                line += ": {}".format(project.description.strip())
            if project.technologies:
                line += " [{}]".format(_join(project.technologies))
            lines.append(line)

    if profile.achievements:
        lines.append("Achievements:")
        lines.extend(
            " - {}".format(item) for item in profile.achievements[:MAX_LIST_ITEMS]
        )

    return "\n".join(lines)


def format_profile(profile_json: dict[str, Any] | None) -> str:
    """Render the profile as raw JSON.

    Kept for the analysis prompts, where the model is asked to reason field by
    field and the explicit structure earns its tokens.
    """
    if not profile_json:
        return "PROFILE:\n(no profile on file)"
    return "PROFILE:\n" + json.dumps(profile_json, indent=2, ensure_ascii=False)


def format_jd(jd_text: str | None) -> str:
    """Render the job description as a labelled block for the prompt."""
    if not jd_text:
        return "JOB DESCRIPTION:\n(no job description provided)"
    return "JOB DESCRIPTION:\n" + jd_text.strip()


def _analysis_field(analysis: Any, name: str) -> Any:
    """Read a field off an analysis, whether it is a dict, a row, or a model."""
    if isinstance(analysis, dict):
        return analysis.get(name)
    return getattr(analysis, name, None)


def format_analysis(analysis: Any) -> str:
    """Render a completed analysis as its four-field summary.

    Args:
        analysis: An ``Analysis`` row, a dict, or None. Only the summary fields
            are used -- the full breakdown is far too long to carry into every
            conversational turn, and the user can already see it on screen.

    Returns:
        An ``ANALYSIS ALREADY SHOWN TO THE USER:`` block, or an empty string when
        no analysis has been run.
    """
    if analysis is None:
        return ""

    score = _analysis_field(analysis, "fit_score")
    strengths = _analysis_field(analysis, "strengths") or []
    gaps = _analysis_field(analysis, "gaps") or []
    verdict = _analysis_field(analysis, "verdict") or ""
    analysis_type = _analysis_field(analysis, "type") or "quick"

    lines = [
        "ANALYSIS ALREADY SHOWN TO THE USER ({}):".format(
            getattr(analysis_type, "value", analysis_type)
        )
    ]
    if score is not None:
        lines.append("Fit score: {}/100".format(score))
    if verdict:
        lines.append("Verdict: {}".format(verdict))
    if strengths:
        lines.append("Strengths:")
        lines.extend(" - {}".format(item) for item in strengths)
    if gaps:
        lines.append("Gaps:")
        lines.extend(" - {}".format(item) for item in gaps)
    lines.append(
        "Do not repeat this analysis back to the user unless they ask about it."
    )
    return "\n".join(lines)


def format_messages(messages: list[dict[str, str]]) -> str:
    """Render chat history as ``role: content`` lines."""
    if not messages:
        return "CONVERSATION:\n(no messages yet)"
    lines = [
        "{}: {}".format(m.get("role", "user").upper(), m.get("content", "").strip())
        for m in messages
    ]
    return "CONVERSATION:\n" + "\n".join(lines)


# --------------------------------------------------------------------------
# Windowing
# --------------------------------------------------------------------------


def apply_sliding_window(
    messages: list[dict[str, str]],
    budget_words: int,
) -> list[dict[str, str]]:
    """Drop the oldest messages until the history fits ``budget_words``.

    The most recent messages are always the ones kept: they carry the live
    thread of the conversation. At least the final message survives even if it
    alone exceeds the budget -- it is the message being answered.

    Args:
        messages: Full history, oldest first.
        budget_words: Words available for history after the fixed context is
            counted.

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


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def build_messages(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    analysis: Any = None,
    history: list[dict[str, str]] | None = None,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[dict[str, str]]:
    """Assemble the OpenAI-style ``messages`` list for one chat turn.

    The persona, the profile summary, the JD, and the analysis summary all go
    into a single system message, so the sliding window can only ever drop
    conversation turns -- the grounding material is structurally un-droppable.

    Args:
        profile_json: The user's structured profile, or None.
        jd_text: This chat's job description, or None.
        analysis: The stored analysis for this chat, or None.
        history: Chat history as ``{"role": ..., "content": ...}``, oldest first.
            The user's current message is expected to be the last entry.
        max_words: Soft ceiling on the whole assembled context.

    Returns:
        ``[{"role": "system", ...}, *windowed history]``.
    """
    blocks = [
        SYSTEM_PROMPT.strip(),
        summarize_profile(profile_json),
        format_jd(jd_text),
    ]
    analysis_block = format_analysis(analysis)
    if analysis_block:
        blocks.append(analysis_block)

    system_content = "\n\n".join(blocks)
    budget = max_words - count_words(system_content)

    windowed = apply_sliding_window(history or [], budget)
    return [{"role": "system", "content": system_content}] + [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in windowed
    ]


def build_context(
    profile_json: dict[str, Any] | None,
    jd_text: str | None,
    messages: list[dict[str, str]] | None = None,
    max_words: int = DEFAULT_MAX_WORDS,
) -> str:
    """Assemble the full AI context as a single string.

    Used by the prompt-shaped calls -- analysis and document generation -- where
    there is no multi-turn history to preserve. Profile and JD are never
    trimmed; chat history is windowed to whatever budget remains.

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
