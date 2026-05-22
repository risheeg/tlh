"""
Monthly digest email: net worth, allocation breakdown, and every active lot
with its current gain/loss status.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.models import (
    Lot,
    LotStatus,
    NetWorthSnapshot,
    PortfolioHoldingEnriched,
    StockPrice,
    User,
)
from services.email_service import send_email


def send_monthly_digest(db: Session, user_id: str) -> dict[str, Any]:
    """
    Build and send a monthly digest covering net worth, allocation, and
    every active lot with its +ve/-ve status.  Always sends.
    """
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%B %d, %Y")

    # --- Net worth -----------------------------------------------------------
    snapshot = (
        db.execute(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.user_id == user_id)
            .order_by(NetWorthSnapshot.snapshot_date.desc())
        )
        .scalars()
        .first()
    )

    # --- Allocation ----------------------------------------------------------
    alloc_rows = (
        db.query(
            PortfolioHoldingEnriched.category,
            PortfolioHoldingEnriched.market_value,
        )
        .filter(PortfolioHoldingEnriched.user_id == user_id)
        .all()
    )
    alloc: dict[str, Decimal] = defaultdict(Decimal)
    for row in alloc_rows:
        alloc[row.category or "Unknown"] += Decimal(str(row.market_value or 0))
    alloc_total = sum(alloc.values())

    # --- Lots ----------------------------------------------------------------
    lots = (
        db.execute(
            select(Lot)
            .where(Lot.user_id == user_id, Lot.status == LotStatus.active)
            .order_by(Lot.ticker, Lot.purchase_date)
        )
        .scalars()
        .all()
    )

    prices: dict[str, float] = {
        p.ticker: float(p.price)
        for p in db.execute(select(StockPrice)).scalars().all()
    }

    # --- Compose email -------------------------------------------------------
    subject = f"[TLH] Monthly Portfolio Digest — {date_str}"

    lines: list[str] = []
    lines.append(f"Monthly Portfolio Digest — {date_str}")
    lines.append("=" * 70)

    # -- Net Worth section --
    lines.append("")
    lines.append("NET WORTH")
    lines.append("-" * 40)
    if snapshot:
        lines.append(f"  ${float(snapshot.total_net_worth):>12,.2f}  "
                     f"(as of {snapshot.snapshot_date.isoformat()})")
    else:
        lines.append("  No snapshot available.")

    # -- Allocation section --
    lines.append("")
    lines.append("ALLOCATION BY CATEGORY")
    lines.append("-" * 40)
    for cat in sorted(alloc, key=lambda c: alloc[c], reverse=True):
        val = alloc[cat]
        pct = (val / alloc_total * 100) if alloc_total else Decimal(0)
        lines.append(f"  {cat:<25} ${float(val):>12,.2f}  ({float(pct):>5.1f}%)")
    if alloc_total:
        lines.append(f"  {'TOTAL':<25} ${float(alloc_total):>12,.2f}")

    # -- Lot detail section --
    lines.append("")
    lines.append("ACTIVE LOTS")
    lines.append("-" * 40)
    lines.append(
        f"  {'Ticker':<7} {'Date':<12} {'Shares':>10} "
        f"{'Buy':>10} {'Current':>10} {'Gain/Loss':>12}  Status"
    )
    lines.append("  " + "-" * 80)

    total_gain = 0.0
    total_loss = 0.0
    lots_positive = 0
    lots_negative = 0

    for lot in lots:
        qty = float(lot.quantity)
        buy = float(lot.original_purchase_price)
        cur = prices.get(lot.ticker)

        if cur is None:
            gl_str = "N/A"
            status_str = "⚠ NO PRICE"
        else:
            gl = (cur - buy) * qty
            if gl >= 0:
                gl_str = f"+${gl:,.2f}"
                status_str = "✅ +ve"
                total_gain += gl
                lots_positive += 1
            else:
                gl_str = f"-${abs(gl):,.2f}"
                status_str = "🔻 -ve"
                total_loss += abs(gl)
                lots_negative += 1

        cur_str = f"${cur:>9.2f}" if cur is not None else "      N/A"
        lines.append(
            f"  {lot.ticker:<7} {lot.purchase_date.isoformat():<12} "
            f"{qty:>10.4f} ${buy:>9.2f} {cur_str} "
            f"{gl_str:>12}  {status_str}"
        )

    lines.append("  " + "-" * 80)
    lines.append("")
    lines.append(f"  Total lots: {len(lots)}  "
                 f"(✅ {lots_positive} positive, 🔻 {lots_negative} negative)")
    lines.append(f"  Total unrealized gains:  +${total_gain:,.2f}")
    lines.append(f"  Total unrealized losses: -${total_loss:,.2f}")
    net = total_gain - total_loss
    lines.append(f"  Net: {'+'if net >= 0 else '-'}${abs(net):,.2f}")
    lines.append("")
    lines.append("—")
    lines.append("Antigravity TLH Backend")

    body = "\n".join(lines)
    send_email(subject, body, user.email)

    return {
        "sent": True,
        "email": user.email,
        "subject": subject,
    }
