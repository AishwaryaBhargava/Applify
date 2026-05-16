from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import uuid
from app.data.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False)
    fit_score = Column(Integer, nullable=True)
    strengths = Column(JSONB, nullable=True)
    gaps = Column(JSONB, nullable=True)
    verdict = Column(Text, nullable=True)
    full_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())