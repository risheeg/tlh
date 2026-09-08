"""Scheduled TLH job entrypoints."""
from __future__ import annotations

import logging
from time import perf_counter

from sqlalchemy.orm import Session

from models.core import User
from .notify import check_and_notify_tlh

logger = logging.getLogger("uvicorn.error")


def run_daily_tlh_check(db: Session, user_id: str) -> dict:
    """Daily maintenance entrypoint for one user."""
    return check_and_notify_tlh(db, user_id)


def run_daily_tlh_for_all_users(db: Session) -> dict:
    """Scan and notify TLH opportunities for every user."""
    started_at = perf_counter()
    users = db.query(User).all()
    logger.info("Daily TLH check starting for %s user(s).", len(users))

    users_notified = 0
    total_harvestable_loss = 0.0
    total_harvestable_lots = 0
    results = []

    for user in users:
        tlh_result = check_and_notify_tlh(db, str(user.id))
        total_loss = float(tlh_result.get("total_loss", 0) or 0)
        lots_count = int(tlh_result.get("lots_count", 0) or 0)
        notified = bool(tlh_result.get("notified"))
        users_notified += int(notified)
        total_harvestable_loss += total_loss
        total_harvestable_lots += lots_count
        results.append(
            {
                "user_id": user.id,
                "email": user.email,
                "total_loss": total_loss,
                "lots_count": lots_count,
                "notified": notified,
            }
        )
        logger.info(
            "Daily TLH user result: user_id=%s, email=%s, "
            "harvestable_loss=%.2f, harvestable_lots=%s, notified=%s.",
            user.id,
            user.email,
            total_loss,
            lots_count,
            notified,
        )

    summary = {
        "users_checked": len(users),
        "users_notified": users_notified,
        "total_harvestable_loss": total_harvestable_loss,
        "total_harvestable_lots": total_harvestable_lots,
        "elapsed_seconds": perf_counter() - started_at,
        "results": results,
    }
    logger.info(
        "Daily TLH check complete: users_checked=%s, users_notified=%s, "
        "total_harvestable_loss=%.2f, total_harvestable_lots=%s.",
        summary["users_checked"],
        summary["users_notified"],
        summary["total_harvestable_loss"],
        summary["total_harvestable_lots"],
    )
    return summary
