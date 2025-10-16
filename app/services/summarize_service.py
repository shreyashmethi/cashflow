import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, desc
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.anomaly import Anomaly

class SummarizeService:
    """Service for generating financial summaries and KPIs."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _get_date_range(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, datetime]:
        """Get the actual date range for the summary period."""
        now = datetime.utcnow()

        if not date_from and not date_to:
            # Default to last 30 days
            date_to = now
            date_from = now - timedelta(days=30)
        elif not date_from:
            # If only end date provided, go back 30 days
            date_from = date_to - timedelta(days=30)
        elif not date_to:
            # If only start date provided, go forward 30 days or use now
            date_to = min(date_from + timedelta(days=30), now)

        return {"from": date_from, "to": date_to}

    def _calculate_kpis(self, date_from: datetime, date_to: datetime) -> Dict[str, float]:
        """Calculate key performance indicators."""
        # Total income (positive amounts)
        total_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        # Total expenses (negative amounts)
        total_expenses = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount < 0)
        ).scalar() or 0

        # Net cash flow
        net_cashflow = total_income + total_expenses

        # Transaction count
        total_transactions = self.db.query(func.count(Transaction.id)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to)
        ).scalar() or 0

        # Average transaction amount
        avg_transaction = (total_income + abs(total_expenses)) / total_transactions if total_transactions > 0 else 0

        # Unique vendors
        unique_vendors = self.db.query(func.count(func.distinct(Transaction.vendor_id))).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.vendor_id.isnot(None))
        ).scalar() or 0

        return {
            "total_income": float(total_income),
            "total_expenses": float(abs(total_expenses)),
            "net_cashflow": float(net_cashflow),
            "total_transactions": int(total_transactions),
            "average_transaction": float(avg_transaction),
            "unique_vendors": int(unique_vendors)
        }

    def _get_top_vendors(self, date_from: datetime, date_to: datetime, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top spending vendors."""
        results = self.db.execute(
            text("""
                SELECT v.name, SUM(t.amount) as total_spent, COUNT(t.id) as transaction_count
                FROM transactions t
                JOIN vendors v ON t.vendor_id = v.id
                WHERE t.amount < 0 AND t.transaction_date >= :date_from AND t.transaction_date <= :date_to
                GROUP BY v.id, v.name
                ORDER BY total_spent ASC
                LIMIT :limit
            """),
            {"date_from": date_from, "date_to": date_to, "limit": limit}
        ).fetchall()

        return [
            {
                "vendor": row[0],
                "total_spent": float(row[1]),
                "transaction_count": int(row[2])
            }
            for row in results
        ]

    def _get_category_breakdown(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """Get spending breakdown by category."""
        results = self.db.execute(
            text("""
                SELECT category, SUM(amount) as total_spent, COUNT(*) as transaction_count
                FROM transactions
                WHERE amount < 0 AND category IS NOT NULL
                AND transaction_date >= :date_from AND transaction_date <= :date_to
                GROUP BY category
                ORDER BY total_spent ASC
            """),
            {"date_from": date_from, "date_to": date_to}
        ).fetchall()

        return [
            {
                "category": row[0],
                "total_spent": float(row[1]),
                "transaction_count": int(row[2]),
                "percentage": 0  # Will calculate below
            }
            for row in results
        ]

    def _get_trends(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Calculate trend analysis."""
        # Get monthly breakdown for the period
        results = self.db.execute(
            text("""
                SELECT
                    DATE_TRUNC('month', transaction_date) as month,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses
                FROM transactions
                WHERE transaction_date >= :date_from AND transaction_date <= :date_to
                GROUP BY DATE_TRUNC('month', transaction_date)
                ORDER BY month
            """),
            {"date_from": date_from, "date_to": date_to}
        ).fetchall()

        monthly_data = [
            {
                "month": row[0].strftime('%Y-%m'),
                "income": float(row[1]),
                "expenses": float(abs(row[2])),
                "net": float(row[1] + row[2])
            }
            for row in results
        ]

        # Calculate trends
        if len(monthly_data) >= 2:
            recent = monthly_data[-1]
            previous = monthly_data[-2]

            income_change = ((recent["income"] - previous["income"]) / previous["income"] * 100) if previous["income"] > 0 else 0
            expense_change = ((recent["expenses"] - previous["expenses"]) / previous["expenses"] * 100) if previous["expenses"] > 0 else 0

            trends = {
                "income_trend": "increasing" if income_change > 5 else "decreasing" if income_change < -5 else "stable",
                "expense_trend": "increasing" if expense_change > 5 else "decreasing" if expense_change < -5 else "stable",
                "income_change_percent": round(income_change, 1),
                "expense_change_percent": round(expense_change, 1)
            }
        else:
            trends = {
                "income_trend": "insufficient_data",
                "expense_trend": "insufficient_data",
                "income_change_percent": 0,
                "expense_change_percent": 0
            }

        return {
            "monthly_breakdown": monthly_data,
            "trends": trends
        }

    def _get_anomalies_summary(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """Get summary of anomalies in the period."""
        anomalies = self.db.query(Anomaly).filter(
            and_(Anomaly.detected_at >= date_from,
                 Anomaly.detected_at <= date_to)
        ).all()

        return [
            {
                "id": str(anomaly.id),
                "type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "description": anomaly.description,
                "vendor": anomaly.transaction.vendor.name if anomaly.transaction and anomaly.transaction.vendor else None,
                "amount": float(anomaly.actual_value) if anomaly.actual_value else None,
                "detected_at": anomaly.detected_at.isoformat()
            }
            for anomaly in anomalies
        ]

    def _generate_summary_text(self, kpis: Dict[str, float], trends: Dict[str, Any],
                              top_vendors: List[Dict[str, Any]], categories: List[Dict[str, Any]],
                              anomalies: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary text."""
        lines = []

        # Period overview
        lines.append("## Financial Summary")
        lines.append(f"**Total Income:** ${kpis['total_income']:,.2f}")
        lines.append(f"**Total Expenses:** ${kpis['total_expenses']:,.2f}")
        lines.append(f"**Net Cash Flow:** ${kpis['net_cashflow']:,.2f}")
        lines.append(f"**Transactions:** {kpis['total_transactions']:,}")
        lines.append(f"**Average Transaction:** ${kpis['average_transaction']:.2f}")

        # Trends
        if trends['trends']['income_trend'] != 'insufficient_data':
            lines.append("
## Trends")
            lines.append(f"Income trend: **{trends['trends']['income_trend']}** ({trends['trends']['income_change_percent']:+.1f}%)")
            lines.append(f"Expense trend: **{trends['trends']['expense_trend']}** ({trends['trends']['expense_change_percent']:+.1f}%)")

        # Top vendors
        if top_vendors:
            lines.append("
## Top Spending Vendors")
            for vendor in top_vendors[:5]:
                lines.append(f"- **{vendor['vendor']}**: ${vendor['total_spent']:,.2f} ({vendor['transaction_count']} transactions)")

        # Categories
        if categories:
            total_expenses = sum(cat['total_spent'] for cat in categories)
            lines.append("
## Spending by Category")
            for category in categories:
                percentage = (category['total_spent'] / total_expenses * 100) if total_expenses > 0 else 0
                lines.append(f"- **{category['category']}**: ${category['total_spent']:,.2f} ({percentage:.1f}%)")

        # Anomalies
        if anomalies:
            lines.append(f"\n## Anomalies Detected ({len(anomalies)})")
            for anomaly in anomalies[:3]:  # Show top 3
                lines.append(f"- **{anomaly['severity'].upper()}**: {anomaly['description']}")

        return "\n".join(lines)

    def generate_summary(self, date_from: Optional[datetime] = None,
                        date_to: Optional[datetime] = None,
                        include_anomalies: bool = False) -> Dict[str, Any]:
        """Generate comprehensive financial summary."""
        date_range = self._get_date_range(date_from, date_to)

        # Calculate KPIs
        kpis = self._calculate_kpis(date_range["from"], date_range["to"])

        # Get trends
        trends = self._get_trends(date_range["from"], date_range["to"])

        # Get top vendors
        top_vendors = self._get_top_vendors(date_range["from"], date_range["to"])

        # Get category breakdown
        categories = self._get_category_breakdown(date_range["from"], date_range["to"])

        # Calculate category percentages
        total_expenses = sum(cat['total_spent'] for cat in categories)
        for category in categories:
            category['percentage'] = (category['total_spent'] / total_expenses * 100) if total_expenses > 0 else 0

        # Get anomalies if requested
        anomalies = []
        if include_anomalies:
            anomalies = self._get_anomalies_summary(date_range["from"], date_range["to"])

        # Generate summary text
        summary_text = self._generate_summary_text(kpis, trends, top_vendors, categories, anomalies)

        return {
            "period": {
                "from": date_range["from"].isoformat(),
                "to": date_range["to"].isoformat(),
                "days": (date_range["to"] - date_range["from"]).days
            },
            "kpis": kpis,
            "trends": trends,
            "top_vendors": top_vendors,
            "categories": categories,
            "anomalies": anomalies if include_anomalies else None,
            "summary_text": summary_text
        }

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
