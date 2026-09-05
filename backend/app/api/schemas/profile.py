"""Schemas for the profile endpoints.

``ParsedProfile`` is the single contract for the structured resume data. The
Groq extraction prompt is written against it, the database stores it as
``profiles.parsed_json``, ``PATCH /profile`` merges into it section by section,
and gap detection reads it. Changing a field name here means changing all four.

Every field is optional and every list defaults to empty, because a resume that
simply does not mention certifications is not an error -- it is a gap, and
:func:`app.services.profile_service.detect_gaps` is what reports it.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

# The parsed_json section names, in the order they are rendered and nudged
# about. Kept as a constant so the extractor, the merge, and gap detection all
# agree on what a "section" is.
PROFILE_SECTIONS: tuple[str, ...] = (
    "summary",
    "work_experience",
    "education",
    "skills",
    "certifications",
    "projects",
    "achievements",
)

# A skill should be a short token ("PostgreSQL"), not a sentence. Anything
# longer than this is a model failure and gets dropped.
MAX_SKILL_CHARS = 60


class WorkExperience(BaseModel):
    """A single role in the user's work history."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    company: str | None = None
    location: str | None = None
    # Free-form, as written on the resume ("Jan 2022"). Resumes use a dozen date
    # formats and normalising them throws away information the model can still
    # read later.
    start_date: str | None = None
    end_date: str | None = None
    current: bool = False
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """A single education entry."""

    model_config = ConfigDict(extra="ignore")

    degree: str | None = None
    institution: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    details: str | None = None


class Certification(BaseModel):
    """A professional certification or licence."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    issuer: str | None = None
    year: str | None = None


class Project(BaseModel):
    """A personal, academic, or professional project."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    link: str | None = None


class ParsedProfile(BaseModel):
    """The structured profile extracted from a resume and enriched by the user."""

    model_config = ConfigDict(extra="ignore")

    summary: str | None = None
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Defensive coercion of model output
# --------------------------------------------------------------------------


