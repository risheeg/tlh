"""Argument parser for the tlh CLI."""

from __future__ import annotations

import argparse

from cli.commands.accounts import cmd_accounts_create, cmd_accounts_list
from cli.commands.auth import cmd_auth_set_user, cmd_auth_whoami
from cli.commands.history import cmd_history_capture, cmd_history_comment
from cli.commands.links import cmd_links
from cli.commands.lots import cmd_lots_upload
from cli.commands.positions import cmd_positions_upload
from cli.commands.prices import cmd_prices_sync
from cli.commands.stock_splits import cmd_stock_splits_apply, cmd_stock_splits_preview
from cli.commands.tlh import cmd_tlh_check, cmd_tlh_monthly_digest
from cli.commands.users import cmd_users_create


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tlh",
        description="Tax Loss Harvesting command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How this CLI interacts with the app
  tlh is a local administrative CLI. It does not call the FastAPI server.
  Commands import backend modules directly, create a SQLAlchemy session, and
  connect to Neon using the same backend/.env-backed settings as the FastAPI app.

  DB path:
    backend/.env -> core.config.settings.neon_db_host -> db.session.engine
         -> SQLAlchemy Session -> domains/models -> Neon

  FastAPI uses the same models and domains through db.session.get_db().
  The scheduled backend job also opens SessionLocal() directly, without HTTP.

Command groups
  auth           Store/show the active user UUID in ~/.tlh_config.json
  users          Create users in the database
  accounts       Create or list accounts for the active user
  lots           Upload taxable account tax lots
  positions      Upload aggregate account positions
  prices         Sync stock prices from Google Sheets into Neon
  history        Capture or comment on net worth snapshots
  tlh            Check TLH opportunities and send notifications
  links          Show local API links in logical order
  stock-splits   Preview or apply stock splits to holdings

Examples
  tlh auth whoami
  tlh users create --email you@example.com --set-active
  tlh accounts list
  tlh links
  tlh links devbox
  tlh prices sync
  tlh history capture --comment "Moved apartments"
  tlh stock-splits preview --ticker VUG --effective-date 2026-04-21 --numerator 6 --denominator 1

Run `tlh <command> --help` or `tlh <command> <action> --help` for details.
""",
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

    weekly_digest_p = tlh_sub.add_parser(
        "monthly-digest", help="Send monthly portfolio digest email (always sends)"
    )
    weekly_digest_p.set_defaults(func=cmd_tlh_monthly_digest)

    # ---- links --------------------------------------------------------------
    links_p = sub.add_parser("links", help="Show local API links in logical order")
    links_p.add_argument(
        "target",
        nargs="?",
        default=None,
        metavar="TARGET",
        help=(
            "Base URL alias or host:port. Aliases: "
            "main=http://127.0.0.1:8001, devbox=http://localhost:8000 "
            "(default: main). Links use the active CLI user for {user_id}."
        ),
    )
    links_p.add_argument(
        "--host",
        default=None,
        choices=["localhost", "127.0.0.1"],
        help="Local host name override for generated links",
    )
    links_p.add_argument(
        "--port",
        default=None,
        type=int,
        help="Local API port override for generated links",
    )
    links_p.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help="Full base URL override, e.g. http://127.0.0.1:8001",
    )
    links_p.set_defaults(func=cmd_links)

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
