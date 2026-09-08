"""Scheduled portfolio job entrypoints."""
from __future__ import annotations

import logging
from time import perf_counter

from sqlalchemy.orm import Session

from models.core import User
from .digest import send_monthly_digest
from .history import create_net_worth_snapshot
from .prices import sync_stock_prices

logger = logging.getLogger("uvicorn.error")


def run_daily_maintenance(db: Session) -> dict:
    """
    Sync prices, snapshot net worth for every user.

    TLH notify is orchestrated separately via domains.tlh.jobs so domains
    stay one-way (portfolio must not import tlh).
    """
    started_at = perf_counter()
    logger.info("Daily portfolio maintenance started.")

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

    users = db.query(User).all()
    snapshots = []
    for user in users:
        snapshot = create_net_worth_snapshot(db, user.id)
        snapshots.append({"user_id": user.id, "net_worth": snapshot.total_net_worth})

    elapsed_seconds = perf_counter() - started_at
    logger.info(
        "Daily portfolio maintenance finished in %.2f seconds for %s user(s).",
        elapsed_seconds,
        len(users),
    )
    return {
        "price_sync": price_sync,
        "users_snapshotted": len(snapshots),
        "snapshots": snapshots,
        "elapsed_seconds": elapsed_seconds,
    }


def run_monthly_digest(db: Session) -> dict:
    """Send monthly portfolio digest emails to all users."""
    logger.info("Monthly digest job started.")
    users = db.query(User).all()
    sent = 0
    for user in users:
        try:
            result = send_monthly_digest(db, str(user.id))
            sent += 1
            logger.info(
                "Monthly digest sent: email=%s, subject=%s",
                result["email"],
                result["subject"],
            )
        except Exception:
            logger.exception("Monthly digest failed for user %s", user.id)
    logger.info("Monthly digest job finished: sent=%s, users=%s.", sent, len(users))
    return {"users": len(users), "sent": sent}
