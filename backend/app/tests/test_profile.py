"""Tests for resume parsing, the profile routes, and gap detection.

Covers Phase 4 (onboarding and resume parsing) and Phase 5 (enrichment and gap
detection). Everything runs offline: the Groq call is patched out, and the
database is the ``FakeSession`` from ``conftest``. The one exception is
``test_live_extract_profile``, which is opt-in behind ``RUN_LIVE=1``.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.profile import (
    PROFILE_SECTIONS,
    ParsedProfile,
    ProfileValidationError,
    coerce_parsed_profile,
    format_profile_errors,
    validate_section_updates,
)
from app.core.config import settings
from app.core.errors import RESUME_EXTRACTION_FAILED
from app.models.profile import Profile
from app.services import llm, profile_service, resume_parser
from app.services.resume_parser import (
    EmptyResumeText,
    ProfileExtractionError,
    ResumeTextExtractionError,
    UnsupportedResumeFormat,
)
from app.tests.conftest import TEST_USER_ID, FakeSession
from app.tests.fixtures import SAMPLE_RESUME_TEXT, make_docx, make_pdf

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# What a well-behaved model returns. Kept small: the shape is what is under
# test, not the extraction quality.
SAMPLE_EXTRACTION = {
    "summary": "Backend engineer with six years of experience.",
    "work_experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Kestrel Payments",
            "location": "Bengaluru, India",
            "start_date": "March 2022",
            "end_date": "",
            "current": True,
            "highlights": ["Cut reconciliation from 40 minutes to 6."],
        }
    ],
    "education": [
        {
            "degree": "Master of Technology",
            "institution": "IIT Hyderabad",
            "field": "Computer Science",
            "start_date": "2017",
            "end_date": "2019",
            "details": "CGPA 8.7/10.",
        }
    ],
    "skills": ["Python", "Go", "PostgreSQL"],
    "certifications": [
        {"name": "AWS Certified Solutions Architect", "issuer": "AWS", "year": "2021"}
    ],
    "projects": [
        {
            "name": "Ledgerlite",
            "description": "An append-only ledger library.",
            "technologies": ["Go", "SQLite"],
            "link": "github.com/example/ledgerlite",
        }
    ],
    "achievements": ["Speaker, IndiaFOSS 2023."],
}


def make_profile(
    user_id: str = TEST_USER_ID,
    parsed_json: dict | None = None,
    raw_text: str = "raw resume text",
) -> Profile:
    """Build a Profile row the way the database would hand one back."""
    now = datetime.now(timezone.utc)
    return Profile(
        user_id=uuid.UUID(user_id),
        raw_text=raw_text,
        parsed_json=parsed_json if parsed_json is not None else dict(SAMPLE_EXTRACTION),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_groq(monkeypatch: pytest.MonkeyPatch):
    """Replace the Groq call with a canned response body.

    Returns a setter so a test can choose what the "model" says, including
    deliberately malformed output.
    """

    def set_response(body: str) -> None:
        monkeypatch.setattr(
            resume_parser, "_call_groq_extraction", lambda resume_text: body
        )

    set_response(json.dumps(SAMPLE_EXTRACTION))
    return set_response


# ==========================================================================
# Phase 4 -- format detection
# ==========================================================================


def test_detect_format_from_content_type() -> None:
    """The declared content type is authoritative when it is one we support."""
    assert resume_parser.detect_format("resume.bin", PDF_CONTENT_TYPE) == "pdf"
    assert resume_parser.detect_format("resume.bin", DOCX_CONTENT_TYPE) == "docx"


def test_detect_format_ignores_charset_parameter() -> None:
    """A content type with parameters still matches."""
    assert resume_parser.detect_format("cv.pdf", "application/pdf; charset=binary") == "pdf"


def test_detect_format_falls_back_to_extension() -> None:
    """Clients that send octet-stream are still parsed by extension."""
    assert (
        resume_parser.detect_format("resume.docx", "application/octet-stream") == "docx"
    )
    assert resume_parser.detect_format("resume.PDF", None) == "pdf"


def test_detect_format_rejects_other_types() -> None:
    """Anything that is not PDF or DOCX raises the typed error the route maps to 400."""
    with pytest.raises(UnsupportedResumeFormat):
        resume_parser.detect_format("headshot.png", "image/png")
    with pytest.raises(UnsupportedResumeFormat):
        resume_parser.detect_format("resume.txt", None)
    with pytest.raises(UnsupportedResumeFormat):
        resume_parser.detect_format(None, None)


# ==========================================================================
# Phase 4 -- text extraction
# ==========================================================================


def test_extract_text_from_pdf() -> None:
    """A generated PDF round-trips through pdfplumber with its lines intact."""
    pdf_bytes = make_pdf("Jordan Rivera\nSenior Backend Engineer\nSkills: Python, Go")

    text = resume_parser.extract_text(pdf_bytes, "resume.pdf", PDF_CONTENT_TYPE)

    assert "Jordan Rivera" in text
    assert "Senior Backend Engineer" in text
    assert "Skills: Python, Go" in text
    # Line structure is what tells the model where one bullet ends.
    assert text.index("Jordan Rivera") < text.index("Senior Backend Engineer")
    assert "\n" in text


def test_extract_text_from_pdf_reads_every_page() -> None:
    """Multi-line content across the page body is all captured."""
    lines = ["Line {}".format(index) for index in range(1, 31)]
    text = resume_parser.extract_text(
        make_pdf("\n".join(lines)), "resume.pdf", PDF_CONTENT_TYPE
    )
    for line in lines:
        assert line in text


def test_extract_text_from_docx_paragraphs_and_tables() -> None:
    """DOCX extraction covers body paragraphs and table cells.

    Table coverage matters: plenty of resumes lay skills out in a borderless
    table, and paragraph-only extraction drops all of it silently.
    """
    docx_bytes = make_docx(
        "Jordan Rivera\nSenior Backend Engineer",
        table_rows=[["Skills", "Python, Go"], ["Tools", "Docker, Kubernetes"]],
    )

    text = resume_parser.extract_text(docx_bytes, "resume.docx", DOCX_CONTENT_TYPE)

    assert "Jordan Rivera" in text
    assert "Python, Go" in text
    assert "Docker, Kubernetes" in text


def test_extract_text_rejects_unsupported_format() -> None:
    """extract_text refuses a file type before it tries to read the bytes."""
    with pytest.raises(UnsupportedResumeFormat):
        resume_parser.extract_text(b"\x89PNG\r\n", "headshot.png", "image/png")


def test_extract_text_raises_on_corrupt_pdf() -> None:
    """Bytes that claim to be a PDF but are not surface as an extraction error."""
    with pytest.raises(ResumeTextExtractionError):
        resume_parser.extract_text(b"not a pdf at all", "resume.pdf", PDF_CONTENT_TYPE)


def test_extract_text_raises_on_corrupt_docx() -> None:
    """A DOCX that is not a valid zip container is reported, not swallowed."""
    with pytest.raises(ResumeTextExtractionError):
        resume_parser.extract_text(b"PK not really", "resume.docx", DOCX_CONTENT_TYPE)


def test_extract_text_raises_on_textless_pdf() -> None:
    """A PDF with no text layer (a scan) gets its own error, not a silent empty parse."""
    with pytest.raises(EmptyResumeText):
        resume_parser.extract_text(make_pdf(""), "scan.pdf", PDF_CONTENT_TYPE)


# ==========================================================================
# Phase 4 -- Groq extraction
# ==========================================================================


def test_strip_code_fences() -> None:
    """A fenced response is unwrapped, an unfenced one is left alone."""
    assert resume_parser.strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert resume_parser.strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert resume_parser.strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_parse_json_response_recovers_from_surrounding_prose() -> None:
    """A stray sentence around the object does not lose the object."""
    parsed = resume_parser.parse_json_response(
        'Here is the profile:\n{"skills": ["Python"]}\nHope that helps.'
    )
    assert parsed == {"skills": ["Python"]}


def test_extract_profile_returns_structured_profile(mock_groq) -> None:
    """A well-formed model response becomes a fully populated ParsedProfile."""
    profile = resume_parser.extract_profile(SAMPLE_RESUME_TEXT)

    assert isinstance(profile, ParsedProfile)
    assert profile.summary == "Backend engineer with six years of experience."
    assert profile.work_experience[0].company == "Kestrel Payments"
    assert profile.work_experience[0].current is True
    assert profile.education[0].field == "Computer Science"
    assert profile.skills == ["Python", "Go", "PostgreSQL"]
    assert profile.certifications[0].issuer == "AWS"
    assert profile.projects[0].technologies == ["Go", "SQLite"]
    assert profile.achievements == ["Speaker, IndiaFOSS 2023."]


def test_extract_profile_accepts_fenced_json(mock_groq) -> None:
    """Models fall back into markdown fences; that is not a failure."""
    mock_groq("```json\n" + json.dumps(SAMPLE_EXTRACTION) + "\n```")
    assert resume_parser.extract_profile("some text").skills == [
        "Python",
        "Go",
        "PostgreSQL",
    ]


def test_extract_profile_raises_on_malformed_json(mock_groq) -> None:
    """Output with no recoverable JSON object is an error, not an empty profile."""
    mock_groq("I could not parse that resume, sorry.")
    with pytest.raises(ProfileExtractionError):
        resume_parser.extract_profile("some text")


def test_extract_profile_drops_bad_fields_rather_than_failing(mock_groq) -> None:
    """A partly-wrong response yields a partial profile instead of a 500.

    Losing the skills section is recoverable -- the user edits it on the profile
    page. Losing the whole upload is not.
    """
    mock_groq(
        json.dumps(
            {
                "summary": "  A summary.  ",
                "work_experience": [
                    {"title": "Engineer", "highlights": ["Did a thing", "Did a thing"]},
                    {"location": "Nowhere"},  # no title, no company -- unusable
                    "a bare string",
                ],
                "education": "not a list",
                "skills": ["Python", "python", "", None, "x" * 200],
                "certifications": ["Bare cert name"],
                "projects": [{"name": "Thing"}],
                "achievements": None,
            }
        )
    )

    profile = resume_parser.extract_profile("some text")

    assert profile.summary == "A summary."
    assert len(profile.work_experience) == 1
    assert profile.work_experience[0].highlights == ["Did a thing"]  # de-duplicated
    assert profile.education == []
    assert profile.skills == ["Python"]  # case-folded dedupe, over-long token dropped
    assert profile.certifications[0].name == "Bare cert name"
    assert profile.achievements == []


def test_extract_profile_rejects_blank_text() -> None:
    """No text means no model call at all."""
    with pytest.raises(EmptyResumeText):
        resume_parser.extract_profile("   \n  ")


def test_extract_profile_wraps_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead Groq surfaces as ProfileExtractionError, which the route maps to 502."""

    def boom(resume_text: str) -> str:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(resume_parser, "_call_groq_extraction", boom)
    with pytest.raises(ProfileExtractionError):
        resume_parser.extract_profile("some text")


