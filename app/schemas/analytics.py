from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class QueryRequest(BaseModel):
    """Request schema for natural language queries."""
    query: str = Field(..., description="Natural language query")
    date_from: Optional[datetime] = Field(None, description="Start date for query filter")
    date_to: Optional[datetime] = Field(None, description="End date for query filter")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="Maximum number of results")

class QueryResponse(BaseModel):
    """Response schema for query results."""
    success: bool = Field(..., description="Whether query executed successfully")
    sql: str = Field(..., description="Generated SQL query")
    intent: str = Field(..., description="Detected query intent")
    results: List[Dict[str, Any]] = Field(..., description="Query results")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")
    result_count: int = Field(..., description="Number of results returned")
    error: Optional[str] = Field(None, description="Error message if query failed")

class SummarizeRequest(BaseModel):
    """Request schema for data summarization."""
    date_from: Optional[datetime] = Field(None, description="Start date for summary period")
    date_to: Optional[datetime] = Field(None, description="End date for summary period")
    include_anomalies: Optional[bool] = Field(False, description="Include anomaly information in summary")

class SummarizeResponse(BaseModel):
    """Response schema for summary data."""
    period: Dict[str, str] = Field(..., description="Summary period information")
    kpis: Dict[str, float] = Field(..., description="Key performance indicators")
    trends: Dict[str, Any] = Field(..., description="Trend analysis")
    top_vendors: List[Dict[str, Any]] = Field(..., description="Top spending vendors")
    categories: List[Dict[str, Any]] = Field(..., description="Spending by category")
    anomalies: Optional[List[Dict[str, Any]]] = Field(None, description="Detected anomalies")
    summary_text: str = Field(..., description="Human-readable summary")

class VisualizationRequest(BaseModel):
    """Request schema for visualization data."""
    chart_type: Literal["line", "bar", "pie", "area"] = Field(..., description="Type of chart")
    date_from: Optional[datetime] = Field(None, description="Start date for data range")
    date_to: Optional[datetime] = Field(None, description="End date for data range")
    group_by: Optional[Literal["day", "week", "month", "quarter", "year"]] = Field("month", description="Time grouping for data")
    vendor_id: Optional[str] = Field(None, description="Filter by specific vendor")
    category: Optional[str] = Field(None, description="Filter by transaction category")

class VisualizationResponse(BaseModel):
    """Response schema for visualization data."""
    chart_type: str = Field(..., description="Type of chart")
    title: str = Field(..., description="Chart title")
    data: List[Dict[str, Any]] = Field(..., description="Chart data points")
    labels: List[str] = Field(..., description="Data labels")
    metadata: Dict[str, Any] = Field(..., description="Additional chart metadata")

class AnomalyScanRequest(BaseModel):
    """Request schema for anomaly scanning."""
    date_from: Optional[datetime] = Field(None, description="Start date for scan period")
    date_to: Optional[datetime] = Field(None, description="End date for scan period")
    vendor_ids: Optional[List[str]] = Field(None, description="Specific vendors to scan")
    persist_results: Optional[bool] = Field(False, description="Save anomalies to database")

class AnomalyScanResponse(BaseModel):
    """Response schema for anomaly scan results."""
    total_scanned: int = Field(..., description="Total transactions scanned")
    anomalies_found: int = Field(..., description="Number of anomalies detected")
    anomalies: List[Dict[str, Any]] = Field(..., description="Detected anomalies")
    scan_time_ms: float = Field(..., description="Scan execution time")

class QueryHistoryResponse(BaseModel):
    """Response schema for query history."""
    queries: List[Dict[str, Any]] = Field(..., description="Recent queries")

class KPICard(BaseModel):
    """Schema for KPI card data."""
    value: float = Field(..., description="KPI value")
    change_percent: float = Field(..., description="Percentage change from previous period")
    change_direction: Literal["up", "down", "stable"] = Field(..., description="Direction of change")
    formatted_value: str = Field(..., description="Formatted value string")
    title: str = Field(..., description="KPI title")
    icon: str = Field(..., description="Icon identifier")

class CashHealthMetric(BaseModel):
    """Schema for cash health metrics."""
    liquidity_ratio: str = Field(..., description="Liquidity ratio assessment")
    cash_runway_months: int = Field(..., description="Cash runway in months")
    burn_rate: str = Field(..., description="Burn rate assessment")
    overall_score: int = Field(..., description="Overall cash health score (0-100)")

class AIInsight(BaseModel):
    """Schema for AI-generated insights."""
    category: str = Field(..., description="Insight category")
    title: str = Field(..., description="Insight title")
    message: str = Field(..., description="Insight message")
    priority: Literal["high", "medium", "low"] = Field(..., description="Priority level")
    actionable: bool = Field(..., description="Whether insight is actionable")

class RecentTransaction(BaseModel):
    """Schema for recent transaction data."""
    id: str = Field(..., description="Transaction ID")
    date: str = Field(..., description="Formatted date")
    description: str = Field(..., description="Transaction description")
    category: Optional[str] = Field(None, description="Transaction category")
    amount: float = Field(..., description="Transaction amount")
    status: str = Field(..., description="Transaction status")
    vendor: Optional[str] = Field(None, description="Vendor name")