def _clean_str(value: Any) -> str | None:
    """Return a stripped string, or None for anything empty or non-scalar."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _clean_str_list(value: Any, max_chars: int | None = None) -> list[str]:
    """Return a de-duplicated list of non-empty strings, preserving order."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        cleaned = _clean_str(item)
        if cleaned is None:
            continue
        if max_chars is not None and len(cleaned) > max_chars:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _clean_bool(value: Any) -> bool:
    """Coerce a model's idea of a boolean into an actual one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "present", "current"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _coerce_work_experience(items: Any) -> list[WorkExperience]:
    """Build work-history entries, skipping any that name neither role nor employer."""
    out: list[WorkExperience] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entry = WorkExperience(
            title=_clean_str(item.get("title")),
            company=_clean_str(item.get("company")),
            location=_clean_str(item.get("location")),
            start_date=_clean_str(item.get("start_date")),
            end_date=_clean_str(item.get("end_date")),
            current=_clean_bool(item.get("current")),
            highlights=_clean_str_list(item.get("highlights")),
        )
        # An entry naming neither the role nor the employer carries nothing
        # usable downstream.
        if entry.title or entry.company:
            out.append(entry)
    return out


def _coerce_education(items: Any) -> list[Education]:
    """Build education entries, skipping any that name neither degree nor school."""
    out: list[Education] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entry = Education(
            degree=_clean_str(item.get("degree")),
            institution=_clean_str(item.get("institution")),
            field=_clean_str(item.get("field")),
            start_date=_clean_str(item.get("start_date")),
            end_date=_clean_str(item.get("end_date")),
            details=_clean_str(item.get("details")),
        )
        if entry.degree or entry.institution:
            out.append(entry)
    return out


def _coerce_certifications(items: Any) -> list[Certification]:
    """Build certifications; a bare string is read as the certification name."""
    out: list[Certification] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            name = _clean_str(item)
            if name:
                out.append(Certification(name=name))
            continue
        if not isinstance(item, dict):
            continue
        entry = Certification(
            name=_clean_str(item.get("name")),
            issuer=_clean_str(item.get("issuer")),
            year=_clean_str(item.get("year")),
        )
        if entry.name:
            out.append(entry)
    return out


def _coerce_projects(items: Any) -> list[Project]:
    """Build projects; a bare string is read as the project name."""
    out: list[Project] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            name = _clean_str(item)
            if name:
                out.append(Project(name=name))
            continue
        if not isinstance(item, dict):
            continue
        entry = Project(
            name=_clean_str(item.get("name")),
            description=_clean_str(item.get("description")),
            technologies=_clean_str_list(item.get("technologies"), MAX_SKILL_CHARS),
            link=_clean_str(item.get("link")),
        )
        if entry.name or entry.description:
            out.append(entry)
    return out


def coerce_parsed_profile(raw: Any) -> ParsedProfile:
    """Turn arbitrary model output into a valid :class:`ParsedProfile`.

    Never raises. A malformed section becomes an empty section and a malformed
    entry inside a good section is dropped, because a partially extracted
    profile is far more useful to the user than a 500 -- they can fix the rest
    by hand on the profile page.

    Args:
        raw: Whatever came back from the model -- ideally a dict, possibly not.

    Returns:
        A ParsedProfile with every field normalised.
    """
    if not isinstance(raw, dict):
        return ParsedProfile()
    return ParsedProfile(
        summary=_clean_str(raw.get("summary")),
        work_experience=_coerce_work_experience(raw.get("work_experience")),
        education=_coerce_education(raw.get("education")),
        skills=_clean_str_list(raw.get("skills"), MAX_SKILL_CHARS),
        certifications=_coerce_certifications(raw.get("certifications")),
        projects=_coerce_projects(raw.get("projects")),
        achievements=_clean_str_list(raw.get("achievements")),
    )


# --------------------------------------------------------------------------
# Strict validation of user edits
# --------------------------------------------------------------------------

# There are two passes over the same shape, deliberately.
#
# ``coerce_parsed_profile`` above is the *lenient* pass and it exists for model
# output: an extraction that half worked is still worth keeping, so junk is
# dropped and nothing ever raises. Applying that leniency to ``PATCH /profile``
# would be wrong in exactly the opposite direction -- a user who typed a company
# but forgot the job title would watch the row disappear on save, with a 200 and
# no explanation. Silent data loss is the worst outcome here; a 422 is the best.
#
# So user edits go through the strict pass below instead. It keeps one forgiving
# rule -- an entry with nothing in it at all is a stray row the editor added, not
# a mistake, and is dropped silently -- and turns every *partially* filled entry
# that is missing a required field into a 422 naming the section, the index, and
# the field, so the profile page can highlight the input the user has to fix.

# A job title or an organisation name; anything longer is a paragraph in the
# wrong box.
MAX_NAME_CHARS = 200
# Two or three paragraphs of positioning statement.
MAX_SUMMARY_CHARS = 2000
# Free-text description / details fields.
MAX_DETAIL_CHARS = 2000
# Dates stay free-form ("Jan 2022"), so this only catches pasted prose.
MAX_DATE_CHARS = 100
MAX_LINK_CHARS = 500
# A role with more than this many bullets is a resume section, not a role, and
# every generated output would be dominated by it.
MAX_HIGHLIGHTS = 20
MAX_HIGHLIGHT_CHARS = 500
MAX_ACHIEVEMENT_CHARS = 500


def format_profile_errors(errors: list[dict[str, Any]]) -> str:
    """Render structured field errors as one readable sentence.

    ``{"section": "work_experience", "index": 1, ...}`` becomes
    ``work_experience[1]: company is required``, and several are joined with
    semicolons so the whole thing fits in a toast -- the same treatment
    :func:`app.core.errors.flatten_validation_errors` gives pydantic's errors.
    """
    parts: list[str] = []
    for error in errors:
        section = str(error.get("section", ""))
        index = error.get("index")
        location = section if index is None else "{}[{}]".format(section, index)
        message = str(error.get("message", "Invalid value"))
        # The structured message is a standalone sentence ("Company is
        # required"); mid-sentence after the location it should not be
        # capitalised.
        message = message[:1].lower() + message[1:]
        parts.append("{}: {}".format(location, message) if location else message)
    return "; ".join(parts) or "Profile update failed validation."


class ProfileValidationError(Exception):
    """A profile edit that is incomplete rather than malformed.

    Malformed bodies -- a string where a list belongs -- are pydantic's job and
    stay a ``RequestValidationError``. This is the layer above: the body parsed
    fine, but an entry the user is actually editing has no title, or no company,
    or no institution.

    Carries both renderings the frontend needs: ``detail`` for the toast and
    ``errors`` for highlighting the offending inputs. Answered as a 422 by
    :func:`app.core.errors.profile_validation_exception_handler`.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        self.detail = format_profile_errors(errors)
        super().__init__(self.detail)


