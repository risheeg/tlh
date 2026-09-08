"""TLH notification: email when harvestable losses exceed threshold."""
from sqlalchemy.orm import Session

from models.core import User
from shared.email import send_email
from shared.user_settings import DEFAULT_TLH_THRESHOLD, get_or_create_user_settings

from .scan import scan_harvestable_losses


def check_and_notify_tlh(db: Session, user_id: str) -> dict:
    """
    Identify lots with a loss and email if combined harvestable losses
    exceed the user's configured threshold.
    """
    user = db.get(User, user_id)
    if not user:
        return {"error": f"User {user_id} not found"}

    settings = get_or_create_user_settings(db, user.id)
    threshold = float(settings.tlh_notify_threshold or DEFAULT_TLH_THRESHOLD)

    scan = scan_harvestable_losses(db, user.id)
    total_loss = float(scan["total_loss"])
    harvestable_lots = scan["lots"]

    if total_loss >= threshold:
        subject = f"TLH Alert: ${total_loss:,.2f} in Harvestable Losses Identified"

        body = "Hello,\n\n"
        body += "We have identified tax loss harvesting opportunities in your portfolio.\n"
        body += f"Total combined harvestable losses: ${total_loss:,.2f}\n\n"
        body += "Details:\n"
        body += f"{'Ticker':<10} | {'Qty':<10} | {'Buy Price':<12} | {'Cur Price':<12} | {'Loss':<12}\n"
        body += "-" * 65 + "\n"

        for lot in harvestable_lots:
            body += (
                f"{lot['ticker']:<10} | {lot['quantity']:<10.2f} | "
                f"${lot['purchase_price']:<11.2f} | ${lot['current_price']:<11.2f} | "
                f"${lot['loss']:<11.2f}\n"
            )

        body += "\nBest regards,\nAntigravity TLH App"

        send_email(subject, body, user.email)
        return {
            "notified": True,
            "total_loss": total_loss,
            "lots_count": len(harvestable_lots),
            "email_sent_to": user.email,
        }

    return {
        "notified": False,
        "total_loss": total_loss,
        "lots_count": len(harvestable_lots),
    }
