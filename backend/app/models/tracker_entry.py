"""TrackerEntry model: one application-tracker row per job chat."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class TrackerEntry(Base):
    """Application status for a job chat, shown in the tracker table."""

    __tablename__ = "tracker_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Exactly one tracker entry per chat.
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_chats.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # not_applied | applied | interviewing | offer | rejected
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'not_applied'"), default="not_applied"
    )
    # unaltered | tailored
    resume_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'unaltered'"), default="unaltered"
    )
    # ------------------------------------------------------------------
    # The application's own facts, all optional and all user-editable.
    #
    # They live on the tracker row rather than on the chat because they
    # describe the *application*, not the conversation: where it was found,
    # what it pays, when it was sent, and what the user has to do next.
    # ------------------------------------------------------------------

    # The posting itself. Validated as http(s) before it is written.
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text on purpose: "$180-210k", "GBP 75,000", "competitive".
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Where the opening came from: LinkedIn, referral, careers page.
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stamped automatically the first time status becomes "applied", and never
    # cleared afterwards -- moving back to not_applied is a correction to the
    # status, not a claim that the application was never sent.
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # low | medium | high
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=text("now()"),
        onupdate=func.now(),
        nullable=False,
    )
