"""Supplementary-file import: read a document, propose a merged profile.

A resume is one snapshot of a career. Most people also keep a spreadsheet, a
notes file, or a long-form CV with the detail the resume had no room for --
every course, every certificate number, the projects that did not make the cut.
This module reads one of those files and proposes what the profile would look
like with it folded in. It never writes: ``POST /profile/import`` returns a
proposal and a diff, the user reviews it section by section, and
``POST /profile/import/apply`` is what actually saves.

Two stages, deliberately split the same way resume parsing is:

1. **Deterministic text extraction.** XLSX becomes one markdown table per
   sheet, CSV the same, DOCX/PDF/TXT/MD reuse the resume parser's readers, JSON
   is pretty-printed. No model involved, so a rendering bug is reproducible and
   a diff of the extracted text is readable.
2. **A merge call** to Azure GPT-4o, which receives the existing profile JSON
   and the document text and returns the merged profile in the same schema.

The diff shown to the user is **not** produced by the model. It is computed
here by comparing the stored profile with the proposal, entry by entry, so what
the review screen says changed is what actually changed -- a model asked to
describe its own edits will confidently list one it did not make.

**References are never imported.** A sheet named for letters of recommendation,
or one whose headers pair an email column with a phone column, is skipped and
reported as skipped. Those rows are other people's contact details; they are
not the user's career history and they have no place in a profile that is fed
to a model.
"""

import csv
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from openpyxl import load_workbook

from app.api.schemas.profile import (
    PROFILE_SECTIONS,
    ParsedProfile,
    coerce_parsed_profile,
)
from app.services import llm, resume_parser

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Formats
# --------------------------------------------------------------------------

XLSX = "xlsx"
CSV = "csv"
DOCX = "docx"
PDF = "pdf"
TXT = "txt"
MD = "md"
JSON = "json"

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".xlsx": XLSX,
    ".xlsm": XLSX,
    ".csv": CSV,
    ".docx": DOCX,
    ".pdf": PDF,
    ".txt": TXT,
    ".md": MD,
    ".markdown": MD,
    ".json": JSON,
}

SUPPORTED_CONTENT_TYPES: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XLSX,
    "application/vnd.ms-excel.sheet.macroenabled.12": XLSX,
    "text/csv": CSV,
    "application/csv": CSV,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCX,
    "application/pdf": PDF,
    "application/x-pdf": PDF,
    "text/plain": TXT,
    "text/markdown": MD,
    "application/json": JSON,
}

# Matches the resume upload cap, and the same reasoning: a client-side limit is
# a courtesy, not a control.
MAX_IMPORT_BYTES = 10 * 1024 * 1024

# Chunk sizes and the token budget live with the merge itself, further down.


class UnsupportedDocumentFormat(Exception):
    """Raised when a file is not one of the importable formats."""


class DocumentTooLarge(Exception):
    """Raised when an upload is over :data:`MAX_IMPORT_BYTES`."""


class EmptyDocumentText(Exception):
    """Raised when a file parses cleanly but holds nothing to import."""


class DocumentReadError(Exception):
    """Raised when a file is the right type but cannot be read."""


class ImportProposalError(Exception):
    """Raised when the merge model is unreachable or returns nothing usable."""


class DocumentTooDense(Exception):
    """Raised when even a minimal chunk cannot be merged inside the token budget.

    Not a provider failure and not a bad file: the section being rebuilt is
    simply larger than one answer can hold. The route answers 422 with the one
    thing that actually helps -- split the file up.
    """


# --------------------------------------------------------------------------
# Reference detection
# --------------------------------------------------------------------------

SKIPPED_REFERENCES = (
    "References contain third-party contact details and are not imported."
)

# Whole-word tokens that name a sheet of referees. "lor" is matched as a token
# rather than a substring on purpose -- "Colors" is not a sheet of referees.
REFERENCE_NAME_TOKENS = frozenset({"lor", "lors", "referee", "referees"})
REFERENCE_NAME_SUBSTRINGS = ("reference", "recommend")

EMAIL_HEADERS = ("email", "e-mail", "mail id", "mailid")
PHONE_HEADERS = ("phone", "mobile", "cell", "telephone", "contact number", "whatsapp")


def _tokens(value: str) -> set[str]:
    """Split a label into lower-cased alphanumeric tokens."""
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


def is_reference_sheet(name: str, headers: list[str]) -> bool:
    """Return True when a sheet holds referees rather than the user's history.

    Two independent signals, because a sheet is named for its author's
    convenience and headed for their reader's:

    * the **name** says so -- "LORs", "References", "Recommenders";
    * the **headers** pair an email column with a phone column, which is a
      contact list for other people and nothing else in a career workbook is.

    Args:
        name: The sheet's name, or the file's stem for a single-table CSV.
        headers: The header row, already stripped.

    Returns:
        True when the sheet must be skipped.
    """
    lowered = (name or "").lower()
    if _tokens(lowered) & REFERENCE_NAME_TOKENS:
        return True
    if any(marker in lowered for marker in REFERENCE_NAME_SUBSTRINGS):
        return True

    joined = [header.lower() for header in headers]
    has_email = any(any(m in header for m in EMAIL_HEADERS) for header in joined)
    has_phone = any(any(m in header for m in PHONE_HEADERS) for header in joined)
    return has_email and has_phone


# --------------------------------------------------------------------------
# Format detection
# --------------------------------------------------------------------------


