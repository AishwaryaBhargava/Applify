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
