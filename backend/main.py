"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from db.session import Base, engine
from routers import ingest

# Create all tables that don't exist yet (dev convenience; use Alembic in prod)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TLH Backend",
    description="Net-worth tracking & tax loss harvesting backend API",
    version="0.1.0",
)

app.include_router(ingest.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