def detect_kind(filename: str | None, content_type: str | None = None) -> str:
    """Return the import kind for an uploaded file.

    The **extension** is checked first here, the opposite of
    ``resume_parser.detect_format``. The formats differ: browsers send
    ``text/plain`` for ``.csv`` and ``.md`` alike and
    ``application/octet-stream`` for anything they do not recognise, so
    trusting the content type first would render a spreadsheet-shaped CSV as
    flat text.

    Args:
        filename: The uploaded file's name.
        content_type: The multipart content type, if the client sent one.

    Returns:
        One of ``xlsx``, ``csv``, ``docx``, ``pdf``, ``txt``, ``md``, ``json``.

    Raises:
        UnsupportedDocumentFormat: If the file is none of those.
    """
    if filename:
        extension = os.path.splitext(filename)[1].lower()
        if extension in SUPPORTED_EXTENSIONS:
            return SUPPORTED_EXTENSIONS[extension]

    if content_type:
        base_type = content_type.split(";")[0].strip().lower()
        if base_type in SUPPORTED_CONTENT_TYPES:
            return SUPPORTED_CONTENT_TYPES[base_type]

    raise UnsupportedDocumentFormat(
        "Supported files are XLSX, CSV, DOCX, PDF, TXT, Markdown, and JSON. "
        "Received: {}".format(content_type or filename or "an unnamed file")
    )


def _decode(file_bytes: bytes) -> str:
    """Decode text bytes, tolerating a BOM and a non-UTF-8 export."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 above decodes every byte sequence, so this is unreachable in
    # practice; the replacement pass is here so a future encoding change cannot
    # turn into a 500.
    return file_bytes.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Tabular rendering
# --------------------------------------------------------------------------


def _cell(value: Any) -> str:
    """Render one spreadsheet cell as a markdown-table-safe string.

    A newline inside a cell would end the table row, so it becomes ``" / "``.
    A pipe would open a new column, so it is escaped. Dates arrive as
    ``datetime`` and are written back in ISO form rather than as a repr.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        text = (
            value.date().isoformat()
            if value.time() == value.min.time()
            else value.isoformat()
        )
    elif isinstance(value, float) and value.is_integer():
        # openpyxl reads every number as a float; "2019.0" is not a year.
        text = str(int(value))
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    joined = " / ".join(part.strip() for part in text.split("\n") if part.strip())
    return joined.replace("|", "\\|").strip()


def _table_rows(rows: list[list[Any]]) -> list[list[str]]:
    """Clean a grid: cells stringified, wholly empty rows dropped."""
    cleaned: list[list[str]] = []
    for row in rows:
        cells = [_cell(value) for value in row]
        while cells and not cells[-1]:
            cells.pop()
        if any(cells):
            cleaned.append(cells)
    return cleaned


def render_markdown_table(rows: list[list[str]]) -> str:
    """Render a cleaned grid as a markdown table, first row as the header.

    Short rows are padded so every row has the same column count -- a ragged
    markdown table reads as a different table further down.
    """
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header, body = padded[0], padded[1:]
    lines = [
        "| {} |".format(" | ".join(header)),
        "| {} |".format(" | ".join(["---"] * width)),
    ]
    lines.extend("| {} |".format(" | ".join(row)) for row in body)
    return "\n".join(lines)


def _sheet_record(
    name: str, rows: int, cols: int, skipped_reason: str | None = None
) -> dict[str, Any]:
    """One entry in ``structure.sheets``.

    ``skipped_reason`` is present only when the sheet was skipped, so a client
    can test for the key rather than compare against None.
    """
    record: dict[str, Any] = {"name": name, "rows": rows, "cols": cols}
    if skipped_reason:
        record["skipped_reason"] = skipped_reason
    return record


def _render_grid(name: str, grid: list[list[Any]]) -> tuple[str, dict[str, Any]]:
    """Render one named grid, skipping it when it holds referees.

    Returns:
        ``(text, sheet_record)``. ``text`` is ``""`` for a skipped or empty
        sheet, and the record always reports the real row and column counts, so
        the user can see that a sheet was read and deliberately left out.
    """
    rows = _table_rows(grid)
    row_count = len(rows)
    col_count = max((len(row) for row in rows), default=0)

    if not rows:
        return "", _sheet_record(name, 0, 0)

    if is_reference_sheet(name, rows[0]):
        return "", _sheet_record(name, row_count, col_count, SKIPPED_REFERENCES)

    body = "## Sheet: {}\n\n{}".format(name, render_markdown_table(rows))
    return body, _sheet_record(name, row_count, col_count)


def extract_xlsx(file_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Render every sheet of a workbook as a markdown table.

    ``data_only=True`` reads the values Excel last calculated rather than the
    formulas, which is what the user sees and what the model can use.

    Raises:
        DocumentReadError: If the bytes are not a readable workbook.
    """
    try:
        workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentReadError(
            "Could not read the spreadsheet: {}".format(exc)
        ) from exc

    parts: list[str] = []
    sheets: list[dict[str, Any]] = []
    try:
        for worksheet in workbook.worksheets:
            grid = [list(row) for row in worksheet.iter_rows(values_only=True)]
            text, record = _render_grid(worksheet.title, grid)
            sheets.append(record)
            if text:
                parts.append(text)
    finally:
        workbook.close()

    return "\n\n".join(parts), sheets


def extract_csv(
    file_bytes: bytes, filename: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """Render a CSV as a single markdown table.

    The delimiter is sniffed, because "CSV" exports from European locales are
    semicolon-separated and would otherwise read as one column of pasted text.
    """
    text = _decode(file_bytes)
    sample = text[:8192]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    grid = [list(row) for row in csv.reader(io.StringIO(text), dialect)]
    name = os.path.splitext(os.path.basename(filename or "Sheet1"))[0] or "Sheet1"
    body, record = _render_grid(name, grid)
    return body, [record]


def extract_document_text(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Read an uploaded supplementary file into text plus a structure summary.

    Args:
        file_bytes: The uploaded file's contents.
        filename: The uploaded file's name, used for extension detection.
        content_type: The multipart content type, if the client sent one.

    Returns:
        ``{"text": str, "structure": {"kind": str, "sheets": [...]}}``. Each
        sheet record is ``{"name", "rows", "cols"}`` plus ``"skipped_reason"``
        when it was left out. Non-tabular formats report a single sheet named
        after the file, so a client renders one shape either way.

    Raises:
        DocumentTooLarge: If the file is over 10MB.
        UnsupportedDocumentFormat: If the format is not importable.
        DocumentReadError: If the file is corrupt.
        EmptyDocumentText: If the file holds no importable text -- which
            includes a workbook whose only sheets were reference sheets.
    """
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise DocumentTooLarge("The file must be 10MB or smaller.")

    kind = detect_kind(filename, content_type)
    display_name = os.path.basename(filename or "document")

    if kind == XLSX:
        text, sheets = extract_xlsx(file_bytes)
    elif kind == CSV:
        text, sheets = extract_csv(file_bytes, filename)
    elif kind in (DOCX, PDF):
        try:
            text = resume_parser.extract_text(
                file_bytes, filename=filename, content_type=content_type
            )
        except resume_parser.EmptyResumeText as exc:
            raise EmptyDocumentText(str(exc)) from exc
        except resume_parser.ResumeTextExtractionError as exc:
            raise DocumentReadError(str(exc)) from exc
        sheets = [_sheet_record(display_name, len(text.splitlines()), 1)]
    elif kind == JSON:
        raw = _decode(file_bytes)
        try:
            text = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # Still worth importing: a hand-edited notes file that is nearly
            # JSON reads perfectly well as text, and refusing it helps nobody.
            text = raw
        sheets = [_sheet_record(display_name, len(text.splitlines()), 1)]
    else:
        text = _decode(file_bytes)
        sheets = [_sheet_record(display_name, len(text.splitlines()), 1)]

    text = text.strip()
    if not text:
        if any(sheet.get("skipped_reason") for sheet in sheets):
            raise EmptyDocumentText(
                "Every sheet in this file holds reference contact details, "
                "which are not imported."
            )
        raise EmptyDocumentText(
            "No text could be read from this file. If it is a scanned or "
            "image-only document, upload a text-based one instead."
        )

    return {"text": text, "structure": {"kind": kind, "sheets": sheets}}


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

# One merge pass reads at most this much document. The ceiling is on the
# *input* because the output scales with it: a pass has to re-emit the whole of
# every section it touches, and 20k characters of spreadsheet is about as much
# as can be merged and returned inside the token budget below.
MAX_CHUNK_CHARS = 20000

# And at most this many table rows, whatever their length. The character
# ceiling alone is not enough: a pass handed fourteen rows of a wide sheet
# returns four amalgamated entries rather than fourteen, however plainly it is
# told not to. Six rows is few enough that re-emitting them one by one is the
# path of least resistance, which is the only instruction a model reliably
# follows.
MAX_ROWS_PER_CHUNK = 6

# A chunk that truncates is halved and retried. Below this there is nothing
# left to split -- the section being rebuilt is simply larger than the output
# budget -- so the import fails with a message the user can act on rather than
# looping.
MIN_CHUNK_CHARS = 4000

# GPT-4o's output ceiling. Generous on purpose: the failure mode this replaced
# was a whole merged profile truncated at 8000 tokens, and a bigger budget plus
# the per-section design below means a pass that still truncates is a real
# signal rather than an inevitability.
MERGE_MAX_TOKENS = 16000

# The merge is a data-shuffling task, not a writing one. Near-zero temperature
# keeps two runs over the same document comparable.
MERGE_TEMPERATURE = 0.1

SHEET_PREFIX = "## Sheet: "
CONTINUED_SUFFIX = " (continued)"

# A markdown table's separator row: | --- | --- |
SEPARATOR_PATTERN = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")


def count_data_rows(chunk: str) -> int:
    """Count the table rows in a chunk that carry data rather than headings.

    Sent to the model as an explicit target. Without it a pass handed a wide
    table of long cells quietly economises -- sixteen roles come back as six,
    each an amalgam of several -- and nothing downstream can tell that apart
    from a document that really did describe six. A number the model can count
    itself against is the cheapest correction available.
    """
    total = 0
    for block in re.split(r"\n(?=## Sheet: )", chunk):
        rows = [
            line
            for line in block.split("\n")
            if line.startswith("|") and not SEPARATOR_PATTERN.match(line)
        ]
        # The first "|" line of a rendered sheet is its header row.
        total += max(len(rows) - 1, 0)
    return total


def _sheet_heading(block: str) -> str:
    """Return the ``## Sheet: name`` heading a block opens with, or ``""``."""
    first = block.split("\n", 1)[0]
    return first if first.startswith(SHEET_PREFIX) else ""


def _table_preamble(lines: list[str]) -> tuple[list[str], int]:
    """Return the header rows to repeat on every part, and where the body starts.

    A markdown table means nothing without its header row: split one in the
    middle and the second half is a grid of unlabelled cells. So the heading,
    the header row, and the separator are re-emitted at the top of every
    continuation.

    Returns:
        ``(preamble lines, index of the first body line)``. The preamble is
        empty for a block that is not a table.
    """
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        # A header row is only a header when a separator follows it.
        if index + 1 < len(lines) and SEPARATOR_PATTERN.match(lines[index + 1]):
            return lines[: index + 2], index + 2
        break
    return [], 0


def _split_sheet_block(block: str, limit: int) -> list[str]:
    """Split one oversized sheet on row boundaries, repeating its header.

    Args:
        block: One ``## Sheet: ...`` block, or a plain-text block.
        limit: Maximum characters per part.

    Returns:
        Two or more parts, each carrying the heading (marked "(continued)"
        after the first) and the table header. A single row longer than
        ``limit`` is emitted on its own rather than cut.
    """
    lines = block.split("\n")
    heading = _sheet_heading(block)
    preamble, body_start = _table_preamble(lines)
    body = lines[body_start:] if preamble else lines[1:] if heading else lines
    max_rows = MAX_ROWS_PER_CHUNK if preamble else 0

    if preamble:
        first_preamble = preamble
        rest_preamble = [
            heading + CONTINUED_SUFFIX if heading else "",
            "",
        ] + preamble[-2:]
    else:
        first_preamble = [heading] if heading else []
        rest_preamble = [heading + CONTINUED_SUFFIX] if heading else []

    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    current_rows = 0

    def flush() -> None:
        if not current:
            return
        head = first_preamble if not parts else rest_preamble
        parts.append("\n".join([line for line in head if line is not None] + current))

    for line in body:
        head = first_preamble if not parts else rest_preamble
        head_len = sum(len(item) + 1 for item in head)
        is_row = line.startswith("|") and not SEPARATOR_PATTERN.match(line)
        too_long = head_len + current_len + len(line) + 1 > limit
        too_many = bool(max_rows) and is_row and current_rows >= max_rows
        if current and (too_long or too_many):
            flush()
            current = []
            current_len = 0
            current_rows = 0
        current.append(line)
        current_len += len(line) + 1
        current_rows += 1 if is_row else 0

    flush()
    return [part for part in parts if part.strip()] or [block]


def split_document(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split a rendered document into merge-sized chunks.

    Sheet boundaries first: a sheet is the natural seam, and a chunk that stops
    at one is a self-describing unit the model can merge on its own. A sheet
    that is bigger than ``limit`` on its own is split on **row** boundaries with
    its heading and header row repeated, so no pass ever reads a table body
    without the columns it belongs to.

    Adjacent small blocks are packed back together, so a workbook of eight tiny
    sheets is one pass rather than eight.

    Args:
        text: The rendered document text.
        limit: Maximum characters per chunk.

    Returns:
        One or more chunks. Never empty for non-empty input.
    """
    if len(text) <= limit and count_data_rows(text) <= MAX_ROWS_PER_CHUNK:
        return [text]

    blocks: list[str] = []
    for block in re.split(r"\n(?=## Sheet: )", text):
        if len(block) <= limit and count_data_rows(block) <= MAX_ROWS_PER_CHUNK:
            blocks.append(block)
        else:
            blocks.extend(_split_sheet_block(block, limit))

    chunks: list[str] = []
    for block in blocks:
        fits = chunks and len(chunks[-1]) + len(block) + 2 <= limit
        room = fits and (
            count_data_rows(chunks[-1]) + count_data_rows(block) <= MAX_ROWS_PER_CHUNK
        )
        if room:
            chunks[-1] = "{}\n\n{}".format(chunks[-1], block)
        else:
            chunks.append(block)
    return [chunk for chunk in chunks if chunk.strip()] or [text[:limit]]


# --------------------------------------------------------------------------
# Which sections a chunk can touch
# --------------------------------------------------------------------------

# Matched against a chunk's sheet headings and table header rows -- not its
# whole text, which mentions everything. The point is to send the model only
# the existing entries it might need, so both the prompt and the answer stay
# small.
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "objective", "profile", "about me", "bio"),
    "work_experience": (
        "work", "experience", "employment", "job", "role", "position",
        "internship", "career", "company", "employer",
    ),
    "education": (
        "education", "degree", "academic", "school", "college", "university",
        "qualification", "cgpa", "gpa",
    ),
    "skills": ("skill", "technolog", "tool", "competenc", "language", "stack"),
    "certifications": (
        "certificat", "certification", "licen", "credential", "course",
        "training", "mooc",
    ),
    "projects": ("project", "portfolio", "build", "repo"),
    "achievements": (
        "achievement", "award", "honour", "honor", "accomplish", "prize",
        "scholarship", "extracurricular", "volunteer", "responsibility",
        "activit", "competition", "hackathon",
    ),
    "publications": (
        "publication", "paper", "patent", "research", "journal", "conference",
        "talk", "poster", "thesis",
    ),
}


def _label_lines(chunk: str) -> str:
    """Return the parts of a chunk that name what it holds, lower-cased.

    Headings and header rows only. A data row mentioning "Kubernetes project
    lead" should not pull the whole projects section into the prompt.
    """
    labels: list[str] = []
    lines = chunk.split("\n")
    for index, line in enumerate(lines):
        if line.startswith(SHEET_PREFIX) or line.startswith("#"):
            labels.append(line)
        elif line.startswith("|") and index + 1 < len(lines):
            if SEPARATOR_PATTERN.match(lines[index + 1]):
                labels.append(line)
    return " ".join(labels).lower()


def guess_sections(chunk: str) -> tuple[str, ...]:
    """Return the profile sections a chunk plausibly carries.

    A superset, deliberately: guessing one section too many costs a few hundred
    tokens of context, while guessing one too few would hand the model a
    section to rebuild without showing it what is already there.

    A chunk whose labels match nothing -- prose, a PDF, an untitled sheet --
    falls back to **every** section, which is correct but expensive; the
    truncation retry in :func:`_merge_chunk` is what keeps that case safe.

    Args:
        chunk: One chunk from :func:`split_document`.

    Returns:
        Section names in ``PROFILE_SECTIONS`` order.
    """
    labels = _label_lines(chunk)
    matched = tuple(
        section
        for section in PROFILE_SECTIONS
        if any(keyword in labels for keyword in SECTION_KEYWORDS[section])
    )
    return matched or PROFILE_SECTIONS


# --------------------------------------------------------------------------
# The merge prompt
# --------------------------------------------------------------------------

# One pass merges one chunk into the sections that chunk affects, and returns
# only those sections. That is the whole reason this works on a real career
# workbook: asking for the entire profile back on every pass made the answer
# grow with the profile until it hit the token ceiling and was cut off
# mid-string.
MERGE_SYSTEM_PROMPT = """\
You merge one part of a supplementary career document into an existing \
structured career profile. You are a merger, not a writer: every value you emit \
must already appear in the existing sections or in the document part.

Return ONLY a JSON object whose keys are a SUBSET of these eight section names:

  summary, work_experience, education, skills, certifications, projects, \
achievements, publications

INCLUDE A SECTION ONLY IF THIS DOCUMENT PART SAYS SOMETHING ABOUT IT. Omit \
every other key entirely. Do not return a section just because it was given to \
you as context.

For each section you do return, return that section's COMPLETE merged value: \
every existing entry you were given, plus every new one from the document part. \
Section shapes:

"summary": string
"work_experience": [{"title": string, "company": string, "location": string,
  "start_date": string, "end_date": string, "current": boolean,
  "employment_type": string, "highlights": [string], "awards": [string]}]
"education": [{"degree": string, "institution": string, "field": string,
  "start_date": string, "end_date": string, "details": string, "gpa": string,
  "coursework": [string], "honors": [string]}]
"skills": [string]
"certifications": [{"name": string, "issuer": string, "year": string,
  "expires": string, "credential_url": string, "description": string}]
"projects": [{"name": string, "description": string, "technologies": [string],
  "start_date": string, "end_date": string, "highlights": [string],
  "link": string, "links": {"github": string, "live": string, "demo": string}}]
"achievements": [string]
"publications": [{"title": string, "authors": string, "url": string,
  "status": string, "year": string}]

Rules:

1. NEVER DROP EXISTING DATA. Every entry you were given in a section you return \
must appear in your output for that section, unchanged or enriched. Removing \
one is the single worst thing you can do here.
2. THE DOCUMENT IS A TABLE: ONE DATA ROW IS ONE ENTRY. Every data row in \
this part becomes its own entry in the section it belongs to. Never fold two \
rows of the same table into one entry -- not two roles at the same employer, \
not two projects sharing a technology, not a role and the row below it. The \
header line above says how many data rows this part holds; your output for \
the sections it covers must account for every one of them.
2a. Match an existing entry to a document row only when they are clearly the \
same thing: the same employer and role, the same institution and degree, the \
same project, certification, or publication name. A different role at the \
same employer is a separate entry.
3. When they match, merge field by field: keep the more complete value -- a \
filled value beats an empty one, a full date beats a vague one. For list fields \
(highlights, skills, technologies, coursework, honors, awards) take the union, \
existing order first, new items appended. Do not duplicate a bullet that is \
merely reworded.
4. Add every entry the document part describes that the existing section does \
not have.
5. NEVER INVENT. Do not infer a date, an employer, a grade, or a metric that \
neither source states. Leave a string empty ("") and an array empty ([]) \
instead. Do not rewrite, embellish, or summarise wording -- copy it.
6. skills: short tokens only, one technology, tool, language, or named \
competency each ("Python", "PostgreSQL", "Stakeholder management"). Split a \
grouped cell like "Languages: Python, Go, SQL" into separate entries, drop the \
category label, de-duplicate case-insensitively.
7. achievements: one string each, written as \
"Name -- Organization (Date): description", dropping any part the sources do \
not state. An achievement that is really a publication belongs in \
publications; one that is really a certification belongs in certifications.
8. publications: papers, articles, patents, preprints, and talks. "title" is \
required; an entry without one is not a publication.
9. Dates stay as written, in the source's own wording ("Jan 2022", "2019"). Do \
not reformat them and do not compute durations. Set "current": true only when \
an end date reads as ongoing, and then leave end_date "".
10. projects: put each URL in "links" under the slot that fits -- repository in \
"github", deployed site in "live", video or walkthrough in "demo" -- and also \
set "link" to the first of those.
11. Ignore any contact details for other people: referees, recommenders, \
managers named as references. Do not return anyone's email address or phone \
number, including the profile owner's.
12. A row split across two parts of the document may arrive without its \
header; use the repeated header row at the top of the part.

Output the JSON object and nothing else. No prose, no explanation, no markdown \
code fences.\
"""

MERGE_USER_TEMPLATE = """\
SECTIONS YOU MAY RETURN (omit any this part says nothing about):
{section_names}

EXISTING ENTRIES FOR THOSE SECTIONS (JSON -- merge into these, never drop them):

{existing_json}

DOCUMENT PART{part_label} (from {filename}){row_note}:

{document_text}

Return one JSON object holding only the sections this part affects.\
"""


def _existing_context(running: dict[str, Any], sections: tuple[str, ...]) -> str:
    """Serialise only the sections this pass may return."""
    return json.dumps(
        {section: running.get(section) for section in sections}, ensure_ascii=False
    )


def combine_sections(
    running: dict[str, Any],
    returned: dict[str, Any],
    context_sections: tuple[str, ...],
) -> dict[str, Any]:
    """Fold one pass's returned sections into the running profile.

    Deterministic, and the reason a per-section merge is safe:

    * A section the pass did not return is left exactly as it was. The model
      never has to re-emit a section it was not asked about, which is what keeps
      each answer small.
    * A section it did return **replaces** the running one -- it is a merge of
      it, not an addition to it.
    * Except that any existing entry missing from the replacement is put back,
      keyed the same way :func:`diff_profiles` matches entries. The prompt
      forbids dropping an entry; this makes it impossible, and logs it when the
      model tries.
    * A section returned without having been given as context is **unioned**
      rather than replacing, because the model was never shown what it would be
      overwriting.

    Args:
        running: The profile so far.
        returned: The model's object for this pass.
        context_sections: The sections whose entries were sent as context.

    Returns:
        A new dict; neither argument is mutated.
    """
    merged = dict(running)
    for section, value in returned.items():
        if section not in PROFILE_SECTIONS:
            continue

        if section == "summary":
            summary = coerce_parsed_profile({"summary": value}).summary
            if summary:
                merged["summary"] = summary
            continue

        cleaned = coerce_parsed_profile({section: value}).model_dump()[section]
        existing = merged.get(section) or []

        if section in context_sections:
            keys = {_section_key(section, entry) for entry in cleaned}
            restored = [
                entry
                for entry in existing
                if _section_key(section, entry) not in keys
            ]
            if restored:
                logger.warning(
                    "import merge dropped %d %s entr(ies); restoring them",
                    len(restored),
                    section,
                )
            merged[section] = cleaned + restored
        else:
            keys = {_section_key(section, entry) for entry in existing}
            merged[section] = list(existing) + [
                entry for entry in cleaned if _section_key(section, entry) not in keys
            ]

    return ParsedProfile.model_validate(merged).model_dump()


def _section_key(section: str, entry: Any) -> str:
    """Identity of one entry, for both list-of-object and list-of-string sections."""
    if isinstance(entry, dict):
        return entry_key(section, entry)
    return normalise_key(entry)


def _merge_chunk(
    running: dict[str, Any],
    chunk: str,
    filename: str,
    *,
    label: str,
    provider_seen: list[str],
    depth: int = 0,
) -> dict[str, Any]:
    """Merge one chunk, halving and retrying if the answer was cut off.

    A ``finish_reason`` of ``"length"`` means the response hit the token ceiling
    mid-JSON. Repairing that would silently keep half a section, so the chunk is
    split in two and each half merged in turn -- less document per pass means a
    smaller answer. The recursion stops at :data:`MIN_CHUNK_CHARS`, below which
    the section being rebuilt is simply too big to return and the import fails
    with a message that says what to do.

    Raises:
        DocumentTooDense: When a chunk at the floor still truncates.
        ImportProposalError: When the provider fails or returns no JSON.
    """
    sections = guess_sections(chunk)
    rows_in_chunk = count_data_rows(chunk)
    messages = [
        {"role": "system", "content": MERGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": MERGE_USER_TEMPLATE.format(
                section_names=", ".join(sections),
                existing_json=_existing_context(running, sections),
                part_label=" {}".format(label) if label else "",
                filename=filename or "document",
                row_note=(
                    ", holding {} data rows -- each one is its own entry".format(
                        rows_in_chunk
                    )
                    if rows_in_chunk
                    else ""
                ),
                document_text=chunk,
            ),
        },
    ]

    started = time.monotonic()
    try:
        content, meta = llm.complete_json_with_meta(
            messages,
            max_tokens=MERGE_MAX_TOKENS,
            temperature=MERGE_TEMPERATURE,
            prefer=llm.AZURE,
            purpose="profile import",
        )
    except Exception as exc:
        logger.exception("profile import merge failed on part %s", label or "1")
        raise ImportProposalError(
            "Could not read a profile update out of this file: {}".format(exc)
        ) from exc
    elapsed = time.monotonic() - started

    if meta.get("provider"):
        provider_seen.append(str(meta["provider"]))

    if meta.get("finish_reason") == "length":
        logger.warning(
            "import merge part %s was truncated at %s tokens after %.1fs "
            "(%d chars in, sections=%s); re-splitting",
            label or "1",
            meta.get("completion_tokens"),
            elapsed,
            len(chunk),
            ",".join(sections),
        )
        halves = split_document(chunk, max(len(chunk) // 2, MIN_CHUNK_CHARS))
        if len(halves) < 2 or len(chunk) <= MIN_CHUNK_CHARS:
            raise DocumentTooDense(
                "This file is too dense to import in one go; split it into "
                "smaller files (one section or a few sheets each) and import "
                "them one at a time."
            )
        for index, half in enumerate(halves, start=1):
            running = _merge_chunk(
                running,
                half,
                filename,
                label="{}.{}".format(label or "1", index),
                provider_seen=provider_seen,
                depth=depth + 1,
            )
        return running

    returned = resume_parser.parse_json_response(content)
    if not isinstance(returned, dict):
        raise ImportProposalError(
            "The merge model did not return a JSON object for part {}.".format(
                label or "1"
            )
        )

    combined = combine_sections(running, returned, sections)
    gained = sum(
        len(combined.get(section) or []) - len(running.get(section) or [])
        for section in PROFILE_SECTIONS
        if isinstance(combined.get(section), list)
    )
    if rows_in_chunk and gained < rows_in_chunk:
        # Not an error on its own: a row can update an existing entry instead of
        # adding one, and a table can continue into the next part. Logged
        # because row-folding is invisible otherwise, and this is where it shows.
        logger.info(
            "import merge part %s added %d entries from %d data rows",
            label or "1",
            gained,
            rows_in_chunk,
        )
    logger.info(
        "import merge part %s: %d chars in, %d rows, context=%s, returned=%s, "
        "%s tokens out, finish=%s, %.1fs",
        label or "1",
        len(chunk),
        rows_in_chunk,
        ",".join(sections),
        ",".join(key for key in returned if key in PROFILE_SECTIONS) or "none",
        meta.get("completion_tokens"),
        meta.get("finish_reason"),
        elapsed,
    )
    return combined


def propose_import(
    existing_parsed_json: dict[str, Any] | None,
    document_text: str,
    filename: str,
) -> dict[str, Any]:
    """Propose the profile that results from folding a document into a profile.

    Nothing is saved. The proposal and the diff are handed to the user, who
    decides section by section what to keep, and ``/profile/import/apply`` is
    what writes.

    The document is split into chunks of at most :data:`MAX_CHUNK_CHARS` and
    merged **one section at a time**: each pass is shown only the existing
    entries of the sections its chunk plausibly touches, and returns only those
    sections. Both halves of that matter. Asking for the whole profile back on
    every pass made the answer grow with the profile -- a workbook with 17 roles
    and 24 projects truncated mid-string and failed the whole import -- and
    sending the whole profile as context made the prompt grow with it too.

    Passes run in order, not in parallel: each one merges into the result of the
    last, so a role listed on two sheets is merged rather than added twice.

    Args:
        existing_parsed_json: The stored profile, or None for a user who has
            none -- in which case every entry in the proposal is an addition.
        document_text: The text produced by :func:`extract_document_text`.
        filename: The source file's name, used only inside the prompt.

    Returns:
        ``{"proposal": dict, "changes": [...], "summary": {...},
        "provider": str}``.

    Raises:
        EmptyDocumentText: If there is no document text to merge.
        DocumentTooDense: If a chunk still truncates at the minimum size.
        ImportProposalError: If the model is unreachable or returns no JSON.
    """
    text = (document_text or "").strip()
    if not text:
        raise EmptyDocumentText("There is no document text to import.")

    existing = ParsedProfile.model_validate(existing_parsed_json or {}).model_dump()
    chunks = split_document(text, MAX_CHUNK_CHARS)
    running = dict(existing)
    providers: list[str] = []

    started = time.monotonic()
    for index, chunk in enumerate(chunks, start=1):
        label = "{}/{}".format(index, len(chunks))
        running = _merge_chunk(
            running, chunk, filename, label=label, provider_seen=providers
        )

    proposal = ParsedProfile.model_validate(running).model_dump()
    changes, summary = diff_profiles(existing, proposal)
    logger.info(
        "import proposal for %s: %d chunk(s), %.1fs total, %d added, %d updated, "
        "%d unchanged, %d removed",
        filename or "document",
        len(chunks),
        time.monotonic() - started,
        summary["added"],
        summary["updated"],
        summary["unchanged"],
        summary["removed"],
    )
    return {
        "proposal": proposal,
        "changes": changes,
        "summary": summary,
        "provider": providers[-1] if providers else "",
    }


# --------------------------------------------------------------------------
# The diff engine
# --------------------------------------------------------------------------

# Sections compared entry by entry, and the fields whose normalised values form
# an entry's identity. Two entries with the same key are the same thing; two
# with different keys are not, however similar they look.
LIST_SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "work_experience": ("company", "title"),
    "education": ("institution", "degree"),
    "certifications": ("name",),
    "projects": ("name",),
    "publications": ("title",),
}

# Sections that are plain lists of strings: the string is its own key.
STRING_SECTIONS: tuple[str, ...] = ("skills", "achievements")

ADDED = "added"
UPDATED = "updated"
UNCHANGED = "unchanged"
# Not produced by a well-behaved merge -- the prompt forbids dropping an entry.
# Computed anyway, because a review screen that silently omits a role the model
# lost is worse than one that shows it as removed.
REMOVED = "removed"

CHANGE_KINDS: tuple[str, ...] = (ADDED, UPDATED, UNCHANGED, REMOVED)


def normalise_key(value: Any) -> str:
    """Normalise one identity field: case-folded, punctuation and spacing gone.

    "Kestrel Labs, Inc." and "kestrel labs inc" are the same employer; a diff
    that called them different would show every role as both added and removed.
    """
    text = "" if value is None else str(value)
    return " ".join(part for part in re.split(r"[^a-z0-9]+", text.casefold()) if part)


def entry_key(section: str, entry: dict[str, Any]) -> str:
    """Return the identity key for one entry of a list section."""
    fields = LIST_SECTION_KEYS.get(section, ("name",))
    return "|".join(normalise_key(entry.get(field)) for field in fields)


def entry_label(section: str, entry: dict[str, Any]) -> str:
    """Return a human-readable label for one entry, for the review screen."""
    if section == "work_experience":
        title = (entry.get("title") or "").strip()
        company = (entry.get("company") or "").strip()
        if title and company:
            return "{} at {}".format(title, company)
        return title or company or "Untitled role"
    if section == "education":
        degree = (entry.get("degree") or entry.get("field") or "").strip()
        institution = (entry.get("institution") or "").strip()
        if degree and institution:
            return "{}, {}".format(degree, institution)
        return degree or institution or "Untitled qualification"
    if section == "publications":
        return (entry.get("title") or "").strip() or "Untitled publication"
    return (entry.get("name") or "").strip() or "Untitled entry"


def _comparable(value: Any) -> Any:
    """Reduce a field value to what a change should be judged on.

    An empty string and a missing value are the same absence, so filling a
    field with "" is not an update. Lists keep their order: a reordered
    highlight list *is* a change the user should see.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_comparable(item) for item in value]
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in sorted(value.items())}
    return value


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return the field names whose values differ, in the proposal's order."""
    return [
        field
        for field in after
        if _comparable(before.get(field)) != _comparable(after.get(field))
    ]


