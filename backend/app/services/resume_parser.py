"""Resume parsing: PDF and DOCX text extraction, then structured extraction.

Files are parsed in memory and discarded -- nothing is written to disk and no
file storage is used. Only the extracted text and its structured parse are
persisted, which is also why ``raw_text`` is stored alongside ``parsed_json``:
if the extraction prompt improves, every existing profile can be re-extracted
without asking anyone to re-upload.

The pipeline is deliberately two-stage:

1. Deterministic text extraction (pdfplumber / python-docx). No model involved,
   so a parsing bug is reproducible.
2. Structured extraction via ``services.llm`` -- Groq first, Azure GPT-4o when
   Groq is rate-limited. The model only ever reads text that stage 1 produced,
   and its output is coerced through
   :func:`app.api.schemas.profile.coerce_parsed_profile` before anyone sees it.
"""

import io
import json
import logging
import os
import re
from typing import Any

import pdfplumber
from docx import Document

from app.api.schemas.profile import ParsedProfile, coerce_parsed_profile
from app.services import llm

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/x-pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
}

# gpt-oss models spend a chunk of their budget reasoning before emitting the
# answer. Extraction returns a whole profile, so the ceiling has to be generous
# or the JSON comes back truncated.
#
# 4096 was enough for the original schema and stopped being enough once
# coursework, honors, project highlights and links, and publications were added:
# a dense two-page resume spends most of 4096 on reasoning and then runs out
# mid-object, which Groq reports as a 400 ``json_validate_failed`` rather than
# as a truncated answer.
#
# 16000 is the largest ceiling that is legal on *both* providers, which is the
# constraint that picks the number: the same budget is handed to the Azure
# fallback verbatim, and GPT-4o refuses anything over 16384 output tokens.
# Groq's openai/gpt-oss-120b allows far more (its 65536-token completion limit
# sits inside a 131072-token context), so this is well within what Groq accepts
# and is bounded by Azure.
EXTRACTION_MAX_TOKENS = 16000

# Deterministic extraction: the same resume should parse the same way twice.
EXTRACTION_TEMPERATURE = 0.1

# Resume text past this point is almost always appendix noise, and the tail of a
# 30-page document is not worth the latency.
MAX_RESUME_CHARS = 24000


class UnsupportedResumeFormat(Exception):
    """Raised when an uploaded file is neither a PDF nor a DOCX."""


class ResumeTextExtractionError(Exception):
    """Raised when a file is the right type but its text cannot be read."""


class EmptyResumeText(Exception):
    """Raised when a file parses cleanly but contains no usable text.

    Usually a scanned or image-only PDF. There is no OCR in the pipeline, so
    this is a dead end the user has to be told about explicitly.
    """


class ProfileExtractionError(Exception):
    """Raised when Groq cannot be reached or returns nothing usable."""


# --------------------------------------------------------------------------
# The extraction prompt
# --------------------------------------------------------------------------

