"""Subcommand: lots."""

from __future__ import annotations

import argparse
import sys
import uuid

from cli.common import BACKEND_ROOT, _get_db_session, _get_user_id


def cmd_lots_upload(args: argparse.Namespace) -> None:
    """Upload a single tax lot for the active user."""
    import uuid as _uuid
    from datetime import date

    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from models.core import Account, User  # noqa: E402
    from models.enums import AccountType, LotStatus  # noqa: E402
    from models.portfolio import Lot  # noqa: E402
    from sqlalchemy.exc import IntegrityError

    user_id = _get_user_id()

    # Parse / validate args
    try:
        account_id = uuid.UUID(args.account_id)
    except ValueError:
        sys.exit(f"Error: --account-id '{args.account_id}' is not a valid UUID.")

    try:
        purchase_date = date.fromisoformat(args.purchase_date)
    except ValueError:
        sys.exit(f"Error: --purchase-date '{args.purchase_date}' must be YYYY-MM-DD.")

    try:
        lot_status = LotStatus(args.status)
    except ValueError:
        sys.exit(f"Error: invalid --status '{args.status}'. "
                 "Choose from: active, closed, ignored")

    db = _get_db_session()
    try:
        user = db.get(User, user_id)
        if not user:
            sys.exit(f"Error: user {user_id} not found in the database.")

        account = db.get(Account, account_id)
        if not account or account.user_id != user_id:
            sys.exit(f"Error: account {account_id} not found for this user.")

        if account.type != AccountType.taxable:
            sys.exit(
                f"Error: account '{account.name}' is of type '{account.type.value}'. "
                "Tax lots can only be uploaded to taxable accounts."
            )

        lot = Lot(
            id=_uuid.uuid4(),
            user_id=user_id,
            account_id=account_id,
            ticker=args.ticker.upper(),
            quantity=args.quantity,
            original_purchase_price=args.purchase_price,
            current_adjusted_basis=args.adjusted_basis,
            purchase_date=purchase_date,
            status=lot_status,
            external_ref_id=args.ref_id,
        )
        db.add(lot)
        try:
            db.commit()
            lot_id = str(lot.id)
        except IntegrityError:
            db.rollback()
            sys.exit(
                f"Error: a lot with external_ref_id='{args.ref_id}' already exists. "
                "Use a different --ref-id or omit it."
            )
    finally:
        db.close()

    print(f"✓ Lot uploaded.")
    print(f"  lot_id        : {lot_id}")
    print(f"  ticker        : {args.ticker.upper()}")
    print(f"  quantity      : {args.quantity}")
    print(f"  purchase_price: {args.purchase_price}")
    print(f"  adjusted_basis: {args.adjusted_basis}")
    print(f"  purchase_date : {purchase_date}")
    print(f"  status        : {lot_status.value}")
    if args.ref_id:
        print(f"  ref_id        : {args.ref_id}")
