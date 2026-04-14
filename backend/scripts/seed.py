"""
Seed script: creates a mock user + accounts directly in the DB.

This only needs to be run ONCE. After running, copy the printed IDs
into your scripts/data/*.json files as user_id / account_id.

Run from the backend/ directory:
    uv run python scripts/seed.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from db.session import engine  # noqa: E402
from models.models import Account, AccountType, User  # noqa: E402

MOCK_EMAIL = "alice@example.com"
TARGET_USER_ID = uuid.UUID("45a10eec-1398-483e-b7cd-be90fbd2c77c")


def ensure_account(
    *,
    db: Session,
    user_id: uuid.UUID,
    name: str,
    type_: AccountType,
    institution: str | None,
) -> Account:
    existing = (
        db.query(Account).filter(Account.user_id == user_id, Account.name == name).first()
    )
    if existing:
        if existing.type != type_ or existing.institution != institution:
            existing.type = type_
            existing.institution = institution
            db.flush()
        return existing

    account = Account(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        type=type_,
        institution=institution,
        created_at=datetime.now(timezone.utc),
    )
    db.add(account)
    db.flush()
    return account


def main():
    with Session(engine) as db:
        # ---- User ----
        user = db.query(User).filter(User.email == MOCK_EMAIL).first()
        if user:
            print(f"[seed] User already exists — reusing.")
        else:
            user = User(
                id=uuid.uuid4(),
                email=MOCK_EMAIL,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.flush()
            print(f"[seed] Created user.")

        # ---- Taxable account ----
        taxable = (
            db.query(Account)
            .filter(Account.user_id == user.id, Account.name == "Schwab Brokerage")
            .first()
        )
        if taxable:
            print(f"[seed] Taxable account already exists — reusing.")
        else:
            taxable = Account(
                id=uuid.uuid4(),
                user_id=user.id,
                name="Schwab Brokerage",
                type=AccountType.taxable,
                institution="Charles Schwab",
                created_at=datetime.now(timezone.utc),
            )
            db.add(taxable)
            db.flush()
            print(f"[seed] Created taxable account.")

        # ---- Retirement account ----
        retirement = (
            db.query(Account)
            .filter(Account.user_id == user.id, Account.name == "Vanguard IRA")
            .first()
        )
        if retirement:
            print(f"[seed] Retirement account already exists — reusing.")
        else:
            retirement = Account(
                id=uuid.uuid4(),
                user_id=user.id,
                name="Vanguard IRA",
                type=AccountType.retirement,
                institution="Vanguard",
                created_at=datetime.now(timezone.utc),
            )
            db.add(retirement)
            db.flush()
            print(f"[seed] Created retirement account.")

        db.commit()

        # Capture IDs as plain values BEFORE the session closes;
        # accessing ORM attributes after session exit raises DetachedInstanceError.
        user_id = str(user.id)
        taxable_id = str(taxable.id)
        retirement_id = str(retirement.id)

    # ---- Ensure accounts for specific user ----
    with Session(engine) as db:
        target_user = db.get(User, TARGET_USER_ID)
        if not target_user:
            raise SystemExit(
                f"[seed] Target user {TARGET_USER_ID} not found. "
                "Create the user first, then re-run this script."
            )

        desired_accounts: list[tuple[str, AccountType, str | None]] = [
            ("Robinhood Brokerage", AccountType.taxable, "Robinhood"),
            ("Fidelity Brokerage", AccountType.taxable, "Fidelity"),
            ("Shareworks", AccountType.taxable, "Shareworks"),
            ("Kraken", AccountType.taxable, "Kraken"),
            ("ROTH IRA @ Robinhood", AccountType.retirement, "Robinhood"),
            ("Roth IRA @ SoFi", AccountType.retirement, "SoFi"),
            ("ROTH IRA @ Etrade", AccountType.retirement, "E*TRADE"),
            ("ROTH 401k @ Fidelity", AccountType.retirement, "Fidelity"),
            ("Traditional 401k @ Fidelity", AccountType.retirement, "Fidelity"),
            ("HSA Fidelity (non taxable)", AccountType.retirement, "Fidelity"),
        ]

        ensured: list[Account] = []
        for name, type_, institution in desired_accounts:
            ensured.append(
                ensure_account(
                    db=db,
                    user_id=target_user.id,
                    name=name,
                    type_=type_,
                    institution=institution,
                )
            )
        db.commit()
        ensured_ids = {a.name: str(a.id) for a in ensured}

    print()
    print("=" * 60)
    print("Copy these IDs into your scripts/data/*.json files:")
    print("=" * 60)
    print(f"  user_id (alice)        : {user_id}")
    print(f"  account_id (taxable)   : {taxable_id}")
    print(f"  account_id (retirement): {retirement_id}")
    print()
    print("=" * 60)
    print(f"Ensured accounts for user: {TARGET_USER_ID}")
    print("=" * 60)
    for name, account_id in ensured_ids.items():
        print(f"  {name:<28} : {account_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
