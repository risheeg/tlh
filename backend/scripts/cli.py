#!/usr/bin/env python3
"""
tlh-cli — Command-line interface for the Tax Loss Harvesting app.

Authentication
--------------
  uv run python scripts/cli.py auth set-user --uuid <UUID>
  uv run python scripts/cli.py auth whoami

Accounts
--------
  uv run python scripts/cli.py accounts create \\
      --name "Schwab Brokerage" --type taxable --institution "Charles Schwab"

Lots (tax lots)
---------------
  uv run python scripts/cli.py lots upload \\
      --account-id <UUID> \\
      --ticker AAPL \\
      --quantity 10 \\
      --purchase-price 150.00 \\
      --adjusted-basis 150.00 \\
      --purchase-date 2024-01-15 \\
      [--status active] \\
      [--ref-id my-unique-ref]

Positions (aggregate)
---------------------
  uv run python scripts/cli.py positions upload \\
      --account-id <UUID> \\
      --ticker VTSAX \\
      --quantity 42.5

Prices
------
  uv run python scripts/cli.py prices sync

Run from the backend/ directory:
  uv run python scripts/cli.py <command> [options]
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Config helpers  (~/.tlh_config.json  stores the active user UUID)
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".tlh_config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _get_user_id() -> uuid.UUID:
    """Return the active user UUID or exit with a helpful message."""
    cfg = _load_config()
    raw = cfg.get("user_id")
    if not raw:
        sys.exit(
            "Error: no user set.\n"
            "Run:  uv run python scripts/cli.py auth set-user --uuid <UUID>\n"
            "  or  uv run python scripts/cli.py auth set-user --new"
        )
    try:
        return uuid.UUID(raw)
    except ValueError:
        sys.exit(f"Error: stored user_id '{raw}' is not a valid UUID. "
                 "Re-run `auth set-user` to fix it.")


# ---------------------------------------------------------------------------
# DB / session helpers (identical path-setup as seed.py)
# ---------------------------------------------------------------------------

def _get_db_session():
    """Return a live SQLAlchemy Session (caller must close it)."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

    from sqlalchemy.orm import Session  # noqa: E402 (local import)
    from db.constraints import ensure_db_constraints  # noqa: E402
    from db.session import engine  # noqa: E402
    from models.models import StockSplit  # noqa: E402

    StockSplit.__table__.create(bind=engine, checkfirst=True)
    ensure_db_constraints(engine)

    return Session(engine)


# ---------------------------------------------------------------------------
# Subcommand: auth
# ---------------------------------------------------------------------------

def cmd_auth_set_user(args: argparse.Namespace) -> None:
    """Store a user UUID in the local config file."""
    if args.new:
        new_id = uuid.uuid4()
        print(f"Generated new UUID: {new_id}")
    elif args.uuid:
        try:
            new_id = uuid.UUID(args.uuid)
        except ValueError:
            sys.exit(f"Error: '{args.uuid}' is not a valid UUID.")
    else:
        sys.exit("Error: provide --uuid <UUID> or --new.")

    cfg = _load_config()
    cfg["user_id"] = str(new_id)
    _save_config(cfg)
    print(f"✓ Active user set to: {new_id}")
    print(f"  Config saved to: {CONFIG_PATH}")


