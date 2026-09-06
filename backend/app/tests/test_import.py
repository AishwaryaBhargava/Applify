"""Tests for the supplementary-file import: extraction, diff, and the routes.

Everything here runs offline. The merge call is replaced with a canned response
so the tests are about the extraction, the deterministic diff, and what the
apply route writes -- none of which should depend on a model being reachable.
``test_live_import_workbook`` is the one exception and is opt-in behind
``RUN_LIVE=1``.

The workbook the tests read is built in-process by ``fixtures.make_xlsx``, so
the file under test and the expectation of it sit next to each other.
"""

import csv
import io
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.profile import Profile
from app.services import import_service
from app.services.import_service import (
    SKIPPED_REFERENCES,
    diff_profiles,
    extract_document_text,
    is_reference_sheet,
    propose_import,
    split_document,
)
from app.tests.conftest import TEST_USER_ID, FakeSession
from app.tests.fixtures import SAMPLE_WORKBOOK, make_docx, make_pdf, make_xlsx

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# A small stored profile the import merges into. One role, one degree, two
# skills -- enough for every diff kind to appear in one comparison.
EXISTING_PROFILE = {
    "summary": "Backend engineer with six years of experience.",
    "work_experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Kestrel Payments",
            "start_date": "March 2022",
            "current": True,
            "highlights": ["Owned the settlement ledger migration"],
        }
    ],
    "education": [
        {
            "degree": "Master of Technology",
            "institution": "Indian Institute of Technology, Hyderabad",
            "field": "Computer Science",
        }
    ],
    "skills": ["Python", "PostgreSQL"],
    "certifications": [],
    "projects": [],
    "achievements": [],
    "publications": [],
}


def make_profile(
    user_id: str = TEST_USER_ID,
    parsed_json: dict | None = None,
    raw_text: str = "original resume text",
) -> Profile:
    """Build a Profile row the way the database would hand one back."""
    now = datetime.now(timezone.utc)
    return Profile(
        user_id=uuid.UUID(user_id),
        raw_text=raw_text,
        parsed_json=EXISTING_PROFILE if parsed_json is None else parsed_json,
        created_at=now,
        updated_at=now,
    )


