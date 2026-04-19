from decimal import Decimal
from collections import defaultdict
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from models.models import PortfolioHoldingEnriched, StockPrice
from schemas.portfolio import PortfolioSnapshot

def get_portfolio_snapshot(db: Session, user_id) -> PortfolioSnapshot | None:
    """
    Returns a unified snapshot of all holdings (lots + positions) enriched with current prices.
    """
    results = db.query(PortfolioHoldingEnriched).filter(PortfolioHoldingEnriched.user_id == user_id).all()
    
    if not results:
        return None
        
    total_net_worth = sum(res.market_value for res in results if res.market_value)
    last_updated = max((res.price_last_updated for res in results if res.price_last_updated), default=None)
    
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
            PortfolioHoldingEnriched.market_value
        )
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .all()
    )

    
    if not results:
        return None
        
    summary_data = defaultdict(Decimal)
    for res in results:
        summary_data[res.category or "Unknown"] += Decimal(str(res.market_value or 0))
        
    total = sum(summary_data.values())
    return [
        {
            "category": cat,
            "value": float(val),
            "percentage": float(val / total) if total > 0 else 0
        }
        for cat, val in summary_data.items()
    ]
