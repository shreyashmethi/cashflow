from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.core.database import SessionLocal, engine, Base, get_db
from app.models import transaction, vendor, statement, anomaly, nlq_query, quickbooks_connection, quickbooks_sync_log  # Import all models
from app.api import transactions as transaction_router
from app.api import analytics as analytics_router
from app.api import quickbooks as quickbooks_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cash Flow Analysis & Visualization Tool",
    description="AI-powered financial data analysis and visualization API",
    version="1.0.0"
)

app.include_router(transaction_router.router, prefix="/api", tags=["transactions"])
app.include_router(analytics_router.router, prefix="/api", tags=["analytics"])
app.include_router(quickbooks_router.router, tags=["quickbooks"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
