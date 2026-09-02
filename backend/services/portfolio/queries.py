from decimal import Decimal
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from models.models import PortfolioHoldingEnriched, StockPrice

def _get_account_market_values(db: Session, user_id) -> dict[str, Decimal]:
    """Returns a mapping of account_id -> total_market_value for a user."""
    return {
        str(account_id): Decimal(str(total_value)) 
        for account_id, total_value in db.query(
            PortfolioHoldingEnriched.account_id, 
            func.sum(PortfolioHoldingEnriched.market_value)
        ).filter(PortfolioHoldingEnriched.user_id == user_id).group_by(PortfolioHoldingEnriched.account_id).all()
    }

def _fetch_aggregated_holdings(db: Session, user_id) -> list:
    """Executes the aggregated database query to get market values per ticker and account."""
    return (
        db.query(
            PortfolioHoldingEnriched.ticker,
            PortfolioHoldingEnriched.account_id,
            PortfolioHoldingEnriched.category,
            PortfolioHoldingEnriched.expense_ratio,
            PortfolioHoldingEnriched.market_value,
            (PortfolioHoldingEnriched.asset_type == "Cash").label("is_cash")
        )
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .filter(PortfolioHoldingEnriched.quantity != 0)
        .all()
    )

