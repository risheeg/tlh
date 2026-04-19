import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel
from models.models import AssetType

class EnrichedHolding(BaseModel):
    holding_id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    ticker: str
    quantity: Decimal
    purchase_date: date | None = None
    original_purchase_price: Decimal | None = None
    cost_basis: Decimal | None = None
    external_ref_id: str | None = None
    last_updated: datetime | None = None
    holding_type: str  # 'lot' or 'aggregate'
    asset_type: str  # 'Equity' or 'Cash'
    current_price: Decimal
    market_value: Decimal
    price_last_updated: datetime | None = None

    model_config = {"from_attributes": True}

class PortfolioSnapshot(BaseModel):
    holdings: list[EnrichedHolding]
    total_net_worth: Decimal
    last_updated: datetime | None
