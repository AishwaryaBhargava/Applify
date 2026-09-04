"""Resume parsing: PDF and DOCX text extraction.

Files are parsed in memory and discarded -- nothing is written to disk and no
file storage is used. Only the extracted text and its structured parse are
persisted.

Phase 1 scaffolding. Implemented in Phase 4.
"""

from typing import Any

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class UnsupportedResumeFormat(Exception):
    """Raised when an uploaded file is neither a PDF nor a DOCX."""


def detect_format(filename: str, content_type: str | None = None) -> str:
    """Return ``"pdf"`` or ``"docx"`` for an uploaded file.

    Raises:
        UnsupportedResumeFormat: If the file is neither format.
    """
    raise NotImplementedError("Implemented in Phase 4")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    raise NotImplementedError("Implemented in Phase 4")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from DOCX bytes using python-docx."""
    raise NotImplementedError("Implemented in Phase 4")


def extract_text(file_bytes: bytes, filename: str, content_type: str | None = None) -> str:
    """Detect the format and return the resume's raw text."""
    raise NotImplementedError("Implemented in Phase 4")


def parse_resume(file_bytes: bytes, filename: str, content_type: str | None = None) -> dict[str, Any]:
    """Extract text and turn it into a structured profile dict.

    Returns:
        A dict matching ``api.schemas.profile.ParsedProfile``, plus the raw text
        under ``raw_text``.
    """
    raise NotImplementedError("Implemented in Phase 4")
