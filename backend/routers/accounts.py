"""
Router: /accounts — endpoints for creating user accounts.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.models import Account, User, Lot, Transaction, LotHistory, AccountType, TransactionType, LotStatus
from schemas.schemas import AccountRegisterRequest, AccountResponse, TransferLotsRequest, TransferLotsResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an account",
    description=(
        "Create an account for a user. If an account with the same (user_id, name) "
        "already exists, it is returned (idempotent)."
    ),
)
def register_account(payload: AccountRegisterRequest, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = (
        db.query(Account)
        .filter(Account.user_id == payload.user_id, Account.name == payload.name)
        .first()
    )
    if existing:
        return existing

    account = Account(
        user_id=payload.user_id,
        name=payload.name,
        type=payload.type,
        institution=payload.institution,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.post(
    "/transfer-lots",
    response_model=TransferLotsResponse,
    status_code=status.HTTP_200_OK,
    summary="Transfer all lots via ACATS",
    description="Transfers all active lots from the origin account to the destination account via ACATS.",
)
def transfer_lots(payload: TransferLotsRequest, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    origin_acc = db.get(Account, payload.origin_account_id)
    dest_acc = db.get(Account, payload.destination_account_id)

    if not origin_acc or origin_acc.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Origin account not found")
    if not dest_acc or dest_acc.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination account not found")

    if origin_acc.type != AccountType.taxable or dest_acc.type != AccountType.taxable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both accounts must be lot-based (taxable)."
        )

    # Fetch all active lots in the origin account
    lots = (
        db.query(Lot)
        .filter(
            Lot.account_id == payload.origin_account_id,
            Lot.status == LotStatus.active,
        )
        .all()
    )

    if not lots:
        return TransferLotsResponse(
            transferred_count=0,
            origin_account_id=payload.origin_account_id,
            destination_account_id=payload.destination_account_id,
        )

    transferred_count = 0
    now = datetime.now(timezone.utc)
    transaction_date = now.date()

    for lot in lots:
        # Transfer the lot
        lot.account_id = payload.destination_account_id

        # Create the transaction
        transaction = Transaction(
            user_id=payload.user_id,
            type=TransactionType.acats,
            ticker=lot.ticker,
            quantity=lot.quantity,
            price=None,
            transaction_date=transaction_date,
            origin_account_id=payload.origin_account_id,
            destination_account_id=payload.destination_account_id,
            created_at=now,
        )
        db.add(transaction)
        db.flush()  # to get transaction.id

        # Create lot history
        lot_history = LotHistory(
            lot_id=lot.id,
            transaction_id=transaction.id,
            quantity_affected=lot.quantity,
            created_at=now,
        )
        db.add(lot_history)
        transferred_count += 1

    db.commit()

    return TransferLotsResponse(
        transferred_count=transferred_count,
        origin_account_id=payload.origin_account_id,
        destination_account_id=payload.destination_account_id,
    )

