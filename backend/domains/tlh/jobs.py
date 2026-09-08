"""Scheduled TLH job entrypoints."""
from sqlalchemy.orm import Session

from .notify import check_and_notify_tlh


def run_daily_tlh_check(db: Session, user_id: str) -> dict:
    """Daily maintenance entrypoint for one user."""
    return check_and_notify_tlh(db, user_id)
