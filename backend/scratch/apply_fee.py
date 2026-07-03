import sys
sys.path.insert(0, '/home/ubuntu/tlh/backend')

from db.session import engine, SessionLocal
from sqlalchemy import text
from models.models import User, Account, CashHolding, Transaction, TransactionType
from datetime import datetime, timezone
import uuid

# 1. Update DB Schema
with engine.connect() as conn:
    try:
        # Commit any open transaction
        conn.execute(text("COMMIT"))
        conn.execute(text("ALTER TYPE transactiontype ADD VALUE 'fee'"))
    except Exception as e:
        print("Enum fee might already exist or error:", e)
    
    try:
        conn.execute(text("ALTER TABLE transactions ADD COLUMN note VARCHAR"))
    except Exception as e:
        print("Column note might already exist or error:", e)
        
    conn.commit()

# 2. Mutate data
db = SessionLocal()
try:
    user = db.query(User).first()
    rh_acc = db.query(Account).filter(Account.user_id == user.id, Account.name == "Robinhood Brokerage").first()
    
    if rh_acc:
        # Zero out cash holdings
        cash = db.query(CashHolding).filter(CashHolding.account_id == rh_acc.id).first()
        if cash:
            cash.amount = 0
            cash.last_updated = datetime.now(timezone.utc)
        else:
            cash = CashHolding(
                user_id=user.id,
                account_id=rh_acc.id,
                amount=0,
                last_updated=datetime.now(timezone.utc)
            )
            db.add(cash)
            
        # Add 100 ACATS fee transaction
        fee_tx = Transaction(
            user_id=user.id,
            type=TransactionType.fee,
            ticker="CASH",
            quantity=100,
            price=1,
            transaction_date=datetime.now(timezone.utc).date(),
            note="fidelity gave credit for it",
            origin_account_id=rh_acc.id,
            destination_account_id=None,
            created_at=datetime.now(timezone.utc)
        )
        db.add(fee_tx)
        
        db.commit()
        print("Data mutated successfully.")
    else:
        print("Robinhood Brokerage account not found.")
finally:
    db.close()
