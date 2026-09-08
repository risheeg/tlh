"""Subcommand: auth."""

from __future__ import annotations

import argparse
import sys
import uuid

from cli.common import CONFIG_PATH, _load_config, _save_config


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
