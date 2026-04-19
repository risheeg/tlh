"""
Pydantic schemas for request / response validation.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from models.models import AccountType, AssetType, LotStatus


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


# ---------------------------------------------------------------------------
# Lot schemas
# ---------------------------------------------------------------------------

class LotCreate(BaseModel):
    """Fields required to create a single tax lot."""
    account_id: uuid.UUID
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., gt=0, decimal_places=8)
    original_purchase_price: Decimal = Field(..., gt=0, decimal_places=2)
    current_adjusted_basis: Decimal = Field(..., gt=0, decimal_places=2)
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
    asset_type: AssetType
    last_updated: datetime

    model_config = {"from_attributes": True}


class AggregatePositionUploadResponse(BaseModel):
    upserted: int
    positions: list[AggregatePositionResponse]


# ---------------------------------------------------------------------------
# Aggregated positions (lots + aggregate positions)
# ---------------------------------------------------------------------------

class AggregatedPositionResponse(BaseModel):
    ticker: str
    quantity: Decimal
    cost_basis: Decimal | None = None
    asset_type: AssetType = AssetType.Equity
