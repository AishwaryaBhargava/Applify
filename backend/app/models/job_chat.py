from sqlalchemy import Column, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
import uuid
from app.data.database import Base


class JobChat(Base):
    __tablename__ = "job_chats"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=True)
    jd_text = Column(Text, nullable=False)
    analysis_type = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())