def test_extraction_retries_on_the_other_provider_when_truncated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A response cut off at the ceiling is a 200, so only ``finish_reason`` shows it.

    Repairing the half-object would silently drop whatever came after the cut,
    and the user would never know a role was missing. Asking the other provider
    once costs a few seconds and usually returns the whole thing.
    """
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "azure_openai_endpoint", "https://test.openai.azure.com/")
    monkeypatch.setattr(settings, "azure_openai_api_key", "test-azure-key")

    truncated = json.dumps(SAMPLE_EXTRACTION)[: len(json.dumps(SAMPLE_EXTRACTION)) // 2]
    called: list[str] = []

    def groq(messages, **kwargs):
        called.append("groq")
        return llm.CompletionText(truncated, "length", kwargs["max_tokens"])

    def azure(messages, **kwargs):
        called.append("azure")
        return llm.CompletionText(json.dumps(SAMPLE_EXTRACTION), "stop", 900)

    monkeypatch.setattr(llm, "_complete_groq_json", groq)
    monkeypatch.setattr(llm, "_complete_azure_json", azure)

    with caplog.at_level(logging.WARNING, logger="app.services.resume_parser"):
        profile = resume_parser.extract_profile(SAMPLE_RESUME_TEXT)

    assert called == ["groq", "azure"]
    # The whole answer, not the repaired half: the second role survived.
    assert len(profile.work_experience) == len(SAMPLE_EXTRACTION["work_experience"])
    assert profile.skills == SAMPLE_EXTRACTION["skills"]
    assert "truncated at 16000 tokens by groq; retrying on azure" in caplog.text


def test_a_truncated_retry_that_also_fails_keeps_the_first_answer(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a profile beats a 502: the retry is an improvement, not a gate."""
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "azure_openai_endpoint", "https://test.openai.azure.com/")
    monkeypatch.setattr(settings, "azure_openai_api_key", "test-azure-key")

    body = json.dumps(SAMPLE_EXTRACTION)

    monkeypatch.setattr(
        llm,
        "_complete_groq_json",
        lambda messages, **kwargs: llm.CompletionText(body, "length", 16000),
    )

    def azure(messages, **kwargs):
        raise RuntimeError("azure is down too")

    monkeypatch.setattr(llm, "_complete_azure_json", azure)

    profile = resume_parser.extract_profile(SAMPLE_RESUME_TEXT)

    assert profile.skills == SAMPLE_EXTRACTION["skills"]


def test_coerce_parsed_profile_never_raises() -> None:
    """Coercion tolerates anything the model might emit."""
    assert coerce_parsed_profile(None) == ParsedProfile()
    assert coerce_parsed_profile("a string") == ParsedProfile()
    assert coerce_parsed_profile([1, 2, 3]) == ParsedProfile()


