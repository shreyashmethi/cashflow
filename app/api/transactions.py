from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.parser import FileParser
from app.services.vendor_service import VendorService
from app.services.validation_service import ValidationService
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.schemas.transaction import (
    ValidationRequest, ValidationResponse,
    BulkValidationRequest, BulkValidationResponse,
    TransactionCreate, TransactionResponse
)
from datetime import datetime
from typing import List, Optional
import uuid

router = APIRouter()

@router.post("/parse-transactions")
async def parse_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Parse transactions from uploaded file and save to database."""
    parser = FileParser(file)
    parsed_result = await parser.parse()

    if not parsed_result.get("success", False):
        raise HTTPException(status_code=400, detail=parsed_result.get("error", "Parsing failed"))

    records = parsed_result.get("records", [])
    if not records:
        raise HTTPException(status_code=400, detail="No valid transactions found in file")

    # Resolve vendors
    vendor_service = VendorService(db)
    vendor_names = [record.get("vendor") for record in records if record.get("vendor")]
    vendor_resolutions = vendor_service.bulk_resolve_vendors(vendor_names)

    # Create transactions
    transactions_to_create = []
    for record in records:
        try:
            # Get vendor ID if vendor exists
            vendor_name = record.get("vendor")
            vendor_id = None
            if vendor_name and vendor_name in vendor_resolutions:
                vendor_id = vendor_resolutions[vendor_name].id

            new_transaction = Transaction(
                transaction_date=record.get("date"),
                amount=record.get("amount"),
                vendor_id=vendor_id,
                category=record.get("category"),
                normalized_description=record.get("description"),
                raw_description=record.get("description"),
                source=file.filename
            )
            transactions_to_create.append(new_transaction)

        except Exception as e:
            print(f"Skipping record due to error: {record} - Error: {e}")
            continue

    if not transactions_to_create:
        raise HTTPException(status_code=400, detail="No valid transactions could be created from parsed data")

    try:
        db.add_all(transactions_to_create)
        db.commit()

        # Return success with statistics
        return {
            "filename": file.filename,
            "transactions_saved": len(transactions_to_create),
            "vendors_resolved": len(vendor_resolutions),
            "duplicates_found": len(parsed_result.get("duplicates", [])),
            "metadata": parsed_result.get("metadata", {})
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save transactions to database: {e}")

@router.post("/validate-transactions", response_model=ValidationResponse)
async def validate_transactions(request: ValidationRequest, db: Session = Depends(get_db)):
    """Validate a list of transactions before saving."""
    validation_service = ValidationService(db)

    # Run validation
    result = validation_service.validate_bulk_transactions(request.transactions)

    # Also check for duplicates and anomalies
    duplicates = validation_service.detect_duplicates(request.transactions)
    anomalies = validation_service.detect_anomalies(request.transactions)

    # Enhance result with additional checks
    result["duplicates"] = duplicates
    result["anomalies"] = anomalies

    return ValidationResponse(**result)

@router.post("/validate-bulk", response_model=BulkValidationResponse)
async def validate_bulk_transactions(request: BulkValidationRequest, db: Session = Depends(get_db)):
    """Validate existing transactions in the database."""
    validation_service = ValidationService(db)

    # Run validation on existing transactions
    result = validation_service.validate_existing_transactions({
        "transaction_ids": request.transaction_ids,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "vendor_ids": request.vendor_ids
    })

    # Convert to response format
    return BulkValidationResponse(
        total_validated=result["total_transactions"],
        valid_count=result["valid_transactions"],
        invalid_count=result["invalid_transactions"],
        errors_by_type={err["type"]: err["count"] for err in result["summary"]["common_errors"]},
        common_issues=result["summary"]["common_errors"]
    )

@router.get("/transactions")
def get_transactions(
    limit: int = 100,
    offset: int = 0,
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Get transactions with optional filtering."""
    query = db.query(Transaction)

    if vendor_id:
        query = query.filter(Transaction.vendor_id == vendor_id)
    if category:
        query = query.filter(Transaction.category == category)
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    transactions = query.offset(offset).limit(limit).all()

    # Convert to response format
    return [
        TransactionResponse(
            id=str(tx.id),
            transaction_date=tx.transaction_date,
            amount=tx.amount,
            vendor=tx.vendor.name if tx.vendor else None,
            vendor_id=str(tx.vendor_id) if tx.vendor_id else None,
            category=tx.category,
            description=tx.raw_description or tx.normalized_description,
            created_at=tx.created_at,
            updated_at=tx.updated_at
        )
        for tx in transactions
    ]
