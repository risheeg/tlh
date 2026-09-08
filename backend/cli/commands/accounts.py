"""Subcommand: accounts."""

from __future__ import annotations

import argparse
import sys

from cli.common import BACKEND_ROOT, _get_db_session, _get_user_id


def cmd_accounts_create(args: argparse.Namespace) -> None:
    """Create a new account for the active user and persist it to the DB."""
    import uuid as _uuid
    from datetime import datetime, timezone

    # Lazy import to avoid loading DB code when --help is shown
    _sys = __import__("sys")
    _sys.path.insert(0, str(BACKEND_ROOT))

    from models.core import Account, User  # noqa: E402
    from models.enums import AccountType, AssetType  # noqa: E402

    user_id = _get_user_id()

    # Validate type
    try:
        account_type = AccountType(args.type)
    except ValueError:
        sys.exit(f"Error: invalid account type '{args.type}'. "
                 "Choose from: taxable, retirement, savings, checkings, cma")

    db = _get_db_session()
    try:
        user = db.get(User, user_id)
        if not user:
            sys.exit(f"Error: user {user_id} not found in the database.\n"
                     "Create the user first or update your active user with `auth set-user`.")

        # Check for duplicate name under this user
        existing = (
            db.query(Account)
            .filter(Account.user_id == user_id, Account.name == args.name)
            .first()
        )
        if existing:
            print(f"Account '{args.name}' already exists for this user.")
            print(f"  account_id: {existing.id}")
            return

        account = Account(
            id=_uuid.uuid4(),
            user_id=user_id,
            name=args.name,
            type=account_type,
            institution=args.institution,
            created_at=datetime.now(timezone.utc),
        )
        db.add(account)
        db.commit()
        account_id = str(account.id)
    finally:
        db.close()

    print(f"✓ Account created.")
    print(f"  name       : {args.name}")
    print(f"  type       : {args.type}")
    print(f"  institution: {args.institution}")
    print(f"  account_id : {account_id}")


def cmd_accounts_list(args: argparse.Namespace) -> None:  # noqa: ARG001
    """List all accounts for the active user."""
    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from models.core import Account

    user_id = _get_user_id()
    db = _get_db_session()
    try:
        accounts = db.query(Account).filter(Account.user_id == user_id).all()
        if not accounts:
            print("No accounts found for this user.")
            return
        print(f"Accounts for user {user_id}:\n")
        print(f"  {'ID':<38}  {'Type':<12}  {'Institution':<20}  {'Status':<8}  Name")
        print(f"  {'-'*38}  {'-'*12}  {'-'*20}  {'-'*8}  ----")
        for acc in accounts:
            status = "closed" if acc.closed_at else "active"
            print(
                f"  {str(acc.id):<38}  {acc.type.value:<12}  "
                f"{(acc.institution or ''):<20}  {status:<8}  {acc.name}"
            )
    finally:
        db.close()
