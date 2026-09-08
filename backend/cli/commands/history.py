"""Subcommand: history."""

from __future__ import annotations

import argparse
import sys

from cli.common import BACKEND_ROOT, _get_db_session, _get_user_id


def cmd_history_capture(args: argparse.Namespace) -> None:
    """Capture a net worth snapshot for all users."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.history import create_net_worth_snapshot
    from models.core import User

    db = _get_db_session()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found.")
            return

        print("Starting net worth snapshot capture...")
        for user in users:
            try:
                print(f"  Capturing for: {user.email}...")
                create_net_worth_snapshot(db, user.id, comments=args.comment)
            except Exception as e:
                print(f"  FAILED for {user.email}: {e}")
        print("✓ Capture complete.")
    finally:
        db.close()


def cmd_history_comment(args: argparse.Namespace) -> None:
    """Update comments on a net worth snapshot for the active user."""
    import sys as _sys
    from datetime import date

    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.history import update_net_worth_snapshot_comments

    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        sys.exit(f"Error: --date '{args.date}' must be YYYY-MM-DD.")

    db = _get_db_session()
    try:
        snapshot = update_net_worth_snapshot_comments(
            db,
            _get_user_id(),
            snapshot_date,
            args.comment,
        )
    finally:
        db.close()

    if not snapshot:
        sys.exit(f"Error: no net worth snapshot found for {snapshot_date}.")

    print("✓ Snapshot comments updated.")
    print(f"  date    : {snapshot.snapshot_date}")
    print(f"  comments: {snapshot.comments or ''}")
