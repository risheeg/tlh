"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from db.constraints import ensure_db_constraints
from db.session import Base, engine
from routers import accounts, ingest

# Create all tables that don't exist yet (dev convenience; use Alembic in prod)
Base.metadata.create_all(bind=engine)
ensure_db_constraints(engine)

app = FastAPI(
    title="TLH Backend",
    description="Net-worth tracking & tax loss harvesting backend API",
    version="0.1.0",
)

app.include_router(ingest.router)
app.include_router(accounts.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
