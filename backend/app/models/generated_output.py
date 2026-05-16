from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
import uuid
from app.data.database import Base


class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, index=True, nullable=False)
    output_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())