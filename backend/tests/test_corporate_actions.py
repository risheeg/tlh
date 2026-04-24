import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.session import Base
from models.models import (
    Account,
    AccountType,
    AggregatePosition,
    AssetType,
    Lot,
    LotStatus,
    StockSplit,
    User,
)
from schemas.schemas import StockSplitCreate
from services.corporate_actions import apply_stock_split, preview_stock_split


class StockSplitServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Account.__table__,
                Lot.__table__,
                AggregatePosition.__table__,
                StockSplit.__table__,
            ],
        )
        self.db = Session(self.engine)
        self.user_id = uuid.uuid4()
        self.account_id = uuid.uuid4()
        self.retirement_account_id = uuid.uuid4()

        self.db.add(
            User(
                id=self.user_id,
                email="split-test@example.com",
            )
        )
        self.db.add(
            Account(
                id=self.account_id,
                user_id=self.user_id,
                name="Taxable",
                type=AccountType.taxable,
            )
        )
        self.db.add(
            Account(
                id=self.retirement_account_id,
                user_id=self.user_id,
                name="Retirement",
                type=AccountType.retirement,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _payload(self) -> StockSplitCreate:
        return StockSplitCreate(
            ticker="vug",
            effective_date=date(2026, 4, 21),
            split_numerator=6,
            split_denominator=1,
        )

    def _add_lot(
        self,
        *,
        quantity: str,
        purchase_price: str,
        purchase_date: date,
        status: LotStatus = LotStatus.active,
    ) -> Lot:
        lot = Lot(
            user_id=self.user_id,
            account_id=self.account_id,
            ticker="VUG",
            quantity=Decimal(quantity),
            original_purchase_price=Decimal(purchase_price),
            current_adjusted_basis=Decimal(purchase_price),
            purchase_date=purchase_date,
            status=status,
        )
        self.db.add(lot)
        self.db.commit()
        return lot

    def _add_position(self) -> AggregatePosition:
        position = AggregatePosition(
            user_id=self.user_id,
            account_id=self.retirement_account_id,
            ticker="VUG",
            quantity=Decimal("12"),
            cost_basis=Decimal("1200"),
            asset_type=AssetType.Equity,
        )
        self.db.add(position)
        self.db.commit()
        return position

    def test_apply_vug_split_updates_lots_and_aggregate_positions(self):
        lot = self._add_lot(
            quantity="0.925008",
            purchase_price="435.11",
            purchase_date=date(2025, 7, 2),
        )
        position = self._add_position()

        result = apply_stock_split(self.db, self._payload())

        self.assertTrue(result.applied)
        self.db.refresh(lot)
        self.db.refresh(position)

        self.assertEqual(lot.ticker, "VUG")
        self.assertAlmostEqual(float(lot.quantity), 5.550048, places=8)
        self.assertAlmostEqual(float(lot.original_purchase_price), 72.518333333, places=8)
        self.assertAlmostEqual(float(lot.current_adjusted_basis), 72.518333333, places=8)
        self.assertEqual(float(position.quantity), 72.0)
        self.assertEqual(float(position.cost_basis), 1200.0)

    def test_split_skips_lots_purchased_on_or_after_effective_date(self):
        before_split = self._add_lot(
            quantity="1",
            purchase_price="420",
            purchase_date=date(2026, 4, 20),
        )
        on_split_date = self._add_lot(
            quantity="1",
            purchase_price="70",
            purchase_date=date(2026, 4, 21),
        )
        closed_before_split = self._add_lot(
            quantity="1",
            purchase_price="420",
            purchase_date=date(2026, 4, 20),
            status=LotStatus.closed,
        )

        apply_stock_split(self.db, self._payload())

        self.db.refresh(before_split)
        self.db.refresh(on_split_date)
        self.db.refresh(closed_before_split)

        self.assertEqual(float(before_split.quantity), 6.0)
        self.assertEqual(float(on_split_date.quantity), 1.0)
        self.assertEqual(float(closed_before_split.quantity), 1.0)

    def test_reapplying_same_split_is_a_noop(self):
        lot = self._add_lot(
            quantity="2",
            purchase_price="420",
            purchase_date=date(2026, 4, 20),
        )

        first = apply_stock_split(self.db, self._payload())
        second = apply_stock_split(self.db, self._payload())
        preview = preview_stock_split(self.db, self._payload())

        self.db.refresh(lot)

        self.assertTrue(first.applied)
        self.assertFalse(second.applied)
        self.assertTrue(preview.already_applied)
        self.assertEqual(float(lot.quantity), 12.0)
        self.assertEqual(preview.impact.lot_quantity_before, preview.impact.lot_quantity_after)


if __name__ == "__main__":
    unittest.main()
