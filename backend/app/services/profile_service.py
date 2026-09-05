"""Profile persistence, manual enrichment, and gap detection.

The routes stay thin: every read, write, and merge of a profile row goes through
this module, and :func:`detect_gaps` is the one place that decides what counts
as a thin profile.

Gap detection is deliberately rule-based, not a model call. The pipeline doc
calls it "AI-powered", but nudging is a per-page-load, per-keystroke concern --
the profile page refetches it after every inline edit. Spending a model call and
a second of latency to notice that a list is empty would make the page worse,
and a rule gives the same nudge every time, which is what makes a dismissal
stick. The AI budget belongs in analysis and generation, where judgement is
actually required.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.api.schemas.profile import PROFILE_SECTIONS, ParsedProfile
from app.models.profile import Profile

# --------------------------------------------------------------------------
# Thinness thresholds
# --------------------------------------------------------------------------

# A summary shorter than this reads as a placeholder rather than a positioning
# statement, and gives the generator nothing to work with.
MIN_SUMMARY_WORDS = 30

# Below this, a skills list cannot support a meaningful JD comparison.
MIN_SKILLS = 3


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def _as_uuid(user_id: uuid.UUID | str) -> uuid.UUID:
    """Coerce a Supabase ``sub`` claim into a UUID.

    ``get_current_user`` hands routes a string; the primary key is a UUID.

    Raises:
        ValueError: If the id is not a valid UUID.
    """
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def get_profile(db: Session, user_id: uuid.UUID | str) -> Profile | None:
    """Return the stored profile for a user, or None if they have none yet.

    A None here is what drives the onboarding redirect: the frontend treats a
    404 from ``GET /profile`` as "this user has not uploaded a resume".
    """
    return db.get(Profile, _as_uuid(user_id))


def upsert_profile(
    db: Session,
    user_id: uuid.UUID | str,
    raw_text: str | None,
    parsed_json: dict[str, Any] | None,
) -> Profile:
    """Create or replace a user's profile row.

    A re-upload replaces both columns outright rather than merging: the new
    resume is the user's new statement of record, and silently keeping stale
    roles from a previous upload would be worse than losing a manual edit.
    ``PATCH /profile`` is the merging path.

    Timestamps are stamped here rather than left to the column defaults so the
    returned object is complete without a post-commit refresh round trip.
    """
    now = datetime.now(timezone.utc)
    profile = get_profile(db, user_id)

    if profile is None:
        profile = Profile(
            user_id=_as_uuid(user_id),
            raw_text=raw_text,
            parsed_json=parsed_json,
            created_at=now,
            updated_at=now,
        )
        db.add(profile)
    else:
        profile.raw_text = raw_text
        profile.parsed_json = parsed_json
        profile.updated_at = now

    db.commit()
    return profile


def merge_profile(
    db: Session,
    profile: Profile,
    section_updates: dict[str, Any],
    raw_text: str | None = None,
) -> Profile:
    """Apply a manual enrichment to a stored profile and save it.

    Args:
        db: The active session.
        profile: The row to update.
        section_updates: Sections to replace, as returned by
            ``ProfileUpdateRequest.section_updates``.
        raw_text: Replaces the stored resume text when given.

    Returns:
        The same, now-updated, profile row.
    """
    profile.parsed_json = merge_profile_updates(profile.parsed_json, section_updates)
    if raw_text is not None:
        profile.raw_text = raw_text
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    return profile


def merge_profile_updates(
    existing: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Merge a manual enrichment into the stored parsed profile.

    The merge is section-by-section, not field-by-field: a section that appears
    in ``updates`` replaces that section wholesale, and a section that does not
    appear is left exactly as it was. Deep-merging inside a list has no sensible
    definition -- there is no stable identity for "the second job" -- so the
    editor sends a whole section back and this replaces it.

    The result always carries all seven sections, so callers never have to guard
    against a missing key.

    Args:
        existing: The currently stored ``parsed_json``, or None.
        updates: New values keyed by section name. Unknown keys are ignored.

    Returns:
        A new dict; neither argument is mutated.
    """
    merged = ParsedProfile.model_validate(existing or {}).model_dump()
    for section in PROFILE_SECTIONS:
        if section in updates:
            merged[section] = updates[section]
    # Re-validate so a hand-written update is normalised the same way an
    # extracted one is.
    return ParsedProfile.model_validate(merged).model_dump()


