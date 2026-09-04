"""Analysis model: the fit analysis produced for a job chat."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class Analysis(Base):
    """A quick snapshot or detailed breakdown of profile-to-JD fit."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "quick" or "detailed"
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strengths: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    gaps: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The complete model response, kept so richer detail can be surfaced later.
    full_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
