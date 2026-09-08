"""Account registration and lot transfers (ACATS)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from models.core import Account, User
from models.enums import AccountType, LotStatus, TransactionType
from models.portfolio import Lot, LotHistory, Transaction


class AccountNotFoundError(ValueError):
    """Raised when a referenced account or user is missing."""


class InvalidAccountTypeError(ValueError):
    """Raised when an operation requires taxable (lot-based) accounts."""


def register_account(
    db: Session,
    *,
    user_id: UUID,
    name: str,
    type: AccountType,
    institution: str | None = None,
) -> Account:
    """Create an account idempotently on (user_id, name)."""
    user = db.get(User, user_id)
    if not user:
        raise AccountNotFoundError("User not found")

    existing = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.name == name)
        .first()
    )
    if existing:
        return existing

    account = Account(
        user_id=user_id,
        name=name,
        type=type,
        institution=institution,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def transfer_lots(
    db: Session,
    *,
    user_id: UUID,
    origin_account_id: UUID,
    destination_account_id: UUID,
) -> dict:
    """
    Transfer all active lots from origin to destination via ACATS.

    Records a Transaction + LotHistory row per transferred lot.
    """
    user = db.get(User, user_id)
    if not user:
        raise AccountNotFoundError("User not found")

    origin_acc = db.get(Account, origin_account_id)
    dest_acc = db.get(Account, destination_account_id)

    if not origin_acc or origin_acc.user_id != user_id:
        raise AccountNotFoundError("Origin account not found")
    if not dest_acc or dest_acc.user_id != user_id:
        raise AccountNotFoundError("Destination account not found")

    if origin_acc.type != AccountType.taxable or dest_acc.type != AccountType.taxable:
        raise InvalidAccountTypeError("Both accounts must be lot-based (taxable).")

    lots = (
        db.query(Lot)
        .filter(
            Lot.account_id == origin_account_id,
            Lot.status == LotStatus.active,
        )
        .all()
    )

    if not lots:
        return {
            "transferred_count": 0,
            "origin_account_id": origin_account_id,
            "destination_account_id": destination_account_id,
        }

    transferred_count = 0
    now = datetime.now(timezone.utc)
    transaction_date = now.date()

    for lot in lots:
        lot.account_id = destination_account_id

        transaction = Transaction(
            user_id=user_id,
            type=TransactionType.acats,
            ticker=lot.ticker,
            quantity=lot.quantity,
            price=None,
            transaction_date=transaction_date,
            origin_account_id=origin_account_id,
            destination_account_id=destination_account_id,
            created_at=now,
        )
        db.add(transaction)
        db.flush()

        lot_history = LotHistory(
            lot_id=lot.id,
            transaction_id=transaction.id,
            quantity_affected=lot.quantity,
            created_at=now,
        )
        db.add(lot_history)
        transferred_count += 1

    db.commit()

    return {
        "transferred_count": transferred_count,
        "origin_account_id": origin_account_id,
        "destination_account_id": destination_account_id,
    }
