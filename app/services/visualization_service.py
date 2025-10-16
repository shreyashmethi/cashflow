from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Literal
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.vendor import Vendor

class VisualizationService:
    """Service for generating visualization data from financial transactions."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _get_date_range(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, datetime]:
        """Get the actual date range for the query."""
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

    def _get_time_series_data(self, chart_type: str, group_by: str, date_from: datetime, date_to: datetime,
                             vendor_id: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get time series data for line/area charts."""
        # Build the date truncation function
        if group_by == "day":
            date_func = "DATE_TRUNC('day', transaction_date)"
            format_str = "%Y-%m-%d"
        elif group_by == "week":
            date_func = "DATE_TRUNC('week', transaction_date)"
            format_str = "%Y-%m-%d"
        elif group_by == "month":
            date_func = "DATE_TRUNC('month', transaction_date)"
            format_str = "%Y-%m"
        elif group_by == "quarter":
            date_func = "DATE_TRUNC('quarter', transaction_date)"
            format_str = "%Y-%m"
        elif group_by == "year":
            date_func = "DATE_TRUNC('year', transaction_date)"
            format_str = "%Y"
        else:
            date_func = "DATE_TRUNC('month', transaction_date)"
            format_str = "%Y-%m"

        # Build filters
        filters = ["transaction_date >= :date_from", "transaction_date <= :date_to"]
        params = {"date_from": date_from, "date_to": date_to}

        if vendor_id:
            filters.append("vendor_id = :vendor_id")
            params["vendor_id"] = vendor_id

        if category:
            filters.append("category = :category")
            params["category"] = category

        where_clause = " AND ".join(filters)

        # Build query based on chart type
        if chart_type in ["line", "area"]:
            # Income vs Expenses over time
            query = text(f"""
                SELECT
                    {date_func} as period,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses
                FROM transactions
                WHERE {where_clause}
                GROUP BY {date_func}
                ORDER BY period
            """)
        else:
            # Net cashflow over time
            query = text(f"""
                SELECT
                    {date_func} as period,
                    SUM(amount) as net_cashflow
                FROM transactions
                WHERE {where_clause}
                GROUP BY {date_func}
                ORDER BY period
            """)

        results = self.db.execute(query, params).fetchall()

        data = []
        for row in results:
            period_str = row[0].strftime(format_str)
            if chart_type in ["line", "area"]:
                data.append({
                    "period": period_str,
                    "income": float(row[1]),
                    "expenses": float(abs(row[2]))
                })
            else:
                data.append({
                    "period": period_str,
                    "net_cashflow": float(row[1])
                })

        return data

    def _get_category_pie_data(self, date_from: datetime, date_to: datetime,
                              vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get category breakdown for pie charts."""
        filters = ["transaction_date >= :date_from", "transaction_date <= :date_to", "amount < 0", "category IS NOT NULL"]
        params = {"date_from": date_from, "date_to": date_to}

        if vendor_id:
            filters.append("vendor_id = :vendor_id")
            params["vendor_id"] = vendor_id

        where_clause = " AND ".join(filters)

        query = text(f"""
            SELECT category, SUM(amount) as total_spent, COUNT(*) as transaction_count
            FROM transactions
            WHERE {where_clause}
            GROUP BY category
            ORDER BY total_spent ASC
        """)

        results = self.db.execute(query, params).fetchall()

        # Calculate total for percentages
        total_amount = sum(abs(row[1]) for row in results)

        data = []
        for row in results:
            percentage = (abs(row[1]) / total_amount * 100) if total_amount > 0 else 0
            data.append({
                "category": row[0],
                "amount": float(abs(row[1])),
                "count": int(row[2]),
                "percentage": round(percentage, 1)
            })

        return data

    def _get_vendor_bar_data(self, date_from: datetime, date_to: datetime,
                            category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top vendors for bar charts."""
        filters = ["transaction_date >= :date_from", "transaction_date <= :date_to", "amount < 0"]
        params = {"date_from": date_from, "date_to": date_to, "limit": limit}

        if category:
            filters.append("category = :category")
            params["category"] = category

        where_clause = " AND ".join(filters)

        query = text(f"""
            SELECT v.name, SUM(t.amount) as total_spent, COUNT(t.id) as transaction_count
            FROM transactions t
            JOIN vendors v ON t.vendor_id = v.id
            WHERE {where_clause}
            GROUP BY v.id, v.name
            ORDER BY total_spent ASC
            LIMIT :limit
        """)

        results = self.db.execute(query, params).fetchall()

        data = []
        for row in results:
            data.append({
                "vendor": row[0],
                "amount": float(abs(row[1])),
                "count": int(row[2])
            })

        return data

    def _get_monthly_comparison_data(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """Get monthly comparison data for multi-series charts."""
        query = text("""
            SELECT
                DATE_TRUNC('month', transaction_date) as month,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
                COUNT(*) as transaction_count
            FROM transactions
            WHERE transaction_date >= :date_from AND transaction_date <= :date_to
            GROUP BY DATE_TRUNC('month', transaction_date)
            ORDER BY month
        """)

        results = self.db.execute(query, {"date_from": date_from, "date_to": date_to}).fetchall()

        data = []
        for row in results:
            data.append({
                "month": row[0].strftime('%Y-%m'),
                "income": float(row[1]),
                "expenses": float(abs(row[2])),
                "transactions": int(row[3])
            })

        return data

    def get_visualization_data(self, chart_type: str, date_from: Optional[datetime] = None,
                              date_to: Optional[datetime] = None, group_by: str = "month",
                              vendor_id: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Generate visualization data based on chart type and filters."""
        date_range = self._get_date_range(date_from, date_to)

        # Generate title based on parameters
        title = self._generate_chart_title(chart_type, date_range, vendor_id, category)

        # Generate data based on chart type
        if chart_type == "pie":
            data = self._get_category_pie_data(date_range["from"], date_range["to"], vendor_id)
            labels = [item["category"] for item in data]
        elif chart_type == "bar":
            data = self._get_vendor_bar_data(date_range["from"], date_range["to"], category)
            labels = [item["vendor"] for item in data]
        elif chart_type in ["line", "area"]:
            data = self._get_time_series_data(chart_type, group_by, date_range["from"], date_range["to"], vendor_id, category)
            labels = list(data[0].keys()) if data else []
        else:
            # Default to monthly comparison
            data = self._get_monthly_comparison_data(date_range["from"], date_range["to"])
            labels = list(data[0].keys()) if data else []

        return {
            "chart_type": chart_type,
            "title": title,
            "data": data,
            "labels": labels,
            "metadata": {
                "date_range": {
                    "from": date_range["from"].isoformat(),
                    "to": date_range["to"].isoformat()
                },
                "filters": {
                    "vendor_id": vendor_id,
                    "category": category,
                    "group_by": group_by
                }
            }
        }

    def _generate_chart_title(self, chart_type: str, date_range: Dict[str, datetime],
                             vendor_id: Optional[str] = None, category: Optional[str] = None) -> str:
        """Generate appropriate chart title based on parameters."""
        start_date = date_range["from"].strftime("%b %Y")
        end_date = date_range["to"].strftime("%b %Y")

        if chart_type == "pie":
            title = "Spending by Category"
            if vendor_id:
                vendor = self.db.query(Vendor).filter(Vendor.id == vendor_id).first()
                title = f"Spending by Category - {vendor.name if vendor else 'Unknown Vendor'}"
        elif chart_type == "bar":
            title = "Top Spending Vendors"
            if category:
                title = f"Top Vendors - {category.title()} Category"
        elif chart_type == "line":
            title = "Income vs Expenses Over Time"
        elif chart_type == "area":
            title = "Cash Flow Trends"
        else:
            title = "Financial Overview"

        title += f" ({start_date} - {end_date})"
        return title

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
