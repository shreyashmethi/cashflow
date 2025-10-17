import uuid
from sqlalchemy import Column, String, DateTime, Float, Text, func
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), nullable=False)  # FK to transactions
    anomaly_type = Column(String, nullable=False)  # z_score, negative_amount, spike, duplicate, etc.
    severity = Column(String, nullable=False)  # low, medium, high, critical
    description = Column(Text, nullable=False)
    expected_value = Column(Float, nullable=True)
    actual_value = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)  # 0-1 score
    detected_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