def make_csv(rows: list[list[str]]) -> bytes:
    """Serialise rows as CSV bytes."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture
def mock_merge(monkeypatch: pytest.MonkeyPatch):
    """Replace the merge model call with a canned JSON body.

    Returns a setter and records the calls, so a test can assert both on what
    came back and on what was sent -- which provider was preferred, and how many
    passes ran.
    """
    calls: list[dict] = []

    def set_response(body) -> None:
        payload = body if isinstance(body, str) else json.dumps(body)

        def fake_complete_json(messages, **kwargs):
            calls.append({"messages": messages, **kwargs})
            return payload

        monkeypatch.setattr(
            import_service.llm, "complete_json", fake_complete_json
        )

    set_response(EXISTING_PROFILE)
    set_response.calls = calls  # type: ignore[attr-defined]
    return set_response


# ==========================================================================
# Reference detection
# ==========================================================================


def test_reference_sheet_detected_by_name() -> None:
    """A sheet named for letters of recommendation is a reference sheet."""
    assert is_reference_sheet("LORs", ["Name"])
    assert is_reference_sheet("References", ["Name"])
    assert is_reference_sheet("Recommenders", ["Name"])
    assert is_reference_sheet("Referees", ["Name"])


def test_reference_sheet_detected_by_headers() -> None:
    """Email plus phone columns is a contact list for other people."""
    assert is_reference_sheet("Contacts", ["Name", "Email", "Mobile"])
    assert is_reference_sheet("People", ["Full name", "E-mail address", "Phone"])


def test_reference_detection_does_not_match_on_a_substring() -> None:
    """"lor" is matched as a word, so an ordinary sheet is not skipped."""
    assert not is_reference_sheet("Colors", ["Name", "Hex"])
    assert not is_reference_sheet("Explorations", ["Project", "Year"])


def test_an_email_column_alone_is_not_a_reference_sheet() -> None:
    """One contact column is not enough -- a certificates tab may carry a URL."""
    assert not is_reference_sheet("Certificates", ["Name", "Issuer", "Email"])


# ==========================================================================
# Extraction
# ==========================================================================


def test_extract_xlsx_renders_one_markdown_table_per_sheet() -> None:
    """Each sheet becomes a headed markdown table under its own heading."""
    document = extract_document_text(make_xlsx(SAMPLE_WORKBOOK), "career.xlsx")

    assert document["structure"]["kind"] == "xlsx"
    text = document["text"]
    assert "## Sheet: Education" in text
    assert "## Sheet: Work Experiences" in text
    assert "| Degree | Institution | Field | Start | End | GPA | Coursework |" in text
    assert "| --- | --- | --- | --- | --- | --- | --- |" in text
    assert "Master of Technology" in text


def test_extract_xlsx_reports_row_and_column_counts() -> None:
    """Every sheet is reported with its real size, skipped or not."""
    document = extract_document_text(make_xlsx(SAMPLE_WORKBOOK), "career.xlsx")

    sheets = {sheet["name"]: sheet for sheet in document["structure"]["sheets"]}
    assert [sheet["name"] for sheet in document["structure"]["sheets"]] == list(
        SAMPLE_WORKBOOK
    )
    assert sheets["Education"]["rows"] == 3
    assert sheets["Education"]["cols"] == 7
    assert sheets["Publications"]["rows"] == 2


def test_extract_xlsx_skips_the_references_sheet_and_says_so() -> None:
    """The LORs tab is reported, excluded from the text, and explained."""
    document = extract_document_text(make_xlsx(SAMPLE_WORKBOOK), "career.xlsx")

    sheets = {sheet["name"]: sheet for sheet in document["structure"]["sheets"]}
    assert sheets["LORs"]["skipped_reason"] == SKIPPED_REFERENCES
    assert "skipped_reason" not in sheets["Education"]

    text = document["text"]
    assert "## Sheet: LORs" not in text
    # Nothing from the sheet reaches the text that is sent to a model.
    assert "Beltrame" not in text
    assert "ana.beltrame@example.edu" not in text
    assert "+91 90000 11111" not in text


def test_extract_xlsx_keeps_newlines_inside_a_cell_as_a_separator() -> None:
    """A multi-line cell stays on one table row, joined with " / "."""
    document = extract_document_text(make_xlsx(SAMPLE_WORKBOOK), "career.xlsx")
    assert (
        "Owned the settlement ledger migration / Mentored four engineers"
        in document["text"]
    )


def test_extract_xlsx_renders_whole_numbers_without_a_decimal_point() -> None:
    """openpyxl reads every number as a float; "2019.0" is not a year."""
    document = extract_document_text(
        make_xlsx({"Years": [["Year"], [2019]]}), "years.xlsx"
    )
    assert "| 2019 |" in document["text"]
    assert "2019.0" not in document["text"]


def test_extract_xlsx_drops_empty_rows_and_pads_short_ones() -> None:
    """A ragged sheet still renders as one rectangular table."""
    document = extract_document_text(
        make_xlsx({"Skills": [["Skill", "Level"], [], ["Python"]]}), "s.xlsx"
    )
    lines = [line for line in document["text"].splitlines() if line.startswith("|")]
    assert len(lines) == 3  # header, separator, one row
    assert lines[-1] == "| Python |  |"


def test_extract_xlsx_raises_on_a_workbook_of_references_only() -> None:
    """A file with nothing but referees has nothing to import."""
    with pytest.raises(import_service.EmptyDocumentText, match="reference"):
        extract_document_text(
            make_xlsx({"LORs": SAMPLE_WORKBOOK["LORs"]}), "refs.xlsx"
        )


def test_extract_csv_renders_a_markdown_table() -> None:
    """A CSV is one table, named after the file."""
    document = extract_document_text(
        make_csv([["Skill", "Years"], ["Python", "6"], ["Go", "3"]]), "skills.csv"
    )

    assert document["structure"]["kind"] == "csv"
    assert document["structure"]["sheets"][0]["name"] == "skills"
    assert document["structure"]["sheets"][0]["rows"] == 3
    assert "## Sheet: skills" in document["text"]
    assert "| Python | 6 |" in document["text"]


def test_extract_csv_skips_a_reference_table() -> None:
    """The same rule applies to a CSV of referees."""
    with pytest.raises(import_service.EmptyDocumentText):
        extract_document_text(
            make_csv([["Name", "Email", "Phone"], ["A", "a@example.com", "123"]]),
            "references.csv",
        )


def test_extract_csv_sniffs_a_semicolon_delimiter() -> None:
    """A European CSV export is a table, not one column of pasted text."""
    document = extract_document_text(
        b"Skill;Years\nPython;6\nGo;3\n", "skills.csv"
    )
    assert "| Python | 6 |" in document["text"]


def test_extract_reuses_the_resume_readers_for_docx_and_pdf() -> None:
    """DOCX and PDF go through the same extraction the resume upload uses."""
    docx = extract_document_text(make_docx("Extra project notes"), "notes.docx")
    assert docx["structure"]["kind"] == "docx"
    assert "Extra project notes" in docx["text"]

    pdf = extract_document_text(make_pdf("Extra project notes"), "notes.pdf")
    assert pdf["structure"]["kind"] == "pdf"
    assert "Extra project notes" in pdf["text"]


def test_extract_pretty_prints_json() -> None:
    """A JSON file is reformatted so the model reads a stable shape."""
    document = extract_document_text(b'{"skills":["Python","Go"]}', "profile.json")
    assert document["structure"]["kind"] == "json"
    assert '"skills": [' in document["text"]


def test_extract_falls_back_to_text_for_invalid_json() -> None:
    """A nearly-JSON notes file is still worth importing."""
    document = extract_document_text(b"{not really json}", "notes.json")
    assert document["text"] == "{not really json}"


def test_extract_reads_markdown_and_text() -> None:
    """Plain formats are decoded and passed through."""
    for name in ("notes.md", "notes.txt"):
        document = extract_document_text("# Notes\n- Kafka".encode("utf-8"), name)
        assert "Kafka" in document["text"]


def test_extract_prefers_the_extension_over_a_generic_content_type() -> None:
    """A browser sending text/csv as text/plain still gets a table."""
    document = extract_document_text(
        make_csv([["Skill"], ["Python"]]), "skills.csv", "text/plain"
    )
    assert document["structure"]["kind"] == "csv"


def test_extract_falls_back_to_the_content_type_without_an_extension() -> None:
    """A file with no extension is read from what the client declared."""
    document = extract_document_text(
        make_xlsx({"Skills": [["Skill"], ["Go"]]}), "download", XLSX_CONTENT_TYPE
    )
    assert document["structure"]["kind"] == "xlsx"


def test_extract_rejects_an_unsupported_format() -> None:
    """An image is not an importable document."""
    with pytest.raises(import_service.UnsupportedDocumentFormat):
        extract_document_text(b"\x89PNG", "photo.png", "image/png")


def test_extract_rejects_an_oversized_file() -> None:
    """The 10MB cap is enforced in the service, not only in the route."""
    with pytest.raises(import_service.DocumentTooLarge):
        extract_document_text(b"x" * (import_service.MAX_IMPORT_BYTES + 1), "big.txt")


def test_extract_raises_on_a_corrupt_workbook() -> None:
    """A file claiming to be XLSX but is not is a read error, not a 500."""
    with pytest.raises(import_service.DocumentReadError):
        extract_document_text(b"not a workbook", "career.xlsx")


# ==========================================================================
# Splitting long documents
# ==========================================================================


def test_split_document_keeps_a_short_document_whole() -> None:
    """One pass is the normal case."""
    assert split_document("## Sheet: A\n| x |") == ["## Sheet: A\n| x |"]


def test_split_document_splits_on_sheet_boundaries() -> None:
    """A sheet is the seam, so no pass ever sees a header-less table body."""
    sheets = ["## Sheet: S{}\n{}".format(i, "row\n" * 200) for i in range(4)]
    parts = split_document("\n".join(sheets), limit=1200)

    assert len(parts) > 1
    for part in parts:
        assert part.startswith("## Sheet: ")
    # Nothing is lost in the split.
    assert sum(part.count("row") for part in parts) == 800


def test_split_document_falls_back_to_lines_for_one_huge_block() -> None:
    """A single oversized sheet is split on line boundaries rather than refused."""
    parts = split_document("## Sheet: S\n" + ("row\n" * 1000), limit=500)
    assert len(parts) > 1
    assert all(len(part) <= 500 for part in parts)


# ==========================================================================
# The diff engine
# ==========================================================================


def test_diff_reports_an_added_entry() -> None:
    """An entry the stored profile does not have is an addition."""
    proposal = dict(EXISTING_PROFILE)
    proposal["work_experience"] = EXISTING_PROFILE["work_experience"] + [
        {"title": "Backend Engineering Intern", "company": "Aldermill Systems"}
    ]

    changes, summary = diff_profiles(EXISTING_PROFILE, proposal)

    added = [c for c in changes if c["kind"] == "added"]
    assert len(added) == 1
    assert added[0]["section"] == "work_experience"
    assert added[0]["label"] == "Backend Engineering Intern at Aldermill Systems"
    assert added[0]["index"] == 1
    assert summary["added"] == 1
    assert summary["sections"]["work_experience"]["added"] == 1


def test_diff_reports_an_updated_entry_and_names_the_fields() -> None:
    """A matched entry that gained a field is an update naming that field."""
    role = dict(EXISTING_PROFILE["work_experience"][0])
    role["employment_type"] = "Full-time"
    role["highlights"] = role["highlights"] + ["Mentored four engineers"]
    proposal = {**EXISTING_PROFILE, "work_experience": [role]}

    changes, summary = diff_profiles(EXISTING_PROFILE, proposal)

    updated = [c for c in changes if c["kind"] == "updated"]
    assert len(updated) == 1
    assert set(updated[0]["fields"]) == {"employment_type", "highlights"}
    assert summary["sections"]["work_experience"]["updated"] == 1


def test_diff_reports_an_unchanged_entry() -> None:
    """An identical proposal is entirely unchanged."""
    changes, summary = diff_profiles(EXISTING_PROFILE, EXISTING_PROFILE)

    assert {change["kind"] for change in changes} == {"unchanged"}
    assert summary["added"] == 0
    assert summary["updated"] == 0
    assert summary["unchanged"] == len(changes)


def test_diff_matches_entries_despite_punctuation_and_case() -> None:
    """"Kestrel Payments, Inc." is the same employer as "kestrel payments inc"."""
    role = {
        "title": "senior backend engineer",
        "company": "Kestrel Payments,  Inc",
        "start_date": "March 2022",
        "current": True,
        "highlights": ["Owned the settlement ledger migration"],
    }
    existing = {
        **EXISTING_PROFILE,
        "work_experience": [
            {**EXISTING_PROFILE["work_experience"][0], "company": "Kestrel Payments Inc."}
        ],
    }

    changes, _ = diff_profiles(existing, {**EXISTING_PROFILE, "work_experience": [role]})

    work = [c for c in changes if c["section"] == "work_experience"]
    assert len(work) == 1
    assert work[0]["kind"] == "updated"
    assert "title" in work[0]["fields"]


def test_diff_matches_education_on_institution_and_degree() -> None:
    """A second degree at the same institution is an addition, not an update."""
    proposal = {
        **EXISTING_PROFILE,
        "education": EXISTING_PROFILE["education"]
        + [
            {
                "degree": "Bachelor of Engineering",
                "institution": "Indian Institute of Technology, Hyderabad",
            }
        ],
    }

    changes, _ = diff_profiles(EXISTING_PROFILE, proposal)

    education = [c for c in changes if c["section"] == "education"]
    assert [c["kind"] for c in education] == ["unchanged", "added"]
    assert education[1]["label"] == (
        "Bachelor of Engineering, Indian Institute of Technology, Hyderabad"
    )


def test_diff_treats_a_union_of_skills_as_additions() -> None:
    """A skills union reports only the new tokens, each by name."""
    proposal = {**EXISTING_PROFILE, "skills": ["Python", "PostgreSQL", "Kafka", "Go"]}

    changes, summary = diff_profiles(EXISTING_PROFILE, proposal)

    skills = [c for c in changes if c["section"] == "skills"]
    assert [c["kind"] for c in skills] == ["unchanged", "unchanged", "added", "added"]
    assert [c["label"] for c in skills if c["kind"] == "added"] == ["Kafka", "Go"]
    assert summary["sections"]["skills"]["added"] == 2


def test_diff_reports_a_respelled_skill_as_an_update() -> None:
    """"postgresql" -> "PostgreSQL" is a rewrite the user should see."""
    proposal = {**EXISTING_PROFILE, "skills": ["Python", "postgresql"]}

    changes, _ = diff_profiles(EXISTING_PROFILE, proposal)

    respelled = [c for c in changes if c["section"] == "skills" and c["label"] == "postgresql"]
    assert respelled[0]["kind"] == "updated"
    assert respelled[0]["fields"] == ["value"]


def test_diff_reports_an_entry_the_merge_dropped() -> None:
    """The prompt forbids dropping an entry; the diff still shows it if one goes."""
    proposal = {**EXISTING_PROFILE, "work_experience": []}

    changes, summary = diff_profiles(EXISTING_PROFILE, proposal)

    removed = [c for c in changes if c["kind"] == "removed"]
    assert [c["label"] for c in removed] == ["Senior Backend Engineer at Kestrel Payments"]
    assert removed[0]["index"] is None
    assert summary["removed"] == 1


def test_diff_against_no_profile_is_all_additions() -> None:
    """A user with no profile sees every proposed entry as new."""
    changes, summary = diff_profiles(None, EXISTING_PROFILE)

    assert {change["kind"] for change in changes} == {"added"}
    assert summary["unchanged"] == 0
    assert summary["sections"]["summary"]["added"] == 1


def test_diff_ignores_a_field_filled_with_an_empty_string() -> None:
    """Absent and "" are the same absence, so filling one is not a change."""
    role = {**EXISTING_PROFILE["work_experience"][0], "location": "", "end_date": ""}
    changes, _ = diff_profiles(
        EXISTING_PROFILE, {**EXISTING_PROFILE, "work_experience": [role]}
    )
    work = [c for c in changes if c["section"] == "work_experience"]
    assert work[0]["kind"] == "unchanged"


# ==========================================================================
# propose_import
# ==========================================================================


def test_propose_import_returns_a_proposal_and_a_diff(mock_merge) -> None:
    """The service returns the merged profile plus the computed changes."""
    merged = {
        **EXISTING_PROFILE,
        "skills": ["Python", "PostgreSQL", "Kafka"],
    }
    mock_merge(merged)

    result = propose_import(EXISTING_PROFILE, "## Sheet: Skills\n| Kafka |", "s.xlsx")

    assert result["proposal"]["skills"] == ["Python", "PostgreSQL", "Kafka"]
    assert result["summary"]["added"] == 1
    assert any(
        change["label"] == "Kafka" and change["kind"] == "added"
        for change in result["changes"]
    )


def test_propose_import_prefers_azure(mock_merge) -> None:
    """Import extraction is uncapped Azure work, not Groq's daily budget."""
    mock_merge(EXISTING_PROFILE)

    propose_import(EXISTING_PROFILE, "## Sheet: Skills\n| Kafka |", "s.xlsx")

    call = mock_merge.calls[-1]
    assert call["prefer"] == "azure"
    assert call["purpose"] == "profile import"
    assert call["max_tokens"] == 8000


