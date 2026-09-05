"""Schemas for the job application tracker endpoints."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ApplicationStatus(str, Enum):
    """Where an application currently stands.

    The only field of a tracker row the user edits by hand. Declaring it as an
    enum is what makes ``PATCH /tracker/{chat_id}`` reject an unknown status
    with a 422 instead of writing a value nothing else in the product
    understands.
    """

    NOT_APPLIED = "not_applied"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"


class ResumeType(str, Enum):
    """Whether the user sent the base resume or one generated for this job.

    ``TAILORED`` is set automatically the first time a resume is generated in
    the chat -- never by the client. The tracker table renders it as
    "AI-Tailored".
    """

    UNALTERED = "unaltered"
    TAILORED = "tailored"


class TrackerEntry(BaseModel):
    """A tracker row as returned to the client.

    Flattened for the tracker table: everything a row renders comes from this
    one object, so the page never fans out to ``/chats`` or ``/analyses`` to
    fill in a column. ``date_added`` is the *chat's* creation time -- the moment
    the user started working on this application -- while ``created_at`` is the
    tracker row's own. They are written together and normally match.
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


class TrackerUpdateRequest(BaseModel):
    """Update the application status of one tracker row.

    Status is the only editable field. ``resume_type`` follows from whether a
    resume was generated, and every other column is copied from the chat.
    """

    status: ApplicationStatus