def test_parse_resume_returns_raw_text_and_parsed_json(mock_groq) -> None:
    """parse_resume returns exactly the two columns the profiles table stores."""
    result = resume_parser.parse_resume(
        make_pdf(SAMPLE_RESUME_TEXT), "resume.pdf", PDF_CONTENT_TYPE
    )

    assert set(result) == {"raw_text", "parsed_json"}
    assert "JORDAN A. RIVERA" in result["raw_text"]
    assert result["parsed_json"]["skills"] == ["Python", "Go", "PostgreSQL"]


# ==========================================================================
# Phase 4 -- routes: auth guard
# ==========================================================================


def test_get_profile_requires_auth(client: TestClient) -> None:
    """GET /profile is protected by get_current_user."""
    assert client.get("/profile").status_code == 401


def test_patch_profile_requires_auth(client: TestClient) -> None:
    """PATCH /profile is protected by get_current_user."""
    assert client.patch("/profile", json={}).status_code == 401


def test_upload_profile_requires_auth(client: TestClient) -> None:
    """POST /profile/upload is protected by get_current_user."""
    assert client.post("/profile/upload").status_code == 401


def test_get_gaps_requires_auth(client: TestClient) -> None:
    """GET /profile/gaps is protected by get_current_user."""
    assert client.get("/profile/gaps").status_code == 401


# ==========================================================================
# Phase 4 -- routes: upload
# ==========================================================================


