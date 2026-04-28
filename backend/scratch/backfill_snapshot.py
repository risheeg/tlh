import sys
import uuid
from datetime import date, timedelta
from db.session import SessionLocal
from services.portfolio.history_service import create_net_worth_snapshot
from models.models import User, NetWorthSnapshot

def backfill_for_date(target_date: date, user_id: uuid.UUID):
    db = SessionLocal()
    try:
        print(f"Backfilling snapshot for user {user_id} on {target_date}...")
        
        # We need to temporarily monkeypatch date.today() or just manually insert
        # Since history_service.py uses date.today(), we'll copy the logic here or modify it.
        # Let's just do it manually here to be safe and flexible.
        
        from services.portfolio.service import get_portfolio_snapshot
        from decimal import Decimal
        from collections import defaultdict
        from models.models import Account
        
        snapshot_data = get_portfolio_snapshot(db, user_id)
        if not snapshot_data:
            print(f"No holdings found for user {user_id}")
            return

        categories = defaultdict(Decimal)
        asset_types = defaultdict(Decimal)
        accounts_by_id = defaultdict(Decimal)
        
        for holding in snapshot_data.holdings:
            mv = Decimal(str(holding.market_value or 0))
            categories[holding.category or "Unknown"] += mv
            asset_types[holding.asset_type or "Unknown"] += mv
            accounts_by_id[holding.account_id] += mv

        accounts_metadata = {acc.id: acc for acc in db.query(Account).filter(Account.id.in_(accounts_by_id.keys())).all()}
        
        account_types = defaultdict(Decimal)
        for acc_id, mv in accounts_by_id.items():
            acc = accounts_metadata.get(acc_id)
            if acc:
                if acc.type.value == "retirement":
                    bucket = "Retirement"
                else:
                    bucket = "Taxable"
                account_types[bucket] += mv

        breakdown = {
            "categories": {k: float(v) for k, v in categories.items()},
            "asset_types": {k: float(v) for k, v in asset_types.items()},
            "accounts": {accounts_metadata[k].name if k in accounts_metadata else str(k): float(v) for k, v in accounts_by_id.items()},
            "account_types": {k: float(v) for k, v in account_types.items()}
        }

        # Check if exists
        existing = db.query(NetWorthSnapshot).filter(
            NetWorthSnapshot.user_id == user_id,
            NetWorthSnapshot.snapshot_date == target_date
        ).first()

        if existing:
            print(f"Snapshot already exists for {target_date}. Updating...")
            existing.total_net_worth = float(snapshot_data.total_net_worth)
            existing.breakdown = breakdown
        else:
            print(f"Creating new snapshot for {target_date}...")
            new_snapshot = NetWorthSnapshot(
                user_id=user_id,
                snapshot_date=target_date,
                total_net_worth=float(snapshot_data.total_net_worth),
                breakdown=breakdown,
                comments="Backfilled due to view regression fix"
            )
            db.add(new_snapshot)
        
        db.commit()
        print("Success!")
        
    finally:
        db.close()

if __name__ == "__main__":
    # Default to yesterday if no args
    target_date_str = sys.argv[1] if len(sys.argv) > 1 else None
    if target_date_str:
        target_date = date.fromisoformat(target_date_str)
    else:
        target_date = date.today() - timedelta(days=1)
        
    db = SessionLocal()
    users = db.query(User).all()
    db.close()
    
    for user in users:
        backfill_for_date(target_date, user.id)
