from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Literal
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, desc
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.models.anomaly import Anomaly

class DashboardService:
    """Service for generating comprehensive dashboard data."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _get_date_range(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, datetime]:
        """Get the actual date range for the dashboard period."""
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

    def _calculate_kpi_with_change(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """Calculate KPIs with percentage changes from previous period."""
        # Current period
        current_period_days = (date_to - date_from).days

        # Previous period (same duration before current period)
        prev_date_to = date_from
        prev_date_from = date_from - timedelta(days=current_period_days)

        # Current period calculations
        current_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        current_expenses = abs(self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount < 0)
        ).scalar() or 0)

        # Previous period calculations
        prev_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= prev_date_from,
                 Transaction.transaction_date <= prev_date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        prev_expenses = abs(self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= prev_date_from,
                 Transaction.transaction_date <= prev_date_to,
                 Transaction.amount < 0)
        ).scalar() or 0)

        # Calculate percentage changes
        def calculate_change(current: float, previous: float) -> tuple:
            if previous == 0:
                return 0, "stable" if current == 0 else "up"
            change = ((current - previous) / previous) * 100
            return change, "up" if change > 0 else "down" if change < 0 else "stable"

        income_change, income_direction = calculate_change(current_income, prev_income)
        expense_change, expense_direction = calculate_change(current_expenses, prev_expenses)

        # Calculate derived metrics
        net_cashflow = current_income - current_expenses
        prev_net = prev_income - prev_expenses
        net_change, net_direction = calculate_change(net_cashflow, prev_net)

        def format_currency(amount: float) -> str:
            return f"${amount:,.0f}"

        return [
            {
                "title": "Cash Balance",
                "value": current_income - current_expenses,
                "formatted_value": format_currency(current_income - current_expenses),
                "change_percent": round(net_change, 1),
                "change_direction": net_direction,
                "icon": "dollar-sign"
            },
            {
                "title": "Monthly Inflow",
                "value": current_income,
                "formatted_value": format_currency(current_income),
                "change_percent": round(income_change, 1),
                "change_direction": income_direction,
                "icon": "trending-up"
            },
            {
                "title": "Monthly Outflow",
                "value": current_expenses,
                "formatted_value": format_currency(current_expenses),
                "change_percent": round(expense_change, 1),
                "change_direction": expense_direction,
                "icon": "trending-down"
            },
            {
                "title": "Net Cash Flow",
                "value": net_cashflow,
                "formatted_value": format_currency(net_cashflow),
                "change_percent": round(net_change, 1),
                "change_direction": net_direction,
                "icon": "activity"
            }
        ]

    def _calculate_cash_health(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Calculate cash health metrics."""
        # Get current cash position
        total_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        total_expenses = abs(self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount < 0)
        ).scalar() or 0)

        net_cashflow = total_income - total_expenses

        # Calculate average monthly expenses (last 3 months)
        three_months_ago = date_to - timedelta(days=90)
        avg_monthly_expenses = abs(self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= three_months_ago,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount < 0)
        ).scalar() or 0) / 3

        # Calculate cash runway (months of expenses we can cover)
        cash_runway_months = int(net_cashflow / avg_monthly_expenses) if avg_monthly_expenses > 0 else 0

        # Calculate liquidity ratio (current assets / current liabilities approximation)
        # For simplicity, using income vs expenses ratio
        liquidity_ratio = (total_income / total_expenses * 100) if total_expenses > 0 else 100

        # Determine assessments
        if liquidity_ratio >= 150:
            liquidity_assessment = "Excellent"
            score_contribution = 40
        elif liquidity_ratio >= 120:
            liquidity_assessment = "Good"
            score_contribution = 30
        elif liquidity_ratio >= 100:
            liquidity_assessment = "Fair"
            score_contribution = 20
        else:
            liquidity_assessment = "Poor"
            score_contribution = 10

        if cash_runway_months >= 12:
            runway_assessment = f"{cash_runway_months} months"
            runway_score = 30
        elif cash_runway_months >= 6:
            runway_assessment = f"{cash_runway_months} months"
            runway_score = 20
        elif cash_runway_months >= 3:
            runway_assessment = f"{cash_runway_months} months"
            runway_score = 10
        else:
            runway_assessment = "Critical"
            runway_score = 0

        # Burn rate assessment
        burn_rate = abs(total_expenses - total_income)
        if burn_rate < avg_monthly_expenses * 0.1:
            burn_assessment = "Excellent"
            burn_score = 30
        elif burn_rate < avg_monthly_expenses * 0.3:
            burn_assessment = "Moderate"
            burn_score = 20
        else:
            burn_assessment = "High"
            burn_score = 5

        overall_score = min(100, score_contribution + runway_score + burn_score)

        return {
            "liquidity_ratio": liquidity_assessment,
            "cash_runway_months": cash_runway_months,
            "burn_rate": burn_assessment,
            "overall_score": overall_score
        }

    def _generate_ai_insights(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """Generate AI-powered insights."""
        insights = []

        # Get current period data
        current_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        current_expenses = abs(self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= date_from,
                 Transaction.transaction_date <= date_to,
                 Transaction.amount < 0)
        ).scalar() or 0)

        # Previous period comparison
        prev_date_to = date_from
        prev_date_from = date_from - timedelta(days=(date_to - date_from).days)
        prev_income = self.db.query(func.sum(Transaction.amount)).filter(
            and_(Transaction.transaction_date >= prev_date_from,
                 Transaction.transaction_date <= prev_date_to,
                 Transaction.amount > 0)
        ).scalar() or 0

        # Expense growth insight
        if current_expenses > prev_income * 1.15:  # 15% increase in expenses
            insights.append({
                "category": "Cash Flow Optimization",
                "title": "Operating Expenses Increased",
                "message": f"Your operating expenses increased by {((current_expenses/prev_income) - 1) * 100:.1f}% this month. Consider reviewing subscription services and vendor contracts.",
                "priority": "high",
                "actionable": True
            })

        # Revenue growth insight
        if current_income > prev_income * 1.03:  # 3% growth
            days_diff = (date_to - date_from).days
            avg_daily = current_income / days_diff
            insights.append({
                "category": "Revenue Growth",
                "title": "Revenue Growth Detected",
                "message": f"Customer payments are arriving {avg_daily:.0f} days faster on average. Your collection strategy is working well.",
                "priority": "medium",
                "actionable": False
            })

        # Upcoming obligations (simulate based on recurring transactions)
        # Look for recurring vendors in the last 3 months
        recurring_vendors = self.db.execute(
            text("""
                SELECT v.name, COUNT(*) as frequency, AVG(ABS(t.amount)) as avg_amount
                FROM transactions t
                JOIN vendors v ON t.vendor_id = v.id
                WHERE t.amount < 0 AND t.transaction_date >= :three_months_ago
                GROUP BY v.id, v.name
                HAVING COUNT(*) >= 3
                ORDER BY AVG(ABS(t.amount)) DESC
                LIMIT 3
            """),
            {"three_months_ago": date_to - timedelta(days=90)}
        ).fetchall()

        if recurring_vendors:
            largest_recurring = recurring_vendors[0]
            insights.append({
                "category": "Upcoming Obligations",
                "title": "Large Payment Due Soon",
                "message": f"Large payment of ${largest_recurring[2]:.0f} due to {largest_recurring[0]} in 12 days. Ensure sufficient liquidity is maintained.",
                "priority": "high",
                "actionable": True
            })

        # Default insights if no specific patterns detected
        if not insights:
            insights.append({
                "category": "General",
                "title": "Cash Flow Stable",
                "message": "Your cash flow appears stable for this period. Continue monitoring key metrics.",
                "priority": "low",
                "actionable": False
            })

        return insights

    def _get_recent_transactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transactions formatted for dashboard."""
        transactions = self.db.query(Transaction).order_by(
            desc(Transaction.transaction_date)
        ).limit(limit).all()

        return [
            {
                "id": str(tx.id),
                "date": tx.transaction_date.strftime("%b %d, %Y"),
                "description": tx.raw_description or tx.normalized_description or "Transaction",
                "category": tx.category or "Uncategorized",
                "amount": float(tx.amount),
                "status": "Completed",
                "vendor": tx.vendor.name if tx.vendor else None
            }
            for tx in transactions
        ]

    def _get_cash_flow_trend(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Get cash flow trend data for visualization."""
        # Use the existing visualization service logic
        results = self.db.execute(
            text("""
                SELECT
                    DATE_TRUNC('month', transaction_date) as period,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses
                FROM transactions
                WHERE transaction_date >= :date_from AND transaction_date <= :date_to
                GROUP BY DATE_TRUNC('month', transaction_date)
                ORDER BY period
            """),
            {"date_from": date_from, "date_to": date_to}
        ).fetchall()

        data = []
        for row in results:
            data.append({
                "period": row[0].strftime('%Y-%m'),
                "inflow": float(row[1]),
                "outflow": float(abs(row[2])),
                "net": float(row[1] + row[2])
            })

        return {
            "chart_type": "line",
            "title": "Cash Flow Trend",
            "data": data,
            "labels": ["period", "inflow", "outflow", "net"]
        }

    def _get_spending_by_category(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Get spending by category data."""
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

        return {
            "chart_type": "pie",
            "title": "Spending by Category",
            "data": data,
            "labels": [item["category"] for item in data]
        }

    def get_dashboard_data(self, date_from: Optional[datetime] = None,
                          date_to: Optional[datetime] = None,
                          include_insights: bool = True,
                          include_transactions: bool = True) -> Dict[str, Any]:
        """Generate comprehensive dashboard data."""
        date_range = self._get_date_range(date_from, date_to)

        # Calculate KPI cards with changes
        kpi_cards = self._calculate_kpi_with_change(date_range["from"], date_range["to"])

        # Calculate cash health metrics
        cash_health = self._calculate_cash_health(date_range["from"], date_range["to"])

        # Get chart data
        cash_flow_trend = self._get_cash_flow_trend(date_range["from"], date_range["to"])
        spending_by_category = self._get_spending_by_category(date_range["from"], date_range["to"])

        # Generate AI insights
        ai_insights = []
        if include_insights:
            ai_insights = self._generate_ai_insights(date_range["from"], date_range["to"])

        # Get recent transactions
        recent_transactions = []
        if include_transactions:
            recent_transactions = self._get_recent_transactions()

        return {
            "period": {
                "from": date_range["from"].isoformat(),
                "to": date_range["to"].isoformat(),
                "days": (date_range["to"] - date_range["from"]).days
            },
            "kpi_cards": kpi_cards,
            "cash_flow_trend": cash_flow_trend,
            "cash_health": cash_health,
            "spending_by_category": spending_by_category,
            "ai_insights": ai_insights,
            "recent_transactions": recent_transactions,
            "last_updated": datetime.utcnow()
        }

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
