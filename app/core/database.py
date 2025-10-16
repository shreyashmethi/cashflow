import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/cashflow")

engine = create_engine(DATABASE_URL)

# Enable pgvector extension
with engine.connect() as conn:
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    except Exception:
        # Extension might not be available or already exists
        pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Import all models to register them with Base
def register_models():
    from app.models import Transaction, Vendor, Statement, Anomaly, NLQQuery
    return True

# Register models on import
register_models()
