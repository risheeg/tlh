from datetime import date, datetime, timezone
from decimal import Decimal
from collections import defaultdict
from sqlalchemy.orm import Session
from models.models import NetWorthSnapshot, PortfolioHoldingEnriched, Account
from services.portfolio.service import get_portfolio_snapshot

def create_net_worth_snapshot(db: Session, user_id) -> NetWorthSnapshot:
    """
    Calculates current net worth and breakdown, then saves it to the database.
    """
    # 1. Get current snapshot data
    snapshot_data = get_portfolio_snapshot(db, user_id)
    if not snapshot_data:
        raise ValueError(f"No holdings found for user {user_id}")

    # 2. Build breakdown
    categories = defaultdict(Decimal)
    asset_types = defaultdict(Decimal)
    accounts_by_id = defaultdict(Decimal)
    
    for holding in snapshot_data.holdings:
        mv = Decimal(str(holding.market_value or 0))
        categories[holding.category or "Unknown"] += mv
        asset_types[holding.asset_type or "Unknown"] += mv
        accounts_by_id[holding.account_id] += mv

    # Fetch account metadata for the breakdown
    accounts_metadata = {acc.id: acc for acc in db.query(Account).filter(Account.id.in_(accounts_by_id.keys())).all()}
    
    account_types = defaultdict(Decimal)
    for acc_id, mv in accounts_by_id.items():
        acc = accounts_metadata.get(acc_id)
        if acc:
            # Group into Retirement vs Taxable/Other
            if acc.type.value == "retirement":
                bucket = "Retirement"
            else:
                bucket = "Taxable"  # Includes taxable, savings, checking, cma
            account_types[bucket] += mv

    breakdown = {
        "categories": {k: float(v) for k, v in categories.items()},
        "asset_types": {k: float(v) for k, v in asset_types.items()},
        "accounts": {accounts_metadata[k].name if k in accounts_metadata else str(k): float(v) for k, v in accounts_by_id.items()},
        "account_types": {k: float(v) for k, v in account_types.items()}
    }

    # 3. Save to database
    today = date.today()
    
    # Check if a snapshot for today already exists (upsert logic)
    existing = db.query(NetWorthSnapshot).filter(
        NetWorthSnapshot.user_id == user_id,
        NetWorthSnapshot.snapshot_date == today
    ).first()

    if existing:
        existing.total_net_worth = float(snapshot_data.total_net_worth)
        existing.breakdown = breakdown
        existing.created_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_snapshot = NetWorthSnapshot(
            user_id=user_id,
            snapshot_date=today,
            total_net_worth=float(snapshot_data.total_net_worth),
            breakdown=breakdown
        )
        db.add(new_snapshot)
        db.commit()
        db.refresh(new_snapshot)
        return new_snapshot

def get_net_worth_history(db: Session, user_id, start_date: date = None, end_date: date = None):
    """
    Retrieves historical net worth snapshots for a user.
    """
    query = db.query(NetWorthSnapshot).filter(NetWorthSnapshot.user_id == user_id)
    
    if start_date:
        query = query.filter(NetWorthSnapshot.snapshot_date >= start_date)
    if end_date:
        query = query.filter(NetWorthSnapshot.snapshot_date <= end_date)
        
    return query.order_by(NetWorthSnapshot.snapshot_date.asc()).all()
