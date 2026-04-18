"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from db.constraints import ensure_db_constraints
from db.session import Base, engine, SessionLocal
from routers import accounts, ingest, prices
from services.prices import sync_stock_prices
from apscheduler.schedulers.background import BackgroundScheduler

# Create all tables that don't exist yet (dev convenience; use Alembic in prod)
Base.metadata.create_all(bind=engine)
ensure_db_constraints(engine)

app = FastAPI(
    title="TLH Backend",
    description="Net-worth tracking & tax loss harvesting backend API",
    version="0.1.0",
)

# --- Scheduler Setup ---
scheduler = BackgroundScheduler()

def daily_sync_job():
    db = SessionLocal()
    try:
        sync_stock_prices(db)
    finally:
        db.close()

# Run once at 00:00 every day
scheduler.add_job(daily_sync_job, 'cron', hour=0, minute=0)
scheduler.start()

app.include_router(ingest.router)
app.include_router(accounts.router)
app.include_router(prices.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