# --------------------------------------------------------------------------
# Gap detection
# --------------------------------------------------------------------------


def _gap(gap_id: str, section: str, severity: str, message: str) -> dict[str, str]:
    """Build one gap record."""
    return {"id": gap_id, "section": section, "severity": severity, "message": message}


def detect_gaps(parsed_json: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return nudges for profile sections that are missing or thin.

    Two severities:

    * ``missing`` -- the section is empty. The AI has nothing at all to draw on.
    * ``thin`` -- the section exists but is underweight in a way that will show
      up in generated output.

    Gap ids are stable strings tied to the section and the rule, never to a list
    index, because the frontend persists dismissals in localStorage. An
    index-based id would silently resurrect a dismissed nudge the moment a user
    reordered their roles.

    Args:
        parsed_json: The stored profile sections, or None.

    Returns:
        A list of dicts matching ``api.schemas.profile.ProfileGap``, ordered by
        the section order in ``PROFILE_SECTIONS``.
    """
    profile = ParsedProfile.model_validate(parsed_json or {})
    gaps: list[dict[str, str]] = []

    # --- summary ---
    summary = (profile.summary or "").strip()
    if not summary:
        gaps.append(
            _gap(
                "summary-missing",
                "summary",
                "missing",
                "Add a short professional summary. It is the first thing every "
                "generated cover letter builds on.",
            )
        )
    elif len(summary.split()) < MIN_SUMMARY_WORDS:
        gaps.append(
            _gap(
                "summary-thin",
                "summary",
                "thin",
                "Your summary is only {} words. Two or three sentences on what "
                "you do and the impact you have had gives tailored outputs much "
                "more to work with.".format(len(summary.split())),
            )
        )

    # --- work experience ---
    if not profile.work_experience:
        gaps.append(
            _gap(
                "work_experience-missing",
                "work_experience",
                "missing",
                "Add your work experience. Without it, fit analysis has nothing "
                "to compare against a job description.",
            )
        )
    else:
        bare = [
            role
            for role in profile.work_experience
            if not [h for h in role.highlights if h.strip()]
        ]
        if bare:
            names = ", ".join(
                role.title or role.company or "an untitled role" for role in bare[:3]
            )
            gaps.append(
                _gap(
                    "work_experience-thin",
                    "work_experience",
                    "thin",
                    "{} {} no bullet points yet. Add two or three achievements "
                    "with numbers -- they are what tailored resumes are built "
                    "from.".format(
                        names, "has" if len(bare) == 1 else "have"
                    ),
                )
            )

    # --- education ---
    if not profile.education:
        gaps.append(
            _gap(
                "education-missing",
                "education",
                "missing",
                "Add your education. Some roles screen on it before anything else.",
            )
        )
    elif any(not (entry.degree or "").strip() for entry in profile.education):
        gaps.append(
            _gap(
                "education-thin",
                "education",
                "thin",
                "One of your education entries has no degree or qualification "
                "name. Add it so it reads correctly on a generated resume.",
            )
        )

    # --- skills ---
    if not profile.skills:
        gaps.append(
            _gap(
                "skills-missing",
                "skills",
                "missing",
                "Add your skills. Keyword matching against a job description "
                "starts here.",
            )
        )
    elif len(profile.skills) < MIN_SKILLS:
        gaps.append(
            _gap(
                "skills-thin",
                "skills",
                "thin",
                "Only {} skill{} listed. List the tools, languages, and "
                "competencies you would be comfortable being asked about.".format(
                    len(profile.skills), "" if len(profile.skills) == 1 else "s"
                ),
            )
        )

    # --- certifications ---
    if not profile.certifications:
        gaps.append(
            _gap(
                "certifications-missing",
                "certifications",
                "missing",
                "No certifications listed. Add any you hold -- they are an easy "
                "differentiator when a job description asks for one by name.",
            )
        )

    # --- projects ---
    if not profile.projects:
        gaps.append(
            _gap(
                "projects-missing",
                "projects",
                "missing",
                "No projects listed. Projects are often the strongest evidence "
                "for a skill your job history does not show.",
            )
        )

    # --- achievements ---
    if not profile.achievements:
        gaps.append(
            _gap(
                "achievements-missing",
                "achievements",
                "missing",
                "No achievements listed. Awards, talks, and publications give a "
                "cover letter something concrete to open with.",
            )
        )

    return gaps
