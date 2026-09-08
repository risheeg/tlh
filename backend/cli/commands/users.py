"""Subcommand: users (create a user directly in the DB)."""

from __future__ import annotations

import argparse

from cli.common import BACKEND_ROOT, CONFIG_PATH, _get_db_session, _load_config, _save_config


def cmd_users_create(args: argparse.Namespace) -> None:
    """Create a new user in the database."""
    import uuid as _uuid
    from datetime import datetime, timezone

    import sys as _sys
    _sys.path.insert(0, str(BACKEND_ROOT))
    from models.core import User  # noqa: E402

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
