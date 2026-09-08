"""APScheduler wiring for domain job entrypoints."""
from __future__ import annotations

import logging
from time import perf_counter

from apscheduler.schedulers.background import BackgroundScheduler

from db.session import SessionLocal
from domains.portfolio.jobs import run_daily_maintenance, run_monthly_digest
from domains.tlh.jobs import run_daily_tlh_for_all_users

logger = logging.getLogger("uvicorn.error")

scheduler = BackgroundScheduler()


def daily_maintenance_job() -> None:
    """Price sync + net-worth snapshots + TLH notify."""
    started_at = perf_counter()
    logger.info("Daily maintenance job started.")
    db = SessionLocal()
    try:
        run_daily_maintenance(db)
        run_daily_tlh_for_all_users(db)
    except Exception:
        logger.exception("Daily maintenance job failed.")
        raise
    else:
        logger.info(
            "Daily maintenance job finished in %.2f seconds.",
            perf_counter() - started_at,
        )
    finally:
        db.close()


def monthly_digest_job() -> None:
    """Send monthly portfolio digests on the 1st at 08:00 UTC."""
    db = SessionLocal()
    try:
        run_monthly_digest(db)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Register cron jobs and start the background scheduler."""
    scheduler.add_job(daily_maintenance_job, "cron", hour=0, minute=0)
    scheduler.add_job(monthly_digest_job, "cron", day=1, hour=8, minute=0)
    scheduler.start()
    return scheduler