def test_upload_creates_profile(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID, mock_groq
) -> None:
    """A first upload parses the file and writes a new profile row."""
    response = auth_client.post(
        "/profile/upload",
        files={"file": ("resume.pdf", make_pdf(SAMPLE_RESUME_TEXT), PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(test_user_uuid)
    assert "JORDAN A. RIVERA" in body["raw_text"]
    assert body["parsed_json"]["skills"] == ["Python", "Go", "PostgreSQL"]

    stored = db.get(Profile, test_user_uuid)
    assert stored is not None
    assert stored.parsed_json["work_experience"][0]["company"] == "Kestrel Payments"
    assert db.commits == 1


def test_upload_accepts_docx(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID, mock_groq
) -> None:
    """The DOCX path stores a profile the same way the PDF path does."""
    response = auth_client.post(
        "/profile/upload",
        files={
            "file": ("resume.docx", make_docx(SAMPLE_RESUME_TEXT), DOCX_CONTENT_TYPE)
        },
    )

    assert response.status_code == 200
    assert db.get(Profile, test_user_uuid) is not None


def test_upload_replaces_existing_profile(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID, mock_groq
) -> None:
    """Re-uploading replaces the stored resume rather than merging into it."""
    existing = db.seed(make_profile(parsed_json={"skills": ["COBOL"]}, raw_text="old"))
    created_at = existing.created_at

    response = auth_client.post(
        "/profile/upload",
        files={"file": ("resume.pdf", make_pdf(SAMPLE_RESUME_TEXT), PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 200
    stored = db.get(Profile, test_user_uuid)
    assert stored.parsed_json["skills"] == ["Python", "Go", "PostgreSQL"]
    assert "COBOL" not in json.dumps(stored.parsed_json)
    assert stored.created_at == created_at  # the row is the same one
    assert stored.updated_at >= created_at


def test_upload_rejects_unsupported_type(auth_client: TestClient, db: FakeSession) -> None:
    """A PNG is refused with 400 and never reaches the database."""
    response = auth_client.post(
        "/profile/upload",
        files={"file": ("headshot.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert response.status_code == 400
    assert "PDF and DOCX" in response.json()["detail"]
    assert db.store == {}


def test_upload_rejects_oversized_file(auth_client: TestClient, db: FakeSession) -> None:
    """A file over the 10MB cap is refused with 413 before any parsing happens."""
    oversized = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024)

    response = auth_client.post(
        "/profile/upload",
        files={"file": ("huge.pdf", oversized, PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 413
    assert "10MB" in response.json()["detail"]
    assert db.store == {}


def test_upload_rejects_empty_file(auth_client: TestClient) -> None:
    """A zero-byte upload is a 422, not a parser crash."""
    response = auth_client.post(
        "/profile/upload", files={"file": ("resume.pdf", b"", PDF_CONTENT_TYPE)}
    )
    assert response.status_code == 422


def test_upload_rejects_textless_pdf(auth_client: TestClient) -> None:
    """A scanned PDF gets a 422 that explains why, since there is no OCR."""
    response = auth_client.post(
        "/profile/upload",
        files={"file": ("scan.pdf", make_pdf(""), PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 422
    assert "scanned" in response.json()["detail"]


def test_upload_maps_extraction_failure_to_502(
    auth_client: TestClient, mock_groq
) -> None:
    """When the model fails, the user is told to retry -- not that their file is bad."""
    mock_groq("not json")

    response = auth_client.post(
        "/profile/upload",
        files={"file": ("resume.pdf", make_pdf(SAMPLE_RESUME_TEXT), PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == RESUME_EXTRACTION_FAILED


def test_upload_502_says_what_to_do_instead_of_quoting_the_provider(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The provider's error is a diagnostic; the detail is a message to a person.

    A real upload once answered with the whole of Groq's
    ``json_validate_failed`` body -- status code, vendor error code, and
    ``'failed_generation': 'max completion tokens reached...'`` -- rendered
    straight into a toast. It named nothing the user could act on. The raw text
    belongs in the log, where the request id can find it.
    """
    provider_error = (
        "Error code: 400 - {'error': {'message': 'Failed to generate JSON.', "
        "'code': 'json_validate_failed', 'failed_generation': 'max completion "
        "tokens reached before generating a valid document'}}"
    )

    def boom(resume_text: str) -> str:
        raise RuntimeError(provider_error)

    monkeypatch.setattr(resume_parser, "_call_groq_extraction", boom)

    with caplog.at_level(logging.ERROR, logger="app.api.routes.profile"):
        response = auth_client.post(
            "/profile/upload",
            files={
                "file": ("resume.pdf", make_pdf(SAMPLE_RESUME_TEXT), PDF_CONTENT_TYPE)
            },
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == RESUME_EXTRACTION_FAILED
    assert "Error code" not in detail
    assert "json_validate_failed" not in detail
    assert "failed_generation" not in detail
    # ...and none of it is lost: it is in the log, on a record that carries the
    # request id like every other.
    assert "json_validate_failed" in caplog.text


# ==========================================================================
# Phase 4 -- routes: read
# ==========================================================================


def test_get_profile_returns_404_when_absent(auth_client: TestClient) -> None:
    """The onboarding redirect depends on this exact 404 body."""
    response = auth_client.get("/profile")

    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


def test_get_profile_returns_stored_profile(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID
) -> None:
    """A stored profile comes back with every section."""
    db.seed(make_profile())

    response = auth_client.get("/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(test_user_uuid)
    assert body["parsed_json"]["work_experience"][0]["title"] == "Senior Backend Engineer"
    assert set(body["parsed_json"]) == set(PROFILE_SECTIONS)


# ==========================================================================
# Phase 5 -- routes: enrichment
# ==========================================================================


def test_patch_profile_replaces_one_section(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID
) -> None:
    """A provided section replaces that section; the others are untouched."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"skills": ["Rust", "Elixir"]})

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_json"]["skills"] == ["Rust", "Elixir"]
    assert body["parsed_json"]["work_experience"][0]["company"] == "Kestrel Payments"
    assert db.get(Profile, test_user_uuid).parsed_json["skills"] == ["Rust", "Elixir"]


def test_patch_profile_accepts_multiple_sections(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Several sections can be enriched in one request."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "summary": "A new summary.",
            "achievements": ["Award A", "Award B"],
        },
    )

    body = response.json()
    assert body["parsed_json"]["summary"] == "A new summary."
    assert body["parsed_json"]["achievements"] == ["Award A", "Award B"]
    assert body["parsed_json"]["skills"] == ["Python", "Go", "PostgreSQL"]


def test_patch_profile_accepts_wrapped_payload(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The ``{"parsed_json": {...}}`` wrapper is merged identically."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"parsed_json": {"skills": ["Rust"]}})

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Rust"]


def test_patch_profile_can_empty_a_section(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An explicit empty list clears a section -- deleting the last row must work."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"certifications": []})

    assert response.json()["parsed_json"]["certifications"] == []


def test_patch_profile_ignores_unknown_keys(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Extra keys are dropped rather than 422-ing a whole edit."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"favourite_colour": "green"})

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Python", "Go", "PostgreSQL"]


def test_patch_profile_returns_404_when_absent(auth_client: TestClient) -> None:
    """There is nothing to enrich before onboarding has run."""
    response = auth_client.patch("/profile", json={"skills": ["Rust"]})

    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


# ==========================================================================
# Phase 5 -- enrichment: required-field validation
# ==========================================================================

# The rule under test throughout this block: a *partially* filled entry missing
# a required field is a 422 the user can act on, while an entry with nothing in
# it at all is a stray editor row and is dropped without comment. The extraction
# path keeps its own, lenient rules -- the last test here guards that.


def test_patch_profile_accepts_a_complete_role(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A role naming both a title and a company saves."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"work_experience": [{"title": "Staff Engineer", "company": "Acme"}]},
    )

    assert response.status_code == 200
    roles = response.json()["parsed_json"]["work_experience"]
    assert [role["title"] for role in roles] == ["Staff Engineer"]


def test_patch_profile_rejects_a_role_without_a_company(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A half-filled role is the case that used to vanish silently on save."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {"title": "Staff Engineer", "company": "Acme"},
                {"title": "Analyst", "company": "   "},
            ]
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "work_experience[1]: company is required"
    assert body["errors"] == [
        {
            "section": "work_experience",
            "index": 1,
            "field": "company",
            "message": "Company is required",
        }
    ]


def test_patch_profile_rejects_a_role_without_a_title(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A company with no role attached is equally unusable downstream."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"work_experience": [{"company": "Acme"}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "work_experience",
            "index": 0,
            "field": "title",
            "message": "Job title is required",
        }
    ]


def test_patch_profile_drops_a_blank_role_without_erroring(
    auth_client: TestClient, db: FakeSession
) -> None:
    """"Added a row, never filled it" is not a mistake worth a 422."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {"title": "Staff Engineer", "company": "Acme"},
                {"title": "", "company": "  ", "location": None, "highlights": []},
                {},
            ]
        },
    )

    assert response.status_code == 200
    assert len(response.json()["parsed_json"]["work_experience"]) == 1


def test_patch_profile_drops_a_blank_role_even_when_its_toggle_is_set(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A flipped "I work here now" switch says nothing about the job."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"work_experience": [{"current": True}]}
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["work_experience"] == []


def test_patch_profile_accepts_education_with_a_degree(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An institution plus a degree is a complete education entry."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"education": [{"institution": "IIT Madras", "degree": "BTech"}]},
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["education"][0]["degree"] == "BTech"


def test_patch_profile_accepts_education_with_only_a_field(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Resumes name the subject as often as the qualification; either will do."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"education": [{"institution": "IIT Madras", "field": "Physics"}]},
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["education"][0]["field"] == "Physics"


def test_patch_profile_rejects_education_without_an_institution(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A degree from nowhere cannot be rendered on a resume."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"education": [{"degree": "BTech"}]})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "education",
            "index": 0,
            "field": "institution",
            "message": "Institution is required",
        }
    ]


def test_patch_profile_rejects_education_without_a_degree_or_field(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Naming the school alone does not say what was studied there."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"education": [{"institution": "IIT Madras"}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "education",
            "index": 0,
            "field": "degree",
            "message": "Degree or field of study is required",
        }
    ]


def test_patch_profile_rejects_a_certification_without_a_name(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An issuer and a year with no certification named is half a row."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"certifications": [{"issuer": "AWS", "year": "2021"}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "certifications",
            "index": 0,
            "field": "name",
            "message": "Certification name is required",
        }
    ]


def test_patch_profile_accepts_a_named_certification(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A name alone is enough; issuer and year stay optional."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"certifications": [{"name": "CKA"}]}
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["certifications"][0]["name"] == "CKA"


def test_patch_profile_rejects_a_project_without_a_name(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A described project with no name cannot be listed."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"projects": [{"description": "An append-only ledger."}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "projects",
            "index": 0,
            "field": "name",
            "message": "Project name is required",
        }
    ]


def test_patch_profile_accepts_a_named_project(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A name alone is a valid project row."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"projects": [{"name": "Ledgerlite"}]})

    assert response.status_code == 200
    assert response.json()["parsed_json"]["projects"][0]["name"] == "Ledgerlite"


def test_patch_profile_removes_blank_skills_without_erroring(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An empty chip in a tag input is a user mid-edit, not an error."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"skills": ["Python", "", "   ", "Go"]}
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Python", "Go"]


def test_patch_profile_deduplicates_skills_case_insensitively(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The first spelling wins; the rest are dropped rather than rejected."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"skills": ["Python", "python", "PYTHON", "Go"]}
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Python", "Go"]


def test_patch_profile_cleans_achievements_the_same_way(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Achievements follow the skills rules: blanks out, duplicates folded."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"achievements": ["Award A", "  ", "award a", "Award B"]},
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["achievements"] == ["Award A", "Award B"]


def test_patch_profile_trims_the_summary_and_allows_an_empty_one(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Whitespace is stripped, and clearing the summary is a legitimate edit."""
    db.seed(make_profile())

    trimmed = auth_client.patch("/profile", json={"summary": "  Backend engineer.  "})
    assert trimmed.json()["parsed_json"]["summary"] == "Backend engineer."

    cleared = auth_client.patch("/profile", json={"summary": "   "})
    assert cleared.status_code == 200
    assert cleared.json()["parsed_json"]["summary"] is None


def test_patch_profile_rejects_an_over_long_title(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A pasted paragraph in the title box gets a message naming the limit."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"work_experience": [{"title": "x" * 201, "company": "Acme"}]},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "work_experience",
            "index": 0,
            "field": "title",
            "message": "Job title must be 200 characters or less",
        }
    ]


def test_patch_profile_rejects_an_over_long_summary(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A section-level error carries a null index -- there is no row to point at."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"summary": "x" * 2001})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "summary",
            "index": None,
            "field": "summary",
            "message": "Summary must be 2000 characters or less",
        }
    ]
    assert response.json()["detail"] == (
        "summary: summary must be 2000 characters or less"
    )


def test_patch_profile_rejects_too_many_highlights(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A role with 21 bullets would dominate every generated output."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "highlights": ["Bullet {}".format(n) for n in range(21)],
                }
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "work_experience",
            "index": 0,
            "field": "highlights",
            "message": "Keep highlights to 20 or fewer",
        }
    ]


def test_patch_profile_rejects_an_over_long_highlight(
    auth_client: TestClient, db: FakeSession
) -> None:
    """One error per list, not one per bullet: the user gets the rule once."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "highlights": ["x" * 501, "y" * 501],
                }
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "work_experience",
            "index": 0,
            "field": "highlights",
            "message": "Each highlight must be 500 characters or less",
        }
    ]


def test_patch_profile_reports_every_problem_in_one_response(
    auth_client: TestClient, db: FakeSession
) -> None:
    """One save reports every bad entry, with the index of each."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {"title": "Engineer", "company": "Acme"},
                {"title": "Analyst"},
            ],
            "education": [{"degree": "BTech"}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == (
        "work_experience[1]: company is required; "
        "education[0]: institution is required"
    )
    assert [(e["section"], e["index"], e["field"]) for e in body["errors"]] == [
        ("work_experience", 1, "company"),
        ("education", 0, "institution"),
    ]


def test_patch_profile_writes_nothing_when_validation_fails(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID
) -> None:
    """A 422 must leave the stored profile exactly as it was."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "skills": ["Rust"],
            "work_experience": [{"company": "Acme"}],
        },
    )

    assert response.status_code == 422
    stored = db.get(Profile, test_user_uuid)
    assert db.commits == 0
    assert stored.parsed_json["skills"] == ["Python", "Go", "PostgreSQL"]
    assert stored.parsed_json["work_experience"][0]["title"] == "Senior Backend Engineer"


def test_patch_profile_only_validates_the_sections_it_was_sent(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A weak entry left by an old extraction never blocks an unrelated edit."""
    db.seed(
        make_profile(
            parsed_json={
                "summary": None,
                # No title: the lenient extraction path allows this.
                "work_experience": [{"company": "Kestrel Payments"}],
                "education": [],
                "skills": ["Python"],
                "certifications": [],
                "projects": [],
                "achievements": [],
            }
        )
    )

    response = auth_client.patch("/profile", json={"skills": ["Rust"]})

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Rust"]


def test_patch_profile_keeps_the_flattened_shape_for_malformed_bodies(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Pydantic's own 422 is unchanged: one sentence, and no ``errors`` key."""
    db.seed(make_profile())

    response = auth_client.patch("/profile", json={"skills": "Python"})

    assert response.status_code == 422
    body = response.json()
    assert "errors" not in body
    assert body["detail"].startswith("skills: ")


def test_upload_still_accepts_a_title_less_role(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID, mock_groq
) -> None:
    """Extraction stays lenient: strict rules apply to user edits only.

    A model that read the employer but missed the job title still produces a
    usable profile -- the user fixes the title on the profile page, which is
    exactly where the strict rules take over.
    """
    mock_groq(
        json.dumps(
            {
                "work_experience": [{"company": "Kestrel Payments"}],
                "education": [{"institution": "IIT Hyderabad"}],
                "skills": ["Python"],
            }
        )
    )

    response = auth_client.post(
        "/profile/upload",
        files={"file": ("resume.pdf", make_pdf(SAMPLE_RESUME_TEXT), PDF_CONTENT_TYPE)},
    )

    assert response.status_code == 200
    stored = db.get(Profile, test_user_uuid)
    assert stored.parsed_json["work_experience"][0]["company"] == "Kestrel Payments"
    assert stored.parsed_json["work_experience"][0]["title"] is None
    assert stored.parsed_json["education"][0]["institution"] == "IIT Hyderabad"


# ==========================================================================
# Phase 5 -- enrichment: the validator on its own
# ==========================================================================


def test_validate_section_updates_ignores_absent_sections() -> None:
    """Only what the user sent is inspected, and nothing else is invented."""
    assert validate_section_updates({}) == {}
    assert validate_section_updates({"skills": ["Go"]}) == {"skills": ["Go"]}


def test_validate_section_updates_drops_blank_entries_from_every_section() -> None:
    """Every section list treats an empty row the same way."""
    cleaned = validate_section_updates(
        {
            "work_experience": [{"title": "", "company": ""}],
            "education": [{"institution": None, "degree": "  "}],
            "certifications": [{"name": ""}],
            "projects": [{"name": "", "description": ""}],
        }
    )

    assert cleaned == {
        "work_experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
    }


def test_validate_section_updates_raises_with_structured_errors() -> None:
    """The exception carries both renderings the frontend needs."""
    with pytest.raises(ProfileValidationError) as raised:
        validate_section_updates({"projects": [{"description": "A thing."}]})

    assert raised.value.detail == "projects[0]: project name is required"
    assert raised.value.errors == [
        {
            "section": "projects",
            "index": 0,
            "field": "name",
            "message": "Project name is required",
        }
    ]


def test_format_profile_errors_joins_with_semicolons() -> None:
    """Several failures still fit in one toast."""
    detail = format_profile_errors(
        [
            {
                "section": "work_experience",
                "index": 1,
                "field": "company",
                "message": "Company is required",
            },
            {
                "section": "summary",
                "index": None,
                "field": "summary",
                "message": "Summary must be 2000 characters or less",
            },
        ]
    )

    assert detail == (
        "work_experience[1]: company is required; "
        "summary: summary must be 2000 characters or less"
    )


# ==========================================================================
# Phase 5 -- merge semantics
# ==========================================================================


def test_merge_profile_updates_leaves_omitted_sections_alone() -> None:
    """Section-by-section merge: absent means untouched, present means replaced."""
    existing = {"skills": ["Python"], "achievements": ["Award"]}

    merged = profile_service.merge_profile_updates(existing, {"skills": ["Rust"]})

    assert merged["skills"] == ["Rust"]
    assert merged["achievements"] == ["Award"]


def test_merge_profile_updates_fills_every_section() -> None:
    """The result always carries every section, so callers need no guards."""
    merged = profile_service.merge_profile_updates(None, {"skills": ["Rust"]})

    assert merged["skills"] == ["Rust"]
    assert merged["summary"] is None
    assert merged["work_experience"] == []
    assert merged["projects"] == []


def test_merge_profile_updates_does_not_mutate_its_input() -> None:
    """Callers keep whatever they passed in."""
    existing = {"skills": ["Python"]}

    profile_service.merge_profile_updates(existing, {"skills": ["Rust"]})

    assert existing == {"skills": ["Python"]}


def test_merge_profile_updates_ignores_unknown_sections() -> None:
    """A key that is not a profile section never reaches the stored JSON."""
    merged = profile_service.merge_profile_updates({}, {"nonsense": [1, 2, 3]})

    assert "nonsense" not in merged


# ==========================================================================
# Phase 5 -- gap detection
# ==========================================================================


def gap_ids(parsed_json) -> set:
    """The set of gap ids detected for a profile."""
    return {gap["id"] for gap in profile_service.detect_gaps(parsed_json)}


def test_detect_gaps_flags_every_empty_section() -> None:
    """An empty profile is missing every gap-checked section."""
    ids = gap_ids({})

    assert ids == {
        "summary-missing",
        "work_experience-missing",
        "education-missing",
        "skills-missing",
        "certifications-missing",
        "projects-missing",
        "achievements-missing",
    }
    assert all(
        gap["severity"] == "missing" for gap in profile_service.detect_gaps({})
    )


def test_detect_gaps_handles_no_profile_json() -> None:
    """A null parsed_json is treated as an empty profile, not a crash."""
    assert len(profile_service.detect_gaps(None)) == 7


def test_detect_gaps_returns_nothing_for_a_complete_profile() -> None:
    """A profile with every section filled produces no nudges at all."""
    complete = ParsedProfile.model_validate(SAMPLE_EXTRACTION).model_dump()
    complete["summary"] = " ".join(["word"] * 40)

    assert profile_service.detect_gaps(complete) == []


def test_detect_gaps_flags_a_short_summary() -> None:
    """A summary under 30 words reads as a placeholder."""
    gaps = profile_service.detect_gaps({"summary": "Backend engineer."})
    summary_gap = next(gap for gap in gaps if gap["section"] == "summary")

    assert summary_gap["id"] == "summary-thin"
    assert summary_gap["severity"] == "thin"


def test_detect_gaps_accepts_a_long_summary() -> None:
    """At the threshold, the summary is no longer a gap."""
    assert "summary-thin" not in gap_ids({"summary": " ".join(["word"] * 30)})
    assert "summary-missing" not in gap_ids({"summary": " ".join(["word"] * 30)})


def test_detect_gaps_flags_too_few_skills() -> None:
    """Under three skills cannot support a JD comparison."""
    ids = gap_ids({"skills": ["Python", "Go"]})

    assert "skills-thin" in ids
    assert "skills-missing" not in ids
    assert "skills-thin" not in gap_ids({"skills": ["Python", "Go", "SQL"]})


def test_detect_gaps_flags_roles_without_highlights() -> None:
    """A role with no bullet points gives tailored resumes nothing to draw on."""
    gaps = profile_service.detect_gaps(
        {
            "work_experience": [
                {"title": "Engineer", "company": "Acme", "highlights": []},
                {"title": "Analyst", "company": "Beta", "highlights": ["Did a thing"]},
            ]
        }
    )
    role_gap = next(gap for gap in gaps if gap["section"] == "work_experience")

    assert role_gap["id"] == "work_experience-thin"
    assert "Engineer" in role_gap["message"]
    assert "Analyst" not in role_gap["message"]


def test_detect_gaps_ignores_whitespace_only_highlights() -> None:
    """A bullet made of spaces is not a bullet."""
    ids = gap_ids(
        {"work_experience": [{"title": "Engineer", "highlights": ["   ", ""]}]}
    )
    assert "work_experience-thin" in ids


def test_detect_gaps_flags_education_without_a_degree() -> None:
    """An education entry with no qualification name reads wrong on a resume."""
    ids = gap_ids({"education": [{"institution": "Some University"}]})

    assert "education-thin" in ids
    assert "education-missing" not in ids
    assert "education-thin" not in gap_ids(
        {"education": [{"degree": "B.E.", "institution": "Some University"}]}
    )


def test_detect_gap_ids_are_stable_across_calls() -> None:
    """Dismissals are persisted by id, so the ids must not depend on list order."""
    first = {"work_experience": [{"title": "A"}, {"title": "B"}]}
    second = {"work_experience": [{"title": "B"}, {"title": "A"}]}

    assert gap_ids(first) == gap_ids(second)


def test_detect_gaps_on_a_thin_resume_is_actionable() -> None:
    """The sparse fixture produces nudges for most of the profile."""
    thin = ParsedProfile(
        work_experience=[{"title": "Junior Analyst", "company": "Harbourline"}],
        skills=["Excel"],
    ).model_dump()

    ids = gap_ids(thin)

    assert "summary-missing" in ids
    assert "work_experience-thin" in ids
    assert "skills-thin" in ids
    assert "education-missing" in ids


# ==========================================================================
# Phase 5 -- routes: gaps
# ==========================================================================


def test_get_gaps_returns_nudges(auth_client: TestClient, db: FakeSession) -> None:
    """GET /profile/gaps returns the detected gaps under a "gaps" key."""
    db.seed(make_profile(parsed_json={"skills": ["Python"]}))

    response = auth_client.get("/profile/gaps")

    assert response.status_code == 200
    body = response.json()
    ids = {gap["id"] for gap in body["gaps"]}
    assert "skills-thin" in ids
    assert "work_experience-missing" in ids
    assert all({"id", "section", "severity", "message"} <= set(gap) for gap in body["gaps"])


def test_get_gaps_is_empty_for_a_complete_profile(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A complete profile stops nudging entirely."""
    complete = ParsedProfile.model_validate(SAMPLE_EXTRACTION).model_dump()
    complete["summary"] = " ".join(["word"] * 40)
    db.seed(make_profile(parsed_json=complete))

    assert auth_client.get("/profile/gaps").json() == {"gaps": []}


def test_get_gaps_returns_404_when_absent(auth_client: TestClient) -> None:
    """No profile means the same 404 as GET /profile, so either call can redirect."""
    response = auth_client.get("/profile/gaps")

    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


# ==========================================================================
# Opt-in live model test
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Groq test. Set RUN_LIVE=1 to run it.",
)
def test_live_extraction_accepts_the_larger_token_ceiling() -> None:
    """Confirm Groq serves the raised ceiling, and report how much of it was used.

    The bug this guards is invisible offline: 4096 tokens was a legal request
    that simply ran out mid-JSON, and the only way to know 16000 is both
    accepted by the API and enough for a full extraction is to ask. Run with
    ``-s`` to see the finish reason and the token count.
    """
    content, meta = llm.complete_json_with_meta(
        [
            {"role": "system", "content": resume_parser.EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": resume_parser.EXTRACTION_USER_TEMPLATE.format(
                    resume_text=SAMPLE_RESUME_TEXT
                ),
            },
        ],
        max_tokens=resume_parser.EXTRACTION_MAX_TOKENS,
        temperature=resume_parser.EXTRACTION_TEMPERATURE,
        prefer=llm.GROQ,
        purpose="resume extraction",
    )

    print(
        "\nlive extraction: provider={} max_tokens={} finish_reason={} "
        "completion_tokens={}".format(
            meta["provider"],
            resume_parser.EXTRACTION_MAX_TOKENS,
            meta["finish_reason"],
            meta["completion_tokens"],
        )
    )

    # Groq accepted the ceiling rather than rejecting the request for it...
    assert meta["provider"] == llm.GROQ
    # ...and the answer ended because the model was finished, not because it ran
    # out of room, which is the whole point of raising it.
    assert meta["finish_reason"] == "stop"
    assert json.loads(resume_parser.strip_code_fences(str(content)))


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Groq test. Set RUN_LIVE=1 to run it.",
)
def test_live_extract_profile() -> None:
    """Run the real extraction prompt against the fictional sample resume.

    This is the only test that spends a model call, so it is opt-in. It guards
    the prompt itself: the offline tests all mock the response and would happily
    pass with a prompt that returns nothing useful.
    """
    profile = resume_parser.extract_profile(SAMPLE_RESUME_TEXT)

    assert profile.summary and len(profile.summary.split()) > 15
    assert len(profile.work_experience) == 2
    assert len(profile.education) == 2
    assert len(profile.certifications) == 2
    assert len(profile.projects) == 2
    assert len(profile.achievements) >= 3

    current = profile.work_experience[0]
    assert current.company == "Kestrel Payments"
    assert current.current is True
    assert current.start_date and "2022" in current.start_date
    assert len(current.highlights) >= 3

    # Grouped skill lines must be split into tokens with the category label
    # dropped -- "Languages: Python, Go, SQL" is three skills, not one.
    assert {"Python", "Go", "PostgreSQL", "Kubernetes"} <= set(profile.skills)
    assert not any(skill.lower().startswith("languages") for skill in profile.skills)
    assert all(len(skill) <= 60 for skill in profile.skills)

    # The prompt forbids returning contact details.
    serialised = json.dumps(profile.model_dump()).lower()
    assert "jordan.rivera@example.com" not in serialised
    assert "+91 90000" not in serialised


# ==========================================================================
# The extended schema
# ==========================================================================

# Every field added here is optional or defaulted, so a profile stored before
# any of them existed has to load unchanged. That is the first test below, and
# it is the one that would break a live deployment if the schema ever stopped
# being additive.

# A profile in the shape the database held before the schema was extended.
LEGACY_PARSED_JSON = {
    "summary": "Backend engineer.",
    "work_experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Kestrel Payments",
            "location": "Bengaluru",
            "start_date": "March 2022",
            "end_date": "",
            "current": True,
            "highlights": ["Cut reconciliation from 40 minutes to 6."],
        }
    ],
    "education": [
        {
            "degree": "Master of Technology",
            "institution": "IIT Hyderabad",
            "field": "Computer Science",
            "start_date": "2017",
            "end_date": "2019",
            "details": "CGPA 8.7/10.",
        }
    ],
    "skills": ["Python"],
    "certifications": [{"name": "CKA", "issuer": "CNCF", "year": "2023"}],
    "projects": [
        {
            "name": "Ledgerlite",
            "description": "A ledger library.",
            "technologies": ["Go"],
            "link": "github.com/example/ledgerlite",
        }
    ],
    "achievements": ["Speaker, IndiaFOSS 2023."],
}


def test_a_legacy_profile_loads_unchanged() -> None:
    """Stored JSON from before the extension keeps every value it had."""
    profile = ParsedProfile.model_validate(LEGACY_PARSED_JSON)

    assert profile.summary == "Backend engineer."
    assert profile.work_experience[0].company == "Kestrel Payments"
    assert profile.work_experience[0].highlights == [
        "Cut reconciliation from 40 minutes to 6."
    ]
    assert profile.education[0].details == "CGPA 8.7/10."
    assert profile.certifications[0].year == "2023"
    assert profile.projects[0].link == "github.com/example/ledgerlite"
    assert profile.achievements == ["Speaker, IndiaFOSS 2023."]


def test_a_legacy_profile_gains_the_new_fields_as_empty() -> None:
    """The new fields default rather than appearing as nulls the UI must guard."""
    profile = ParsedProfile.model_validate(LEGACY_PARSED_JSON)

    assert profile.publications == []
    assert profile.work_experience[0].employment_type is None
    assert profile.work_experience[0].awards == []
    assert profile.education[0].gpa is None
    assert profile.education[0].coursework == []
    assert profile.projects[0].highlights == []
    assert profile.projects[0].links.github is None
    assert profile.certifications[0].expires is None


def test_coercion_reads_every_new_field() -> None:
    """The lenient pass fills the new fields from model output."""
    profile = coerce_parsed_profile(
        {
            "work_experience": [
                {
                    "title": "Backend Engineer",
                    "company": "Aldermill",
                    "employment_type": "Internship",
                    "awards": ["Intern of the Year", "", "Intern of the Year"],
                }
            ],
            "education": [
                {
                    "institution": "IIT Hyderabad",
                    "degree": "M.Tech",
                    "gpa": "8.7/10",
                    "coursework": ["Compilers", "Distributed Systems"],
                    "honors": ["Gold medal"],
                }
            ],
            "certifications": [
                {
                    "name": "CKA",
                    "expires": "2026",
                    "credential_url": "https://example.com/cka",
                    "description": "Kubernetes administration.",
                }
            ],
            "projects": [
                {
                    "name": "Tracewire",
                    "start_date": "2023",
                    "end_date": "2024",
                    "highlights": ["Sampled by error budget burn"],
                    "links": {"github": "https://github.com/example/tracewire"},
                }
            ],
            "publications": [
                {
                    "title": "Reconciling at Scale",
                    "authors": "Rivera, J.",
                    "url": "https://example.com/paper",
                    "status": "Published",
                    "year": "2023",
                }
            ],
        }
    )

    role = profile.work_experience[0]
    assert role.employment_type == "Internship"
    # Blanks and repeats are dropped, as everywhere else in the lenient pass.
    assert role.awards == ["Intern of the Year"]
    education = profile.education[0]
    assert education.gpa == "8.7/10"
    assert education.coursework == ["Compilers", "Distributed Systems"]
    assert education.honors == ["Gold medal"]
    assert profile.certifications[0].expires == "2026"
    assert profile.certifications[0].description == "Kubernetes administration."
    assert profile.projects[0].highlights == ["Sampled by error budget burn"]
    assert profile.publications[0].status == "Published"


def test_coercion_backfills_the_legacy_project_link() -> None:
    """A project with only `links` still exposes `link` for older readers."""
    profile = coerce_parsed_profile(
        {
            "projects": [
                {"name": "A", "links": {"live": "https://a.example.com"}},
                {"name": "B", "links": {"github": "https://github.com/b"}},
                {"name": "C", "link": "https://c.example.com", "links": {}},
            ]
        }
    )

    assert profile.projects[0].link == "https://a.example.com"
    assert profile.projects[1].link == "https://github.com/b"
    # An explicit link is never overwritten by the links block.
    assert profile.projects[2].link == "https://c.example.com"


def test_coercion_reads_a_bare_string_publication() -> None:
    """A model that returns a list of titles is still usable."""
    profile = coerce_parsed_profile({"publications": ["Reconciling at Scale", "  "]})
    assert [item.title for item in profile.publications] == ["Reconciling at Scale"]


def test_patch_profile_accepts_a_publication(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A titled publication is stored with its metadata."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "publications": [
                {
                    "title": "Reconciling at Scale",
                    "authors": "Rivera, J.",
                    "status": "Published",
                    "year": "2023",
                }
            ]
        },
    )

    assert response.status_code == 200
    stored = response.json()["parsed_json"]["publications"]
    assert stored[0]["title"] == "Reconciling at Scale"
    assert stored[0]["authors"] == "Rivera, J."


def test_patch_profile_rejects_a_publication_without_a_title(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A partially filled publication is a 422 naming the field."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile", json={"publications": [{"authors": "Rivera, J."}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "section": "publications",
            "index": 0,
            "field": "title",
            "message": "Publication title is required",
        }
    ]


def test_patch_profile_drops_a_blank_publication(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An entirely empty row is one the editor added, not a mistake."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={"publications": [{"title": "A Paper"}, {"title": "", "year": ""}]},
    )

    assert response.status_code == 200
    assert len(response.json()["parsed_json"]["publications"]) == 1


def test_patch_profile_keeps_a_project_that_only_has_links(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A row whose only content is a URL is not a blank row."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "projects": [
                {"name": "Tracewire", "links": {"github": "https://github.com/x"}}
            ]
        },
    )

    assert response.status_code == 200
    project = response.json()["parsed_json"]["projects"][0]
    assert project["links"]["github"] == "https://github.com/x"
    assert project["link"] == "https://github.com/x"


def test_patch_profile_rejects_an_over_long_new_field(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The new fields carry length limits like every other one."""
    db.seed(make_profile())

    response = auth_client.patch(
        "/profile",
        json={
            "work_experience": [
                {
                    "title": "Engineer",
                    "company": "Kestrel",
                    "employment_type": "x" * 101,
                }
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "employment_type"


def test_detect_gaps_never_asks_for_publications() -> None:
    """Most people have none, and a nudge that can only be dismissed is noise."""
    gaps = profile_service.detect_gaps({})
    assert not any(gap["section"] == "publications" for gap in gaps)
    assert "publications-missing" not in {gap["id"] for gap in gaps}


# ==========================================================================
# Plain-text rendering
# ==========================================================================


def test_render_profile_text_includes_every_section() -> None:
    """The full rendering is complete: nothing capped, nothing summarised."""
    parsed = {
        **LEGACY_PARSED_JSON,
        "work_experience": [
            {
                **LEGACY_PARSED_JSON["work_experience"][0],
                "employment_type": "Full-time",
                "awards": ["Engineer of the Year"],
            }
        ],
        "education": [
            {
                **LEGACY_PARSED_JSON["education"][0],
                "gpa": "8.7/10",
                "coursework": ["Compilers"],
                "honors": ["Gold medal"],
            }
        ],
        "projects": [
            {
                **LEGACY_PARSED_JSON["projects"][0],
                "highlights": ["Used by two fintech teams"],
                "links": {"github": "https://github.com/example/ledgerlite"},
            }
        ],
        "publications": [
            {"title": "Reconciling at Scale", "authors": "Rivera, J.", "year": "2023"}
        ],
    }

    text = profile_service.render_profile_text(parsed)

    for heading in (
        "SUMMARY",
        "WORK EXPERIENCE",
        "EDUCATION",
        "SKILLS",
        "CERTIFICATIONS",
        "PROJECTS",
        "ACHIEVEMENTS",
        "PUBLICATIONS",
    ):
        assert heading in text

    assert "Senior Backend Engineer at Kestrel Payments" in text
    assert "March 2022 - Present" in text
    assert "Full-time" in text
    assert "Engineer of the Year" in text
    assert "GPA: 8.7/10" in text
    assert "Coursework: Compilers" in text
    assert "Honours: Gold medal" in text
    assert "Used by two fintech teams" in text
    assert "GitHub: https://github.com/example/ledgerlite" in text
    assert "Reconciling at Scale" in text


def test_render_profile_text_omits_empty_sections() -> None:
    """An empty profile renders as nothing, not as a page of headings."""
    assert profile_service.render_profile_text({}) == ""
    assert profile_service.render_profile_text(None) == ""

    only_skills = profile_service.render_profile_text({"skills": ["Python", "Go"]})
    assert only_skills == "SKILLS\nPython, Go"


def test_render_profile_text_does_not_repeat_a_project_link() -> None:
    """`link` mirrors `links.github`, so it is printed once."""
    text = profile_service.render_profile_text(
        {
            "projects": [
                {
                    "name": "Ledgerlite",
                    "link": "https://github.com/x",
                    "links": {"github": "https://github.com/x"},
                }
            ]
        }
    )
    assert text.count("https://github.com/x") == 1


# ==========================================================================
# Recovering a truncated model response
# ==========================================================================

# The real fix for a cut-off response is to ask for less of it, which is what
# import_service does when finish_reason is "length". This is the last resort
# under that: some data beats none, and the WARNING says the result is partial.


def test_repair_truncated_json_closes_open_structures() -> None:
    """A response cut off mid-string loses that entry and keeps the rest."""
    truncated = (
        '{"skills": ["Python", "Go"], "work_experience": [{"title": "Engineer", '
        '"company": "Kestrel", "highlights": ["Shipped it", "Half a bul'
    )
    parsed = resume_parser.parse_json_response(truncated)

    assert parsed["skills"] == ["Python", "Go"]
    assert parsed["work_experience"][0]["company"] == "Kestrel"
    assert parsed["work_experience"][0]["highlights"] == ["Shipped it"]


def test_repair_truncated_json_drops_a_key_with_no_value() -> None:
    """A dangling key would be invalid JSON, so it goes with its comma."""
    parsed = resume_parser.parse_json_response('{"a": "x", "b":')
    assert parsed == {"a": "x"}


def test_repair_truncated_json_keeps_completed_bare_literals() -> None:
    """A comma proves the value before it finished, numbers included."""
    parsed = resume_parser.parse_json_response('{"a": 1, "b": [1, 2,')
    assert parsed == {"a": 1, "b": [1, 2]}


def test_repair_truncated_json_gives_up_on_a_non_object() -> None:
    """Prose is not a truncated object, and pretending otherwise hides a bug."""
    assert resume_parser.repair_truncated_json("no json at all") is None
    with pytest.raises(ProfileExtractionError):
        resume_parser.parse_json_response("no json at all")


def test_repair_is_not_reached_by_a_well_formed_response() -> None:
    """The repair only ever runs after both honest parses have failed."""
    assert resume_parser.parse_json_response('{"valid": true}') == {"valid": True}
    assert resume_parser.parse_json_response(
        'Here you go:\n```json\n{"valid": true}\n```'
    ) == {"valid": True}
