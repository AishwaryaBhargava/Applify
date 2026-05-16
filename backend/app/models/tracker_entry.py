from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
import uuid
from app.data.database import Base


class TrackerEntry(Base):
    __tablename__ = "tracker_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    status = Column(String, default="Not Applied")
    resume_type = Column(String, default="Unaltered")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())