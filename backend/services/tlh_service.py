from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from models.models import PortfolioHoldingEnriched, User
from services.email_service import send_email

def check_and_notify_tlh(db: Session, user_id: str) -> dict:
    """
    Identifies lots with a loss and sends an email if the combined harvestable losses exceed 1000.
    Excludes 'Individual Stock' category.
    """
    user = db.get(User, user_id)
    if not user:
        return {"error": f"User {user_id} not found"}

    # Query enriched holdings for lots
    stmt = select(PortfolioHoldingEnriched).where(
        and_(
            PortfolioHoldingEnriched.user_id == user_id,
            PortfolioHoldingEnriched.holding_type == 'lot',
            PortfolioHoldingEnriched.category != 'Indvl Company'
        )
    )
    
    results = db.execute(stmt).scalars().all()
    
    harvestable_lots = []
    total_loss = 0.0
    
    for lot in results:
        if lot.current_price is None or lot.original_purchase_price is None:
            continue
            
        # Loss = (Purchase Price - Current Price) * Quantity
        # If current_price < purchase_price, it's a loss.
        price_diff = float(lot.original_purchase_price) - float(lot.current_price)
        
        if price_diff > 0:
            lot_loss = price_diff * float(lot.quantity)
            total_loss += lot_loss
            harvestable_lots.append({
                "ticker": lot.ticker,
                "quantity": float(lot.quantity),
                "purchase_price": float(lot.original_purchase_price),
                "current_price": float(lot.current_price),
                "loss": lot_loss
            })
            
    if total_loss >= 1000:
        # Prepare email
        subject = f"TLH Alert: ${total_loss:,.2f} in Harvestable Losses Identified"
        
        body = f"Hello,\n\n"
        body += f"We have identified tax loss harvesting opportunities in your portfolio.\n"
        body += f"Total combined harvestable losses: ${total_loss:,.2f}\n\n"
        body += "Details:\n"
        body += f"{'Ticker':<10} | {'Qty':<10} | {'Buy Price':<12} | {'Cur Price':<12} | {'Loss':<12}\n"
        body += "-" * 65 + "\n"
        
        for lot in harvestable_lots:
            body += f"{lot['ticker']:<10} | {lot['quantity']:<10.2f} | ${lot['purchase_price']:<11.2f} | ${lot['current_price']:<11.2f} | ${lot['loss']:<11.2f}\n"
            
        body += "\nBest regards,\nAntigravity TLH App"
        
        send_email(subject, body, user.email)
        return {
            "notified": True,
            "total_loss": total_loss,
            "lots_count": len(harvestable_lots),
            "email_sent_to": user.email
        }
    
    return {
        "notified": False,
        "total_loss": total_loss,
        "lots_count": len(harvestable_lots)
    }
