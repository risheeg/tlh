import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.session import get_db
from services.portfolio import get_portfolio_snapshot, generate_snapshot_rows, get_category_summary
from schemas.portfolio import PortfolioSnapshot
from services.sheets import sheets_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

def _get_snapshot_or_404(db: Session, user_id: uuid.UUID) -> PortfolioSnapshot:
    """Helper to fetch snapshot and raise 404 if prices are stale or missing."""
    snapshot = get_portfolio_snapshot(db, user_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio snapshot unavailable: stock prices are not fresh (updated >24h ago)."
        )
    return snapshot

@router.get("/{user_id}/snapshot", response_model=PortfolioSnapshot)
def get_user_portfolio_snapshot(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns enriched portfolio snapshot with current stock prices."""
    return _get_snapshot_or_404(db, user_id)

@router.get("/{user_id}/net-worth")
def get_user_net_worth(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns current total net worth and last update timestamp."""
    snapshot = _get_snapshot_or_404(db, user_id)
    return {
        "user_id": user_id, 
        "net_worth": snapshot.total_net_worth, 
        "last_updated": snapshot.last_updated
    }

@router.post("/{user_id}/snapshot/sync")
def sync_portfolio_snapshot(user_id: uuid.UUID, group_by: str = "type", db: Session = Depends(get_db)):
    """Appends daily snapshot to Google Sheets if it hasn't been synced today."""
    today_str = datetime.now().strftime("%-m/%-d/%Y")
    
    if sheets_service.get_last_snapshot_date() == today_str:
        return {"status": "skipped", "message": f"Snapshot for {today_str} already exists."}
    
    res = generate_snapshot_rows(db, user_id, group_by=group_by)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not generate spreadsheet rows. Ensure stock prices are fresh."
        )
    
    rows, num_main_cols, num_summary_cols = res
    sheets_service.append_snapshot(rows, num_main_cols, num_summary_cols)
    
    return {"status": "success", "message": f"Snapshot for {today_str} synced to Google Sheets."}

@router.get("/{user_id}/allocation")
def get_user_category_allocation(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns asset allocation breakdown by category."""
    summary = get_category_summary(db, user_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allocation summary unavailable: ensure stock prices are fresh."
        )
    return summary
