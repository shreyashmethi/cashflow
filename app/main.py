from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from typing import List
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
logger.info("Environment variables loaded")

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

# Configure CORS
import os

def _build_allowed_origins() -> List[str]:
    """
    Build the list of allowed origins for CORS.
    Ensures localhost/127.0.0.1 variants are always present in development.
    """
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8080,http://localhost:3000,http://127.0.0.1:3000",
    )
    configured = {origin.strip() for origin in raw.split(",") if origin.strip()}

    if os.getenv("ENVIRONMENT", "development") == "development":
        configured.update(
            {
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:8080",
                "http://127.0.0.1:8080",
            }
        )

    return sorted(configured)


allowed_origins = _build_allowed_origins()
allowed_origin_regex = os.getenv(
    "ALLOWED_ORIGIN_REGEX", r"http://(?:127\.0\.0\.1|localhost):\d+$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(transaction_router.router, prefix="/api", tags=["transactions"])
app.include_router(analytics_router.router, prefix="/api", tags=["analytics"])
app.include_router(quickbooks_router.router, tags=["quickbooks"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
