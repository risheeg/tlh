from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.models import (
    AggregatePosition,
    AssetType,
    Lot,
    LotStatus,
    StockSplit,
)
from schemas.schemas import (
    StockSplitApplyResponse,
    StockSplitCreate,
    StockSplitImpact,
    StockSplitPreviewResponse,
    StockSplitResponse,
)


class StockSplitRatioConflictError(ValueError):
    """Raised when a split already exists for a ticker/date with a different ratio."""


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _normalize_payload(payload: StockSplitCreate) -> StockSplitCreate:
    return StockSplitCreate(
        ticker=payload.ticker.upper(),
        effective_date=payload.effective_date,
        split_numerator=payload.split_numerator,
        split_denominator=payload.split_denominator,
    )


def _ratio(payload: StockSplitCreate) -> Decimal:
    return Decimal(payload.split_numerator) / Decimal(payload.split_denominator)


def _get_existing_split(db: Session, payload: StockSplitCreate) -> StockSplit | None:
    return (
        db.query(StockSplit)
        .filter(
            StockSplit.ticker == payload.ticker,
            StockSplit.effective_date == payload.effective_date,
        )
        .first()
    )


def _validate_existing_split(existing: StockSplit | None, payload: StockSplitCreate) -> None:
    if not existing:
        return

    if (
        existing.split_numerator != payload.split_numerator
        or existing.split_denominator != payload.split_denominator
    ):
        raise StockSplitRatioConflictError(
            "A stock split already exists for this ticker/effective date with a different ratio."
        )


def _affected_lots(db: Session, payload: StockSplitCreate) -> list[Lot]:
    return (
        db.query(Lot)
        .filter(
            Lot.ticker == payload.ticker,
            Lot.status == LotStatus.active,
            Lot.purchase_date < payload.effective_date,
        )
        .all()
    )


def _affected_aggregate_positions(
    db: Session, payload: StockSplitCreate
) -> list[AggregatePosition]:
    return (
        db.query(AggregatePosition)
        .filter(
            AggregatePosition.ticker == payload.ticker,
            AggregatePosition.asset_type == AssetType.Equity,
        )
        .all()
    )


def _build_impact(
    *,
    lots: list[Lot],
    aggregate_positions: list[AggregatePosition],
    ratio: Decimal,
) -> StockSplitImpact:
    lot_quantity_before = sum((_decimal(lot.quantity) for lot in lots), Decimal("0"))
    lot_quantity_after = lot_quantity_before * ratio
    lot_cost_basis_before = sum(
        (
            _decimal(lot.quantity) * _decimal(lot.original_purchase_price)
            for lot in lots
        ),
        Decimal("0"),
    )
    lot_cost_basis_after = sum(
        (
            (_decimal(lot.quantity) * ratio)
            * (_decimal(lot.original_purchase_price) / ratio)
            for lot in lots
        ),
        Decimal("0"),
    )

    aggregate_quantity_before = sum(
        (_decimal(position.quantity) for position in aggregate_positions),
        Decimal("0"),
    )
    aggregate_quantity_after = aggregate_quantity_before * ratio
    aggregate_cost_basis_before = sum(
        (_decimal(position.cost_basis) for position in aggregate_positions),
        Decimal("0"),
    )

    return StockSplitImpact(
        affected_lots=len(lots),
        affected_aggregate_positions=len(aggregate_positions),
        lot_quantity_before=lot_quantity_before,
        lot_quantity_after=lot_quantity_after,
        lot_cost_basis_before=lot_cost_basis_before,
        lot_cost_basis_after=lot_cost_basis_after,
        aggregate_quantity_before=aggregate_quantity_before,
        aggregate_quantity_after=aggregate_quantity_after,
        aggregate_cost_basis_before=aggregate_cost_basis_before,
        aggregate_cost_basis_after=aggregate_cost_basis_before,
    )


def preview_stock_split(
    db: Session, payload: StockSplitCreate
) -> StockSplitPreviewResponse:
    payload = _normalize_payload(payload)
    existing = _get_existing_split(db, payload)
    _validate_existing_split(existing, payload)

    lots = _affected_lots(db, payload)
    aggregate_positions = _affected_aggregate_positions(db, payload)
    ratio = _ratio(payload)
    already_applied = bool(existing and existing.applied_at)

    return StockSplitPreviewResponse(
        ticker=payload.ticker,
        effective_date=payload.effective_date,
        split_numerator=payload.split_numerator,
        split_denominator=payload.split_denominator,
        ratio=ratio,
        already_applied=already_applied,
        impact=_build_impact(
            lots=lots,
            aggregate_positions=aggregate_positions,
            ratio=Decimal("1") if already_applied else ratio,
        ),
    )


def apply_stock_split(db: Session, payload: StockSplitCreate) -> StockSplitApplyResponse:
    payload = _normalize_payload(payload)
    existing = _get_existing_split(db, payload)
    _validate_existing_split(existing, payload)

    lots = _affected_lots(db, payload)
    aggregate_positions = _affected_aggregate_positions(db, payload)
    ratio = _ratio(payload)
    already_applied = bool(existing and existing.applied_at)
    preview = StockSplitPreviewResponse(
        ticker=payload.ticker,
        effective_date=payload.effective_date,
        split_numerator=payload.split_numerator,
        split_denominator=payload.split_denominator,
        ratio=ratio,
        already_applied=already_applied,
        impact=_build_impact(
            lots=lots,
            aggregate_positions=aggregate_positions,
            ratio=Decimal("1") if already_applied else ratio,
        ),
    )

    if existing and existing.applied_at:
        return StockSplitApplyResponse(
            **preview.model_dump(),
            stock_split=StockSplitResponse.model_validate(existing),
            applied=False,
        )

    stock_split = existing or StockSplit(
        ticker=payload.ticker,
        effective_date=payload.effective_date,
        split_numerator=payload.split_numerator,
        split_denominator=payload.split_denominator,
    )
    if not existing:
        db.add(stock_split)

    try:
        for lot in lots:
            lot.quantity = _decimal(lot.quantity) * ratio
            lot.original_purchase_price = _decimal(lot.original_purchase_price) / ratio
            lot.current_adjusted_basis = _decimal(lot.current_adjusted_basis) / ratio

        for position in aggregate_positions:
            position.quantity = _decimal(position.quantity) * ratio
            position.last_updated = datetime.now(timezone.utc)

        stock_split.applied_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(stock_split)

    return StockSplitApplyResponse(
        **preview.model_dump(),
        stock_split=StockSplitResponse.model_validate(stock_split),
        applied=True,
    )
