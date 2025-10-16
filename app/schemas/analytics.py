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
