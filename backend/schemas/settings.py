"""Pydantic schemas for per-user settings."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


GroupByMode = Literal["custom", "type", "name"]

_SHEET_URL_RE = re.compile(
    r"/spreadsheets/d/([a-zA-Z0-9-_]+)",
)


def normalize_sheet_id(value: str | None) -> str | None:
    """Accept a raw sheet id or a full Google Sheets URL; return the sheet key."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    match = _SHEET_URL_RE.search(stripped)
    if match:
        return match.group(1)
    return stripped


class SpreadsheetColumnConfig(BaseModel):
    header: str = Field(..., min_length=1, max_length=200)
    account_ids: list[uuid.UUID] = Field(default_factory=list)


class UserSettingsBase(BaseModel):
    default_group_by: GroupByMode = "type"
    spreadsheet_columns: list[SpreadsheetColumnConfig] = Field(default_factory=list)
    category_order: list[str] = Field(default_factory=list)
    ticker_order: list[str] = Field(default_factory=list)
    portfolio_snapshot_sheet_id: str | None = None
    tlh_notify_threshold: Decimal = Field(default=Decimal("1000"), ge=0)
    tlh_excluded_categories: list[str] = Field(
        default_factory=lambda: ["Indvl Company", "Individual Stocks"]
    )


class UserSettingsUpdate(BaseModel):
    """Partial update. Omitted fields are left unchanged."""

    default_group_by: GroupByMode | None = None
    spreadsheet_columns: list[SpreadsheetColumnConfig] | None = None
    category_order: list[str] | None = None
    ticker_order: list[str] | None = None
    portfolio_snapshot_sheet_id: str | None = None
    portfolio_snapshot_sheet_url: str | None = None
    google_sheets_credentials: dict[str, Any] | None = None
    tlh_notify_threshold: Decimal | None = Field(default=None, ge=0)
    tlh_excluded_categories: list[str] | None = None
    clear_google_sheets_credentials: bool = False

    @model_validator(mode="after")
    def normalize_sheet_ref(self) -> UserSettingsUpdate:
        url = self.portfolio_snapshot_sheet_url
        sheet_id = self.portfolio_snapshot_sheet_id
        if url is not None:
            self.portfolio_snapshot_sheet_id = normalize_sheet_id(url)
        elif sheet_id is not None:
            self.portfolio_snapshot_sheet_id = normalize_sheet_id(sheet_id)
        return self


class UserSettingsPut(UserSettingsBase):
    """Full replace of user settings."""

    portfolio_snapshot_sheet_url: str | None = None
    google_sheets_credentials: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_sheet_ref(self) -> UserSettingsPut:
        if self.portfolio_snapshot_sheet_url is not None:
            self.portfolio_snapshot_sheet_id = normalize_sheet_id(
                self.portfolio_snapshot_sheet_url
            )
        elif self.portfolio_snapshot_sheet_id is not None:
            self.portfolio_snapshot_sheet_id = normalize_sheet_id(
                self.portfolio_snapshot_sheet_id
            )
        return self


class UserSettingsResponse(UserSettingsBase):
    user_id: uuid.UUID
    has_google_sheets_credentials: bool = False
    google_sheets_credentials_client_email: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}
