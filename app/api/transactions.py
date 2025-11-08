from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
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
from uuid import UUID
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

def _apply_transaction_filters(
    query,
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    transaction_type: Optional[str] = None,
    search: Optional[str] = None
):
    """Apply common transaction filters to a query."""
    if vendor_id:
        try:
            vendor_uuid = UUID(vendor_id)
            query = query.filter(Transaction.vendor_id == vendor_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid vendor_id format")

    if category:
        query = query.filter(Transaction.category == category)

    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)

    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    if transaction_type:
        transaction_type = transaction_type.lower()
        if transaction_type not in {"inflow", "outflow"}:
            raise HTTPException(
                status_code=400,
                detail="transaction_type must be either 'inflow' or 'outflow'"
            )
        if transaction_type == "inflow":
            query = query.filter(Transaction.amount > 0)
        else:
            query = query.filter(Transaction.amount < 0)

    if search:
        like_pattern = f"%{search.strip()}%"
        description_field = func.coalesce(
            Transaction.raw_description,
            Transaction.normalized_description,
            ""
        )
        query = query.filter(description_field.ilike(like_pattern))

    return query


@router.get("/transactions")
def get_transactions(
    limit: int = 100,
    offset: int = 0,
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    transaction_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get transactions with optional filtering."""
    query = db.query(Transaction)
    query = _apply_transaction_filters(
        query=query,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    )

    total_count = query.count()

    transactions = (
        query
        .order_by(Transaction.transaction_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
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
        ).model_dump()
        for tx in transactions
    ]

    return {
        "transactions": items,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }


@router.get("/transactions/summary")
def get_transactions_summary(
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    transaction_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get aggregated metrics for transactions dashboard."""
    base_query = db.query(Transaction)
    filtered_query = _apply_transaction_filters(
        query=base_query,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    )

    total_transactions = filtered_query.count()

    total_inflow = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.amount > 0
    )
    total_outflow = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.amount < 0
    )

    total_inflow = _apply_transaction_filters(
        query=total_inflow,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    ).scalar() or 0

    total_outflow = abs(_apply_transaction_filters(
        query=total_outflow,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    ).scalar() or 0)

    net_cashflow = total_inflow - total_outflow

    avg_amount = filtered_query.with_entities(
        func.coalesce(func.avg(func.abs(Transaction.amount)), 0)
    ).scalar() or 0

    category_breakdown_query = db.query(
        Transaction.category,
        func.count(Transaction.id).label("transaction_count"),
        func.coalesce(func.sum(Transaction.amount), 0).label("total_amount")
    ).filter(Transaction.category.isnot(None))

    category_breakdown_query = _apply_transaction_filters(
        query=category_breakdown_query,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    ).group_by(Transaction.category).order_by(func.sum(func.abs(Transaction.amount)).desc()).limit(6)

    category_breakdown = [
        {
            "category": row.category,
            "transaction_count": row.transaction_count,
            "total_amount": float(row.total_amount),
            "direction": "inflow" if row.total_amount >= 0 else "outflow"
        }
        for row in category_breakdown_query.all()
    ]

    monthly_breakdown_query = db.query(
        func.date_trunc('month', Transaction.transaction_date).label("period"),
        func.coalesce(func.sum(
            case((Transaction.amount > 0, Transaction.amount), else_=0.0)
        ), 0).label("inflow"),
        func.coalesce(func.sum(
            case((Transaction.amount < 0, Transaction.amount), else_=0.0)
        ), 0).label("outflow")
    )

    monthly_breakdown_query = _apply_transaction_filters(
        query=monthly_breakdown_query,
        vendor_id=vendor_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        search=search
    ).group_by(func.date_trunc('month', Transaction.transaction_date)).order_by(func.date_trunc('month', Transaction.transaction_date))

    monthly_breakdown = [
        {
            "period": row.period.strftime("%Y-%m"),
            "inflow": float(row.inflow),
            "outflow": abs(float(row.outflow)),
            "net": float(row.inflow + row.outflow)
        }
        for row in monthly_breakdown_query.all()
    ]

    recent_transactions = [
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
        ).model_dump()
        for tx in filtered_query.order_by(Transaction.transaction_date.desc()).limit(5).all()
    ]

    last_transaction = filtered_query.order_by(Transaction.transaction_date.desc()).first()

    return {
        "metrics": {
            "total_transactions": total_transactions,
            "total_inflow": float(total_inflow),
            "total_outflow": float(total_outflow),
            "net_cashflow": float(net_cashflow),
            "average_transaction": float(avg_amount)
        },
        "category_breakdown": category_breakdown,
        "monthly_breakdown": monthly_breakdown,
        "recent_transactions": recent_transactions,
        "last_activity": {
            "transaction_date": last_transaction.transaction_date.isoformat() if last_transaction else None,
            "source": last_transaction.source if last_transaction else None,
            "source_type": last_transaction.source_type if last_transaction else None
        }
    }