# Kept as a module-level constant so it can be iterated on -- and diffed -- on
# its own. Per the pipeline doc this prompt is the single highest-leverage thing
# in Phase 4: every downstream analysis and generated document reads only what
# this produces.
EXTRACTION_SYSTEM_PROMPT = """\
You are a resume parser. You convert the plain text of one person's resume into \
structured JSON. You are an extractor, not a writer.

Return ONLY a JSON object with exactly these keys and no others:

{
  "summary": string,
  "work_experience": [
    {
      "title": string,
      "company": string,
      "location": string,
      "start_date": string,
      "end_date": string,
      "current": boolean,
      "employment_type": string,
      "highlights": [string],
      "awards": [string]
    }
  ],
  "education": [
    {
      "degree": string,
      "institution": string,
      "field": string,
      "start_date": string,
      "end_date": string,
      "details": string,
      "gpa": string,
      "coursework": [string],
      "honors": [string]
    }
  ],
  "skills": [string],
  "certifications": [
    {
      "name": string,
      "issuer": string,
      "year": string,
      "expires": string,
      "credential_url": string,
      "description": string
    }
  ],
  "projects": [
    {
      "name": string,
      "description": string,
      "technologies": [string],
      "start_date": string,
      "end_date": string,
      "highlights": [string],
      "link": string,
      "links": {"github": string, "live": string, "demo": string}
    }
  ],
  "achievements": [string],
  "publications": [
    {
      "title": string,
      "authors": string,
      "url": string,
      "status": string,
      "year": string
    }
  ]
}

Rules:

1. Extract only what is written in the resume. Never invent, infer, embellish, \
or fill a field with a plausible guess. If the resume does not state something, \
leave that string empty ("") and that array empty ([]).
2. Every key above must be present in your output, even when its value is empty.
3. summary: copy the resume's own professional summary, objective, or profile \
paragraph. If the resume has no such section, return "".
4. work_experience: one entry per role, in the order the resume lists them. \
Split a promotion within the same company into separate entries only when the \
resume lists them as separate roles. highlights are the bullet points for that \
role, each copied as its own string with leading bullet characters removed. \
Keep the numbers and metrics exactly as written. "employment_type" only when \
the resume states one ("Full-time", "Part-time", "Internship", "Contract", \
"Freelance"). "awards" holds recognition named for that specific role \
("Employee of the Quarter, 2023"); leave it empty unless the resume names one.
5. Dates stay as free text in the resume's own wording, e.g. "Jan 2022", \
"2019", "March 2020". Do not reformat them and do not compute durations. Set \
"current": true only when the role's end date reads as ongoing ("Present", \
"Current", "Till date", "-"), and in that case set end_date to "".
6. skills: short tokens only, one technology, tool, language, or named \
competency each -- "Python", "PostgreSQL", "Docker", "Stakeholder management". \
Never a sentence, never a comma-joined list in one string, never a proficiency \
level or a years-of-experience number. Split any grouped line like "Languages: \
Python, Go, SQL" into separate entries and drop the category label. De-duplicate.
7. education: one entry per qualification. "field" is the subject or major. \
"gpa" is the grade exactly as written, with its scale ("8.7/10", "3.8/4.0", \
"First Class"); never convert between scales. "coursework" and "honors" are \
lists of short names ("Distributed Systems", "Dean's List 2018"), not \
sentences. "details" keeps any remaining note that fits none of those.
8. certifications: only named certifications or licences. Do not promote a \
course, a workshop, or a degree into a certification. "expires" and \
"credential_url" only when the resume states them; "description" only when the \
resume adds a line about what the certification covers.
9. projects: personal, academic, or professional projects the resume names \
separately from a job. "technologies" follows the same short-token rule as \
skills. "highlights" are the project's bullet points -- key contributions and \
impact -- copied one per string. Put each URL in "links" under the slot that \
fits: a source repository in "github", a deployed site in "live", a video or \
walkthrough in "demo". Also set "link" to that same URL when the project has \
exactly one. Only URLs actually written in the resume.
10. achievements: awards, honours, competition results, and standalone \
accomplishments not already captured as a role's highlight or as a \
publication. When the resume gives an achievement a date or an awarding body, \
write it as "Name -- Organization (Date): description", dropping any part the \
resume does not state.
10a. publications: papers, articles, patents, preprints, and conference talks \
the person authored. "title" is required -- an entry without one is not a \
publication. "authors" is the author list as one string in the resume's own \
order. "status" is what the resume says ("Published", "Under review", \
"Accepted", "Preprint"). Return an empty array when the resume names none, \
which is the normal case.
11. Ignore contact details, page headers and footers, page numbers, and any \
"References available on request" line. Do not return name, email, phone, or \
address.
12. Preserve the resume's original wording. Fix only obvious extraction \
artefacts: ligature damage, a word split across a line break, and stray bullet \
glyphs.

Output the JSON object and nothing else. No prose, no explanation, no markdown \
code fences.\
"""

EXTRACTION_USER_TEMPLATE = "RESUME TEXT:\n\n{resume_text}"


# --------------------------------------------------------------------------
# Format detection
# --------------------------------------------------------------------------


def detect_format(filename: str | None, content_type: str | None = None) -> str:
    """Return ``"pdf"`` or ``"docx"`` for an uploaded file.

    The content type is checked first because it is what the browser asserts,
    with the filename extension as the fallback -- some clients send
    ``application/octet-stream`` for a perfectly good DOCX.

    Args:
        filename: The uploaded file's name, used for its extension.
        content_type: The multipart content type, if the client sent one.

    Returns:
        ``"pdf"`` or ``"docx"``.

    Raises:
        UnsupportedResumeFormat: If the file is neither format.
    """
    if content_type:
        # Strip any "; charset=..." parameter before matching.
        base_type = content_type.split(";")[0].strip().lower()
        if base_type in SUPPORTED_CONTENT_TYPES:
            return SUPPORTED_CONTENT_TYPES[base_type]

    if filename:
        extension = os.path.splitext(filename)[1].lower()
        if extension in SUPPORTED_EXTENSIONS:
            return SUPPORTED_EXTENSIONS[extension]

    raise UnsupportedResumeFormat(
        "Only PDF and DOCX resumes are supported. Received: {}".format(
            content_type or filename or "an unnamed file"
        )
    )


