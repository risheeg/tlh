from decimal import Decimal
from collections import defaultdict
from sqlalchemy import func
from sqlalchemy.orm import Session
from models.models import PortfolioHoldingEnriched
from schemas.portfolio import PortfolioSnapshot

def get_portfolio_snapshot(db: Session, user_id) -> PortfolioSnapshot | None:
    """
    Returns a unified snapshot of all holdings (lots + positions) enriched with current prices.
    """
    results = (
        db.query(PortfolioHoldingEnriched)
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .filter(PortfolioHoldingEnriched.quantity != 0)
        .all()
    )
    
    if not results:
        return None

    total_net_worth, last_updated = (
        db.query(
            func.coalesce(func.sum(PortfolioHoldingEnriched.market_value), 0),
            func.max(PortfolioHoldingEnriched.price_last_updated),
        )
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .filter(PortfolioHoldingEnriched.quantity != 0)
        .one()
    )
    
    return PortfolioSnapshot(
        user_id=user_id,
        total_net_worth=total_net_worth,
        last_updated=last_updated,
        holdings=results
    )

def get_current_net_worth(db: Session, user_id) -> float | None:
    """
    Returns the current net worth for a user.
    """
    snapshot = get_portfolio_snapshot(db, user_id)
    if snapshot is None:
        return None
    return snapshot.total_net_worth

def get_category_summary(db: Session, user_id) -> list[dict] | None:
    """
    Returns a list of category allocations (name, value, percentage).
    """
    results = (
        db.query(
            PortfolioHoldingEnriched.category,
            PortfolioHoldingEnriched.ticker,
            PortfolioHoldingEnriched.market_value
        )
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .all()
    )

    
    if not results:
        return None
        
    summary_data = defaultdict(Decimal)
    tickers_by_category = defaultdict(set)
    for res in results:
        cat = res.category or "Unknown"
        summary_data[cat] += Decimal(str(res.market_value or 0))
        if res.ticker:
            tickers_by_category[cat].add(res.ticker)
        
    total = sum(summary_data.values())
    return [
        {
            "category": cat,
            "value": float(val),
            "percentage": float(val / total) if total > 0 else 0,
            "tickers": sorted(tickers_by_category[cat])
        }
        for cat, val in summary_data.items()
    ]
