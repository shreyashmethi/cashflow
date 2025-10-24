from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.nlq_service import NLQService
from app.services.summarize_service import SummarizeService
from app.services.visualization_service import VisualizationService
from app.services.anomaly_service import AnomalyService
from app.services.dashboard_service import DashboardService
from app.schemas.analytics import (
    QueryRequest, QueryResponse,
    SummarizeRequest, SummarizeResponse,
    VisualizationRequest, VisualizationResponse,
    AnomalyScanRequest, AnomalyScanResponse,
    QueryHistoryResponse,
    DashboardRequest, DashboardResponse
)
from datetime import datetime
from typing import Optional

router = APIRouter()

@router.post("/query", response_model=QueryResponse)
async def query_data(
    request: QueryRequest,
    db: Session = Depends(get_db)
):
    """Execute a natural language query against the database."""
    nlq_service = NLQService(db)

    try:
        result = nlq_service.execute_query(
            query=request.query,
            parameters={
                "date_from": request.date_from,
                "date_to": request.date_to,
                "limit": request.limit or 100
            }
        )

        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )

        return QueryResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/query-history", response_model=QueryHistoryResponse)
async def get_query_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get recent query history."""
    nlq_service = NLQService(db)

    try:
        history = nlq_service.get_query_history(limit)
        return QueryHistoryResponse(queries=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_data(
    request: SummarizeRequest,
    db: Session = Depends(get_db)
):
    """Generate a summary of financial data for a given period."""
    summarize_service = SummarizeService(db)

    try:
        summary = summarize_service.generate_summary(
            date_from=request.date_from,
            date_to=request.date_to,
            include_anomalies=request.include_anomalies or False
        )

        return SummarizeResponse(**summary)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/visualize-data", response_model=VisualizationResponse)
async def get_visualization_data(
    request: VisualizationRequest,
    db: Session = Depends(get_db)
):
    """Get data series for visualization charts."""
    viz_service = VisualizationService(db)

    try:
        data = viz_service.get_visualization_data(
            chart_type=request.chart_type,
            date_from=request.date_from,
            date_to=request.date_to,
            group_by=request.group_by,
            vendor_id=request.vendor_id,
            category=request.category
        )

        return VisualizationResponse(**data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run-anomaly-scan", response_model=AnomalyScanResponse)
async def run_anomaly_scan(
    request: AnomalyScanRequest,
    db: Session = Depends(get_db)
):
    """Run anomaly detection scan on transactions."""
    anomaly_service = AnomalyService(db)

    try:
        result = anomaly_service.scan_for_anomalies(
            date_from=request.date_from,
            date_to=request.date_to,
            vendor_ids=request.vendor_ids,
            persist_results=request.persist_results or False
        )

        return AnomalyScanResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/anomalies")
async def get_anomalies(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """Get recent anomalies."""
    anomaly_service = AnomalyService(db)

    try:
        anomalies = anomaly_service.get_anomalies(
            limit=limit,
            offset=offset,
            severity=severity,
            resolved=resolved
        )

        return {
            "anomalies": anomalies,
            "total": len(anomalies),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dashboard", response_model=DashboardResponse)
async def get_dashboard_data(
    request: DashboardRequest,
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard data for frontend."""
    dashboard_service = DashboardService(db)

    try:
        data = dashboard_service.get_dashboard_data(
            date_from=request.date_from,
            date_to=request.date_to,
            include_insights=request.include_insights,
            include_transactions=request.include_transactions
        )

        return DashboardResponse(**data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
