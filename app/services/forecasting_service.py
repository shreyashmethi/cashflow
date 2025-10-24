import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Literal, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.vendor import Vendor
import statistics
from scipy import stats
import json

class ForecastingService:
    """Service for cash flow forecasting and prediction analysis."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _get_historical_data(self, months_back: int = 12) -> List[Dict[str, Any]]:
        """Get historical cash flow data for the past N months."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=months_back * 30)

        query = text("""
            SELECT
                DATE_TRUNC('month', transaction_date) as period,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
                COUNT(*) as transaction_count
            FROM transactions
            WHERE transaction_date >= :start_date AND transaction_date <= :end_date
            GROUP BY DATE_TRUNC('month', transaction_date)
            ORDER BY period
        """)

        results = self.db.execute(query, {
            "start_date": start_date,
            "end_date": end_date
        }).fetchall()

        return [
            {
                "period": row[0].strftime('%Y-%m'),
                "income": float(row[1]),
                "expenses": float(abs(row[2])),
                "net_cashflow": float(row[1] + row[2]),
                "transaction_count": int(row[3])
            }
            for row in results
        ]

    def _calculate_seasonal_patterns(self, historical_data: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate seasonal adjustment factors based on historical patterns."""
        if len(historical_data) < 3:
            return {"seasonal_factors": [1.0] * 12, "seasonality_strength": 0.0}

        # Group by month to find seasonal patterns
        monthly_data = {}
        for record in historical_data:
            month = datetime.strptime(record["period"], '%Y-%m').month
            if month not in monthly_data:
                monthly_data[month] = []
            monthly_data[month].append(record["net_cashflow"])

        # Calculate average by month
        monthly_averages = {}
        overall_avg = statistics.mean([r["net_cashflow"] for r in historical_data])

        for month in range(1, 13):
            if month in monthly_data:
                monthly_averages[month] = statistics.mean(monthly_data[month])
            else:
                monthly_averages[month] = overall_avg

        # Calculate seasonal factors (ratio to overall average)
        seasonal_factors = []
        for month in range(1, 13):
            factor = monthly_averages[month] / overall_avg if overall_avg != 0 else 1.0
            seasonal_factors.append(factor)

        # Calculate seasonality strength (coefficient of variation)
        if len(monthly_averages) > 1:
            monthly_values = list(monthly_averages.values())
            seasonality_strength = statistics.stdev(monthly_values) / abs(statistics.mean(monthly_values)) if statistics.mean(monthly_values) != 0 else 0
        else:
            seasonality_strength = 0.0

        return {
            "seasonal_factors": seasonal_factors,
            "seasonality_strength": min(seasonality_strength, 1.0)  # Cap at 1.0
        }

    def _calculate_trend(self, historical_data: List[Dict[str, Any]]) -> Tuple[float, float]:
        """Calculate linear trend using least squares regression."""
        if len(historical_data) < 2:
            return 0.0, 0.0

        # Prepare data for regression
        x_values = list(range(len(historical_data)))
        y_values = [record["net_cashflow"] for record in historical_data]

        # Calculate linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)

        return slope, intercept

    def _predict_future_values(self, historical_data: List[Dict[str, Any]],
                              forecast_periods: int, scenario: str,
                              include_seasonality: bool = True) -> List[Dict[str, Any]]:
        """Generate future cash flow predictions using trend analysis and seasonal adjustments."""

        if not historical_data:
            # No historical data, return zero predictions
            return self._generate_empty_forecast(forecast_periods)

        seasonal_info = self._calculate_seasonal_patterns(historical_data)
        trend_slope, trend_intercept = self._calculate_trend(historical_data)

        # Calculate scenario multipliers
        scenario_multipliers = {
            "optimistic": 1.15,
            "realistic": 1.0,
            "conservative": 0.85
        }

        multiplier = scenario_multipliers.get(scenario.lower(), 1.0)

        # Get last known values for starting point
        last_data = historical_data[-1]
        last_net = last_data["net_cashflow"]
        last_income = last_data["income"]
        last_expenses = last_data["expenses"]

        predictions = []
        base_date = datetime.strptime(last_data["period"], '%Y-%m')

        for i in range(forecast_periods):
            # Calculate next period
            next_month = base_date.month + i + 1
            next_year = base_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1

            # Apply trend
            trend_adjustment = trend_slope * (i + 1)

            # Apply seasonal adjustment
            seasonal_factor = 1.0
            if include_seasonality and seasonal_info["seasonal_factors"]:
                seasonal_factor = seasonal_info["seasonal_factors"][next_month - 1]

            # Apply scenario multiplier
            predicted_net = (last_net + trend_adjustment) * seasonal_factor * multiplier

            # Split into income and expenses (maintain similar ratios)
            income_ratio = last_income / (last_income + last_expenses) if (last_income + last_expenses) > 0 else 0.5
            expense_ratio = 1 - income_ratio

            predicted_income = abs(predicted_net) * income_ratio if predicted_net > 0 else 0
            predicted_expenses = abs(predicted_net) * expense_ratio if predicted_net < 0 else 0

            if predicted_net > 0:
                predicted_income = predicted_net
                predicted_expenses = 0
            else:
                predicted_income = 0
                predicted_expenses = abs(predicted_net)

            predictions.append({
                "period": f"{next_year}-{next_month:02d}",
                "income": predicted_income,
                "expenses": predicted_expenses,
                "net_cashflow": predicted_net,
                "confidence_lower": predicted_net * 0.8,
                "confidence_upper": predicted_net * 1.2,
                "is_forecast": True
            })

        return predictions

    def _generate_empty_forecast(self, forecast_periods: int) -> List[Dict[str, Any]]:
        """Generate empty forecast when no historical data is available."""
        predictions = []
        base_date = datetime.utcnow()

        for i in range(forecast_periods):
            next_month = base_date.month + i + 1
            next_year = base_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1

            predictions.append({
                "period": f"{next_year}-{next_month:02d}",
                "income": 0,
                "expenses": 0,
                "net_cashflow": 0,
                "confidence_lower": 0,
                "confidence_upper": 0,
                "is_forecast": True
            })

        return predictions

    def _calculate_kpis(self, historical_data: List[Dict[str, Any]],
                       predictions: List[Dict[str, Any]], confidence_level: float) -> Dict[str, Any]:
        """Calculate key forecasting KPIs."""

        # Projected Cash Flow (sum of predictions)
        projected_cashflow = sum(p["net_cashflow"] for p in predictions)

        # Minimum Cash Balance (lowest point in forecast with confidence)
        if predictions:
            min_net = min(p["net_cashflow"] for p in predictions)
            confidence_multiplier = confidence_level / 100.0
            min_balance = min_net * confidence_multiplier
        else:
            min_balance = 0

        # Forecast Accuracy (simulate based on historical trend consistency)
        if len(historical_data) >= 3:
            # Calculate how consistent historical trends are
            recent_trends = []
            for i in range(1, min(4, len(historical_data))):
                trend = (historical_data[-i]["net_cashflow"] - historical_data[-(i+1)]["net_cashflow"]) / abs(historical_data[-(i+1)]["net_cashflow"]) if historical_data[-(i+1)]["net_cashflow"] != 0 else 0
                recent_trends.append(abs(trend))

            if recent_trends:
                avg_volatility = statistics.mean(recent_trends)
                # Convert volatility to accuracy (lower volatility = higher accuracy)
                accuracy = max(0, 100 - (avg_volatility * 100))
            else:
                accuracy = 75  # Default accuracy
        else:
            accuracy = 50  # Low accuracy with limited data

        return {
            "projected_cashflow": projected_cashflow,
            "projected_cashflow_formatted": f"${projected_cashflow:.0f}",
            "projected_cashflow_change": self._calculate_projected_change(historical_data, projected_cashflow),
            "minimum_cash_balance": min_balance,
            "minimum_cash_balance_formatted": f"${min_balance:.0f}",
            "forecast_accuracy": accuracy,
            "forecast_accuracy_formatted": f"{accuracy:.0f}%",
            "forecast_accuracy_level": "High" if accuracy >= 80 else "Medium" if accuracy >= 60 else "Low"
        }

    def _calculate_projected_change(self, historical_data: List[Dict[str, Any]],
                                   projected_cashflow: float) -> float:
        """Calculate percentage change from historical average."""
        if not historical_data:
            return 0.0

        historical_avg = statistics.mean([h["net_cashflow"] for h in historical_data])
        if historical_avg == 0:
            return 0.0

        return ((projected_cashflow / len(historical_data)) - historical_avg) / historical_avg * 100

    def _generate_scenario_analysis(self, historical_data: List[Dict[str, Any]],
                                   forecast_periods: int, include_seasonality: bool) -> Dict[str, Any]:
        """Generate scenario analysis (optimistic, realistic, conservative)."""

        scenarios = {}

        for scenario in ["optimistic", "realistic", "conservative"]:
            predictions = self._predict_future_values(
                historical_data, forecast_periods, scenario, include_seasonality
            )
            total_projected = sum(p["net_cashflow"] for p in predictions)

            scenarios[scenario] = {
                "total_projected": total_projected,
                "formatted_total": f"${total_projected:.0f}",
                "monthly_average": total_projected / forecast_periods if forecast_periods > 0 else 0,
                "confidence_range": {
                    "lower": total_projected * 0.7,
                    "upper": total_projected * 1.3
                }
            }

        return scenarios

    def _generate_alerts(self, historical_data: List[Dict[str, Any]],
                        predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate upcoming cash flow alerts."""

        alerts = []

        if not predictions:
            return alerts

        # Calculate current cash position
        current_balance = sum(h["net_cashflow"] for h in historical_data[-3:]) / 3 if historical_data else 0

        # Low cash warning
        min_forecast_balance = min(p["net_cashflow"] for p in predictions) if predictions else 0
        if min_forecast_balance + current_balance < 50000:  # $50k threshold
            days_until = (datetime.strptime(predictions[0]["period"], '%Y-%m') - datetime.utcnow()).days
            alerts.append({
                "type": "warning",
                "priority": "high",
                "title": "Low Cash Warning",
                "message": f"Cash balance may drop below $50k on {predictions[0]['period']}",
                "days_until": max(1, days_until),
                "suggested_action": "Consider reducing expenses or securing additional funding"
            })

        # Large payment detection (simulate based on recurring vendors)
        recurring_payments = self._detect_recurring_payments()
        for payment in recurring_payments:
            if payment["avg_amount"] > 25000:  # $25k threshold
                alerts.append({
                    "type": "info",
                    "priority": "medium",
                    "title": "Large Payment Due",
                    "message": f"${payment['avg_amount']:.0f} payment scheduled for {payment['next_date']}",
                    "days_until": payment["days_until"],
                    "suggested_action": "Ensure sufficient liquidity is maintained"
                })

        # Revenue opportunity detection (simulate based on seasonal patterns)
        seasonal_info = self._calculate_seasonal_patterns(historical_data)
        if seasonal_info["seasonality_strength"] > 0.3:  # Strong seasonal pattern
            # Find next high season
            current_month = datetime.utcnow().month
            high_season_months = [i+1 for i, factor in enumerate(seasonal_info["seasonal_factors"]) if factor > 1.1]
            next_high_season = min([m for m in high_season_months if m > current_month] + [high_season_months[0] + 12])

            days_until_high = (next_high_season - current_month) * 30
            alerts.append({
                "type": "opportunity",
                "priority": "low",
                "title": "Revenue Opportunity",
                "message": f"Expected seasonal revenue increase in {days_until_high} days",
                "days_until": days_until_high,
                "suggested_action": "Prepare for increased cash flow and consider investment timing"
            })

        return alerts[:5]  # Limit to top 5 alerts

    def _detect_recurring_payments(self) -> List[Dict[str, Any]]:
        """Detect recurring large payments from vendors."""
        query = text("""
            SELECT v.name, COUNT(*) as frequency, AVG(ABS(t.amount)) as avg_amount
            FROM transactions t
            JOIN vendors v ON t.vendor_id = v.id
            WHERE t.amount < 0 AND t.transaction_date >= :three_months_ago
            GROUP BY v.id, v.name
            HAVING COUNT(*) >= 2 AND AVG(ABS(t.amount)) > 10000
            ORDER BY AVG(ABS(t.amount)) DESC
            LIMIT 5
        """)

        three_months_ago = datetime.utcnow() - timedelta(days=90)
        results = self.db.execute(query, {"three_months_ago": three_months_ago}).fetchall()

        recurring_payments = []
        for row in results:
            # Simulate next payment date (assume monthly)
            next_date = datetime.utcnow() + timedelta(days=30)
            days_until = (next_date - datetime.utcnow()).days

            recurring_payments.append({
                "vendor": row[0],
                "frequency": int(row[1]),
                "avg_amount": float(row[2]),
                "next_date": next_date.strftime("%B %dth"),
                "days_until": days_until
            })

        return recurring_payments

    def generate_forecast(self, forecast_period: str = "30d", scenario_type: str = "realistic",
                         include_seasonality: bool = True, confidence_level: float = 80) -> Dict[str, Any]:
        """Generate comprehensive cash flow forecast."""

        # Convert forecast period to number of periods
        period_mapping = {
            "7d": 1,
            "30d": 1,
            "90d": 3,
            "180d": 6,
            "365d": 12
        }

        forecast_periods = period_mapping.get(forecast_period, 1)

        # Get historical data
        historical_data = self._get_historical_data(12)  # Last 12 months

        # Generate predictions
        predictions = self._predict_future_values(
            historical_data, forecast_periods, scenario_type, include_seasonality
        )

        # Calculate KPIs
        kpis = self._calculate_kpis(historical_data, predictions, confidence_level)

        # Generate scenario analysis
        scenarios = self._generate_scenario_analysis(
            historical_data, forecast_periods, include_seasonality
        )

        # Generate alerts
        alerts = self._generate_alerts(historical_data, predictions)

        # Combine historical and forecast data for chart
        chart_data = historical_data + predictions

        return {
            "forecast_settings": {
                "period": forecast_period,
                "period_months": forecast_periods,
                "scenario_type": scenario_type,
                "include_seasonality": include_seasonality,
                "confidence_level": confidence_level
            },
            "kpis": kpis,
            "chart_data": {
                "data": chart_data,
                "historical_count": len(historical_data),
                "forecast_count": len(predictions)
            },
            "scenario_analysis": scenarios,
            "alerts": {
                "count": len(alerts),
                "items": alerts[:3]  # Show top 3 alerts
            },
            "metadata": {
                "historical_data_points": len(historical_data),
                "forecast_accuracy_model": "linear_trend_seasonal",
                "last_updated": datetime.utcnow().isoformat()
            }
        }

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