def _change(
    section: str,
    kind: str,
    label: str,
    key: str,
    index: int | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build one change record."""
    return {
        "section": section,
        "kind": kind,
        "label": label,
        "key": key,
        "index": index,
        "fields": fields or [],
    }


def _diff_object_section(
    section: str, existing: list[Any], proposal: list[Any]
) -> list[dict[str, Any]]:
    """Diff one list-of-objects section by entry identity."""
    before: dict[str, dict[str, Any]] = {}
    for entry in existing:
        if isinstance(entry, dict):
            before.setdefault(entry_key(section, entry), entry)

    changes: list[dict[str, Any]] = []
    matched: set[str] = set()
    for index, entry in enumerate(proposal):
        if not isinstance(entry, dict):
            continue
        key = entry_key(section, entry)
        label = entry_label(section, entry)
        original = before.get(key)
        if original is None:
            changes.append(_change(section, ADDED, label, key, index))
            continue
        matched.add(key)
        fields = changed_fields(original, entry)
        changes.append(
            _change(section, UPDATED if fields else UNCHANGED, label, key, index, fields)
        )

    for key, entry in before.items():
        if key not in matched:
            changes.append(_change(section, REMOVED, entry_label(section, entry), key))
    return changes


def _diff_string_section(
    section: str, existing: list[Any], proposal: list[Any]
) -> list[dict[str, Any]]:
    """Diff a plain list of strings, matching on the normalised string."""
    before: dict[str, str] = {}
    for item in existing:
        if item is None or str(item).strip() == "":
            continue
        before.setdefault(normalise_key(item), str(item).strip())

    changes: list[dict[str, Any]] = []
    matched: set[str] = set()
    for index, item in enumerate(proposal):
        if item is None or str(item).strip() == "":
            continue
        key = normalise_key(item)
        label = str(item).strip()
        if key not in before:
            changes.append(_change(section, ADDED, label, key, index))
            continue
        matched.add(key)
        # Same normalised string, different spelling: "postgresql" ->
        # "PostgreSQL" is an update, and the user should see the rewrite.
        fields = [] if before[key] == label else ["value"]
        changes.append(
            _change(section, UPDATED if fields else UNCHANGED, label, key, index, fields)
        )

    for key, item in before.items():
        if key not in matched:
            changes.append(_change(section, REMOVED, item, key))
    return changes


def _diff_summary(existing: Any, proposal: Any) -> list[dict[str, Any]]:
    """Diff the one scalar section, so it appears in the review like any other."""
    before = (existing or "").strip()
    after = (proposal or "").strip()
    if not after:
        if before:
            return [_change("summary", REMOVED, "Professional summary", "summary")]
        return []
    if not before:
        return [_change("summary", ADDED, "Professional summary", "summary", 0)]
    kind = UNCHANGED if before == after else UPDATED
    return [
        _change(
            "summary",
            kind,
            "Professional summary",
            "summary",
            0,
            [] if kind == UNCHANGED else ["summary"],
        )
    ]


def diff_profiles(
    existing: dict[str, Any] | None, proposal: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare a stored profile with a proposed one, entry by entry.

    Computed here rather than asked of the model, so what the review screen says
    changed is what actually changed.

    Args:
        existing: The stored ``parsed_json``, or None.
        proposal: The merged profile the model returned.

    Returns:
        ``(changes, summary)``. ``changes`` is one record per entry, in section
        order then proposal order, each ``{section, kind, label, key, index,
        fields}``. ``summary`` carries the totals and a per-section breakdown.
    """
    before = ParsedProfile.model_validate(existing or {}).model_dump()
    after = ParsedProfile.model_validate(proposal or {}).model_dump()

    changes: list[dict[str, Any]] = []
    for section in PROFILE_SECTIONS:
        if section == "summary":
            changes.extend(_diff_summary(before.get("summary"), after.get("summary")))
        elif section in STRING_SECTIONS:
            changes.extend(
                _diff_string_section(
                    section, before.get(section) or [], after.get(section) or []
                )
            )
        else:
            changes.extend(
                _diff_object_section(
                    section, before.get(section) or [], after.get(section) or []
                )
            )

    totals = {kind: 0 for kind in CHANGE_KINDS}
    sections: dict[str, dict[str, int]] = {}
    for change in changes:
        totals[change["kind"]] += 1
        counts = sections.setdefault(
            change["section"], {kind: 0 for kind in CHANGE_KINDS}
        )
        counts[change["kind"]] += 1

    summary: dict[str, Any] = dict(totals)
    summary["sections"] = sections
    return changes, summary


# --------------------------------------------------------------------------
# Applying an approved proposal
# --------------------------------------------------------------------------

# raw_text is appended to on every import and never pruned otherwise, so it
# needs a ceiling. The tail is kept rather than the head: the newest import is
# the one the user just reviewed.
MAX_RAW_TEXT_CHARS = 200000


def append_import_to_raw_text(
    raw_text: str | None,
    document_text: str,
    filename: str | None,
    when: datetime | None = None,
) -> str:
    """Append an imported document to the stored resume text, under a header.

    The header names the file and the date so a later re-extraction, or a human
    reading the stored text, can tell what came from where.

    Args:
        raw_text: The currently stored text, or None.
        document_text: The imported document's text.
        filename: The source file's name, for the header.
        when: The import date; defaults to now (UTC).

    Returns:
        The combined text, capped at :data:`MAX_RAW_TEXT_CHARS` by dropping the
        oldest characters.
    """
    stamp = (when or datetime.now(timezone.utc)).date().isoformat()
    header = "\n\n--- Imported from {} on {} ---\n".format(
        os.path.basename(filename or "an uploaded file"), stamp
    )
    combined = (raw_text or "") + header + (document_text or "")
    if len(combined) > MAX_RAW_TEXT_CHARS:
        combined = combined[-MAX_RAW_TEXT_CHARS:]
    return combined
