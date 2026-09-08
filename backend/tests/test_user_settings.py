import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.session import Base
from models.core import Account, User
from models.enums import AccountType
from models.user_settings import UserSettings
from schemas.settings import (
    SpreadsheetColumnConfig,
    UserSettingsPut,
    UserSettingsUpdate,
    normalize_sheet_id,
)
from domains.portfolio.spreadsheet import _get_spreadsheet_config
from shared.user_settings import (
    get_or_create_user_settings,
    patch_user_settings,
    put_user_settings,
    settings_to_response,
)


class NormalizeSheetIdTest(unittest.TestCase):
    def test_url_and_raw_id(self):
        url = "https://docs.google.com/spreadsheets/d/abc123XYZ_-/edit#gid=0"
        self.assertEqual(normalize_sheet_id(url), "abc123XYZ_-")
        self.assertEqual(normalize_sheet_id("plainSheetId"), "plainSheetId")
        self.assertIsNone(normalize_sheet_id("  "))


class UserSettingsServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Account.__table__, UserSettings.__table__],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.other_user_id = uuid.uuid4()
        self.acc_a = uuid.uuid4()
        self.acc_b = uuid.uuid4()
        self.foreign_acc = uuid.uuid4()

        self.db.add(User(id=self.user_id, email="a@example.com"))
        self.db.add(User(id=self.other_user_id, email="b@example.com"))
        self.db.add(
            Account(
                id=self.acc_a,
                user_id=self.user_id,
                name="Brokerage A",
                type=AccountType.taxable,
            )
        )
        self.db.add(
            Account(
                id=self.acc_b,
                user_id=self.user_id,
                name="Roth IRA",
                type=AccountType.retirement,
            )
        )
        self.db.add(
            Account(
                id=self.foreign_acc,
                user_id=self.other_user_id,
                name="Someone Else",
                type=AccountType.taxable,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_put_rejects_foreign_account_ids(self):
        payload = UserSettingsPut(
            default_group_by="custom",
            spreadsheet_columns=[
                SpreadsheetColumnConfig(
                    header="Bad",
                    account_ids=[self.foreign_acc],
                )
            ],
        )
        with self.assertRaises(HTTPException) as ctx:
            put_user_settings(self.db, self.user_id, payload)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_put_and_redact_credentials(self):
        payload = UserSettingsPut(
            default_group_by="custom",
            spreadsheet_columns=[
                SpreadsheetColumnConfig(
                    header="Taxable",
                    account_ids=[self.acc_a],
                )
            ],
            portfolio_snapshot_sheet_url=(
                "https://docs.google.com/spreadsheets/d/sheetKey99/edit"
            ),
            google_sheets_credentials={
                "client_email": "bot@project.iam.gserviceaccount.com",
                "private_key": "SECRET",
                "type": "service_account",
            },
            tlh_notify_threshold=Decimal("2500"),
            tlh_excluded_categories=["Individual Stocks"],
        )
        row = put_user_settings(self.db, self.user_id, payload)
        resp = settings_to_response(row)
        self.assertEqual(resp.portfolio_snapshot_sheet_id, "sheetKey99")
        self.assertTrue(resp.has_google_sheets_credentials)
        self.assertEqual(
            resp.google_sheets_credentials_client_email,
            "bot@project.iam.gserviceaccount.com",
        )
        self.assertFalse(hasattr(resp, "google_sheets_credentials") and
                         getattr(resp, "google_sheets_credentials", None) == {"private_key": "SECRET"})
        dumped = resp.model_dump()
        self.assertNotIn("google_sheets_credentials", dumped)
        self.assertEqual(resp.tlh_notify_threshold, Decimal("2500"))

    def test_custom_grouping_uses_account_ids_not_names(self):
        put_user_settings(
            self.db,
            self.user_id,
            UserSettingsPut(
                default_group_by="custom",
                spreadsheet_columns=[
                    SpreadsheetColumnConfig(
                        header="Col A",
                        account_ids=[self.acc_a],
                    ),
                    SpreadsheetColumnConfig(
                        header="Col B",
                        account_ids=[self.acc_b],
                    ),
                ],
            ),
        )
        # Rename account — config must still resolve via id
        acc = self.db.get(Account, self.acc_a)
        acc.name = "Renamed Brokerage"
        self.db.commit()

        accounts = {
            str(a.id): a
            for a in self.db.query(Account).filter(Account.user_id == self.user_id)
        }
        with patch(
            "domains.portfolio.spreadsheet._get_account_market_values",
            return_value={
                str(self.acc_a): Decimal("100"),
                str(self.acc_b): Decimal("50"),
            },
        ):
            config = _get_spreadsheet_config(self.db, self.user_id, accounts, None)
        self.assertEqual(len(config.mapping), 2)
        self.assertEqual(config.mapping[0]["header"], "Col A")
        self.assertIn(str(self.acc_a), config.mapping[0]["account_ids"])
        self.assertEqual(config.mapping[0]["accounts"], ["Renamed Brokerage"])


class PortfolioSyncGatingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Account.__table__, UserSettings.__table__],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.db.add(User(id=self.user_id, email="sync@example.com"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_sync_requires_sheet_and_credentials(self):
        from routers.portfolio import sync_portfolio_snapshot

        get_or_create_user_settings(self.db, self.user_id)

        with self.assertRaises(HTTPException) as ctx:
            sync_portfolio_snapshot(self.user_id, None, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("sheet", ctx.exception.detail.lower())

        patch_user_settings(
            self.db,
            self.user_id,
            UserSettingsUpdate(portfolio_snapshot_sheet_id="onlySheet"),
        )
        with self.assertRaises(HTTPException) as ctx:
            sync_portfolio_snapshot(self.user_id, None, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("credentials", ctx.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