def _add_error(
    errors: list[dict[str, Any]],
    section: str,
    index: int | None,
    field: str,
    message: str,
) -> None:
    """Record one field error in the shape the frontend highlights on."""
    errors.append(
        {"section": section, "index": index, "field": field, "message": message}
    )


def _strict_str(
    errors: list[dict[str, Any]],
    item: dict[str, Any],
    key: str,
    *,
    section: str,
    index: int,
    label: str,
    max_chars: int,
    required: bool = False,
) -> str | None:
    """Clean one string field, recording a missing-or-too-long error.

    The cleaned value is returned either way: collecting every error in one pass
    beats telling the user about one problem per save.
    """
    value = _clean_str(item.get(key))
    if value is None:
        if required:
            _add_error(errors, section, index, key, "{} is required".format(label))
        return None
    if len(value) > max_chars:
        _add_error(
            errors,
            section,
            index,
            key,
            "{} must be {} characters or less".format(label, max_chars),
        )
    return value


def _strict_str_list(
    errors: list[dict[str, Any]],
    value: Any,
    *,
    section: str,
    index: int | None,
    field: str,
    label: str,
    max_chars: int,
    max_items: int | None = None,
) -> list[str]:
    """Clean a list of plain strings the strict way.

    Blank items are removed rather than rejected -- an empty chip in a tag input
    is a user mid-edit, not a mistake -- and duplicates are removed
    case-insensitively. Only over-long items and over-long lists are errors.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    seen: set[str] = set()
    out: list[str] = []
    too_long = False
    for item in value:
        cleaned = _clean_str(item)
        if cleaned is None:
            continue
        if len(cleaned) > max_chars:
            # One error per list, not one per item: the user gets the rule once.
            too_long = True
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)

    if too_long:
        _add_error(
            errors,
            section,
            index,
            field,
            "Each {} must be {} characters or less".format(label, max_chars),
        )
    if max_items is not None and len(out) > max_items:
        _add_error(
            errors,
            section,
            index,
            field,
            "Keep {} to {} or fewer".format(field.replace("_", " "), max_items),
        )
    return out


def _is_blank_entry(item: dict[str, Any]) -> bool:
    """True when nothing in this entry carries content.

    Booleans do not count: a row where the user only flipped the "I work here
    now" toggle still says nothing about the job. ``_clean_str`` already returns
    None for a bool, so that falls out of the same helper the rest of the module
    uses.
    """
    for value in item.values():
        if isinstance(value, list):
            if _clean_str_list(value):
                return False
        elif _clean_str(value) is not None:
            return False
    return True


def _validate_work_experience(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require a title and a company on every role the user actually filled in."""
    section = "work_experience"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        entry = WorkExperience(
            title=_strict_str(
                errors, item, "title", section=section, index=index,
                label="Job title", max_chars=MAX_NAME_CHARS, required=True,
            ),
            company=_strict_str(
                errors, item, "company", section=section, index=index,
                label="Company", max_chars=MAX_NAME_CHARS, required=True,
            ),
            location=_strict_str(
                errors, item, "location", section=section, index=index,
                label="Location", max_chars=MAX_NAME_CHARS,
            ),
            start_date=_strict_str(
                errors, item, "start_date", section=section, index=index,
                label="Start date", max_chars=MAX_DATE_CHARS,
            ),
            end_date=_strict_str(
                errors, item, "end_date", section=section, index=index,
                label="End date", max_chars=MAX_DATE_CHARS,
            ),
            current=_clean_bool(item.get("current")),
            highlights=_strict_str_list(
                errors, item.get("highlights"), section=section, index=index,
                field="highlights", label="highlight",
                max_chars=MAX_HIGHLIGHT_CHARS, max_items=MAX_HIGHLIGHTS,
            ),
        )
        out.append(entry.model_dump())
    return out


