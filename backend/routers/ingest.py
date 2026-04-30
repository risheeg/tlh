"""
Router: /ingest — endpoints for uploading lots and aggregate positions.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.session import get_db
from models.models import Account, AccountType, AggregatePosition, Lot, User
from schemas.schemas import (
    AggregatePositionResponse,
    AggregatePositionUploadRequest,
    AggregatePositionUploadResponse,
    LotResponse,
    LotUploadRequest,
    LotUploadResponse,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_or_404(user_id, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _get_account_or_404(account_id, user_id, db: Session) -> Account:
    account = db.get(Account, account_id)
    if not account or account.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found for this user",
        )
    return account


# ---------------------------------------------------------------------------
# POST /ingest/lots
# ---------------------------------------------------------------------------

@router.post(
    "/lots",
    response_model=LotUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload tax lots",
    description=(
        "Batch-upload individual tax lots for a user. "
        "Lots must belong to a **taxable** account. "
        "Lots with a duplicate `external_ref_id` are silently skipped (idempotent)."
    ),
)
def upload_lots(payload: LotUploadRequest, db: Session = Depends(get_db)):
    user = _get_user_or_404(payload.user_id, db)

    created_lots: list[Lot] = []
    skipped = 0

    for lot_data in payload.lots:
        account = _get_account_or_404(lot_data.account_id, user.id, db)

        # Enforce: lots must only live in taxable accounts
        if account.type != AccountType.taxable:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Account {account.id} is of type '{account.type.value}'. "
                    "Tax lots can only be uploaded to taxable accounts."
                ),
            )

        lot = Lot(
            user_id=user.id,
            account_id=account.id,
            ticker=lot_data.ticker.upper(),
            quantity=lot_data.quantity,
            original_purchase_price=lot_data.original_purchase_price,
            current_adjusted_basis=lot_data.current_adjusted_basis,
            purchase_date=lot_data.purchase_date,
            status=lot_data.status,
            external_ref_id=lot_data.external_ref_id,
        )

        try:
            with db.begin_nested():
                db.add(lot)
                db.flush()  # surface unique constraint violations immediately
            created_lots.append(lot)
        except IntegrityError:
            # begin_nested automatically rolls back to the savepoint on error
            skipped += 1

    db.commit()
    for lot in created_lots:
        db.refresh(lot)

    return LotUploadResponse(
        created=len(created_lots),
        skipped=skipped,
        lots=[LotResponse.model_validate(lot) for lot in created_lots],
    )


# ---------------------------------------------------------------------------
# POST /ingest/positions
# ---------------------------------------------------------------------------

@router.post(
    "/positions",
    response_model=AggregatePositionUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload aggregate positions",
    description=(
        "Batch-upload (upsert) aggregate stock positions for a user. "
        "If a position for the same (user, account, ticker) already exists it is "
        "updated in place; otherwise a new record is created."
    ),
)
def upload_positions(
    payload: AggregatePositionUploadRequest, db: Session = Depends(get_db)
):
    user = _get_user_or_404(payload.user_id, db)

    upserted_positions: list[AggregatePosition] = []

    for pos_data in payload.positions:
        _get_account_or_404(pos_data.account_id, user.id, db)  # validate ownership

        # Attempt to find an existing position record
        existing = (
            db.query(AggregatePosition)
            .filter(
                AggregatePosition.user_id == user.id,
                AggregatePosition.account_id == pos_data.account_id,
                AggregatePosition.ticker == pos_data.ticker.upper(),
            )
            .first()
        )

        if existing:
            existing.quantity = pos_data.quantity
            existing.cost_basis = pos_data.cost_basis
            existing.asset_type = pos_data.asset_type
            existing.last_updated = datetime.now(timezone.utc)
            upserted_positions.append(existing)
        else:
            position = AggregatePosition(
                user_id=user.id,
                account_id=pos_data.account_id,
                ticker=pos_data.ticker.upper(),
                quantity=pos_data.quantity,
                cost_basis=pos_data.cost_basis,
                asset_type=pos_data.asset_type,
                last_updated=datetime.now(timezone.utc),
            )
            db.add(position)
            upserted_positions.append(position)

    db.commit()
    for pos in upserted_positions:
        db.refresh(pos)

    return AggregatePositionUploadResponse(
        upserted=len(upserted_positions),
        positions=[AggregatePositionResponse.model_validate(p) for p in upserted_positions],
    )
