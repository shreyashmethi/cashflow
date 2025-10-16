from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from decimal import Decimal

class TransactionBase(BaseModel):
    """Base transaction schema."""
    transaction_date: datetime = Field(..., description="Transaction date")
    amount: float = Field(..., description="Transaction amount")
    vendor: Optional[str] = Field(None, description="Vendor name")
    category: Optional[str] = Field(None, description="Transaction category")
    description: Optional[str] = Field(None, description="Transaction description")

class TransactionCreate(TransactionBase):
    """Schema for creating transactions."""
    source: Optional[str] = Field(None, description="Source file identifier")
    statement_id: Optional[str] = Field(None, description="Statement ID")

class TransactionResponse(TransactionBase):
    """Schema for transaction responses."""
    id: str = Field(..., description="Transaction ID")
    vendor_id: Optional[str] = Field(None, description="Vendor ID")
    normalized_description: Optional[str] = Field(None, description="Normalized description")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

class TransactionValidationResult(BaseModel):
    """Validation result for a single transaction."""
    is_valid: bool = Field(..., description="Whether transaction is valid")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    warnings: List[str] = Field(default_factory=list, description="List of validation warnings")

class ValidationRequest(BaseModel):
    """Request schema for transaction validation."""
    transactions: List[TransactionCreate] = Field(..., description="Transactions to validate")

class ValidationResponse(BaseModel):
    """Response schema for transaction validation."""
    total_transactions: int = Field(..., description="Total number of transactions processed")
    valid_transactions: int = Field(..., description="Number of valid transactions")
    invalid_transactions: int = Field(..., description="Number of invalid transactions")
    results: List[Dict[str, Any]] = Field(..., description="Detailed validation results")
    summary: Dict[str, Any] = Field(..., description="Validation summary")

class BulkValidationRequest(BaseModel):
    """Request for bulk validation of existing transactions."""
    transaction_ids: Optional[List[str]] = Field(None, description="Specific transaction IDs to validate")
    date_from: Optional[datetime] = Field(None, description="Start date for validation range")
    date_to: Optional[datetime] = Field(None, description="End date for validation range")
    vendor_ids: Optional[List[str]] = Field(None, description="Specific vendor IDs to validate")

class BulkValidationResponse(BaseModel):
    """Response for bulk validation."""
    total_validated: int = Field(..., description="Total transactions validated")
    valid_count: int = Field(..., description="Number of valid transactions")
    invalid_count: int = Field(..., description="Number of invalid transactions")
    errors_by_type: Dict[str, int] = Field(..., description="Count of errors by type")
    common_issues: List[Dict[str, Any]] = Field(..., description="Most common validation issues")