def _validate_education(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require an institution, plus a degree or a field of study."""
    section = "education"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        degree = _strict_str(
            errors, item, "degree", section=section, index=index,
            label="Degree", max_chars=MAX_NAME_CHARS,
        )
        field = _strict_str(
            errors, item, "field", section=section, index=index,
            label="Field of study", max_chars=MAX_NAME_CHARS,
        )
        # Either one says what was studied. Demanding both would reject "BSc"
        # and "Computer Science" alike, and resumes list them both ways.
        if degree is None and field is None:
            _add_error(
                errors, section, index, "degree",
                "Degree or field of study is required",
            )
        entry = Education(
            degree=degree,
            institution=_strict_str(
                errors, item, "institution", section=section, index=index,
                label="Institution", max_chars=MAX_NAME_CHARS, required=True,
            ),
            field=field,
            start_date=_strict_str(
                errors, item, "start_date", section=section, index=index,
                label="Start date", max_chars=MAX_DATE_CHARS,
            ),
            end_date=_strict_str(
                errors, item, "end_date", section=section, index=index,
                label="End date", max_chars=MAX_DATE_CHARS,
            ),
            details=_strict_str(
                errors, item, "details", section=section, index=index,
                label="Details", max_chars=MAX_DETAIL_CHARS,
            ),
        )
        out.append(entry.model_dump())
    return out


def _validate_certifications(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require a name on every certification the user actually filled in."""
    section = "certifications"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        entry = Certification(
            name=_strict_str(
                errors, item, "name", section=section, index=index,
                label="Certification name", max_chars=MAX_NAME_CHARS, required=True,
            ),
            issuer=_strict_str(
                errors, item, "issuer", section=section, index=index,
                label="Issuer", max_chars=MAX_NAME_CHARS,
            ),
            year=_strict_str(
                errors, item, "year", section=section, index=index,
                label="Year", max_chars=MAX_DATE_CHARS,
            ),
        )
        out.append(entry.model_dump())
    return out


def _validate_projects(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require a name on every project the user actually filled in."""
    section = "projects"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        entry = Project(
            name=_strict_str(
                errors, item, "name", section=section, index=index,
                label="Project name", max_chars=MAX_NAME_CHARS, required=True,
            ),
            description=_strict_str(
                errors, item, "description", section=section, index=index,
                label="Description", max_chars=MAX_DETAIL_CHARS,
            ),
            technologies=_strict_str_list(
                errors, item.get("technologies"), section=section, index=index,
                field="technologies", label="technology", max_chars=MAX_SKILL_CHARS,
            ),
            link=_strict_str(
                errors, item, "link", section=section, index=index,
                label="Link", max_chars=MAX_LINK_CHARS,
            ),
        )
        out.append(entry.model_dump())
    return out


def validate_section_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Validate a user's partial profile edit before anything is merged.

    Runs on the output of :meth:`ProfileUpdateRequest.section_updates`, which is
    the incoming partial and nothing else -- sections the user did not send are
    never inspected, so a title-less role left over from an old resume
    extraction cannot block an unrelated edit to the skills list.

    Every section is checked before raising, so one save reports every problem
    rather than making the user fix them one at a time.

    Args:
        updates: Section name to new value, as sent by the profile editor.

    Returns:
        The same mapping with each section cleaned: strings trimmed, entirely
        blank entries and blank list items removed, list items de-duplicated
        case-insensitively.

    Raises:
        ProfileValidationError: If any entry the user filled in is missing a
            required field or breaks a length limit. Nothing is written.
    """
    errors: list[dict[str, Any]] = []
    cleaned: dict[str, Any] = dict(updates)

    if "summary" in cleaned:
        summary = _clean_str(cleaned["summary"])
        if summary is not None and len(summary) > MAX_SUMMARY_CHARS:
            _add_error(
                errors, "summary", None, "summary",
                "Summary must be {} characters or less".format(MAX_SUMMARY_CHARS),
            )
        # An empty summary is a legitimate edit -- the user is clearing it --
        # and the field is nullable, so it lands as None rather than "".
        cleaned["summary"] = summary

    if "work_experience" in cleaned:
        cleaned["work_experience"] = _validate_work_experience(
            cleaned["work_experience"], errors
        )
    if "education" in cleaned:
        cleaned["education"] = _validate_education(cleaned["education"], errors)
    if "certifications" in cleaned:
        cleaned["certifications"] = _validate_certifications(
            cleaned["certifications"], errors
        )
    if "projects" in cleaned:
        cleaned["projects"] = _validate_projects(cleaned["projects"], errors)
    if "skills" in cleaned:
        cleaned["skills"] = _strict_str_list(
            errors, cleaned["skills"], section="skills", index=None,
            field="skills", label="skill", max_chars=MAX_SKILL_CHARS,
        )
    if "achievements" in cleaned:
        cleaned["achievements"] = _strict_str_list(
            errors, cleaned["achievements"], section="achievements", index=None,
            field="achievements", label="achievement",
            max_chars=MAX_ACHIEVEMENT_CHARS,
        )

    if errors:
        raise ProfileValidationError(errors)
    return cleaned


# --------------------------------------------------------------------------
# Request / response models
# --------------------------------------------------------------------------


class ProfileUploadRequest(BaseModel):
    """Optional metadata sent alongside the multipart resume upload.

    The file itself arrives as an ``UploadFile``, not through this model.
    """

    filename: str | None = None


class ProfileResponse(BaseModel):
    """A user's stored profile."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    raw_text: str | None = None
    parsed_json: ParsedProfile | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    """A partial profile update (manual enrichment).

    Sections are sent at the top level -- ``{"skills": [...]}`` -- which is what
    the profile page's inline editor posts. A ``{"parsed_json": {...}}`` wrapper
    is also accepted and merged identically, so either shape works.

    A section that is present replaces that section wholesale; a section that is
    absent is left untouched. ``None`` and "absent" therefore mean the same
    thing, which is why there is no way to null a section out -- send an empty
    list or an empty string instead.
    """

    model_config = ConfigDict(extra="ignore")

    summary: str | None = None
    work_experience: list[WorkExperience] | None = None
    education: list[Education] | None = None
    skills: list[str] | None = None
    certifications: list[Certification] | None = None
    projects: list[Project] | None = None
    achievements: list[str] | None = None

    raw_text: str | None = None
    parsed_json: ParsedProfile | None = None

    def section_updates(self) -> dict[str, Any]:
        """Return only the profile sections this request actually sets.

        Top-level sections win over the same section repeated inside
        ``parsed_json``.

        Returns:
            A mapping of section name to its new, JSON-ready value.
        """
        updates: dict[str, Any] = {}
        if self.parsed_json is not None:
            nested = self.parsed_json.model_dump(exclude_unset=True)
            updates.update({k: v for k, v in nested.items() if k in PROFILE_SECTIONS})
        provided = self.model_dump(exclude_unset=True)
        for section in PROFILE_SECTIONS:
            value = getattr(self, section)
            if section in provided and value is not None:
                # Round-trip through ParsedProfile so the stored value is plain
                # JSON with every sub-model field present.
                updates[section] = ParsedProfile(**{section: value}).model_dump()[section]
        return updates


class ProfileGap(BaseModel):
    """A suggestion surfaced when a profile section is missing or thin.

    ``id`` is stable across requests so the frontend can persist a dismissal in
    localStorage and have it stay dismissed.
    """

    id: str
    section: str
    # "missing" -- the section is empty. "thin" -- present but underweight.
    severity: str
    message: str


class ProfileGapsResponse(BaseModel):
    """The gap-detection result for the current user's profile."""

    gaps: list[ProfileGap] = Field(default_factory=list)