def test_propose_import_sends_the_existing_profile_and_the_document(
    mock_merge,
) -> None:
    """Both sides of the merge reach the model in one prompt."""
    mock_merge(EXISTING_PROFILE)

    propose_import(EXISTING_PROFILE, "## Sheet: Skills\n| Kafka |", "career.xlsx")

    user_message = mock_merge.calls[-1]["messages"][1]["content"]
    assert "Kestrel Payments" in user_message
    assert "## Sheet: Skills" in user_message
    assert "career.xlsx" in user_message


def test_propose_import_runs_one_pass_per_part_for_a_long_document(
    mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document over the single-pass limit is merged sequentially."""
    monkeypatch.setattr(import_service, "MAX_SINGLE_PASS_CHARS", 400)
    mock_merge(EXISTING_PROFILE)
    text = "\n".join(
        "## Sheet: S{}\n{}".format(index, "| row |\n" * 40) for index in range(3)
    )

    propose_import(EXISTING_PROFILE, text, "career.xlsx")

    assert len(mock_merge.calls) > 1
    assert "part 1 of" in mock_merge.calls[0]["messages"][1]["content"]


def test_propose_import_works_without_an_existing_profile(mock_merge) -> None:
    """Everything is an addition when there is nothing to merge into."""
    mock_merge(EXISTING_PROFILE)

    result = propose_import(None, "## Sheet: Skills\n| Kafka |", "s.xlsx")

    assert {change["kind"] for change in result["changes"]} == {"added"}


def test_propose_import_coerces_a_malformed_proposal(mock_merge) -> None:
    """Model junk is dropped rather than raised, as everywhere else."""
    mock_merge({"skills": "Python", "work_experience": "not a list"})

    result = propose_import(EXISTING_PROFILE, "text", "s.xlsx")

    assert result["proposal"]["skills"] == ["Python"]
    assert result["proposal"]["work_experience"] == []


def test_propose_import_wraps_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable model is an ImportProposalError, which the route 502s."""

    def boom(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(import_service.llm, "complete_json", boom)

    with pytest.raises(import_service.ImportProposalError):
        propose_import(EXISTING_PROFILE, "text", "s.xlsx")


def test_propose_import_rejects_an_empty_document() -> None:
    """There is nothing to propose from nothing."""
    with pytest.raises(import_service.EmptyDocumentText):
        propose_import(EXISTING_PROFILE, "   ", "s.xlsx")


# ==========================================================================
# raw_text appending
# ==========================================================================


def test_append_import_writes_a_dated_header() -> None:
    """The stored text records which file the new material came from."""
    combined = import_service.append_import_to_raw_text(
        "original", "imported body", "career.xlsx", when=datetime(2026, 9, 5)
    )
    assert combined == (
        "original\n\n--- Imported from career.xlsx on 2026-09-05 ---\nimported body"
    )


def test_append_import_keeps_the_tail_when_over_the_cap() -> None:
    """The newest import survives; the oldest text is what gets dropped."""
    combined = import_service.append_import_to_raw_text(
        "x" * import_service.MAX_RAW_TEXT_CHARS, "the new material", "a.xlsx"
    )
    assert len(combined) == import_service.MAX_RAW_TEXT_CHARS
    assert combined.endswith("the new material")


# ==========================================================================
# Routes -- auth
# ==========================================================================


def test_import_requires_auth(client: TestClient) -> None:
    """No token, no import."""
    response = client.post("/profile/import")
    assert response.status_code == 401


def test_import_apply_requires_auth(client: TestClient) -> None:
    """No token, no write."""
    response = client.post("/profile/import/apply", json={"parsed_json": {}})
    assert response.status_code == 401


# ==========================================================================
# Routes -- POST /profile/import
# ==========================================================================


def test_import_returns_a_proposal_without_saving(
    auth_client: TestClient, db: FakeSession, mock_merge
) -> None:
    """The proposal is returned and the stored profile is untouched."""
    stored = db.seed(make_profile())
    mock_merge({**EXISTING_PROFILE, "skills": ["Python", "PostgreSQL", "Kafka"]})

    response = auth_client.post(
        "/profile/import",
        files={"file": ("career.xlsx", make_xlsx(SAMPLE_WORKBOOK), XLSX_CONTENT_TYPE)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["skills"] == ["Python", "PostgreSQL", "Kafka"]
    assert body["summary"]["added"] == 1
    assert body["source"]["filename"] == "career.xlsx"
    assert body["source"]["kind"] == "xlsx"
    # Nothing was written.
    assert stored.parsed_json["skills"] == ["Python", "PostgreSQL"]
    assert db.commits == 0


def test_import_reports_the_skipped_reference_sheet(
    auth_client: TestClient, db: FakeSession, mock_merge
) -> None:
    """The user is told the referees tab was read and left out."""
    db.seed(make_profile())
    mock_merge(EXISTING_PROFILE)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("career.xlsx", make_xlsx(SAMPLE_WORKBOOK), XLSX_CONTENT_TYPE)},
    )

    sheets = {sheet["name"]: sheet for sheet in response.json()["source"]["sheets"]}
    assert sheets["LORs"]["skipped_reason"] == SKIPPED_REFERENCES
    assert sheets["Education"]["skipped_reason"] is None


def test_import_works_without_a_profile(
    auth_client: TestClient, db: FakeSession, mock_merge
) -> None:
    """A user who has not uploaded a resume can still import a workbook."""
    mock_merge(EXISTING_PROFILE)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("career.xlsx", make_xlsx(SAMPLE_WORKBOOK), XLSX_CONTENT_TYPE)},
    )

    assert response.status_code == 200
    assert {change["kind"] for change in response.json()["changes"]} == {"added"}


