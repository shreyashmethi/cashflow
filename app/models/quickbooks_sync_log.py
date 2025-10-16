import uuid
from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

class QuickBooksSyncLog(Base):
    """Tracks QuickBooks sync operations"""
    __tablename__ = "quickbooks_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), nullable=False)  # FK to quickbooks_connections
    
    # Sync details
    sync_type = Column(String, nullable=False)  # full, incremental, manual
    status = Column(String, nullable=False)  # started, completed, failed
    
    # Statistics
    transactions_fetched = Column(Integer, default=0)
    transactions_created = Column(Integer, default=0)
    transactions_updated = Column(Integer, default=0)
    transactions_skipped = Column(Integer, default=0)
    vendors_synced = Column(Integer, default=0)
    
    # Timing
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    
    # Sync metadata
    sync_params = Column(JSONB, nullable=True)  # Filters, date ranges, etc.