# --------------------------------------------------------------------------
# Text extraction
# --------------------------------------------------------------------------


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber.

    Every page is read and pages are joined with a blank line. Line breaks
    within a page are kept, because a resume's line structure is what tells the
    model where one bullet ends and the next begins.

    Raises:
        ResumeTextExtractionError: If the bytes are not a readable PDF.
    """
    pages: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
    except Exception as exc:  # pdfminer raises a wide range of parse errors
        raise ResumeTextExtractionError(
            "Could not read the PDF: {}".format(exc)
        ) from exc
    return "\n\n".join(pages).strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from DOCX bytes using python-docx.

    Reads body paragraphs and table cells. Tables matter: a good share of
    resumes lay out skills or dates in an invisible table, and paragraph-only
    extraction silently drops all of it.

    Raises:
        ResumeTextExtractionError: If the bytes are not a readable DOCX.
    """
    try:
        document = Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ResumeTextExtractionError(
            "Could not read the DOCX: {}".format(exc)
        ) from exc

    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            lines.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            # Cells merged across a row repeat their text; collapse the repeats.
            deduped: list[str] = []
            for cell in cells:
                if cell and (not deduped or deduped[-1] != cell):
                    deduped.append(cell)
            if deduped:
                lines.append(" | ".join(deduped))

    return "\n".join(lines).strip()


