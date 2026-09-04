"""Profile model: one row per user, holding the parsed resume and enrichments."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class Profile(Base):
    """A user's career profile: raw resume text plus the structured parse."""

    __tablename__ = "profiles"

    # One profile per user, so the Supabase user id is the primary key. That
    # already gives uniqueness and a backing index -- no extra constraint needed.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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
