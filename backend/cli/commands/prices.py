"""Subcommand: prices."""

from __future__ import annotations

import argparse
import sys

from cli.common import BACKEND_ROOT, _get_db_session


def cmd_prices_sync(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Trigger the stock price synchronization job."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.prices import sync_stock_prices

    db = _get_db_session()
    try:
        print("Starting stock price synchronization...")
        result = sync_stock_prices(db)
        print("✓ Synchronization complete.")
        print(f"  Total tickers requested: {result['total_tickers_requested']}")
        print(f"  Tickers added to sheet : {result['added_to_sheet']}")
        print(f"  Tickers updated in DB  : {result['updated_in_db']}")
    except Exception as e:
        sys.exit(f"Error during synchronization: {e}")
    finally:
        db.close()
