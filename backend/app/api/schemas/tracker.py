"""Schemas for the job application tracker endpoints.

The tracker is the one place in Applify where the *application* is the subject
rather than the conversation, so this is where the application's own facts live:
the posting's URL, where the job is, what it pays, where the user found it, when
they sent it, and what they have to do next.

``TrackerUpdateRequest`` is a partial update in the strict sense -- a field that
is absent is left alone, and a field sent as ``null`` is cleared. The difference
is read from ``model_fields_set``, which is why the route dumps the payload with
``exclude_unset=True`` rather than checking each value for None.

An empty body is rejected. "Update nothing" is never what a client meant, and
accepting it would turn a frontend bug into a silent 200.
"""

import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Field ceilings. Generous, but bounded: every one of these is free text a
# client could otherwise send a megabyte of.
MAX_URL_CHARS = 2000
MAX_SHORT_TEXT_CHARS = 255
MAX_NEXT_ACTION_CHARS = 300
MAX_NOTES_CHARS = 5000

# The only URL schemes a job posting can sensibly have. Anything else -- most
# of all ``javascript:`` -- is a link the frontend would be wrong to render.
URL_SCHEMES = ("http://", "https://")

INVALID_URL = "job_url must start with http:// or https://"
EMPTY_UPDATE = "Send at least one field to update"


class ApplicationStatus(str, Enum):
    """Where an application currently stands.

    Declaring it as an enum is what makes ``PATCH /tracker/{chat_id}`` reject an
    unknown status with a 422 instead of writing a value nothing else in the
    product understands.
    """

    NOT_APPLIED = "not_applied"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"


class ApplicationPriority(str, Enum):
    """How much attention this application deserves next.

    Nullable on the row: "no opinion yet" is a real state, and defaulting every
    new application to medium would make the column meaningless.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResumeType(str, Enum):
    """Whether the user sent the base resume or one generated for this job.

    ``TAILORED`` is set automatically the first time a resume is generated in
    the chat -- never by the client. The tracker table renders it as
    "AI-Tailored".
    """

    UNALTERED = "unaltered"
    TAILORED = "tailored"


class TrackerSort(str, Enum):
    """The orderings ``GET /tracker`` offers.

    ``created_at``, ``applied_at`` and ``fit_score`` are newest/highest first --
    the most recent application and the strongest match are what the user is
    looking for. ``next_action_date`` is the exception and runs *ascending*:
    the follow-up due today matters more than the one due next month. Rows with
    no value for the chosen key always sort last, whichever direction applies.
    """

    CREATED_AT = "created_at"
    APPLIED_AT = "applied_at"
    NEXT_ACTION_DATE = "next_action_date"
    FIT_SCORE = "fit_score"


def validate_job_url(value: str | None) -> str | None:
    """Return a trimmed http(s) URL, or None. Raise on anything else."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if not trimmed.lower().startswith(URL_SCHEMES):
        raise ValueError(INVALID_URL)
    return trimmed


def _blank_to_none(value: str | None) -> str | None:
    """Trim a free-text field, treating whitespace-only as cleared."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class TrackerEntry(BaseModel):
    """A tracker row as returned to the client.

    Flattened for the tracker table: everything a row renders comes from this
    one object, so the page never fans out to ``/chats`` or ``/analyses`` to
    fill in a column. ``date_added`` is the *chat's* creation time -- the moment
    the user started working on this application -- while ``created_at`` is the
    tracker row's own. They are written together and normally match.

    ``days_since_applied`` and ``next_action_due`` are computed per request
    rather than stored: both are answers about *today*, and a stored answer
    would be wrong tomorrow morning.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    job_title: str | None = None
    company: str | None = None
    date_added: datetime | None = None
    # "quick" or "detailed"; null until an analysis has been run.
    analysis_type: str | None = None
    resume_type: ResumeType
    status: ApplicationStatus
    # From the chat's analysis, when it has one.
    fit_score: int | None = None
    created_at: datetime
    updated_at: datetime
    # The Phase 6 name for job_title, kept so the sidebar's optimistic entry and
    # the fetched one stay the same shape.
    title: str | None = None

    # -- the application's own facts ---------------------------------------
    job_url: str | None = None
    location: str | None = None
    salary: str | None = None
    source: str | None = None
    applied_at: datetime | None = None
    next_action: str | None = None
    next_action_date: date | None = None
    notes: str | None = None
    priority: ApplicationPriority | None = None

    # -- derived, as of the moment this response was built ------------------
    # Whole days since the application was sent; null when it has not been.
    days_since_applied: int | None = None
    # True when a next action is set and its date has arrived or passed.
    next_action_due: bool = False


class TrackerUpdateRequest(BaseModel):
    """Partial update to one tracker row.

    Every field is optional and every field may be sent as ``null`` to clear it
    -- except ``status``, which the row always has. ``resume_type`` is absent on
    purpose: it follows from whether a resume was generated in the chat, and a
    client that could set it could claim a tailored resume it never generated.
    """

    status: ApplicationStatus | None = None
    job_url: str | None = Field(default=None, max_length=MAX_URL_CHARS)
    location: str | None = Field(default=None, max_length=MAX_SHORT_TEXT_CHARS)
    salary: str | None = Field(default=None, max_length=MAX_SHORT_TEXT_CHARS)
    source: str | None = Field(default=None, max_length=MAX_SHORT_TEXT_CHARS)
    applied_at: datetime | None = None
    next_action: str | None = Field(default=None, max_length=MAX_NEXT_ACTION_CHARS)
    next_action_date: date | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES_CHARS)
    priority: ApplicationPriority | None = None

    @field_validator("job_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        """Reject anything that is not an http(s) URL."""
        return validate_job_url(value)

    @field_validator("location", "salary", "source", "next_action", "notes")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        """Trim free text; a whitespace-only value clears the field."""
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _reject_empty(self) -> "TrackerUpdateRequest":
        """Refuse a body that names no field at all.

        ``model_fields_set`` counts a field sent explicitly as ``null`` -- that
        is a clear, not an omission -- so ``{"notes": null}`` is accepted while
        ``{}`` is a 422.
        """
        if not self.model_fields_set:
            raise ValueError(EMPTY_UPDATE)
        return self
