import uuid
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, func
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class NLQQuery(Base):
    __tablename__ = "nlq_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_query = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=False)
    parameters = Column(Text, nullable=True)  # JSON string of parameters used
    execution_time_ms = Column(Float, nullable=True)
    result_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    executed_successfully = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
