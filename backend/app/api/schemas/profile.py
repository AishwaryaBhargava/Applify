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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    "publications",
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
    # "Full-time", "Internship", "Contract", "Freelance". Left free-form on
    # purpose: an enum would reject the half-dozen spellings people actually
    # use, and nothing downstream branches on the value.
    employment_type: str | None = None
    # Recognition tied to this specific role, kept apart from `highlights` so a
    # generated resume can lead with an award rather than bury it in bullets.
    awards: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """A single education entry."""

    model_config = ConfigDict(extra="ignore")

    degree: str | None = None
    institution: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    details: str | None = None
    # As written: "8.7/10", "3.8 GPA", "First Class". Never parsed to a number
    # -- grading scales differ by country and a float would lose the scale.
    gpa: str | None = None
    coursework: list[str] = Field(default_factory=list)
    honors: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    """A professional certification or licence."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    issuer: str | None = None
    year: str | None = None
    expires: str | None = None
    credential_url: str | None = None
    description: str | None = None


class ProjectLinks(BaseModel):
    """The places one project can be found.

    Three named slots rather than a list, because a generated resume renders
    them differently: source, a running deployment, and a walkthrough are not
    interchangeable.
    """

    model_config = ConfigDict(extra="ignore")

    github: str | None = None
    live: str | None = None
    demo: str | None = None

    def first(self) -> str | None:
        """Return the first link that is set, in github/live/demo order."""
        return self.github or self.live or self.demo


class Project(BaseModel):
    """A personal, academic, or professional project."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    # Kept alongside `links` for backward compatibility: every profile stored
    # before this field existed carries a single `link`, and every consumer
    # still reads it. When it is absent it is filled from `links` rather than
    # left empty, so an old reader never loses a URL a new writer supplied.
    link: str | None = None
    links: ProjectLinks = Field(default_factory=ProjectLinks)
    start_date: str | None = None
    end_date: str | None = None
    # Key contributions and impact, the project equivalent of a role's bullets.
    highlights: list[str] = Field(default_factory=list)


class Publication(BaseModel):
    """A paper, article, patent, or preprint the user authored."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    # One free-text string ("Rivera, J., Okafor, N.") rather than a list: author
    # order matters and citation styles differ, so splitting would lose both.
    authors: str | None = None
    url: str | None = None
    # "Published", "Under review", "Accepted", "Preprint".
    status: str | None = None
    year: str | None = None


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
    publications: list[Publication] = Field(default_factory=list)


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
            employment_type=_clean_str(item.get("employment_type")),
            awards=_clean_str_list(item.get("awards")),
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
            gpa=_clean_str(item.get("gpa")),
            coursework=_clean_str_list(item.get("coursework")),
            honors=_clean_str_list(item.get("honors")),
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
            expires=_clean_str(item.get("expires")),
            credential_url=_clean_str(item.get("credential_url")),
            description=_clean_str(item.get("description")),
        )
        if entry.name:
            out.append(entry)
    return out


def _coerce_project_links(value: Any) -> ProjectLinks:
    """Build a project's link set, tolerating a bare string or a missing key."""
    if isinstance(value, str):
        return ProjectLinks(github=_clean_str(value))
    if not isinstance(value, dict):
        return ProjectLinks()
    return ProjectLinks(
        github=_clean_str(value.get("github")),
        live=_clean_str(value.get("live")),
        demo=_clean_str(value.get("demo")),
    )


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
        links = _coerce_project_links(item.get("links"))
        entry = Project(
            name=_clean_str(item.get("name")),
            description=_clean_str(item.get("description")),
            technologies=_clean_str_list(item.get("technologies"), MAX_SKILL_CHARS),
            # An old profile has only `link`; a new one may have only `links`.
            # Filling the legacy field keeps both readers working.
            link=_clean_str(item.get("link")) or links.first(),
            links=links,
            start_date=_clean_str(item.get("start_date")),
            end_date=_clean_str(item.get("end_date")),
            highlights=_clean_str_list(item.get("highlights")),
        )
        if entry.name or entry.description:
            out.append(entry)
    return out


