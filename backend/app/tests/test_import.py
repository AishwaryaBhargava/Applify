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

from app.core.errors import IMPORT_EXTRACTION_FAILED
from app.models.profile import Profile
from app.services import import_service
from app.services.import_service import (
    SKIPPED_REFERENCES,
    diff_profiles,
    extract_document_text,
    guess_sections,
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
    """Replace the merge model call with a canned body and a settable meta.

    Returns a setter and records the calls, so a test can assert both on what
    came back and on what was sent -- which provider was preferred, what
    context each pass was given, and how many passes ran. ``set_response`` also
    takes ``finish_reason`` so the truncation retry can be driven, and
    ``set_response.sequence`` takes a callable answering per call.
    """
    calls: list[dict] = []
    state: dict = {}

    def fake_with_meta(messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        answer = state["answer"]
        body, meta = answer(len(calls), messages) if callable(answer) else (
            answer,
            state["meta"],
        )
        payload = body if isinstance(body, str) else json.dumps(body)
        return payload, dict(meta)

    monkeypatch.setattr(
        import_service.llm, "complete_json_with_meta", fake_with_meta
    )

    def set_response(body, **meta) -> None:
        state["answer"] = body
        state["meta"] = {
            "provider": "azure",
            "finish_reason": "stop",
            "completion_tokens": 120,
            **meta,
        }

    def sequence(answer) -> None:
        """Answer each call from a callable ``(call_number, messages)``."""
        state["answer"] = answer

    set_response(EXISTING_PROFILE)
    set_response.calls = calls  # type: ignore[attr-defined]
    set_response.sequence = sequence  # type: ignore[attr-defined]
    set_response.meta = lambda **kw: {  # type: ignore[attr-defined]
        "provider": "azure",
        "finish_reason": "stop",
        "completion_tokens": 120,
        **kw,
    }
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


def test_split_document_packs_small_sheets_together() -> None:
    """Eight tiny sheets are one pass, not eight."""
    text = "\n".join("## Sheet: S{}\n| a |".format(i) for i in range(8))
    assert split_document(text, limit=1000) == [text]


def _sheet_table(name: str, rows: int) -> str:
    """A markdown table of `rows` data rows, as extract_xlsx would render it."""
    lines = ["## Sheet: {}".format(name), "", "| Role | Company |", "| --- | --- |"]
    lines += ["| Engineer {} | Aldermill |".format(index) for index in range(rows)]
    return "\n".join(lines)


def test_split_document_splits_a_huge_sheet_on_row_boundaries() -> None:
    """A sheet bigger than the limit is cut between rows, never mid-row."""
    parts = split_document(_sheet_table("Work Experiences", 120), limit=900)

    assert len(parts) > 1
    for part in parts:
        for line in part.split("\n"):
            assert not line.startswith("| Engineer") or line.endswith("|")
    rows = sum(part.count("| Engineer ") for part in parts)
    assert rows == 120


def test_split_document_repeats_the_header_on_every_continuation() -> None:
    """A table body without its header is a grid of unlabelled cells."""
    parts = split_document(_sheet_table("Work Experiences", 120), limit=900)

    assert parts[0].startswith("## Sheet: Work Experiences\n")
    for part in parts[1:]:
        assert part.startswith("## Sheet: Work Experiences (continued)")
        assert "| Role | Company |" in part
        assert "| --- | --- |" in part


def test_split_document_caps_the_rows_in_one_chunk() -> None:
    """Characters are not the only limit: a pass sees a countable few rows.

    A pass handed a whole wide sheet returns a summary of it -- fourteen roles
    as four amalgams -- and no wording in the prompt reliably prevents that.
    Six rows is few enough that copying them out one by one is the easiest
    thing the model can do.
    """
    parts = split_document(_sheet_table("Work Experiences", 20), limit=100000)

    assert len(parts) == 4
    for part in parts:
        assert import_service.count_data_rows(part) <= import_service.MAX_ROWS_PER_CHUNK
    assert sum(import_service.count_data_rows(part) for part in parts) == 20


def test_split_document_does_not_pack_past_the_row_cap() -> None:
    """Packing small sheets together stops at the same ceiling."""
    text = "\n".join(_sheet_table("S{}".format(index), 4) for index in range(3))
    parts = split_document(text, limit=100000)

    assert len(parts) > 1
    for part in parts:
        assert import_service.count_data_rows(part) <= import_service.MAX_ROWS_PER_CHUNK

def test_split_document_falls_back_to_lines_for_a_huge_block_of_prose() -> None:
    """A long document with no table is still split, on line boundaries."""
    parts = split_document("## Sheet: S\n" + ("row\n" * 1000), limit=500)
    assert len(parts) > 1
    assert all(len(part) <= 600 for part in parts)


# ==========================================================================
# Which sections a chunk may touch
# ==========================================================================


def test_guess_sections_reads_sheet_headings() -> None:
    """The heading is what says which section a chunk is about."""
    assert "education" in guess_sections("## Sheet: Education\n| Degree |")
    assert "publications" in guess_sections("## Sheet: Publications\n| Title |")
    assert "work_experience" in guess_sections(
        "## Sheet: Work Experiences (continued)\n| Role |"
    )


def test_guess_sections_reads_table_headers() -> None:
    """An unhelpfully named sheet is still identified by its columns."""
    sections = guess_sections("## Sheet: Tab1\n\n| Degree | University |\n| --- | --- |")
    assert "education" in sections


def test_guess_sections_ignores_body_rows() -> None:
    """A data row mentioning a word must not pull a whole section into context."""
    chunk = "## Sheet: Skills\n\n| Skill |\n| --- |\n| Project management |"
    assert "projects" not in guess_sections(chunk)


def test_guess_sections_falls_back_to_everything() -> None:
    """Prose names no sheets, so every section is offered as context."""
    from app.api.schemas.profile import PROFILE_SECTIONS

    assert guess_sections("Some free text with no headings") == PROFILE_SECTIONS


# ==========================================================================
# Combining one pass's answer
# ==========================================================================


def test_combine_replaces_a_section_that_was_given_as_context() -> None:
    """A returned section is a merge of the one sent, so it replaces it."""
    running = {"skills": ["Python", "PostgreSQL"]}
    combined = import_service.combine_sections(
        running, {"skills": ["Python", "PostgreSQL", "Kafka"]}, ("skills",)
    )
    assert combined["skills"] == ["Python", "PostgreSQL", "Kafka"]


def test_combine_leaves_untouched_sections_alone() -> None:
    """A section the pass did not return keeps every entry it had."""
    running = {
        "skills": ["Python"],
        "work_experience": [{"title": "Engineer", "company": "Kestrel"}],
    }
    combined = import_service.combine_sections(
        running, {"skills": ["Python", "Go"]}, ("skills",)
    )
    assert combined["work_experience"][0]["company"] == "Kestrel"


def test_combine_restores_an_entry_the_model_dropped() -> None:
    """The prompt forbids dropping an entry; the combine makes it impossible."""
    running = {
        "work_experience": [
            {"title": "Senior Backend Engineer", "company": "Kestrel Payments"},
            {"title": "Backend Engineer", "company": "Northwind"},
        ]
    }
    combined = import_service.combine_sections(
        running,
        {"work_experience": [{"title": "Backend Engineer", "company": "Northwind"}]},
        ("work_experience",),
    )
    companies = {role["company"] for role in combined["work_experience"]}
    assert companies == {"Kestrel Payments", "Northwind"}


def test_combine_unions_a_section_that_was_not_in_context() -> None:
    """Without the context it would be overwriting, a return can only add."""
    running = {"skills": ["Python", "PostgreSQL"]}
    combined = import_service.combine_sections(
        running, {"skills": ["Kafka", "python"]}, ("projects",)
    )
    # "python" matches the existing token case-insensitively and is not added.
    assert combined["skills"] == ["Python", "PostgreSQL", "Kafka"]


def test_combine_takes_a_returned_summary() -> None:
    """The one scalar section is replaced when the pass returns a non-empty one."""
    combined = import_service.combine_sections(
        {"summary": "Old."}, {"summary": "New and longer."}, ("summary",)
    )
    assert combined["summary"] == "New and longer."


def test_combine_ignores_an_empty_summary_and_unknown_keys() -> None:
    """A blank answer never wipes a section, and junk keys are dropped."""
    combined = import_service.combine_sections(
        {"summary": "Old."}, {"summary": "", "nonsense": [1, 2]}, ("summary",)
    )
    assert combined["summary"] == "Old."
    assert "nonsense" not in combined


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
    assert call["max_tokens"] == 16000


def test_propose_import_sends_only_the_relevant_sections_as_context(
    mock_merge,
) -> None:
    """A skills chunk is not shown the work history it cannot possibly touch.

    This is what keeps both the prompt and the answer small enough to finish:
    the pass is given the entries it might have to re-emit, and nothing else.
    """
    mock_merge(EXISTING_PROFILE)

    propose_import(
        EXISTING_PROFILE,
        "## Sheet: Skills\n\n| Skill |\n| --- |\n| Kafka |",
        "career.xlsx",
    )

    user_message = mock_merge.calls[-1]["messages"][1]["content"]
    assert "PostgreSQL" in user_message  # the existing skills, as context
    assert "Kestrel Payments" not in user_message  # the work history, left out
    assert "## Sheet: Skills" in user_message
    assert "career.xlsx" in user_message


def test_propose_import_sends_the_matching_section_for_a_work_chunk(
    mock_merge,
) -> None:
    """The converse: a work sheet does get the existing roles."""
    mock_merge(EXISTING_PROFILE)

    propose_import(
        EXISTING_PROFILE,
        "## Sheet: Work Experiences\n\n| Role | Company |\n| --- | --- |\n| A | B |",
        "career.xlsx",
    )

    assert "Kestrel Payments" in mock_merge.calls[-1]["messages"][1]["content"]


def test_propose_import_runs_one_pass_per_chunk(
    mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document over the chunk limit is merged sequentially, one pass each."""
    monkeypatch.setattr(import_service, "MAX_CHUNK_CHARS", 400)
    mock_merge(EXISTING_PROFILE)
    text = "\n".join(
        "## Sheet: S{}\n{}".format(index, "| row |\n" * 40) for index in range(3)
    )

    propose_import(EXISTING_PROFILE, text, "career.xlsx")

    assert len(mock_merge.calls) > 1
    assert "PART 1/" in mock_merge.calls[0]["messages"][1]["content"]


def test_propose_import_merges_each_chunk_into_the_last_result(
    mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passes are sequential: pass two is shown what pass one added."""
    monkeypatch.setattr(import_service, "MAX_CHUNK_CHARS", 600)
    seen: list[str] = []

    def answer(call_number: int, messages: list[dict]) -> tuple[dict, dict]:
        seen.append(messages[1]["content"])
        if call_number == 1:
            return {"skills": ["Python", "PostgreSQL", "Kafka"]}, mock_merge.meta()
        return {"skills": ["Python", "PostgreSQL", "Kafka", "Go"]}, mock_merge.meta()

    mock_merge.sequence(answer)
    text = "## Sheet: Skills\n\n| Skill |\n| --- |\n" + "| x |\n" * 200

    result = propose_import(EXISTING_PROFILE, text, "career.xlsx")

    assert len(seen) >= 2
    # The second pass was shown the first pass's output, not the stored profile.
    assert "Kafka" in seen[1]
    assert result["proposal"]["skills"] == ["Python", "PostgreSQL", "Kafka", "Go"]


def _dense_sheet(rows: int, width: int = 900) -> str:
    """One sheet whose rows are long enough to fill a chunk on their own."""
    lines = ["## Sheet: Projects", "", "| Project | Notes |", "| --- | --- |"]
    lines += [
        "| Project {} | {} |".format(index, "detail " * (width // 7))
        for index in range(rows)
    ]
    return "\n".join(lines)


def test_propose_import_resplits_a_truncated_pass(
    mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """finish_reason "length" means the answer was cut off: halve and retry."""
    # The row cap would already have made these chunks small; this test is about
    # what happens when a chunk that *is* within both limits still truncates.
    monkeypatch.setattr(import_service, "MAX_ROWS_PER_CHUNK", 50)
    attempts: list[int] = []

    def answer(call_number: int, messages: list[dict]) -> tuple[dict, dict]:
        attempts.append(len(messages[1]["content"]))
        if call_number == 1:
            return {"skills": ["Python"]}, mock_merge.meta(finish_reason="length")
        return (
            {"skills": ["Python", "PostgreSQL", "Kafka"]},
            mock_merge.meta(finish_reason="stop"),
        )

    mock_merge.sequence(answer)

    result = propose_import(EXISTING_PROFILE, _dense_sheet(18), "career.xlsx")

    assert len(attempts) > 1
    # Every retry reads less than the pass that truncated.
    assert attempts[1] < attempts[0]
    assert "Kafka" in result["proposal"]["skills"]


def test_propose_import_gives_up_on_a_chunk_it_cannot_split(mock_merge) -> None:
    """At the floor there is nothing left to split, so say so plainly."""
    mock_merge({"skills": ["Python"]}, finish_reason="length")

    with pytest.raises(import_service.DocumentTooDense, match="too dense"):
        propose_import(EXISTING_PROFILE, "## Sheet: Skills\n| Kafka |", "career.xlsx")


def test_propose_import_never_loops_forever_on_truncation(
    mock_merge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document that always truncates fails rather than halving for ever."""
    monkeypatch.setattr(import_service, "MAX_ROWS_PER_CHUNK", 50)
    mock_merge({"skills": ["Python"]}, finish_reason="length")

    with pytest.raises(import_service.DocumentTooDense):
        propose_import(EXISTING_PROFILE, _dense_sheet(40), "career.xlsx")

    # Bounded: halving stops at the floor rather than recursing indefinitely.
    assert len(mock_merge.calls) < 64


def test_propose_import_works_without_an_existing_profile(mock_merge) -> None:
    """Everything is an addition when there is nothing to merge into."""
    mock_merge(EXISTING_PROFILE)

    result = propose_import(None, "## Sheet: Skills\n| Kafka |", "s.xlsx")

    assert {change["kind"] for change in result["changes"]} == {"added"}


def test_propose_import_coerces_a_malformed_answer_without_losing_data(
    mock_merge,
) -> None:
    """Model junk is coerced, and never at the cost of a stored entry."""
    mock_merge({"skills": "Python", "work_experience": "not a list"})

    result = propose_import(EXISTING_PROFILE, "text", "s.xlsx")

    # "Python" survives coercion, and PostgreSQL is restored rather than lost.
    assert set(result["proposal"]["skills"]) == {"Python", "PostgreSQL"}
    # A section that came back as nonsense keeps what the profile already had.
    assert result["proposal"]["work_experience"][0]["company"] == "Kestrel Payments"
    assert not [c for c in result["changes"] if c["kind"] == "removed"]


def test_propose_import_reports_the_provider_that_answered(mock_merge) -> None:
    """The provider comes from the completion metadata, not a string attribute."""
    mock_merge(EXISTING_PROFILE, provider="groq")

    result = propose_import(EXISTING_PROFILE, "text", "s.xlsx")

    assert result["provider"] == "groq"


def test_propose_import_wraps_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable model is an ImportProposalError, which the route 502s."""

    def boom(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(import_service.llm, "complete_json_with_meta", boom)

    with pytest.raises(import_service.ImportProposalError):
        propose_import(EXISTING_PROFILE, "text", "s.xlsx")


def test_propose_import_rejects_an_empty_document() -> None:
    """There is nothing to propose from nothing."""
    with pytest.raises(import_service.EmptyDocumentText):
        propose_import(EXISTING_PROFILE, "   ", "s.xlsx")


# ==========================================================================
# One row, one entry
# ==========================================================================


def test_count_data_rows_ignores_headers_and_separators() -> None:
    """The header row of each sheet is not data, and neither is the rule line."""
    chunk = (
        "## Sheet: A\n\n| H1 | H2 |\n| --- | --- |\n| a | b |\n| c | d |\n\n"
        "## Sheet: B\n\n| X |\n| --- |\n| 1 |"
    )
    assert import_service.count_data_rows(chunk) == 3


def test_count_data_rows_is_zero_for_prose() -> None:
    """A document with no table has no rows to promise the model."""
    assert import_service.count_data_rows("Just some notes about a project") == 0


def test_the_prompt_tells_each_pass_how_many_rows_it_holds(mock_merge) -> None:
    """A pass given a wide table folds rows together unless it has a target.

    Sixteen roles coming back as six is invisible in the response -- it looks
    exactly like a document that described six -- so the count goes in the
    prompt and the shortfall goes in the log.
    """
    mock_merge(EXISTING_PROFILE)
    chunk = (
        "## Sheet: Work Experiences\n\n| Role | Company |\n| --- | --- |\n"
        "| A | B |\n| C | D |\n| E | F |"
    )

    propose_import(EXISTING_PROFILE, chunk, "career.xlsx")

    user_message = mock_merge.calls[-1]["messages"][1]["content"]
    assert "3 data rows" in user_message
    assert "each one is its own entry" in user_message


def test_the_prompt_omits_the_row_note_for_prose(mock_merge) -> None:
    """A promise of zero rows would be worse than no promise."""
    mock_merge(EXISTING_PROFILE)

    propose_import(EXISTING_PROFILE, "A paragraph about a side project.", "notes.txt")

    assert "data rows" not in mock_merge.calls[-1]["messages"][1]["content"]

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
        raise RuntimeError(
            "Error code: 400 - {'error': {'code': 'json_validate_failed', "
            "'failed_generation': 'max completion tokens reached'}}"
        )

    monkeypatch.setattr(import_service.llm, "complete_json_with_meta", boom)

    response = auth_client.post(
        "/profile/import",
        files={"file": ("skills.csv", make_csv([["Skill"], ["Kafka"]]), "text/csv")},
    )

    assert response.status_code == 502
    # A sentence the user can act on, not the provider's error body.
    detail = response.json()["detail"]
    assert detail == IMPORT_EXTRACTION_FAILED
    assert "Error code" not in detail


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

def test_import_maps_a_too_dense_file_to_422(
    auth_client: TestClient, db: FakeSession, mock_merge
) -> None:
    """A file whose sections cannot be rebuilt in one answer says so, not 502.

    502 would tell the user to retry, and retrying an unsplittable file just
    burns another minute. The message names the fix instead.
    """
    db.seed(make_profile())
    mock_merge({"skills": ["Python"]}, finish_reason="length")

    response = auth_client.post(
        "/profile/import",
        files={"file": ("skills.csv", make_csv([["Skill"], ["Kafka"]]), "text/csv")},
    )

    assert response.status_code == 422
    assert "split it into smaller files" in response.json()["detail"]

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