def test_import_rejects_an_unsupported_type(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An image is a 400 naming the formats that do work."""
    response = auth_client.post(
        "/profile/import", files={"file": ("photo.png", b"\x89PNG", "image/png")}
    )

    assert response.status_code == 400
    assert "XLSX" in response.json()["detail"]


def test_import_rejects_an_oversized_file(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Over 10MB is a 413 before any model call."""
    oversized = b"a" * (import_service.MAX_IMPORT_BYTES + 1)
    response = auth_client.post(
        "/profile/import", files={"file": ("big.csv", oversized, "text/csv")}
    )

    assert response.status_code == 413
    assert "10MB" in response.json()["detail"]


def test_import_rejects_an_empty_file(auth_client: TestClient, db: FakeSession) -> None:
    """An empty upload is a 422, matching the resume upload."""
    response = auth_client.post(
        "/profile/import", files={"file": ("empty.csv", b"", "text/csv")}
    )
    assert response.status_code == 422


def test_import_maps_a_provider_failure_to_502(
    auth_client: TestClient, db: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file was fine; the model was not."""
    db.seed(make_profile())

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(import_service.llm, "complete_json", boom)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("skills.csv", make_csv([["Skill"], ["Kafka"]]), "text/csv")},
    )

    assert response.status_code == 502


def test_import_returns_the_document_text_for_the_apply_call(
    auth_client: TestClient, db: FakeSession, mock_merge
) -> None:
    """The client has to echo the text back, so the response has to carry it.

    Nothing about the upload is stored between /profile/import and
    /profile/import/apply, so this field is the only place the extracted text
    exists once the response has been sent.
    """
    db.seed(make_profile())
    mock_merge(EXISTING_PROFILE)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("career.xlsx", make_xlsx(SAMPLE_WORKBOOK), XLSX_CONTENT_TYPE)},
    )

    document_text = response.json()["document_text"]
    assert document_text.startswith("## Sheet: Education")
    assert "## Sheet: LORs" not in document_text

    # It round-trips: what comes back is exactly what apply appends.
    applied = auth_client.post(
        "/profile/import/apply",
        json={
            "parsed_json": EXISTING_PROFILE,
            "sections": ["skills"],
            "filename": "career.xlsx",
            "document_text": document_text,
        },
    )
    assert applied.status_code == 200
    assert applied.json()["raw_text"].endswith(document_text)


def test_import_caps_the_returned_document_text(
    auth_client: TestClient, db: FakeSession, mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The echoed text is capped at the same ceiling raw_text has."""
    monkeypatch.setattr(import_service, "MAX_RAW_TEXT_CHARS", 200)
    mock_merge(EXISTING_PROFILE)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("notes.txt", b"x" * 5000, "text/plain")},
    )

    assert len(response.json()["document_text"]) == 200

