import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field
from models.models import AssetType

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
