"""
Pydantic schemas for request / response validation.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from models.models import AccountType, AssetType, LotStatus, TransactionType


# ---------------------------------------------------------------------------
# Account schemas
# ---------------------------------------------------------------------------

class AccountRegisterRequest(BaseModel):
    user_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    type: AccountType
    institution: str | None = Field(default=None, max_length=200)


class AccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: AccountType
    institution: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransferLotsRequest(BaseModel):
    user_id: uuid.UUID
    origin_account_id: uuid.UUID
    destination_account_id: uuid.UUID


class TransferLotsResponse(BaseModel):
    transferred_count: int
    origin_account_id: uuid.UUID
    destination_account_id: uuid.UUID


# ---------------------------------------------------------------------------
# Lot schemas
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
    skipped: int  # lots skipped due to duplicate external_ref_id
    lots: list[LotResponse]


# ---------------------------------------------------------------------------
# AggregatePosition schemas
# ---------------------------------------------------------------------------

class AggregatePositionCreate(BaseModel):
    """Fields required to create or update a single aggregate position."""
    account_id: uuid.UUID
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., decimal_places=8)
    cost_basis: Decimal | None = Field(default=None, decimal_places=2)


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


class CashHoldingCreate(BaseModel):
    """Fields required to create or update a cash balance."""
    account_id: uuid.UUID
    amount: Decimal = Field(..., decimal_places=2)


class CashHoldingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    last_updated: datetime

    model_config = {"from_attributes": True}


class AggregatePositionUploadResponse(BaseModel):
    upserted: int
    positions: list[AggregatePositionResponse]


# ---------------------------------------------------------------------------
# Stock split schemas
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Transaction & LotHistory schemas
# ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    user_id: uuid.UUID
    type: TransactionType
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., decimal_places=8)
    price: Decimal | None = Field(default=None, decimal_places=8)
    transaction_date: date
    note: str | None = None
    origin_account_id: uuid.UUID | None = None
    destination_account_id: uuid.UUID | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: TransactionType
    ticker: str
    quantity: Decimal
    price: Decimal | None
    transaction_date: date
    note: str | None
    origin_account_id: uuid.UUID | None
    destination_account_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LotHistoryCreate(BaseModel):
    lot_id: uuid.UUID
    transaction_id: uuid.UUID
    quantity_affected: Decimal = Field(..., decimal_places=8)


class LotHistoryResponse(BaseModel):
    id: uuid.UUID
    lot_id: uuid.UUID
    transaction_id: uuid.UUID
    quantity_affected: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Aggregated positions (lots + aggregate positions)
# ---------------------------------------------------------------------------

class AggregatedPositionResponse(BaseModel):
    ticker: str
    quantity: Decimal
    cost_basis: Decimal | None = None
    asset_type: AssetType = AssetType.Equity
