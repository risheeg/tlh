"""Subcommand: positions."""

from __future__ import annotations

import argparse
import sys
import uuid

from cli.common import BACKEND_ROOT, _get_db_session, _get_user_id


def cmd_positions_upload(args: argparse.Namespace) -> None:
    """Upsert a single aggregate position for the active user."""
    import uuid as _uuid
    from datetime import datetime, timezone

    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from models.core import Account, User  # noqa: E402
    from models.enums import AssetType  # noqa: E402
    from models.portfolio import AggregatePosition, CashHolding  # noqa: E402

    user_id = _get_user_id()

    try:
        account_id = uuid.UUID(args.account_id)
    except ValueError:
        sys.exit(f"Error: --account-id '{args.account_id}' is not a valid UUID.")

    db = _get_db_session()
    try:
        user = db.get(User, user_id)
        if not user:
            sys.exit(f"Error: user {user_id} not found in the database.")

        account = db.get(Account, account_id)
        if not account or account.user_id != user_id:
            sys.exit(f"Error: account {account_id} not found for this user.")

        now = datetime.now(timezone.utc)
        asset_type = AssetType(args.asset_type)

        if asset_type == AssetType.Cash:
            # Route to cash_holdings
            existing = (
                db.query(CashHolding)
                .filter(
                    CashHolding.user_id == user_id,
                    CashHolding.account_id == account_id,
                )
                .first()
            )
            if existing:
                existing.amount = args.quantity
                existing.last_updated = now
                action = "updated"
                position_id = str(existing.id)
            else:
                cash = CashHolding(
                    id=_uuid.uuid4(),
                    user_id=user_id,
                    account_id=account_id,
                    amount=args.quantity,
                    last_updated=now,
                )
                db.add(cash)
                action = "created"
                db.flush()
                position_id = str(cash.id)
        else:
            # Route to aggregate_positions (Equity)
            ticker = args.ticker.upper()
            existing = (
                db.query(AggregatePosition)
                .filter(
                    AggregatePosition.user_id == user_id,
                    AggregatePosition.account_id == account_id,
                    AggregatePosition.ticker == ticker,
                )
                .first()
            )

            if existing:
                existing.quantity = args.quantity
                existing.cost_basis = args.cost_basis
                existing.last_updated = now
                action = "updated"
                position_id = str(existing.id)
            else:
                position = AggregatePosition(
                    id=_uuid.uuid4(),
                    user_id=user_id,
                    account_id=account_id,
                    ticker=ticker,
                    quantity=args.quantity,
                    cost_basis=args.cost_basis,
                    last_updated=now,
                )
                db.add(position)
                action = "created"
                db.flush()
                position_id = str(position.id)

        db.commit()
    finally:
        db.close()

    print(f"✓ Position {action}.")
    print(f"  position_id: {position_id}")
    print(f"  ticker     : {ticker}")
    print(f"  quantity   : {args.quantity}")
    if args.cost_basis is not None:
        print(f"  cost_basis : {args.cost_basis}")
    print(f"  asset_type : {args.asset_type}")
    print(f"  account_id : {account_id}")
