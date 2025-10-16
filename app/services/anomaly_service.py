import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, desc
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.anomaly import Anomaly

class AnomalyService:
    """Service for detecting anomalies in financial transactions."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _get_vendor_amounts(self, date_from: datetime, date_to: datetime, vendor_ids: Optional[List[str]] = None) -> Dict[str, List[float]]:
        """Get amounts grouped by vendor for statistical analysis."""
        query = self.db.query(Transaction.vendor_id, Transaction.amount).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.vendor_id.isnot(None))
        )

        if vendor_ids:
            query = query.filter(Transaction.vendor_id.in_(vendor_ids))

        results = query.all()

        vendor_amounts = {}
        for vendor_id, amount in results:
            if vendor_id not in vendor_amounts:
                vendor_amounts[vendor_id] = []
            vendor_amounts[vendor_id].append(amount)

        return vendor_amounts

    def _detect_z_score_anomalies(self, vendor_amounts: Dict[str, List[float]]) -> List[Dict[str, Any]]:
        """Detect anomalies using z-score method."""
        anomalies = []

        for vendor_id, amounts in vendor_amounts.items():
            if len(amounts) < 5:  # Need at least 5 transactions for statistical analysis
                continue

            # Filter to expenses only for anomaly detection
            expenses = [abs(amount) for amount in amounts if amount < 0]
            if len(expenses) < 3:
                continue

            expenses_array = np.array(expenses)
            mean_amount = np.mean(expenses_array)
            std_amount = np.std(expenses_array)

            if std_amount == 0:  # All amounts are the same
                continue

            # Find transactions that are outliers (z-score > 2.5)
            for i, amount in enumerate(amounts):
                if amount >= 0:  # Skip income transactions
                    continue

                abs_amount = abs(amount)
                z_score = abs(abs_amount - mean_amount) / std_amount

                if z_score > 2.5:  # Threshold for anomaly
                    severity = "high" if z_score > 3.5 else "medium"

                    anomalies.append({
                        "vendor_id": vendor_id,
                        "anomaly_type": "z_score_outlier",
                        "severity": severity,
                        "description": f"Unusual expense amount (${abs_amount:.2f}) for vendor - {z_score:.2f} standard deviations from mean",
                        "expected_value": float(mean_amount),
                        "actual_value": float(abs_amount),
                        "confidence": min(z_score / 4.0, 1.0),  # Normalize confidence
                        "transaction_index": i
                    })

        return anomalies

    def _detect_iqr_anomalies(self, vendor_amounts: Dict[str, List[float]]) -> List[Dict[str, Any]]:
        """Detect anomalies using IQR method."""
        anomalies = []

        for vendor_id, amounts in vendor_amounts.items():
            if len(amounts) < 5:
                continue

            # Filter to expenses only
            expenses = [abs(amount) for amount in amounts if amount < 0]
            if len(expenses) < 3:
                continue

            expenses_array = np.array(expenses)
            q1 = np.percentile(expenses_array, 25)
            q3 = np.percentile(expenses_array, 75)
            iqr = q3 - q1

            if iqr == 0:  # All amounts are the same
                continue

            # Define bounds
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            # Find outliers
            for i, amount in enumerate(amounts):
                if amount >= 0:  # Skip income transactions
                    continue

                abs_amount = abs(amount)
                if abs_amount < lower_bound or abs_amount > upper_bound:
                    severity = "high" if abs_amount > upper_bound * 1.5 else "medium"

                    anomalies.append({
                        "vendor_id": vendor_id,
                        "anomaly_type": "iqr_outlier",
                        "severity": severity,
                        "description": f"Expense amount (${abs_amount:.2f}) outside normal range [${lower_bound:.2f}, ${upper_bound:.2f}]",
                        "expected_value": float((q1 + q3) / 2),  # Median
                        "actual_value": float(abs_amount),
                        "confidence": 0.8,  # IQR is generally reliable
                        "transaction_index": i
                    })

        return anomalies

    def _detect_negative_income_anomalies(self, transactions: List[Transaction]) -> List[Dict[str, Any]]:
        """Detect negative amounts in income categories."""
        anomalies = []

        for tx in transactions:
            if (tx.amount and tx.amount < 0 and
                tx.category and tx.category.lower() in ['income', 'revenue', 'salary']):
                anomalies.append({
                    "transaction_id": str(tx.id),
                    "anomaly_type": "negative_income",
                    "severity": "medium",
                    "description": f"Negative amount (${tx.amount:.2f}) in income category '{tx.category}'",
                    "expected_value": None,
                    "actual_value": float(tx.amount),
                    "confidence": 0.9
                })

        return anomalies

    def _detect_duplicate_transactions(self, transactions: List[Transaction]) -> List[Dict[str, Any]]:
        """Detect potential duplicate transactions."""
        anomalies = []

        # Group by vendor and amount for duplicate detection
        transaction_groups = {}
        for tx in transactions:
            if not tx.vendor_id or not tx.amount:
                continue

            key = f"{tx.vendor_id}_{abs(tx.amount):.2f}_{tx.transaction_date.strftime('%Y%m%d')}"
            if key not in transaction_groups:
                transaction_groups[key] = []
            transaction_groups[key].append(tx)

        # Find groups with multiple transactions on the same day
        for key, group in transaction_groups.items():
            if len(group) > 1:
                for tx in group:
                    anomalies.append({
                        "transaction_id": str(tx.id),
                        "anomaly_type": "potential_duplicate",
                        "severity": "low",
                        "description": f"Multiple transactions with same vendor and amount on same day ({len(group)} found)",
                        "expected_value": None,
                        "actual_value": float(tx.amount),
                        "confidence": 0.7
                    })

        return anomalies

    def _detect_unusual_frequency(self, vendor_amounts: Dict[str, List[float]]) -> List[Dict[str, Any]]:
        """Detect unusual transaction frequency for vendors."""
        anomalies = []

        for vendor_id, amounts in vendor_amounts.items():
            if len(amounts) < 10:  # Need sufficient data for frequency analysis
                continue

            # Calculate daily frequency (transactions per day)
            # This is a simplified approach - in practice you'd want to group by date
            daily_frequency = len(amounts) / 30  # Assume 30-day period

            if daily_frequency > 5:  # More than 5 transactions per day is unusual
                anomalies.append({
                    "vendor_id": vendor_id,
                    "anomaly_type": "high_frequency",
                    "severity": "low",
                    "description": f"High transaction frequency: {daily_frequency:.1f} transactions per day",
                    "expected_value": 2.0,  # Expected daily frequency
                    "actual_value": float(daily_frequency),
                    "confidence": 0.6
                })

        return anomalies

    def scan_for_anomalies(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                          vendor_ids: Optional[List[str]] = None, persist_results: bool = False) -> Dict[str, Any]:
        """Run comprehensive anomaly detection scan."""
        # Set default date range if not provided
        if not date_from and not date_to:
            date_to = datetime.utcnow()
            date_from = date_to - timedelta(days=30)
        elif not date_from:
            date_from = date_to - timedelta(days=30)
        elif not date_to:
            date_to = min(date_from + timedelta(days=30), datetime.utcnow())

        # Get transactions for analysis
        query = self.db.query(Transaction).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to)
        )

        if vendor_ids:
            query = query.filter(Transaction.vendor_id.in_(vendor_ids))

        transactions = query.all()

        if not transactions:
            return {
                "total_scanned": 0,
                "anomalies_found": 0,
                "anomalies": [],
                "scan_time_ms": 0
            }

        start_time = datetime.utcnow()

        # Get vendor amounts for statistical analysis
        vendor_amounts = self._get_vendor_amounts(date_from, date_to, vendor_ids)

        # Run different anomaly detection algorithms
        anomalies = []

        # Z-score anomalies
        z_score_anomalies = self._detect_z_score_anomalies(vendor_amounts)
        anomalies.extend(z_score_anomalies)

        # IQR anomalies
        iqr_anomalies = self._detect_iqr_anomalies(vendor_amounts)
        anomalies.extend(iqr_anomalies)

        # Negative income anomalies
        negative_income_anomalies = self._detect_negative_income_anomalies(transactions)
        anomalies.extend(negative_income_anomalies)

        # Duplicate detection
        duplicate_anomalies = self._detect_duplicate_transactions(transactions)
        anomalies.extend(duplicate_anomalies)

        # Frequency anomalies
        frequency_anomalies = self._detect_unusual_frequency(vendor_amounts)
        anomalies.extend(frequency_anomalies)

        # Remove duplicate anomalies (same transaction, same type)
        seen_anomalies = set()
        unique_anomalies = []

        for anomaly in anomalies:
            anomaly_key = f"{anomaly.get('transaction_id', anomaly.get('vendor_id', ''))}_{anomaly['anomaly_type']}"
            if anomaly_key not in seen_anomalies:
                seen_anomalies.add(anomaly_key)
                unique_anomalies.append(anomaly)

        # Persist anomalies if requested
        if persist_results:
            for anomaly_data in unique_anomalies:
                anomaly = Anomaly(
                    transaction_id=anomaly_data.get('transaction_id'),
                    anomaly_type=anomaly_data['anomaly_type'],
                    severity=anomaly_data['severity'],
                    description=anomaly_data['description'],
                    expected_value=anomaly_data.get('expected_value'),
                    actual_value=anomaly_data.get('actual_value'),
                    confidence=anomaly_data.get('confidence', 0.5)
                )
                self.db.add(anomaly)

            self.db.commit()

        scan_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "total_scanned": len(transactions),
            "anomalies_found": len(unique_anomalies),
            "anomalies": unique_anomalies,
            "scan_time_ms": scan_time
        }

    def get_anomalies(self, limit: int = 50, offset: int = 0, severity: Optional[str] = None,
                     resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get anomalies with optional filtering."""
        query = self.db.query(Anomaly)

        if severity:
            query = query.filter(Anomaly.severity == severity)

        if resolved is not None:
            if resolved:
                query = query.filter(Anomaly.resolved_at.isnot(None))
            else:
                query = query.filter(Anomaly.resolved_at.is_(None))

        anomalies = query.order_by(desc(Anomaly.detected_at)).offset(offset).limit(limit).all()

        return [
            {
                "id": str(anomaly.id),
                "transaction_id": str(anomaly.transaction_id),
                "anomaly_type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "description": anomaly.description,
                "expected_value": float(anomaly.expected_value) if anomaly.expected_value else None,
                "actual_value": float(anomaly.actual_value) if anomaly.actual_value else None,
                "confidence": float(anomaly.confidence) if anomaly.confidence else None,
                "detected_at": anomaly.detected_at.isoformat(),
                "resolved_at": anomaly.resolved_at.isoformat() if anomaly.resolved_at else None,
                "notes": anomaly.notes,
                "vendor_name": anomaly.transaction.vendor.name if anomaly.transaction and anomaly.transaction.vendor else None,
                "transaction_amount": float(anomaly.transaction.amount) if anomaly.transaction else None,
                "transaction_date": anomaly.transaction.transaction_date.isoformat() if anomaly.transaction else None
            }
            for anomaly in anomalies
        ]

    def resolve_anomaly(self, anomaly_id: str, notes: Optional[str] = None) -> bool:
        """Mark an anomaly as resolved."""
        try:
            anomaly = self.db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if anomaly:
                anomaly.resolved_at = datetime.utcnow()
                if notes:
                    anomaly.notes = notes
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