class DashboardRequest(BaseModel):
    """Request schema for dashboard data."""
    date_from: Optional[datetime] = Field(None, description="Start date for dashboard period")
    date_to: Optional[datetime] = Field(None, description="End date for dashboard period")
    include_insights: Optional[bool] = Field(True, description="Include AI insights")
    include_transactions: Optional[bool] = Field(True, description="Include recent transactions")

class DashboardPeriod(BaseModel):
    """Schema describing the dashboard period metadata."""
    model_config = ConfigDict(populate_by_name=True)

    start: str = Field(..., alias="from", description="Period start in ISO format")
    end: str = Field(..., alias="to", description="Period end in ISO format")
    days: int = Field(..., description="Number of days within the period")

class DashboardResponse(BaseModel):
    """Response schema for dashboard data."""
    period: DashboardPeriod = Field(..., description="Dashboard period information")
    kpi_cards: List[KPICard] = Field(..., description="Key performance indicator cards")
    cash_flow_trend: Dict[str, Any] = Field(..., description="Cash flow trend chart data")
    cash_health: CashHealthMetric = Field(..., description="Cash health metrics")
    spending_by_category: Dict[str, Any] = Field(..., description="Spending by category chart data")
    ai_insights: List[AIInsight] = Field(..., description="AI-generated insights")
    recent_transactions: List[RecentTransaction] = Field(..., description="Recent transactions")
    last_updated: datetime = Field(..., description="Last data update timestamp")

# Forecasting schemas
class ForecastRequest(BaseModel):
    """Request schema for cash flow forecasting."""
    forecast_period: Literal["7d", "30d", "90d", "180d", "365d"] = Field("30d", description="Forecast period")
    scenario_type: Literal["optimistic", "realistic", "conservative"] = Field("realistic", description="Forecast scenario type")
    include_seasonality: bool = Field(True, description="Include seasonal adjustments")
    confidence_level: float = Field(80, ge=50, le=95, description="Confidence level percentage")

class ForecastKPIs(BaseModel):
    """Schema for forecasting KPIs."""
    projected_cashflow: float = Field(..., description="Total projected cash flow")
    projected_cashflow_formatted: str = Field(..., description="Formatted projected cash flow")
    projected_cashflow_change: float = Field(..., description="Percentage change from historical")
    minimum_cash_balance: float = Field(..., description="Minimum forecasted cash balance")
    minimum_cash_balance_formatted: str = Field(..., description="Formatted minimum cash balance")
    forecast_accuracy: float = Field(..., description="Forecast accuracy percentage")
    forecast_accuracy_formatted: str = Field(..., description="Formatted forecast accuracy")
    forecast_accuracy_level: Literal["High", "Medium", "Low"] = Field(..., description="Accuracy level")

class ForecastAlert(BaseModel):
    """Schema for forecast alerts."""
    type: Literal["warning", "info", "opportunity"] = Field(..., description="Alert type")
    priority: Literal["high", "medium", "low"] = Field(..., description="Alert priority")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    days_until: int = Field(..., description="Days until the event")
    suggested_action: str = Field(..., description="Suggested action")

class ScenarioAnalysis(BaseModel):
    """Schema for scenario analysis results."""
    total_projected: float = Field(..., description="Total projected amount")
    formatted_total: str = Field(..., description="Formatted total")
    monthly_average: float = Field(..., description="Monthly average")
    confidence_range: Dict[str, float] = Field(..., description="Confidence range (lower/upper)")

class ChartDataPoint(BaseModel):
    """Schema for chart data points."""
    period: str = Field(..., description="Time period")
    income: float = Field(..., description="Income amount")
    expenses: float = Field(..., description="Expenses amount")
    net_cashflow: float = Field(..., description="Net cash flow")
    confidence_lower: Optional[float] = Field(None, description="Lower confidence bound")
    confidence_upper: Optional[float] = Field(None, description="Upper confidence bound")
    is_forecast: Optional[bool] = Field(False, description="Whether this is forecast data")

class ForecastResponse(BaseModel):
    """Response schema for forecasting data."""
    forecast_settings: Dict[str, Any] = Field(..., description="Forecast configuration settings")
    kpis: ForecastKPIs = Field(..., description="Key performance indicators")
    chart_data: Dict[str, Any] = Field(..., description="Chart data with historical and forecast points")
    scenario_analysis: Dict[str, ScenarioAnalysis] = Field(..., description="Scenario analysis results")
    alerts: Dict[str, Any] = Field(..., description="Forecast alerts")
    metadata: Dict[str, Any] = Field(..., description="Additional metadata")

class ForecastSettings(BaseModel):
    """Schema for forecast settings."""
    available_periods: List[str] = Field(..., description="Available forecast periods")
    available_scenarios: List[str] = Field(..., description="Available scenario types")
    default_confidence: float = Field(..., description="Default confidence level")
    max_historical_months: int = Field(..., description="Maximum historical data months")

class AlertsResponse(BaseModel):
    """Response schema for alerts data."""
    alerts: List[ForecastAlert] = Field(..., description="List of alerts")
    total_count: int = Field(..., description="Total number of alerts")
    unread_count: int = Field(..., description="Number of unread alerts")
