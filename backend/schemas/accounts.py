"""Account and transfer API schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from models.enums import AccountType


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
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class TransferLotsRequest(BaseModel):
    user_id: uuid.UUID
    origin_account_id: uuid.UUID
    destination_account_id: uuid.UUID


class TransferLotsResponse(BaseModel):
    transferred_count: int
    origin_account_id: uuid.UUID
    destination_account_id: uuid.UUID
