import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.session import get_db
from services.portfolio import get_portfolio_snapshot
from schemas.portfolio import PortfolioSnapshot

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("/{user_id}/snapshot", response_model=PortfolioSnapshot)
def get_user_portfolio_snapshot(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Returns the current portfolio snapshot for a user, enriched with current stock prices.
    Only returns if ALL stock prices for the user's tickers have been updated in the last 24 hours.
    """
    snapshot = get_portfolio_snapshot(db, user_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not all stock prices for user's assets are fresh (updated within last 24h)."
        )
    return snapshot

@router.get("/{user_id}/net-worth")
def get_user_net_worth(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Returns the current net worth for a user.
    """
    snapshot = get_portfolio_snapshot(db, user_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not all stock prices for user's assets are fresh (updated within last 24h)."
        )
    return {"user_id": user_id, "net_worth": snapshot.total_net_worth, "last_updated": snapshot.last_updated}
