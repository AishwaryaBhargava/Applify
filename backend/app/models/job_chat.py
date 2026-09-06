"""JobChat model: one row per job opening the user is working on."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class JobChat(Base):
    """A single job chat: the JD, its metadata, and the analysis type chosen."""

    __tablename__ = "job_chats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "quick" or "detailed"; null until the user picks one.
    analysis_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Soft delete: DELETE /chats/{id} stamps this instead of removing the row.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The last ATS keyword match run for this chat: the extracted JD keywords
    # and how the user's profile scored against them. Null until
    # ``POST /chats/{id}/keywords`` has been run once.
    #
    # Stored on the chat rather than in its own table because there is exactly
    # one live result per chat -- a re-run replaces it, and nobody queries a
    # keyword across chats.
    keyword_match: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