def extract_text(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Detect the file's format and return its raw text.

    Args:
        file_bytes: The uploaded file's contents.
        filename: The uploaded file's name, used for extension detection.
        content_type: The multipart content type, if the client sent one.

    Returns:
        The resume's text, with line breaks preserved.

    Raises:
        UnsupportedResumeFormat: If the file is neither PDF nor DOCX.
        ResumeTextExtractionError: If the file is corrupt or unreadable.
        EmptyResumeText: If the file parses but holds no text (a scanned PDF).
    """
    file_format = detect_format(filename, content_type)
    if file_format == "pdf":
        text = extract_text_from_pdf(file_bytes)
    else:
        text = extract_text_from_docx(file_bytes)

    if not text.strip():
        raise EmptyResumeText(
            "No text could be read from this file. If it is a scanned or "
            "image-only resume, please upload a text-based PDF or DOCX."
        )
    return text


# --------------------------------------------------------------------------
# Structured extraction via the provider layer
# --------------------------------------------------------------------------


def strip_code_fences(text: str) -> str:
    """Remove a surrounding markdown code fence from a model response.

    Models drop back into ```json fences even when told not to, and a fenced
    body is otherwise perfectly good JSON.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop the opening fence (with or without a language tag).
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def repair_truncated_json(text: str) -> str | None:
    """Close the structures a response left open when it hit the token ceiling.

    A **last resort**, and only for truncation. The proper fix for a cut-off
    response is to ask for less of it -- ``import_service`` re-splits its input
    and retries when ``finish_reason`` is ``"length"`` -- because repairing
    silently keeps whatever half-entry survived and drops the rest without
    anyone noticing. This exists for the case where that has already been tried
    and some data is better than none.

    Walks the text tracking string state, drops any trailing partial token, and
    closes every open ``[`` and ``{``.

    Args:
        text: A response that failed to parse.

    Returns:
        A repaired JSON string, or None when there is nothing to repair (no
        opening brace, or nothing left after the trailing fragment is dropped).
    """
    start = text.find("{")
    if start == -1:
        return None

    stack: list[str] = []
    in_string = False
    escaped = False
    # The last index at which the document was structurally "at rest": not
    # inside a string, and just after a complete value. Truncating back to
    # there throws away the half-written entry and nothing else.
    safe_end = -1

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                safe_end = index
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if stack:
                stack.pop()
            safe_end = index
        elif char == ",":
            # A comma proves the value before it was complete, which is the
            # only way a bare literal (a number, true/false/null) is ever known
            # to have finished. The trailing comma itself is stripped below.
            safe_end = index

    if safe_end < start:
        return None

    repaired = text[start : safe_end + 1]
    # The last complete token may have been a *key* whose value never arrived.
    # What follows it in the original text says which: a colon means it was a
    # key, and a key with no value has to go, comma and all.
    if text[safe_end + 1 :].lstrip().startswith(":"):
        repaired = re.sub(r',?\s*"(?:[^"\\]|\\.)*"\s*$', "", repaired)
    repaired = re.sub(r",\s*$", "", repaired)
    if not repaired.strip() or repaired.strip() == "{":
        # Nothing survived but the opening brace; an empty object is honest.
        return "{}" if stack else None
    return repaired + "".join(reversed(stack))


def parse_json_response(content: str) -> Any:
    """Parse a model response that is supposed to be a JSON object.

    Tries the whole response first, then the outermost ``{...}`` span, which
    rescues a response with a stray sentence before or after the object, and
    only then :func:`repair_truncated_json`, which is logged at WARNING because
    a repaired object is a partial one.

    Raises:
        ProfileExtractionError: If no JSON object can be recovered.
    """
    candidate = strip_code_fences(content)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass

    repaired = repair_truncated_json(candidate)
    if repaired is not None:
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            logger.warning(
                "recovered a truncated model response by closing %d open "
                "structure(s); the result is incomplete",
                len(repaired) - len(repaired.rstrip("}]")),
            )
            return parsed

    raise ProfileExtractionError(
        "The extraction model did not return valid JSON."
    )


def _call_groq_extraction(resume_text: str) -> str:
    """Send the resume text to Groq and return the raw response content.

    Backoff and the Azure fallback both live in ``services.llm``: an upload is a
    one-shot action the user is watching a spinner for, so a Groq daily cap must
    produce a parsed profile from the other provider rather than a 502.

    One failure ``services.llm`` cannot see is a completion that ended at the
    token ceiling. That is not an error -- the provider returns a 200 with
    ``finish_reason == "length"`` and a JSON object missing its last few closing
    braces -- so it is handled here: the same prompt is asked once more of the
    *other* provider, whose different reasoning budget usually leaves room for
    the whole object. Only once. If the second answer is truncated too, the
    longer of the two goes to :func:`parse_json_response`, whose repair path
    salvages what it can rather than losing the upload entirely.

    Returns:
        The model's response, carrying ``.provider`` (see ``services.llm``).
    """
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": EXTRACTION_USER_TEMPLATE.format(resume_text=resume_text),
        },
    ]
    content, meta = llm.complete_json_with_meta(
        messages,
        max_tokens=EXTRACTION_MAX_TOKENS,
        temperature=EXTRACTION_TEMPERATURE,
        prefer=llm.GROQ,
        purpose="resume extraction",
        max_attempts=4,
        base_delay=1.0,
    )
    if meta.get("finish_reason") != "length":
        return content

    served_by = meta.get("provider") or llm.GROQ
    fallback = llm.AZURE if served_by != llm.AZURE else llm.GROQ
    logger.warning(
        "resume extraction was truncated at %s tokens by %s; retrying on %s",
        meta.get("completion_tokens"),
        served_by,
        fallback,
    )
    if not llm.is_configured(fallback):
        logger.warning(
            "cannot retry the truncated extraction on %s: it has no credentials "
            "configured",
            fallback,
        )
        return content

    try:
        retried, retry_meta = llm.complete_json_with_meta(
            messages,
            max_tokens=EXTRACTION_MAX_TOKENS,
            temperature=EXTRACTION_TEMPERATURE,
            prefer=fallback,
            purpose="resume extraction (truncated retry)",
            max_attempts=2,
            base_delay=1.0,
        )
    except Exception:
        # The first answer is truncated, not worthless. Losing it here would
        # turn a partial profile into a 502.
        logger.exception("the truncated-extraction retry on %s failed too", fallback)
        return content

    if retry_meta.get("finish_reason") == "length" and len(retried) < len(content):
        return content
    return retried


def extract_profile(raw_text: str) -> ParsedProfile:
    """Turn a resume's raw text into a structured profile using Groq.

    Args:
        raw_text: The text produced by :func:`extract_text`.

    Returns:
        A :class:`ParsedProfile`. Sections the model got wrong come back empty
        rather than raising, so a partial parse still reaches the user.

    Raises:
        EmptyResumeText: If ``raw_text`` is blank.
        ProfileExtractionError: If Groq is unreachable or returns no JSON.
    """
    text = (raw_text or "").strip()
    if not text:
        raise EmptyResumeText("There is no resume text to extract a profile from.")

    if len(text) > MAX_RESUME_CHARS:
        logger.warning(
            "Resume text truncated from %d to %d characters for extraction",
            len(text),
            MAX_RESUME_CHARS,
        )
        text = text[:MAX_RESUME_CHARS]

    try:
        content = _call_groq_extraction(text)
    except Exception as exc:
        logger.exception("Groq profile extraction failed")
        raise ProfileExtractionError(
            "Could not extract a profile from this resume: {}".format(exc)
        ) from exc

    return coerce_parsed_profile(parse_json_response(content))


def parse_resume(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Extract a resume's text and its structured profile.

    Args:
        file_bytes: The uploaded file's contents.
        filename: The uploaded file's name, used for extension detection.
        content_type: The multipart content type, if the client sent one.

    Returns:
        ``{"raw_text": str, "parsed_json": dict}`` -- exactly the two columns
        the profiles table stores.

    Raises:
        UnsupportedResumeFormat: If the file is neither PDF nor DOCX.
        ResumeTextExtractionError: If the file is corrupt or unreadable.
        EmptyResumeText: If the file holds no text.
        ProfileExtractionError: If the Groq extraction fails.
    """
    raw_text = extract_text(file_bytes, filename=filename, content_type=content_type)
    parsed = extract_profile(raw_text)
    return {"raw_text": raw_text, "parsed_json": parsed.model_dump()}