def _coerce_publications(items: Any) -> list[Publication]:
    """Build publications; a bare string is read as the title."""
    out: list[Publication] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            title = _clean_str(item)
            if title:
                out.append(Publication(title=title))
            continue
        if not isinstance(item, dict):
            continue
        entry = Publication(
            title=_clean_str(item.get("title")),
            authors=_clean_str(item.get("authors")),
            url=_clean_str(item.get("url")),
            status=_clean_str(item.get("status")),
            year=_clean_str(item.get("year")),
        )
        if entry.title:
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
        publications=_coerce_publications(raw.get("publications")),
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
# Short labels kept as free text: employment type, GPA, publication status.
MAX_LABEL_CHARS = 100
# A paper title is routinely longer than a job title and shorter than an
# abstract, so it gets its own ceiling rather than borrowing either.
MAX_TITLE_CHARS = 500
MAX_AUTHORS_CHARS = 1000
# A course name or an honour, not a paragraph about one.
MAX_COURSEWORK_ITEMS = 50
MAX_AWARDS = 20
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
        elif isinstance(value, dict):
            # A project whose only content is a github URL is not a blank row.
            if not _is_blank_entry(value):
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
            employment_type=_strict_str(
                errors, item, "employment_type", section=section, index=index,
                label="Employment type", max_chars=MAX_LABEL_CHARS,
            ),
            awards=_strict_str_list(
                errors, item.get("awards"), section=section, index=index,
                field="awards", label="award",
                max_chars=MAX_HIGHLIGHT_CHARS, max_items=MAX_AWARDS,
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
            gpa=_strict_str(
                errors, item, "gpa", section=section, index=index,
                label="GPA", max_chars=MAX_LABEL_CHARS,
            ),
            coursework=_strict_str_list(
                errors, item.get("coursework"), section=section, index=index,
                field="coursework", label="course", max_chars=MAX_NAME_CHARS,
                max_items=MAX_COURSEWORK_ITEMS,
            ),
            honors=_strict_str_list(
                errors, item.get("honors"), section=section, index=index,
                field="honors", label="honour", max_chars=MAX_NAME_CHARS,
                max_items=MAX_COURSEWORK_ITEMS,
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
            expires=_strict_str(
                errors, item, "expires", section=section, index=index,
                label="Expiry", max_chars=MAX_DATE_CHARS,
            ),
            credential_url=_strict_str(
                errors, item, "credential_url", section=section, index=index,
                label="Credential URL", max_chars=MAX_LINK_CHARS,
            ),
            description=_strict_str(
                errors, item, "description", section=section, index=index,
                label="Description", max_chars=MAX_DETAIL_CHARS,
            ),
        )
        out.append(entry.model_dump())
    return out


def _validate_project_links(
    value: Any,
    errors: list[dict[str, Any]],
    *,
    section: str,
    index: int,
) -> ProjectLinks:
    """Clean one project's link set, recording an over-long URL as an error."""
    item = value if isinstance(value, dict) else {}
    return ProjectLinks(
        **{
            key: _strict_str(
                errors, item, key, section=section, index=index,
                label=label, max_chars=MAX_LINK_CHARS,
            )
            for key, label in (
                ("github", "GitHub link"),
                ("live", "Live link"),
                ("demo", "Demo link"),
            )
        }
    )


def _validate_projects(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require a name on every project the user actually filled in."""
    section = "projects"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        links = _validate_project_links(
            item.get("links"), errors, section=section, index=index
        )
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
            )
            or links.first(),
            links=links,
            start_date=_strict_str(
                errors, item, "start_date", section=section, index=index,
                label="Start date", max_chars=MAX_DATE_CHARS,
            ),
            end_date=_strict_str(
                errors, item, "end_date", section=section, index=index,
                label="End date", max_chars=MAX_DATE_CHARS,
            ),
            highlights=_strict_str_list(
                errors, item.get("highlights"), section=section, index=index,
                field="highlights", label="highlight",
                max_chars=MAX_HIGHLIGHT_CHARS, max_items=MAX_HIGHLIGHTS,
            ),
        )
        out.append(entry.model_dump())
    return out


def _validate_publications(
    items: Any, errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require a title on every publication the user actually filled in."""
    section = "publications"
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or _is_blank_entry(item):
            continue
        entry = Publication(
            title=_strict_str(
                errors, item, "title", section=section, index=index,
                label="Publication title", max_chars=MAX_TITLE_CHARS, required=True,
            ),
            authors=_strict_str(
                errors, item, "authors", section=section, index=index,
                label="Authors", max_chars=MAX_AUTHORS_CHARS,
            ),
            url=_strict_str(
                errors, item, "url", section=section, index=index,
                label="Link", max_chars=MAX_LINK_CHARS,
            ),
            status=_strict_str(
                errors, item, "status", section=section, index=index,
                label="Status", max_chars=MAX_LABEL_CHARS,
            ),
            year=_strict_str(
                errors, item, "year", section=section, index=index,
                label="Year", max_chars=MAX_DATE_CHARS,
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
    if "publications" in cleaned:
        cleaned["publications"] = _validate_publications(
            cleaned["publications"], errors
        )
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
    publications: list[Publication] | None = None

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


# --------------------------------------------------------------------------
# Supplementary file import
# --------------------------------------------------------------------------


class ImportSheet(BaseModel):
    """One sheet, table, or document section that was read.

    A skipped sheet still appears, with ``skipped_reason`` set: a user who
    uploaded a workbook with a references tab should be told it was left out
    rather than left to wonder why nothing from it turned up.
    """

    name: str
    rows: int = 0
    cols: int = 0
    skipped_reason: str | None = None


class ImportSource(BaseModel):
    """What the proposal was read from. Nothing about the file is stored."""

    filename: str | None = None
    # "xlsx", "csv", "docx", "pdf", "txt", "md", or "json".
    kind: str
    sheets: list[ImportSheet] = Field(default_factory=list)


class ProfileChange(BaseModel):
    """One entry-level difference between the stored profile and the proposal."""

    section: str
    # "added", "updated", "unchanged", or "removed".
    kind: str
    # Human-readable, e.g. "Senior Backend Engineer at Kestrel Labs".
    label: str
    # The normalised identity the diff matched on. Stable across a re-import,
    # so a client can keep a per-entry decision through a refresh.
    key: str
    # Position in the *proposal's* section list, or null for a removed entry.
    index: int | None = None
    # Field names that differ. Only meaningful for "updated".
    fields: list[str] = Field(default_factory=list)


class ImportChangeCounts(BaseModel):
    """How many entries fall into each change kind."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0


class ImportSummary(ImportChangeCounts):
    """Totals across the whole proposal, plus a per-section breakdown."""

    sections: dict[str, ImportChangeCounts] = Field(default_factory=dict)


class ProfileImportResponse(BaseModel):
    """The result of ``POST /profile/import``. Nothing has been saved."""

    proposal: ParsedProfile
    changes: list[ProfileChange] = Field(default_factory=list)
    summary: ImportSummary = Field(default_factory=ImportSummary)
    source: ImportSource
    # The extracted text exactly as it was fed to the merge model, so the
    # client can echo it back to /profile/import/apply. The server stores
    # nothing between the two calls, so this is the only place it exists.
    # Capped at the same 200k as raw_text, keeping the head.
    document_text: str = ""
    # "azure" or "groq" -- which model produced the merge.
    provider: str | None = None


class ProfileImportApplyRequest(BaseModel):
    """The subset of a reviewed proposal the user chose to keep.

    ``parsed_json`` is the whole proposal as returned by ``/profile/import``,
    optionally edited by hand, and ``sections`` names which of its sections to
    write. Anything not named is left exactly as it is stored.

    ``filename`` and ``document_text`` are echoed back by the client because the
    server keeps nothing between the two calls -- no upload is stored, no
    proposal is cached. When ``document_text`` is present it is appended to the
    profile's ``raw_text`` under a dated header.
    """

    model_config = ConfigDict(extra="ignore")

    parsed_json: ParsedProfile
    sections: list[str] = Field(default_factory=list)
    filename: str | None = None
    document_text: str | None = None

    @field_validator("sections")
    @classmethod
    def _known_sections(cls, value: list[str]) -> list[str]:
        """Reject a section name the profile does not have.

        A typo would otherwise be silently ignored and the user would be told
        their import applied when nothing was written.
        """
        unknown = [name for name in value if name not in PROFILE_SECTIONS]
        if unknown:
            raise ValueError(
                "Unknown profile section(s): {}".format(", ".join(sorted(unknown)))
            )
        return value

    def selected_updates(self) -> dict[str, Any]:
        """Return ``{section: proposed value}`` for the chosen sections only."""
        proposal = self.parsed_json.model_dump()
        return {section: proposal[section] for section in self.sections}
