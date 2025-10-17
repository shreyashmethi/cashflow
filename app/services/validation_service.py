from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.core.database import SessionLocal
from app.schemas.transaction import TransactionValidationResult, TransactionCreate

class ValidationService:
    """Service for validating transactions and detecting common issues."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def validate_transaction(self, transaction: TransactionCreate) -> TransactionValidationResult:
        """Validate a single transaction."""
        errors = []
        warnings = []

        # Required field validation
        if not transaction.transaction_date:
            errors.append("Transaction date is required")
        elif transaction.transaction_date > datetime.utcnow():
            warnings.append("Transaction date is in the future")
        elif transaction.transaction_date < datetime(1900, 1, 1):
            errors.append("Transaction date is too old")

        if transaction.amount is None:
            errors.append("Amount is required")
        elif transaction.amount == 0:
            warnings.append("Amount is zero")
        elif abs(transaction.amount) > 1000000:  # $1M threshold
            warnings.append("Amount is unusually large")

        # Vendor validation
        if transaction.vendor:
            if len(transaction.vendor.strip()) < 2:
                warnings.append("Vendor name is too short")
            elif len(transaction.vendor) > 100:
                warnings.append("Vendor name is too long")

        # Category validation
        if transaction.category:
            valid_categories = ['income', 'expense', 'transfer', 'uncategorized']
            if transaction.category.lower() not in valid_categories:
                warnings.append(f"Category '{transaction.category}' is not standard")

        # Amount sign validation based on category
        if transaction.amount and transaction.category:
            if transaction.category.lower() == 'income' and transaction.amount < 0:
                warnings.append("Income transaction has negative amount")
            elif transaction.category.lower() in ['expense', 'transfer'] and transaction.amount > 0:
                warnings.append(f"{transaction.category.title()} transaction has positive amount")

        return TransactionValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_bulk_transactions(self, transactions: List[TransactionCreate]) -> Dict[str, Any]:
        """Validate multiple transactions and return summary."""
        results = []
        error_types = {}
        warning_types = {}

        for i, transaction in enumerate(transactions):
            result = self.validate_transaction(transaction)
            results.append({
                "index": i,
                "transaction": transaction.dict(),
                "is_valid": result.is_valid,
                "errors": result.errors,
                "warnings": result.warnings
            })

            # Collect error statistics
            for error in result.errors:
                error_type = error.split(":")[0] if ":" in error else error
                error_types[error_type] = error_types.get(error_type, 0) + 1

            for warning in result.warnings:
                warning_type = warning.split(":")[0] if ":" in warning else warning
                warning_types[warning_type] = warning_types.get(warning_type, 0) + 1

        valid_count = sum(1 for r in results if r["is_valid"])
        invalid_count = len(results) - valid_count

        # Find most common issues
        common_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        common_warnings = sorted(warning_types.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_transactions": len(transactions),
            "valid_transactions": valid_count,
            "invalid_transactions": invalid_count,
            "results": results,
            "summary": {
                "common_errors": [{"type": err[0], "count": err[1]} for err in common_errors],
                "common_warnings": [{"type": warn[0], "count": warn[1]} for warn in common_warnings],
                "error_rate": invalid_count / len(transactions) if transactions else 0,
                "warning_rate": sum(warning_types.values()) / len(transactions) if transactions else 0
            }
        }

    def validate_existing_transactions(self, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate existing transactions in the database."""
        query = self.db.query(Transaction)

        # Apply filters
        if filters:
            if filters.get('transaction_ids'):
                query = query.filter(Transaction.id.in_(filters['transaction_ids']))
            if filters.get('date_from'):
                query = query.filter(Transaction.transaction_date >= filters['date_from'])
            if filters.get('date_to'):
                query = query.filter(Transaction.transaction_date <= filters['date_to'])
            if filters.get('vendor_ids'):
                query = query.filter(Transaction.vendor_id.in_(filters['vendor_ids']))

        transactions = query.all()
        transaction_data = []

        for tx in transactions:
            # Convert to TransactionCreate for validation
            tx_create = TransactionCreate(
                transaction_date=tx.transaction_date,
                amount=tx.amount,
                vendor=tx.vendor.name if tx.vendor else None,
                category=tx.category,
                description=tx.raw_description or tx.normalized_description,
                source=tx.source
            )
            transaction_data.append(tx_create)

        return self.validate_bulk_transactions(transaction_data)

    def detect_duplicates(self, transactions: List[TransactionCreate], threshold_days: int = 7) -> List[Dict[str, Any]]:
        """Detect potential duplicate transactions."""
        duplicates = []

        # Group transactions by normalized fields for comparison
        transaction_groups = {}
        for tx in transactions:
            # Create a key for grouping similar transactions
            key_parts = [
                tx.vendor or "",
                str(round(tx.amount, 2)) if tx.amount else "",
                tx.transaction_date.strftime('%Y-%m-%d') if tx.transaction_date else ""
            ]
            key = "|".join(key_parts)

            if key not in transaction_groups:
                transaction_groups[key] = []
            transaction_groups[key].append(tx)

        # Find groups with multiple transactions
        for key, group in transaction_groups.items():
            if len(group) > 1:
                # Check if transactions are within threshold days of each other
                if self._are_dates_close([tx.transaction_date for tx in group if tx.transaction_date], threshold_days):
                    duplicates.append({
                        "key": key,
                        "count": len(group),
                        "transactions": [
                            {
                                "vendor": tx.vendor,
                                "amount": tx.amount,
                                "date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                                "description": tx.description
                            }
                            for tx in group
                        ]
                    })

        return duplicates

    def _are_dates_close(self, dates: List[datetime], threshold_days: int) -> bool:
        """Check if dates are within threshold days of each other."""
        if not dates:
            return False

        dates = [d for d in dates if d]  # Filter out None dates
        if len(dates) < 2:
            return False

        min_date = min(dates)
        max_date = max(dates)
        delta = max_date - min_date

        return delta.days <= threshold_days

    def detect_anomalies(self, transactions: List[TransactionCreate]) -> List[Dict[str, Any]]:
        """Detect various types of anomalies in transactions."""
        anomalies = []

        # Group by vendor for amount analysis
        vendor_amounts = {}
        for tx in transactions:
            if tx.vendor and tx.amount:
                if tx.vendor not in vendor_amounts:
                    vendor_amounts[tx.vendor] = []
                vendor_amounts[tx.vendor].append(tx.amount)

        # Detect unusually large amounts per vendor
        for vendor, amounts in vendor_amounts.items():
            if len(amounts) >= 3:  # Need at least 3 transactions for statistical analysis
                mean_amount = sum(amounts) / len(amounts)
                max_amount = max(amounts)

                # Simple anomaly detection: amounts > 3x mean
                if max_amount > mean_amount * 3:
                    anomalies.append({
                        "type": "unusual_amount",
                        "vendor": vendor,
                        "expected_range": f"up to {mean_amount * 2:.2f}",
                        "actual_amount": max_amount,
                        "severity": "medium"
                    })

        # Detect negative amounts for non-refund categories
        for tx in transactions:
            if (tx.amount and tx.amount < 0 and
                tx.category and tx.category.lower() not in ['refund', 'income']):
                anomalies.append({
                    "type": "negative_amount_unexpected",
                    "vendor": tx.vendor,
                    "amount": tx.amount,
                    "category": tx.category,
                    "severity": "low"
                })

        return anomalies

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
