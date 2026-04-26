"""UTC time helpers."""

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def usage_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()