def cmd_auth_whoami(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Print the currently active user UUID."""
    cfg = _load_config()
    uid = cfg.get("user_id")
    if uid:
        print(f"Active user: {uid}")
    else:
        print("No user set. Run `auth set-user` first.")


# ---------------------------------------------------------------------------
# Subcommand: accounts
# ---------------------------------------------------------------------------

def cmd_accounts_create(args: argparse.Namespace) -> None:
    """Create a new account for the active user and persist it to the DB."""
    import uuid as _uuid
    from datetime import datetime, timezone

    # Lazy import to avoid loading DB code when --help is shown
    _sys = __import__("sys")
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from models.models import Account, AccountType, AssetType, User  # noqa: E402

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
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.models import Account

    user_id = _get_user_id()
    db = _get_db_session()
    try:
        accounts = db.query(Account).filter(Account.user_id == user_id).all()
        if not accounts:
            print("No accounts found for this user.")
            return
        print(f"Accounts for user {user_id}:\n")
        print(f"  {'ID':<38}  {'Type':<12}  {'Institution':<20}  Name")
        print(f"  {'-'*38}  {'-'*12}  {'-'*20}  ----")
        for acc in accounts:
            print(
                f"  {str(acc.id):<38}  {acc.type.value:<12}  "
                f"{(acc.institution or ''):<20}  {acc.name}"
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Subcommand: lots
# ---------------------------------------------------------------------------

def cmd_lots_upload(args: argparse.Namespace) -> None:
    """Upload a single tax lot for the active user."""
    import uuid as _uuid
    from datetime import date

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.models import Account, AccountType, Lot, LotStatus, User  # noqa: E402
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


# ---------------------------------------------------------------------------
# Subcommand: positions
# ---------------------------------------------------------------------------

def cmd_positions_upload(args: argparse.Namespace) -> None:
    """Upsert a single aggregate position for the active user."""
    import uuid as _uuid
    from datetime import datetime, timezone

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.models import Account, AggregatePosition, AssetType, User  # noqa: E402

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

        now = datetime.now(timezone.utc)
        if existing:
            existing.quantity = args.quantity
            existing.cost_basis = args.cost_basis
            existing.asset_type = AssetType(args.asset_type)
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
                asset_type=AssetType(args.asset_type),
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


# ---------------------------------------------------------------------------
# Subcommand: prices
# ---------------------------------------------------------------------------

def cmd_prices_sync(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Trigger the stock price synchronization job."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.prices import sync_stock_prices

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


# ---------------------------------------------------------------------------
# Subcommand: history
# ---------------------------------------------------------------------------

def cmd_history_capture(args: argparse.Namespace) -> None:
    """Capture a net worth snapshot for all users."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.portfolio.history_service import create_net_worth_snapshot
    from models.models import User

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

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.portfolio.history_service import update_net_worth_snapshot_comments

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


# ---------------------------------------------------------------------------
# Subcommand: tlh
# ---------------------------------------------------------------------------

def cmd_tlh_check(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Run the tax loss harvesting check for all users."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.tlh_service import check_and_notify_tlh
    from models.models import User

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


# ---------------------------------------------------------------------------
# Subcommand: stock-splits
# ---------------------------------------------------------------------------

def _stock_split_payload(args: argparse.Namespace):
    from datetime import date

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from schemas.schemas import StockSplitCreate

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
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.corporate_actions import (
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
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.corporate_actions import (
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


# ---------------------------------------------------------------------------
# Subcommand: users  (create a user directly in the DB)
# ---------------------------------------------------------------------------

def cmd_users_create(args: argparse.Namespace) -> None:
    """Create a new user in the database."""
    import uuid as _uuid
    from datetime import datetime, timezone

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.models import User  # noqa: E402

    db = _get_db_session()
    try:
        # Check for duplicate email
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            user_id = str(existing.id)
            print(f"User with email '{args.email}' already exists.")
            print(f"  user_id: {user_id}")
        else:
            user = User(
                id=_uuid.uuid4(),
                email=args.email,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.commit()
            user_id = str(user.id)
            print(f"✓ User created.")
            print(f"  email  : {args.email}")
            print(f"  user_id: {user_id}")
    finally:
        db.close()

    # Optionally auto-set the new user as active
    if getattr(args, "set_active", False) or not _load_config().get("user_id"):
        cfg = _load_config()
        cfg["user_id"] = user_id
        _save_config(cfg)
        print(f"  ✓ Set as active user in {CONFIG_PATH}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tlh-cli",
        description="Tax Loss Harvesting — command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="group", metavar="<command>")
    sub.required = True

    # ---- auth ---------------------------------------------------------------
    auth_p = sub.add_parser("auth", help="Manage your active user identity")
    auth_sub = auth_p.add_subparsers(dest="action", metavar="<action>")
    auth_sub.required = True

    set_user_p = auth_sub.add_parser("set-user", help="Set the active user UUID")
    uid_group = set_user_p.add_mutually_exclusive_group(required=True)
    uid_group.add_argument("--uuid", metavar="UUID", help="An existing user UUID")
    uid_group.add_argument(
        "--new", action="store_true",
        help="Generate a fresh random UUID (use when no DB user exists yet)"
    )
    set_user_p.set_defaults(func=cmd_auth_set_user)

    whoami_p = auth_sub.add_parser("whoami", help="Show the currently active user UUID")
    whoami_p.set_defaults(func=cmd_auth_whoami)

    # ---- users --------------------------------------------------------------
    users_p = sub.add_parser("users", help="Manage users in the database")
    users_sub = users_p.add_subparsers(dest="action", metavar="<action>")
    users_sub.required = True

    create_user_p = users_sub.add_parser("create", help="Create a new user in the DB")
    create_user_p.add_argument("--email", required=True, metavar="EMAIL",
                               help="User email address")
    create_user_p.add_argument(
        "--set-active", action="store_true",
        help="Also set this user as the active CLI user"
    )
    create_user_p.set_defaults(func=cmd_users_create)

    # ---- accounts -----------------------------------------------------------
    accounts_p = sub.add_parser("accounts", help="Manage brokerage accounts")
    accounts_sub = accounts_p.add_subparsers(dest="action", metavar="<action>")
    accounts_sub.required = True

    create_acc_p = accounts_sub.add_parser("create", help="Create a new account")
    create_acc_p.add_argument("--name", required=True, metavar="NAME",
                              help="Account name (e.g. 'Schwab Brokerage')")
    create_acc_p.add_argument(
        "--type", required=True, choices=["taxable", "retirement", "savings", "checkings", "cma"],
        metavar="TYPE", help="Account type: taxable | retirement | savings | checkings | cma"
    )
    create_acc_p.add_argument("--institution", default=None, metavar="INSTITUTION",
                              help="Institution name (optional)")
    create_acc_p.set_defaults(func=cmd_accounts_create)

    list_acc_p = accounts_sub.add_parser("list", help="List all accounts for the active user")
    list_acc_p.set_defaults(func=cmd_accounts_list)

    # ---- lots ---------------------------------------------------------------
    lots_p = sub.add_parser("lots", help="Upload tax lots")
    lots_sub = lots_p.add_subparsers(dest="action", metavar="<action>")
    lots_sub.required = True

    upload_lot_p = lots_sub.add_parser("upload", help="Upload a single tax lot")
    upload_lot_p.add_argument("--account-id", required=True, metavar="UUID",
                              help="Account UUID (must be a taxable account)")
    upload_lot_p.add_argument("--ticker", required=True, metavar="TICKER",
                              help="Ticker symbol (e.g. AAPL)")
    upload_lot_p.add_argument("--quantity", required=True, type=float, metavar="QTY",
                              help="Number of shares")
    upload_lot_p.add_argument("--purchase-price", required=True, type=float,
                              metavar="PRICE", help="Original purchase price per share")
    upload_lot_p.add_argument("--adjusted-basis", required=True, type=float,
                              metavar="BASIS",
                              help="Current adjusted cost basis per share")
    upload_lot_p.add_argument("--purchase-date", required=True, metavar="YYYY-MM-DD",
                              help="Purchase date in ISO format (e.g. 2024-01-15)")
    upload_lot_p.add_argument(
        "--status", default="active",
        choices=["active", "closed", "ignored"],
        help="Lot status (default: active)"
    )
    upload_lot_p.add_argument("--ref-id", default=None, metavar="REF_ID",
                              help="Optional unique external reference ID (idempotency key)")
    upload_lot_p.set_defaults(func=cmd_lots_upload)

    # ---- positions ----------------------------------------------------------
    positions_p = sub.add_parser("positions", help="Upload aggregate positions")
    positions_sub = positions_p.add_subparsers(dest="action", metavar="<action>")
    positions_sub.required = True

    upload_pos_p = positions_sub.add_parser(
        "upload", help="Upsert a single aggregate position"
    )
    upload_pos_p.add_argument("--account-id", required=True, metavar="UUID",
                              help="Account UUID")
    upload_pos_p.add_argument("--ticker", required=True, metavar="TICKER",
                              help="Ticker symbol (e.g. VTSAX)")
    upload_pos_p.add_argument("--quantity", required=True, type=float, metavar="QTY",
                              help="Total quantity / shares held")
    upload_pos_p.add_argument("--cost-basis", default=None, type=float, metavar="BASIS",
                              help="Aggregated cost basis in dollars (optional)")
    upload_pos_p.add_argument("--asset-type", default="Equity",
                              choices=["Equity", "Cash"],
                              help="Asset type: Equity | Cash (default: Equity)")
    upload_pos_p.set_defaults(func=cmd_positions_upload)

    # ---- prices -------------------------------------------------------------
    prices_p = sub.add_parser("prices", help="Stock price management")
    prices_sub = prices_p.add_subparsers(dest="action", metavar="<action>")
    prices_sub.required = True

    sync_prices_p = prices_sub.add_parser("sync", help="Trigger stock price synchronization")
    sync_prices_p.set_defaults(func=cmd_prices_sync)

    # ---- history ------------------------------------------------------------
    history_p = sub.add_parser("history", help="Net worth history management")
    history_sub = history_p.add_subparsers(dest="action", metavar="<action>")
    history_sub.required = True

    capture_history_p = history_sub.add_parser("capture", help="Capture a daily net worth snapshot")
    capture_history_p.add_argument(
        "--comment",
        default=None,
        help="Optional comments to store with today's snapshot",
    )
    capture_history_p.set_defaults(func=cmd_history_capture)

    comment_history_p = history_sub.add_parser(
        "comment", help="Update comments on an existing net worth snapshot"
    )
    comment_history_p.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    comment_history_p.add_argument("--comment", required=True, help="Snapshot comments")
    comment_history_p.set_defaults(func=cmd_history_comment)

    # ---- tlh ----------------------------------------------------------------
    tlh_p = sub.add_parser("tlh", help="Tax Loss Harvesting tools")
    tlh_sub = tlh_p.add_subparsers(dest="action", metavar="<action>")
    tlh_sub.required = True

    check_tlh_p = tlh_sub.add_parser("check", help="Identify lots with losses and notify users")
    check_tlh_p.set_defaults(func=cmd_tlh_check)

    # ---- stock splits -------------------------------------------------------
    splits_p = sub.add_parser("stock-splits", help="Preview or apply stock splits")
    splits_sub = splits_p.add_subparsers(dest="action", metavar="<action>")
    splits_sub.required = True

    def add_split_args(split_parser: argparse.ArgumentParser) -> None:
        split_parser.add_argument("--ticker", required=True, metavar="TICKER",
                                  help="Ticker symbol (e.g. VUG)")
        split_parser.add_argument("--effective-date", required=True, metavar="YYYY-MM-DD",
                                  help="Split effective date")
        split_parser.add_argument("--numerator", required=True, type=int, metavar="N",
                                  help="New shares in the split ratio")
        split_parser.add_argument("--denominator", required=True, type=int, metavar="D",
                                  help="Old shares in the split ratio")

    preview_split_p = splits_sub.add_parser(
        "preview", help="Preview holdings affected by a stock split"
    )
    add_split_args(preview_split_p)
    preview_split_p.set_defaults(func=cmd_stock_splits_preview)

    apply_split_p = splits_sub.add_parser(
        "apply", help="Apply a stock split to stored holdings"
    )
    add_split_args(apply_split_p)
    apply_split_p.set_defaults(func=cmd_stock_splits_apply)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
