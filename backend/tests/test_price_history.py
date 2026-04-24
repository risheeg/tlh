import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from services.price_history import backup_daily_stock_prices


class PriceHistoryBackupTest(unittest.TestCase):
    def test_backup_writes_each_ticker_once_per_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "prices.sqlite3"

            first = backup_daily_stock_prices(
                {"VUG": Decimal("72.52"), "VTI": Decimal("300.01")},
                price_date=date(2026, 4, 24),
                db_path=db_path,
            )
            second = backup_daily_stock_prices(
                {"VUG": Decimal("73.00")},
                price_date=date(2026, 4, 24),
                db_path=db_path,
            )

            self.assertEqual(first["inserted"], 2)
            self.assertEqual(first["skipped_existing"], 0)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["skipped_existing"], 1)

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT ticker, price_date, price
                    FROM stock_price_history
                    ORDER BY ticker
                    """
                ).fetchall()

        self.assertEqual(
            rows,
            [
                ("VTI", "2026-04-24", "300.01"),
                ("VUG", "2026-04-24", "72.52"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
