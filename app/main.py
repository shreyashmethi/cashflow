from fastapi import FastAPI
from app.core.database import SessionLocal, engine, Base
from aop.api import transactions as transaction_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cash Flow Analysis & Visualization Tool")

app.include_router(transaction_router.router, prefix="/api", tags=["transactions"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}