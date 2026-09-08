"""Subcommand: stock-splits."""

from __future__ import annotations

import argparse
import sys

from cli.common import BACKEND_ROOT, _get_db_session


def _stock_split_payload(args: argparse.Namespace):
    from datetime import date

    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from schemas.corporate_actions import StockSplitCreate

    try:
        effective_date = date.fromisoformat(args.effective_date)
    except ValueError:
        sys.exit(f"Error: --effective-date '{args.effective_date}' must be YYYY-MM-DD.")

    return StockSplitCreate(
        ticker=args.ticker,
        effective_date=effective_date,
        split_numerator=args.numerator,
        split_denominator=args.denominator,
    )


def _print_stock_split_result(result) -> None:
    impact = result.impact
    print(f"  ticker                       : {result.ticker}")
    print(f"  effective_date               : {result.effective_date}")
    print(f"  ratio                        : {result.split_numerator}:{result.split_denominator}")
    print(f"  already_applied              : {result.already_applied}")
    if hasattr(result, "applied"):
        print(f"  applied                      : {result.applied}")
        print(f"  stock_split_id               : {result.stock_split.id}")
    print(f"  affected_lots                : {impact.affected_lots}")
    print(f"  lot_quantity_before          : {impact.lot_quantity_before}")
    print(f"  lot_quantity_after           : {impact.lot_quantity_after}")
    print(f"  lot_cost_basis_before        : {impact.lot_cost_basis_before}")
    print(f"  lot_cost_basis_after         : {impact.lot_cost_basis_after}")
    print(f"  affected_aggregate_positions : {impact.affected_aggregate_positions}")
    print(f"  aggregate_quantity_before    : {impact.aggregate_quantity_before}")
    print(f"  aggregate_quantity_after     : {impact.aggregate_quantity_after}")
    print(f"  aggregate_cost_basis_before  : {impact.aggregate_cost_basis_before}")
    print(f"  aggregate_cost_basis_after   : {impact.aggregate_cost_basis_after}")


def cmd_stock_splits_preview(args: argparse.Namespace) -> None:
    """Preview the holdings affected by a stock split."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.corporate_actions import (
        StockSplitRatioConflictError,
        preview_stock_split,
    )

    db = _get_db_session()
    try:
        try:
            result = preview_stock_split(db, _stock_split_payload(args))
        except StockSplitRatioConflictError as exc:
            sys.exit(f"Error: {exc}")
    finally:
        db.close()

    print("Stock split preview:")
    _print_stock_split_result(result)


def cmd_stock_splits_apply(args: argparse.Namespace) -> None:
    """Apply a stock split to stored holdings."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.corporate_actions import (
        StockSplitRatioConflictError,
        apply_stock_split,
    )

    db = _get_db_session()
    try:
        try:
            result = apply_stock_split(db, _stock_split_payload(args))
        except StockSplitRatioConflictError as exc:
            sys.exit(f"Error: {exc}")
    finally:
        db.close()

    print("Stock split apply result:")
    _print_stock_split_result(result)
