from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

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

class DashboardResponse(BaseModel):
    """Response schema for dashboard data."""
    period: Dict[str, str] = Field(..., description="Dashboard period information")
    kpi_cards: List[KPICard] = Field(..., description="Key performance indicator cards")
    cash_flow_trend: Dict[str, Any] = Field(..., description="Cash flow trend chart data")
    cash_health: CashHealthMetric = Field(..., description="Cash health metrics")
    spending_by_category: Dict[str, Any] = Field(..., description="Spending by category chart data")
    ai_insights: List[AIInsight] = Field(..., description="AI-generated insights")
    recent_transactions: List[RecentTransaction] = Field(..., description="Recent transactions")
    last_updated: datetime = Field(..., description="Last data update timestamp")
