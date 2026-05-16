from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.data.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    user_id = Column(String, primary_key=True, index=True)
    raw_text = Column(Text, nullable=True)
    parsed_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())