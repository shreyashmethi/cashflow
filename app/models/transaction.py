import uuid
from sqlalchemy import Column, DateTime, Float, String, Text, func, Index, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_date = Column(DateTime, nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True)  # FK to vendors
    amount = Column(Float, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)  # expense, income, transfer, etc.
    normalized_description = Column(String, nullable=True, index=True)
    raw_description = Column(Text, nullable=True)  # Original description from source
    source = Column(String, nullable=True)  # File name or source identifier
    source_type = Column(String, nullable=True, index=True)  # 'upload', 'quickbooks', 'manual'
    statement_id = Column(UUID(as_uuid=True), nullable=True)  # FK to statements
    
    # QuickBooks specific fields
    quickbooks_id = Column(String, nullable=True, index=True)  # QuickBooks transaction ID
    quickbooks_connection_id = Column(UUID(as_uuid=True), nullable=True)  # FK to quickbooks_connections
    quickbooks_sync_version = Column(String, nullable=True)  # For detecting updates
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", back_populates="transactions")

    # Indexes for performance
    __table_args__ = (
        Index('idx_transaction_date_amount', 'transaction_date', 'amount'),
        Index('idx_vendor_category', 'vendor_id', 'category'),
        Index('idx_quickbooks_id', 'quickbooks_id', unique=False),
        Index('idx_source_type', 'source_type'),
        # Note: For PostgreSQL trigram matching on normalized_description, would need pg_trgm extension
    )