# ==========================================================================
# Routes -- POST /profile/import/apply
# ==========================================================================


def _apply_payload(**overrides) -> dict:
    """A body applying a skills-and-publications proposal."""
    payload = {
        "parsed_json": {
            **EXISTING_PROFILE,
            "skills": ["Python", "PostgreSQL", "Kafka"],
            "publications": [
                {"title": "Reconciling at Scale", "year": "2023"}
            ],
            "summary": "A rewritten summary the user did not tick.",
        },
        "sections": ["skills", "publications"],
        "filename": "career.xlsx",
        "document_text": "## Sheet: Skills\n| Kafka |",
    }
    payload.update(overrides)
    return payload


def test_apply_writes_only_the_listed_sections(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A section the user did not tick is left exactly as it was."""
    stored = db.seed(make_profile())

    response = auth_client.post("/profile/import/apply", json=_apply_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_json"]["skills"] == ["Python", "PostgreSQL", "Kafka"]
    assert body["parsed_json"]["publications"][0]["title"] == "Reconciling at Scale"
    # Untouched: the summary was in the proposal but not in `sections`.
    assert body["parsed_json"]["summary"] == EXISTING_PROFILE["summary"]
    assert stored.parsed_json["work_experience"][0]["company"] == "Kestrel Payments"


def test_apply_appends_the_document_to_raw_text(
    auth_client: TestClient, db: FakeSession
) -> None:
    """The imported source is kept, under a dated header, for re-extraction."""
    db.seed(make_profile())

    response = auth_client.post("/profile/import/apply", json=_apply_payload())

    raw_text = response.json()["raw_text"]
    assert raw_text.startswith("original resume text")
    assert "--- Imported from career.xlsx on " in raw_text
    assert raw_text.endswith("## Sheet: Skills\n| Kafka |")


def test_apply_leaves_raw_text_alone_without_a_document(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A client that does not echo the document simply does not append one."""
    db.seed(make_profile())

    response = auth_client.post(
        "/profile/import/apply", json=_apply_payload(document_text=None)
    )

    assert response.json()["raw_text"] == "original resume text"


def test_apply_drops_a_blank_proposed_entry(
    auth_client: TestClient, db: FakeSession
) -> None:
    """An entry with nothing in it is a stray row, not an error."""
    db.seed(make_profile())

    response = auth_client.post(
        "/profile/import/apply",
        json=_apply_payload(
            parsed_json={
                **EXISTING_PROFILE,
                "publications": [
                    {"title": "Reconciling at Scale"},
                    {"title": "", "authors": ""},
                ],
            },
            sections=["publications"],
        ),
    )

    assert response.status_code == 200
    assert len(response.json()["parsed_json"]["publications"]) == 1


def test_apply_rejects_an_incomplete_entry_and_writes_nothing(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A proposed publication with no title is a 422 with a per-field error."""
    stored = db.seed(make_profile())

    response = auth_client.post(
        "/profile/import/apply",
        json=_apply_payload(
            parsed_json={
                **EXISTING_PROFILE,
                "publications": [{"authors": "Rivera, J.", "year": "2023"}],
            },
            sections=["publications"],
        ),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["errors"][0] == {
        "section": "publications",
        "index": 0,
        "field": "title",
        "message": "Publication title is required",
    }
    assert stored.parsed_json == EXISTING_PROFILE
    assert stored.raw_text == "original resume text"
    assert db.commits == 0


def test_apply_rejects_an_unknown_section(
    auth_client: TestClient, db: FakeSession
) -> None:
    """A typo in `sections` is a 422, not a silent no-op."""
    db.seed(make_profile())

    response = auth_client.post(
        "/profile/import/apply", json=_apply_payload(sections=["skillz"])
    )

    assert response.status_code == 422
    assert "skillz" in response.json()["detail"]


def test_apply_creates_a_profile_for_a_user_who_has_none(
    auth_client: TestClient, db: FakeSession, test_user_uuid: uuid.UUID
) -> None:
    """An import can be the first thing a user ever does."""
    response = auth_client.post("/profile/import/apply", json=_apply_payload())

    assert response.status_code == 200
    stored = db.get(Profile, test_user_uuid)
    assert stored is not None
    assert stored.parsed_json["skills"] == ["Python", "PostgreSQL", "Kafka"]
    assert stored.raw_text.startswith("\n\n--- Imported from career.xlsx")


def test_apply_with_no_sections_changes_nothing(
    auth_client: TestClient, db: FakeSession
) -> None:
    """Reviewing a proposal and ticking nothing is a valid, empty, save."""
    db.seed(make_profile())

    response = auth_client.post(
        "/profile/import/apply", json=_apply_payload(sections=[])
    )

    assert response.status_code == 200
    assert response.json()["parsed_json"]["skills"] == ["Python", "PostgreSQL"]


# ==========================================================================
# Live -- opt in with RUN_LIVE=1
# ==========================================================================


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="Live Azure import test. Set RUN_LIVE=1 to run it.",
)
def test_live_import_workbook() -> None:
    """Merge a real three-sheet workbook into a fixture profile through Azure.

    This is the only import test that spends a model call, so it is opt-in. It
    guards the merge prompt itself: every offline test mocks the response and
    would pass with a prompt that dropped the existing profile on the floor.
    """
    sheets = {
        name: rows
        for name, rows in SAMPLE_WORKBOOK.items()
        if name in ("Education", "Work Experiences", "Publications")
    }
    document = extract_document_text(make_xlsx(sheets), "career.xlsx")

    started = time.monotonic()
    result = propose_import(EXISTING_PROFILE, document["text"], "career.xlsx")
    elapsed = time.monotonic() - started
    print("\nlive import merge took {:.1f}s".format(elapsed))

    proposal = result["proposal"]

    # The existing role survives, and the workbook's internship is added.
    companies = {role["company"] for role in proposal["work_experience"]}
    assert "Kestrel Payments" in companies
    assert any("Aldermill" in (company or "") for company in companies)

    # The existing degree survives, and the workbook's certificate course is
    # added as a second education entry.
    institutions = " ".join(
        entry["institution"] or "" for entry in proposal["education"]
    )
    assert "Hyderabad" in institutions
    assert "Fernwood" in institutions

    # A publication the stored profile did not have.
    assert any(
        "Reconciling" in (item["title"] or "") for item in proposal["publications"]
    )

    # Nothing from the existing profile was dropped.
    assert not [change for change in result["changes"] if change["kind"] == "removed"]
    assert result["summary"]["added"] >= 3
    assert result["provider"] in ("azure", "groq")
