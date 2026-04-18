"""
Pydantic schemas for portfolio and net worth.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from schemas.schemas import LotResponse, AggregatePositionResponse

class EnrichedLot(BaseModel):
    lot: LotResponse
    current_price: Decimal | None
    market_value: Decimal | None

class EnrichedAggregatePosition(BaseModel):
    position: AggregatePositionResponse
    current_price: Decimal | None
    market_value: Decimal | None

class PortfolioSnapshot(BaseModel):
    lots: list[EnrichedLot]
    aggregate_positions: list[EnrichedAggregatePosition]
    total_net_worth: Decimal
    last_updated: datetime | None
