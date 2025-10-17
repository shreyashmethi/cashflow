import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class QuickBooksConnection(Base):
    """Stores QuickBooks OAuth connection info per user/company"""
    __tablename__ = "quickbooks_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    realm_id = Column(String, nullable=False, unique=True)  # QuickBooks company ID
    company_name = Column(String, nullable=True)
    
    # OAuth tokens (should be encrypted in production)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime, nullable=False)
    
    # Connection metadata
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime, nullable=True)
    sync_status = Column(String, nullable=True)  # success, failed, in_progress
    sync_error = Column(Text, nullable=True)
    
    # Sync configuration
    auto_sync_enabled = Column(Boolean, default=True)
    sync_frequency_hours = Column(Integer, default=24)  # How often to sync
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

