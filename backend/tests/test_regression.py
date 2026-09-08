"""Regression coverage for portfolio grouping, accounts, and TLH settings wiring."""
import unittest
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.session import Base
from models.core import Account, User
from models.enums import AccountType
from models.user_settings import UserSettings
from schemas.settings import SpreadsheetColumnConfig, UserSettingsPut
from domains.portfolio.spreadsheet import _get_spreadsheet_config
from shared.user_settings import (
    DEFAULT_TLH_EXCLUSIONS,
    DEFAULT_TLH_THRESHOLD,
    get_or_create_user_settings,
    put_user_settings,
)


class SpreadsheetGroupingRegressionTest(unittest.TestCase):
    """Ensure type/name/custom grouping still works after settings migration."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Account.__table__, UserSettings.__table__],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.taxable_id = uuid.uuid4()
        self.retirement_id = uuid.uuid4()
        self.savings_id = uuid.uuid4()

        self.db.add(User(id=self.user_id, email="regress@example.com"))
        self.db.add(
            Account(
                id=self.taxable_id,
                user_id=self.user_id,
                name="Taxable Brokerage",
                type=AccountType.taxable,
            )
        )
        self.db.add(
            Account(
                id=self.retirement_id,
                user_id=self.user_id,
                name="401k",
                type=AccountType.retirement,
            )
        )
        self.db.add(
            Account(
                id=self.savings_id,
                user_id=self.user_id,
                name="High Yield Savings",
                type=AccountType.savings,
            )
        )
        self.db.commit()
        self.accounts = {
            str(a.id): a
            for a in self.db.query(Account).filter(Account.user_id == self.user_id)
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _market_values(self):
        return {
            str(self.taxable_id): Decimal("100"),
            str(self.retirement_id): Decimal("50"),
            str(self.savings_id): Decimal("0"),
        }

    def test_default_without_settings_uses_type_grouping(self):
        with patch(
            "domains.portfolio.spreadsheet._get_account_market_values",
            return_value=self._market_values(),
        ):
            config = _get_spreadsheet_config(self.db, self.user_id, self.accounts, None)
        headers = [c["header"] for c in config.mapping]
        self.assertEqual(headers, ["Brokerage / Taxable", "Retirement"])
        self.assertEqual(len(config.cash_accounts), 1)
        self.assertEqual(config.cash_accounts[0].id, self.savings_id)
        self.assertEqual(config.unmapped_accounts, [])

    def test_explicit_name_grouping(self):
        with patch(
            "domains.portfolio.spreadsheet._get_account_market_values",
            return_value=self._market_values(),
        ):
            config = _get_spreadsheet_config(
                self.db, self.user_id, self.accounts, "name"
            )
        headers = [c["header"] for c in config.mapping]
        self.assertEqual(headers, ["Taxable Brokerage", "401k"])

    def test_custom_empty_columns_falls_back_to_type(self):
        put_user_settings(
            self.db,
            self.user_id,
            UserSettingsPut(default_group_by="custom", spreadsheet_columns=[]),
        )
        with patch(
            "domains.portfolio.spreadsheet._get_account_market_values",
            return_value=self._market_values(),
        ):
            config = _get_spreadsheet_config(self.db, self.user_id, self.accounts, None)
        headers = [c["header"] for c in config.mapping]
        self.assertEqual(headers, ["Brokerage / Taxable", "Retirement"])

    def test_custom_columns_and_orders_from_settings(self):
        put_user_settings(
            self.db,
            self.user_id,
            UserSettingsPut(
                default_group_by="custom",
                spreadsheet_columns=[
                    SpreadsheetColumnConfig(
                        header="All Investable",
                        account_ids=[self.taxable_id, self.retirement_id],
                    )
                ],
                category_order=["US Total Market", "International Broad"],
                ticker_order=["VTI", "VXUS"],
            ),
        )
        with patch(
            "domains.portfolio.spreadsheet._get_account_market_values",
            return_value=self._market_values(),
        ):
            config = _get_spreadsheet_config(self.db, self.user_id, self.accounts, None)
        self.assertEqual(len(config.mapping), 1)
        self.assertEqual(config.mapping[0]["header"], "All Investable")
        self.assertEqual(
            set(config.mapping[0]["account_ids"]),
            {str(self.taxable_id), str(self.retirement_id)},
        )
        self.assertEqual(config.category_order, ["US Total Market", "International Broad"])
        self.assertEqual(config.ticker_order, ["VTI", "VXUS"])
        self.assertEqual(config.cash_accounts[0].id, self.savings_id)


class AccountRegisterRegressionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Account.__table__],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.db.add(User(id=self.user_id, email="acct@example.com"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_register_account_idempotent(self):
        from routers.accounts import register_account
        from schemas.accounts import AccountRegisterRequest

        payload = AccountRegisterRequest(
            user_id=self.user_id,
            name="Fidelity Brokerage",
            type=AccountType.taxable,
            institution="Fidelity",
        )
        first = register_account(payload, self.db)
        second = register_account(payload, self.db)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.db.query(Account).filter(Account.user_id == self.user_id).count(),
            1,
        )


class TlhSettingsWiringRegressionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, UserSettings.__table__],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.db.add(User(id=self.user_id, email="tlh@example.com"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_defaults_match_legacy_behavior(self):
        settings = get_or_create_user_settings(self.db, self.user_id)
        self.assertEqual(settings.default_group_by, "type")
        self.assertEqual(
            Decimal(str(settings.tlh_notify_threshold)), DEFAULT_TLH_THRESHOLD
        )
        self.assertEqual(
            list(settings.tlh_excluded_categories), DEFAULT_TLH_EXCLUSIONS
        )

    def test_check_and_notify_uses_threshold_and_exclusions(self):
        from domains.tlh import notify as tlh_notify
        from domains.tlh import scan as tlh_scan

        settings_row = put_user_settings(
            self.db,
            self.user_id,
            UserSettingsPut(
                tlh_notify_threshold=Decimal("500"),
                tlh_excluded_categories=["Individual Stocks"],
            ),
        )

        included = MagicMock(
            category="US Total Market",
            ticker="VTI",
            quantity=10,
            current_price=80,
            original_purchase_price=100,
        )
        excluded = MagicMock(
            category="Individual Stocks",
            ticker="TEAM",
            quantity=5,
            current_price=50,
            original_purchase_price=200,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [included, excluded]

        with patch.object(tlh_notify, "send_email") as send_email, patch.object(
            tlh_notify,
            "get_or_create_user_settings",
            return_value=settings_row,
        ), patch.object(
            tlh_scan,
            "get_or_create_user_settings",
            return_value=settings_row,
        ), patch.object(self.db, "execute", return_value=mock_result):
            result = tlh_notify.check_and_notify_tlh(self.db, str(self.user_id))

        # Loss from VTI only: (100-80)*10 = 200 < 500 => no notify
        self.assertFalse(result["notified"])
        self.assertEqual(result["total_loss"], 200.0)
        self.assertEqual(result["lots_count"], 1)
        send_email.assert_not_called()

        # Raise loss above threshold
        included.quantity = 30  # (100-80)*30 = 600
        mock_result.scalars.return_value.all.return_value = [included, excluded]
        with patch.object(tlh_notify, "send_email") as send_email, patch.object(
            tlh_notify,
            "get_or_create_user_settings",
            return_value=settings_row,
        ), patch.object(
            tlh_scan,
            "get_or_create_user_settings",
            return_value=settings_row,
        ), patch.object(self.db, "execute", return_value=mock_result):
            result = tlh_notify.check_and_notify_tlh(self.db, str(self.user_id))
        self.assertTrue(result["notified"])
        self.assertEqual(result["total_loss"], 600.0)
        send_email.assert_called_once()


class AppRoutesSmokeTest(unittest.TestCase):
    def test_settings_and_portfolio_routes_registered(self):
        # Importing main touches live DB/scheduler; instead inspect router modules.
        from routers import accounts, portfolio, settings as settings_router, ingest

        account_paths = {r.path for r in accounts.router.routes}
        portfolio_paths = {r.path for r in portfolio.router.routes}
        settings_paths = {r.path for r in settings_router.router.routes}
        ingest_paths = {r.path for r in ingest.router.routes}

        self.assertIn("/accounts", account_paths)
        self.assertIn("/accounts/transfer-lots", account_paths)
        self.assertIn("/portfolio/{user_id}/snapshot", portfolio_paths)
        self.assertIn("/portfolio/{user_id}/snapshot/sync", portfolio_paths)
        self.assertIn("/portfolio/{user_id}/net-worth", portfolio_paths)
        self.assertIn("/settings/{user_id}", settings_paths)
        self.assertIn("/ingest/lots", ingest_paths)
        self.assertIn("/ingest/positions", ingest_paths)


if __name__ == "__main__":
    unittest.main()
