"""Subcommand: tlh."""

from __future__ import annotations

import argparse

from cli.common import BACKEND_ROOT, _get_db_session


def cmd_tlh_check(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Run the tax loss harvesting check for all users."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.tlh import check_and_notify_tlh
    from models.core import User

    db = _get_db_session()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found.")
            return

        print("Starting tax loss harvesting check...")
        for user in users:
            try:
                print(f"  Checking for: {user.email}...")
                result = check_and_notify_tlh(db, str(user.id))
                if result.get("notified"):
                    print(f"    ✓ NOTIFIED: ${result['total_loss']:,.2f} loss identified.")
                else:
                    print(f"    - No notification sent (Loss: ${result.get('total_loss', 0):,.2f}).")
            except Exception as e:
                print(f"  FAILED for {user.email}: {e}")
        print("✓ TLH check complete.")
    finally:
        db.close()


def cmd_tlh_monthly_digest(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Send the monthly portfolio digest email for all users."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from domains.portfolio.digest import send_monthly_digest
    from models.core import User

    db = _get_db_session()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found.")
            return

        print("Sending monthly digest...")
        for user in users:
            try:
                result = send_monthly_digest(db, str(user.id))
                print(f"  ✓ Sent to {result['email']}")
            except Exception as e:
                print(f"  FAILED for {user.email}: {e}")
        print("✓ Monthly digest complete.")
    finally:
        db.close()
