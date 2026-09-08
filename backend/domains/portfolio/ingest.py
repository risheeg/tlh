"""Lot and aggregate-position upload rules."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.core import Account, User
from models.enums import AccountType
from models.portfolio import AggregatePosition, Lot
from schemas.portfolio import (
    AggregatePositionResponse,
    AggregatePositionUploadRequest,
    AggregatePositionUploadResponse,
    LotResponse,
    LotUploadRequest,
    LotUploadResponse,
)


def _get_user_or_404(user_id: UUID, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _get_account_or_404(account_id: UUID, user_id: UUID, db: Session) -> Account:
    account = db.get(Account, account_id)
    if not account or account.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found for this user",
        )
    return account


def upload_lots(db: Session, payload: LotUploadRequest) -> LotUploadResponse:
    user = _get_user_or_404(payload.user_id, db)

    created_lots: list[Lot] = []
    skipped = 0

    for lot_data in payload.lots:
        account = _get_account_or_404(lot_data.account_id, user.id, db)

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
                db.flush()
            created_lots.append(lot)
        except IntegrityError:
            skipped += 1

    db.commit()
    for lot in created_lots:
        db.refresh(lot)

    return LotUploadResponse(
        created=len(created_lots),
        skipped=skipped,
        lots=[LotResponse.model_validate(lot) for lot in created_lots],
    )


def upload_positions(
    db: Session, payload: AggregatePositionUploadRequest
) -> AggregatePositionUploadResponse:
    user = _get_user_or_404(payload.user_id, db)

    upserted_positions: list[AggregatePosition] = []

    for pos_data in payload.positions:
        _get_account_or_404(pos_data.account_id, user.id, db)

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
