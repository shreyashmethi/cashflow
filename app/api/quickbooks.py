"""
QuickBooks API Endpoints

Provides endpoints for:
- OAuth flow (connect/callback)
- Manual sync trigger
- Connection status
- Disconnect
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, field_validator
from uuid import UUID
import uuid

from app.core.database import SessionLocal
from app.models.quickbooks_connection import QuickBooksConnection
from app.models.quickbooks_sync_log import QuickBooksSyncLog
from app.services.quickbooks_oauth_service import QuickBooksOAuthService
from app.services.quickbooks_sync_service import QuickBooksSyncService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quickbooks", tags=["quickbooks"])


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models for request/response
class QuickBooksConnectionResponse(BaseModel):
    id: str
    realm_id: str
    company_name: Optional[str]
    is_active: bool
    last_sync_at: Optional[datetime]
    sync_status: Optional[str]
    sync_error: Optional[str]
    created_at: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class SyncLogResponse(BaseModel):
    id: str
    sync_type: str
    status: str
    transactions_fetched: int
    transactions_created: int
    transactions_updated: int
    transactions_skipped: int
    vendors_synced: int
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    error_message: Optional[str]
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class SyncRequest(BaseModel):
    sync_type: str = "incremental"  # or "full"
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


# Initialize services
oauth_service = QuickBooksOAuthService()
sync_service = QuickBooksSyncService(oauth_service)


@router.get("/connect")
async def connect_quickbooks(state: Optional[str] = Query(None)):
    """
    Initiate QuickBooks OAuth flow
    
    Returns authorization URL for user to visit
    """
    try:
        auth_url = oauth_service.get_authorization_url(state=state)
        return {
            "authorization_url": auth_url,
            "message": "Please visit the authorization URL to connect your QuickBooks account"
        }
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def quickbooks_callback(
    code: str = Query(...),
    realmId: str = Query(...),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle QuickBooks OAuth callback
    
    This endpoint is called by QuickBooks after user authorizes the app
    """
    try:
        # Exchange code for tokens
        connection = oauth_service.exchange_code_for_tokens(code, realmId, db)
        
        return {
            "message": "Successfully connected to QuickBooks",
            "realm_id": connection.realm_id,
            "connection_id": str(connection.id)
        }
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to connect: {str(e)}")


@router.get("/connections", response_model=List[QuickBooksConnectionResponse])
async def list_connections(
    active_only: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    List all QuickBooks connections
    """
    query = db.query(QuickBooksConnection)
    if active_only:
        query = query.filter(QuickBooksConnection.is_active == True)
    
    connections = query.all()
    return connections


@router.get("/connections/{connection_id}", response_model=QuickBooksConnectionResponse)
async def get_connection(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific QuickBooks connection
    """
    try:
        # Convert string to UUID for database query
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection_id format")
    
    connection = db.query(QuickBooksConnection).filter(
        QuickBooksConnection.id == connection_uuid
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    return connection


@router.post("/connections/{connection_id}/sync")
async def trigger_sync(
    connection_id: str,
    sync_request: SyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Manually trigger a sync for a QuickBooks connection
    
    The sync runs in the background
    """
    try:
        # Convert string to UUID for database query
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection_id format")
    
    connection = db.query(QuickBooksConnection).filter(
        QuickBooksConnection.id == connection_uuid
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if not connection.is_active:
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    # Run sync in background
    background_tasks.add_task(
        _run_sync,
        connection_id,  # Keep as string for logging
        sync_request.sync_type,
        sync_request.date_from,
        sync_request.date_to
    )
    
    return {
        "message": f"Sync initiated for connection {connection_id}",
        "sync_type": sync_request.sync_type
    }


@router.delete("/connections/{connection_id}")
async def disconnect_quickbooks(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """
    Disconnect and revoke QuickBooks connection
    """
    try:
        # Convert string to UUID for database query
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection_id format")
    
    connection = db.query(QuickBooksConnection).filter(
        QuickBooksConnection.id == connection_uuid
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        success = oauth_service.revoke_tokens(connection, db)
        if success:
            return {"message": "Successfully disconnected QuickBooks"}
        else:
            return {"message": "Connection deactivated, but token revocation may have failed"}
    except Exception as e:
        logger.error(f"Error disconnecting: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/sync-logs", response_model=List[SyncLogResponse])
async def get_sync_logs(
    connection_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get sync logs for a connection
    """
    try:
        # Convert string to UUID for database query
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection_id format")
    
    logs = db.query(QuickBooksSyncLog).filter(
        QuickBooksSyncLog.connection_id == connection_uuid
    ).order_by(
        QuickBooksSyncLog.started_at.desc()
    ).limit(limit).all()
    
    return logs


@router.get("/sync-logs/{log_id}", response_model=SyncLogResponse)
async def get_sync_log(
    log_id: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific sync log
    """
    try:
        # Convert string to UUID for database query
        log_uuid = uuid.UUID(log_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid log_id format")
    
    log = db.query(QuickBooksSyncLog).filter(
        QuickBooksSyncLog.id == log_uuid
    ).first()
    
    if not log:
        raise HTTPException(status_code=404, detail="Sync log not found")
    
    return log


# Background task helper
def _run_sync(
    connection_id: str,
    sync_type: str,
    date_from: Optional[datetime],
    date_to: Optional[datetime]
):
    """
    Background task to run sync
    """
    db = SessionLocal()
    try:
        # Convert string to UUID for database query
        try:
            connection_uuid = uuid.UUID(connection_id)
        except ValueError:
            logger.error(f"Invalid connection_id format: {connection_id}")
            return
        
        connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.id == connection_uuid
        ).first()
        
        if not connection:
            logger.error(f"Connection {connection_id} not found")
            return
        
        logger.info(f"Starting background sync for connection {connection_id}")
        sync_service.sync_connection(
            connection,
            db,
            sync_type=sync_type,
            date_from=date_from,
            date_to=date_to
        )
        logger.info(f"Background sync completed for connection {connection_id}")
        
    except Exception as e:
        logger.error(f"Background sync failed: {str(e)}")
    finally:
        db.close()


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """
    Test QuickBooks connection by fetching company info
    """
    try:
        # Convert string to UUID for database query
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection_id format")
    
    connection = db.query(QuickBooksConnection).filter(
        QuickBooksConnection.id == connection_uuid
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if not connection.is_active:
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    try:
        company_info = oauth_service.get_company_info(connection, db)
        return {
            "status": "connected",
            "company_info": company_info
        }
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Connection test failed: {str(e)}")

