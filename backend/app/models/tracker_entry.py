"""TrackerEntry model: one application-tracker row per job chat."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
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
