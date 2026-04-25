"""
FastAPI application entry point.
"""
import logging
from time import perf_counter

from fastapi import FastAPI

from db.constraints import ensure_db_constraints, ensure_db_schemas
from db.session import Base, engine, SessionLocal
from routers import accounts, corporate_actions, ingest, prices, portfolio
from services.prices import sync_stock_prices
from services.portfolio.history_service import create_net_worth_snapshot
from services.tlh_service import check_and_notify_tlh
from models.models import User
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("uvicorn.error")

# Create all tables that don't exist yet (dev convenience; use Alembic in prod)
ensure_db_schemas(engine)
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
    started_at = perf_counter()
    logger.info("Daily maintenance job started.")
    db = SessionLocal()
    try:
        # 1. Sync stock prices
        price_sync = sync_stock_prices(db)
        price_history = price_sync.get("price_history") or {}
        logger.info(
            "Daily maintenance price sync complete: requested=%s, updated=%s, "
            "added_to_sheet=%s, price_history_inserted=%s, "
            "price_history_skipped=%s.",
            price_sync.get("total_tickers_requested", 0),
            price_sync.get("updated_in_db", 0),
            price_sync.get("added_to_sheet", 0),
            price_history.get("inserted", 0),
            price_history.get("skipped_existing", 0),
        )
        
        # 2. Capture snapshots for all users
        users = db.query(User).all()
        logger.info("Daily TLH check starting for %s user(s).", len(users))
        users_notified = 0
        total_harvestable_loss = 0.0
        total_harvestable_lots = 0
        for user in users:
            snapshot = create_net_worth_snapshot(db, user.id)
            
            # 3. Check for TLH opportunities and notify
            tlh_result = check_and_notify_tlh(db, str(user.id))
            total_loss = float(tlh_result.get("total_loss", 0) or 0)
            lots_count = int(tlh_result.get("lots_count", 0) or 0)
            notified = bool(tlh_result.get("notified"))
            users_notified += int(notified)
            total_harvestable_loss += total_loss
            total_harvestable_lots += lots_count
            logger.info(
                "Daily TLH user result: user_id=%s, email=%s, net_worth=%.2f, "
                "harvestable_loss=%.2f, harvestable_lots=%s, notified=%s.",
                user.id,
                user.email,
                snapshot.total_net_worth,
                total_loss,
                lots_count,
                notified,
            )
        logger.info(
            "Daily TLH check complete: users_checked=%s, users_notified=%s, "
            "total_harvestable_loss=%.2f, total_harvestable_lots=%s.",
            len(users),
            users_notified,
            total_harvestable_loss,
            total_harvestable_lots,
        )
    except Exception:
        logger.exception("Daily maintenance job failed.")
        raise
    else:
        elapsed_seconds = perf_counter() - started_at
        logger.info("Daily maintenance job finished in %.2f seconds.", elapsed_seconds)
            
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
