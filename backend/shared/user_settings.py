"""Load and mutate per-user settings."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import Account, User, UserSettings
from schemas.settings import (
    SpreadsheetColumnConfig,
    UserSettingsPut,
    UserSettingsResponse,
    UserSettingsUpdate,
)

DEFAULT_TLH_EXCLUSIONS = ["Indvl Company", "Individual Stocks"]
DEFAULT_GROUP_BY = "type"
DEFAULT_TLH_THRESHOLD = Decimal("1000")


def _columns_as_dicts(columns: list[SpreadsheetColumnConfig] | list[dict]) -> list[dict]:
    result = []
    for col in columns:
        if isinstance(col, SpreadsheetColumnConfig):
            result.append(
                {
                    "header": col.header,
                    "account_ids": [str(aid) for aid in col.account_ids],
                }
            )
        else:
            result.append(
                {
                    "header": col["header"],
                    "account_ids": [str(aid) for aid in col.get("account_ids", [])],
                }
            )
    return result


def _validate_account_ids(db: Session, user_id: uuid.UUID, columns: list) -> None:
    if not columns:
        return
    account_ids: set[uuid.UUID] = set()
    for col in columns:
        ids = (
            col.account_ids
            if isinstance(col, SpreadsheetColumnConfig)
            else [uuid.UUID(str(a)) for a in col.get("account_ids", [])]
        )
        account_ids.update(ids)

    if not account_ids:
        return

    owned = {
        row.id
        for row in db.query(Account.id)
        .filter(Account.user_id == user_id, Account.id.in_(account_ids))
        .all()
    }
    missing = account_ids - owned
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Account ids not owned by user: {sorted(str(m) for m in missing)}",
        )


def get_or_create_user_settings(db: Session, user_id: uuid.UUID) -> UserSettings:
    settings = db.get(UserSettings, user_id)
    if settings:
        return settings

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    settings = UserSettings(
        user_id=user_id,
        default_group_by=DEFAULT_GROUP_BY,
        spreadsheet_columns=[],
        category_order=[],
        ticker_order=[],
        tlh_notify_threshold=DEFAULT_TLH_THRESHOLD,
        tlh_excluded_categories=list(DEFAULT_TLH_EXCLUSIONS),
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def settings_to_response(settings: UserSettings) -> UserSettingsResponse:
    creds = settings.google_sheets_credentials or None
    client_email = None
    if isinstance(creds, dict):
        client_email = creds.get("client_email")

    columns = []
    for col in settings.spreadsheet_columns or []:
        columns.append(
            SpreadsheetColumnConfig(
                header=col["header"],
                account_ids=[uuid.UUID(str(a)) for a in col.get("account_ids", [])],
            )
        )

    return UserSettingsResponse(
        user_id=settings.user_id,
        default_group_by=settings.default_group_by,
        spreadsheet_columns=columns,
        category_order=list(settings.category_order or []),
        ticker_order=list(settings.ticker_order or []),
        portfolio_snapshot_sheet_id=settings.portfolio_snapshot_sheet_id,
        tlh_notify_threshold=Decimal(str(settings.tlh_notify_threshold)),
        tlh_excluded_categories=list(settings.tlh_excluded_categories or []),
        has_google_sheets_credentials=bool(creds),
        google_sheets_credentials_client_email=client_email,
        updated_at=settings.updated_at,
    )


def put_user_settings(
    db: Session, user_id: uuid.UUID, payload: UserSettingsPut
) -> UserSettings:
    _validate_account_ids(db, user_id, payload.spreadsheet_columns)
    settings = get_or_create_user_settings(db, user_id)

    settings.default_group_by = payload.default_group_by
    settings.spreadsheet_columns = _columns_as_dicts(payload.spreadsheet_columns)
    settings.category_order = list(payload.category_order)
    settings.ticker_order = list(payload.ticker_order)
    settings.portfolio_snapshot_sheet_id = payload.portfolio_snapshot_sheet_id
    settings.tlh_notify_threshold = payload.tlh_notify_threshold
    settings.tlh_excluded_categories = list(payload.tlh_excluded_categories)
    if payload.google_sheets_credentials is not None:
        settings.google_sheets_credentials = payload.google_sheets_credentials
    settings.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(settings)
    return settings


def patch_user_settings(
    db: Session, user_id: uuid.UUID, payload: UserSettingsUpdate
) -> UserSettings:
    if payload.spreadsheet_columns is not None:
        _validate_account_ids(db, user_id, payload.spreadsheet_columns)

    settings = get_or_create_user_settings(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    data.pop("portfolio_snapshot_sheet_url", None)
    clear_creds = data.pop("clear_google_sheets_credentials", False)

    if "spreadsheet_columns" in data and data["spreadsheet_columns"] is not None:
        settings.spreadsheet_columns = _columns_as_dicts(payload.spreadsheet_columns or [])
        data.pop("spreadsheet_columns")

    for key, value in data.items():
        if key == "google_sheets_credentials" and value is None:
            continue
        setattr(settings, key, value)

    if clear_creds:
        settings.google_sheets_credentials = None

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings
