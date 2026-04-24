import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping


DEFAULT_PRICE_HISTORY_DB = (
    Path(__file__).resolve().parent.parent / "var" / "stock_price_history.sqlite3"
)


def get_price_history_db_path() -> Path:
    configured = os.getenv("TLH_PRICE_HISTORY_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_PRICE_HISTORY_DB


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_price_history (
            ticker TEXT NOT NULL,
            price_date TEXT NOT NULL,
            price TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY (ticker, price_date)
        )
        """
    )
    return conn


def backup_daily_stock_prices(
    prices: Mapping[str, object],
    *,
    price_date: date | None = None,
    db_path: Path | None = None,
) -> dict:
    """
    Persist one local historical price row per ticker per day.

    This intentionally writes to SQLite on the instance instead of Neon because
    historical prices are rarely queried and can be treated as local archive data.
    """
    target_date = price_date or datetime.now(timezone.utc).date()
    captured_at = datetime.now(timezone.utc).isoformat()
    path = db_path or get_price_history_db_path()

    inserted = 0
    skipped = 0
    with _connect(path) as conn:
        for ticker, price in prices.items():
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO stock_price_history
                    (ticker, price_date, price, captured_at)
                VALUES (?, ?, ?, ?)
                """,
                (ticker.upper(), target_date.isoformat(), str(price), captured_at),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                skipped += 1

    return {
        "db_path": str(path),
        "price_date": target_date.isoformat(),
        "inserted": inserted,
        "skipped_existing": skipped,
    }
