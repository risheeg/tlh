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
    from db.session import engine  # noqa: E402

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

    from models.models import Account, AccountType, User  # noqa: E402

    user_id = _get_user_id()

    # Validate type
    try:
        account_type = AccountType(args.type)
    except ValueError:
        sys.exit(f"Error: invalid account type '{args.type}'. "
                 "Choose from: taxable, retirement")

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
    from models.models import Account, AggregatePosition, User  # noqa: E402

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
    print(f"  account_id : {account_id}")


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
        "--type", required=True, choices=["taxable", "retirement"],
        metavar="TYPE", help="Account type: taxable | retirement"
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
    upload_pos_p.set_defaults(func=cmd_positions_upload)

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
