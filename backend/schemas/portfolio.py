import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field

from models.enums import AssetType, LotStatus


class EnrichedHolding(BaseModel):
    holding_id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    ticker: str
    quantity: Decimal
    original_purchase_price: Decimal | None = None
    cost_basis: Decimal | None = None
    holding_type: str  # 'lot' or 'aggregate'
    asset_type: str  # 'Equity' or 'Cash'
    category: str | None = None
    expense_ratio: Decimal | None = None
    current_price: Decimal

    market_value: Decimal
    price_last_updated: datetime | None = None

    model_config = {"from_attributes": True}


class PortfolioSnapshot(BaseModel):
    holdings: list[EnrichedHolding]
    total_net_worth: Decimal
    last_updated: datetime | None


class NetWorthSnapshotResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    snapshot_date: date
    total_net_worth: Decimal
    breakdown: dict
    comments: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NetWorthSnapshotCommentUpdate(BaseModel):
    comments: str | None = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Lot / position upload
# ---------------------------------------------------------------------------


class LotCreate(BaseModel):
    """Fields required to create a single tax lot."""

    account_id: uuid.UUID
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., gt=0, decimal_places=8)
    original_purchase_price: Decimal = Field(..., gt=0, decimal_places=8)
    current_adjusted_basis: Decimal = Field(..., gt=0, decimal_places=8)
    purchase_date: date
    status: LotStatus = LotStatus.active
    external_ref_id: str | None = None


class LotUploadRequest(BaseModel):
    """Batch upload payload for tax lots."""

    user_id: uuid.UUID
    lots: list[LotCreate] = Field(..., min_length=1)


class LotResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    ticker: str
    quantity: Decimal
    original_purchase_price: Decimal
    current_adjusted_basis: Decimal
    purchase_date: date
    status: LotStatus
    external_ref_id: str | None

    model_config = {"from_attributes": True}


class LotUploadResponse(BaseModel):
    created: int
    skipped: int
    lots: list[LotResponse]


class AggregatePositionCreate(BaseModel):
    """Fields required to create or update a single aggregate position."""

    account_id: uuid.UUID
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., decimal_places=8)
    cost_basis: Decimal | None = Field(default=None, decimal_places=2)
    asset_type: AssetType = AssetType.Equity


class AggregatePositionUploadRequest(BaseModel):
    """Batch upload payload for aggregate positions."""

    user_id: uuid.UUID
    positions: list[AggregatePositionCreate] = Field(..., min_length=1)


class AggregatePositionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    ticker: str
    quantity: Decimal
    cost_basis: Decimal | None
    last_updated: datetime

    model_config = {"from_attributes": True}


class AggregatePositionUploadResponse(BaseModel):
    upserted: int
    positions: list[AggregatePositionResponse]


class AggregatedPositionResponse(BaseModel):
    ticker: str
    quantity: Decimal
    cost_basis: Decimal | None = None
    asset_type: AssetType = AssetType.Equity
