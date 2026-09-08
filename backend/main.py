"""
FastAPI application entry point.
"""
import logging
import os

from fastapi import FastAPI

from db.constraints import ensure_db_constraints, ensure_db_schemas
from db.session import Base, engine
from routers import (
    accounts,
    corporate_actions,
    ingest,
    prices,
    portfolio,
    taxes,
    settings as settings_router,
)
from scheduler import start_scheduler

logger = logging.getLogger("uvicorn.error")

# Dev convenience: create missing tables when TLH_AUTO_CREATE_SCHEMA=1 (default).
# Prefer Alembic migrations (`alembic upgrade head`) for durable schema changes.
if os.getenv("TLH_AUTO_CREATE_SCHEMA", "1") == "1":
    ensure_db_schemas(engine)
    Base.metadata.create_all(bind=engine)
    ensure_db_constraints(engine)
else:
    logger.info("TLH_AUTO_CREATE_SCHEMA disabled; relying on Alembic migrations.")

app = FastAPI(
    title="TLH Backend",
    description="Net-worth tracking & tax loss harvesting backend API",
    version="0.1.0",
)

start_scheduler()

app.include_router(ingest.router)
app.include_router(accounts.router)
app.include_router(settings_router.router)
app.include_router(corporate_actions.router)
app.include_router(prices.router)
app.include_router(portfolio.router)
app.include_router(taxes.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
