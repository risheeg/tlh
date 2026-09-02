import uuid
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from db.session import get_db
from services.portfolio import get_portfolio_snapshot, generate_snapshot_rows, get_category_summary
from schemas.portfolio import (
    NetWorthSnapshotCommentUpdate,
    NetWorthSnapshotResponse,
    PortfolioSnapshot,
)
from services.portfolio.history_service import (
    get_net_worth_history,
    update_net_worth_snapshot_comments,
)
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


@router.get(
    "/{user_id}/net-worth/history",
    response_model=list[NetWorthSnapshotResponse],
)
def get_user_net_worth_history(
    user_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """Returns persisted net worth snapshots, including optional comments."""
    return get_net_worth_history(db, user_id, start_date=start_date, end_date=end_date)


@router.patch(
    "/{user_id}/net-worth/history/{snapshot_date}/comments",
    response_model=NetWorthSnapshotResponse,
)
def update_user_net_worth_snapshot_comments(
    user_id: uuid.UUID,
    snapshot_date: date,
    payload: NetWorthSnapshotCommentUpdate,
    db: Session = Depends(get_db),
):
    """Updates the free-form comments for a net worth snapshot."""
    snapshot = update_net_worth_snapshot_comments(
        db,
        user_id,
        snapshot_date,
        payload.comments,
    )
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Net worth snapshot not found for that date.",
        )
    return snapshot

@router.post("/{user_id}/snapshot/sync")
def sync_portfolio_snapshot(user_id: uuid.UUID, group_by: str | None = None, db: Session = Depends(get_db)):
    """Appends daily snapshot to Google Sheets if it hasn't been synced today."""
    today_str = datetime.now().strftime("%-m/%-d/%Y")
    
    if sheets_service.get_last_snapshot_date() == today_str:
        return {"status": "skipped", "message": f"Snapshot for {today_str} already exists."}
    
    rows = generate_snapshot_rows(db, user_id, group_by=group_by)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not generate spreadsheet rows. Ensure stock prices are fresh."
        )
    
    sheets_service.append_snapshot(rows)
    
    return {"status": "success", "message": f"Snapshot for {today_str} synced to Google Sheets."}

@router.get("/{user_id}/allocation", response_class=HTMLResponse)
def get_user_category_allocation(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns asset allocation breakdown by category as an HTML page."""
    summary = get_category_summary(db, user_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allocation summary unavailable: ensure stock prices are fresh."
        )

    # Sort by value descending, filter out zero-value categories
    summary = [s for s in summary if s["value"] > 0]
    summary.sort(key=lambda x: x["value"], reverse=True)
    total = sum(s["value"] for s in summary)

    rows_html = ""
    for s in summary:
        cat = s["category"]
        val = s["value"]
        pct = s["percentage"] * 100
        tickers = ", ".join(s.get("tickers", [])) or "-"
        rows_html += f"""
        <tr>
          <td>{cat}</td>
          <td>{tickers}</td>
          <td>${val:,.2f}</td>
          <td>{pct:.1f}%</td>
        </tr>"""

    html = f"""<html>
<body>
Asset Allocation - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
Total: ${total:,.2f}<br><br>
<table border='1'>
  <tr>
    <td>Category</td><td>Tickers</td><td>Value</td><td>%</td>
  </tr>
  {rows_html}
  <tr>
    <td>Total</td><td></td><td>${total:,.2f}</td><td>100.0%</td>
  </tr>
</table>
</body>
</html>"""
    return html
@router.get("/{user_id}/snapshot/view", response_class=HTMLResponse)
def view_portfolio_snapshot(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns a pure plain-text HTML view of the 3 different snapshot structures."""
    views = ["custom", "type", "name"]
    html_content = "<html><body>"
    html_content += "PORTFOLIO SNAPSHOT REPORT - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "<br><br>"
    
    for view in views:
        rows = generate_snapshot_rows(db, user_id, group_by=view)
        if not rows:
            continue
            
        html_content += f"Grouping: {view.capitalize()}<br>"
        html_content += "<table border='1'>"
        
        for row in rows:
            html_content += "<tr>"
            for cell in row:
                html_content += f"<td>{cell}</td>"
            html_content += "</tr>"
            
        html_content += "</table><br><br>"
        
    html_content += "</body></html>"
    return html_content
