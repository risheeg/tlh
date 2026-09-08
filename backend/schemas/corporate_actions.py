"""Corporate action API schemas."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class StockSplitCreate(BaseModel):
    """Fields required to preview or apply a stock split."""

    ticker: str = Field(..., min_length=1, max_length=10)
    effective_date: date
    split_numerator: int = Field(..., gt=0)
    split_denominator: int = Field(..., gt=0)


class StockSplitResponse(BaseModel):
    id: uuid.UUID
    ticker: str
    effective_date: date
    split_numerator: int
    split_denominator: int
    created_at: datetime
    applied_at: datetime | None

    model_config = {"from_attributes": True}


class StockSplitImpact(BaseModel):
    affected_lots: int
    affected_aggregate_positions: int
    lot_quantity_before: Decimal
    lot_quantity_after: Decimal
    lot_cost_basis_before: Decimal
    lot_cost_basis_after: Decimal
    aggregate_quantity_before: Decimal
    aggregate_quantity_after: Decimal
    aggregate_cost_basis_before: Decimal
    aggregate_cost_basis_after: Decimal


class StockSplitPreviewResponse(BaseModel):
    ticker: str
    effective_date: date
    split_numerator: int
    split_denominator: int
    ratio: Decimal
    already_applied: bool
    impact: StockSplitImpact


class StockSplitApplyResponse(StockSplitPreviewResponse):
    stock_split: StockSplitResponse
    applied: bool
