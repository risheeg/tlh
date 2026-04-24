"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from db.constraints import ensure_db_constraints
from db.session import Base, engine, SessionLocal
from routers import accounts, corporate_actions, ingest, prices, portfolio
from services.prices import sync_stock_prices
from services.portfolio.history_service import create_net_worth_snapshot
from services.tlh_service import check_and_notify_tlh
from models.models import User
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

def daily_maintenance_job():
    db = SessionLocal()
    try:
        # 1. Sync stock prices
        sync_stock_prices(db)
        
        # 2. Capture snapshots for all users
        users = db.query(User).all()
        for user in users:
            create_net_worth_snapshot(db, user.id)
            
            # 3. Check for TLH opportunities and notify
            check_and_notify_tlh(db, str(user.id))
            
    finally:
        db.close()

# Run once at 00:00 every day
scheduler.add_job(daily_maintenance_job, 'cron', hour=0, minute=0)
scheduler.start()

app.include_router(ingest.router)
app.include_router(accounts.router)
app.include_router(corporate_actions.router)
app.include_router(prices.router)
app.include_router(portfolio.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
