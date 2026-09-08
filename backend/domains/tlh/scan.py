"""Scan portfolio lots for harvestable unrealized losses."""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models.portfolio import PortfolioHoldingEnriched
from shared.user_settings import DEFAULT_TLH_EXCLUSIONS, get_or_create_user_settings


def scan_harvestable_losses(db: Session, user_id) -> dict:
    """
    Return harvestable unrealized losses for taxable lots.

    Applies the user's TLH excluded categories. Does not send email or apply
    the $3,000 ordinary-income offset — callers decide how to use total_loss.
    """
    settings = get_or_create_user_settings(db, user_id)
    excluded = set(settings.tlh_excluded_categories or DEFAULT_TLH_EXCLUSIONS)

    stmt = select(PortfolioHoldingEnriched).where(
        and_(
            PortfolioHoldingEnriched.user_id == user_id,
            PortfolioHoldingEnriched.holding_type == "lot",
        )
    )
    results = db.execute(stmt).scalars().all()

    harvestable_lots: list[dict] = []
    total_loss = 0.0

    for lot in results:
        if lot.category in excluded:
            continue
        if lot.current_price is None or lot.original_purchase_price is None:
            continue

        price_diff = float(lot.original_purchase_price) - float(lot.current_price)
        if price_diff > 0:
            lot_loss = price_diff * float(lot.quantity)
            total_loss += lot_loss
            harvestable_lots.append(
                {
                    "ticker": lot.ticker,
                    "quantity": float(lot.quantity),
                    "purchase_price": float(lot.original_purchase_price),
                    "current_price": float(lot.current_price),
                    "loss": lot_loss,
                }
            )

    return {
        "total_loss": total_loss,
        "lots": harvestable_lots,
        "lots_count": len(harvestable_lots),
    }
