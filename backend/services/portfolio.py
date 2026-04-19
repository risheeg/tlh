from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, func, case, union_all, and_, or_
from models.models import Lot, AggregatePosition, StockPrice, LotStatus, AssetType
from schemas.portfolio import EnrichedLot, EnrichedAggregatePosition, PortfolioSnapshot


def get_portfolio_snapshot(db: Session, user_id) -> PortfolioSnapshot | None:
    """
    Returns a snapshot of the user's portfolio with current prices and market values.
    Only returns if ALL stock prices for the user's EQUITY tickers have been updated in the last 24 hours.
    """
    now = datetime.now(timezone.utc)
    fresh_threshold = now - timedelta(hours=24)

    # 1. Freshness Check in SQL
    # Find all unique equity tickers and check if any are missing or stale
    equity_lots_sub = select(Lot.ticker).where(and_(Lot.user_id == user_id, Lot.status == LotStatus.active))
    equity_agg_sub = select(AggregatePosition.ticker).where(and_(AggregatePosition.user_id == user_id, AggregatePosition.asset_type == AssetType.Equity))
    all_equity_tickers = union_all(equity_lots_sub, equity_agg_sub).subquery()
    
    stale_query = (
        select(1)
        .select_from(all_equity_tickers)
        .outerjoin(StockPrice, all_equity_tickers.c.ticker == StockPrice.ticker)
        .where(or_(StockPrice.price == None, StockPrice.last_updated < fresh_threshold))
        .limit(1)
    )
    
    if db.execute(stale_query).first() is not None:
        return None

    # 2. Fetch enriched data in optimized queries
    lots_with_prices = (
        db.query(Lot, StockPrice)
        .outerjoin(StockPrice, Lot.ticker == StockPrice.ticker)
        .filter(Lot.user_id == user_id, Lot.status == LotStatus.active)
        .all()
    )
    
    agg_with_prices = (
        db.query(AggregatePosition, StockPrice)
        .outerjoin(StockPrice, AggregatePosition.ticker == StockPrice.ticker)
        .filter(AggregatePosition.user_id == user_id)
        .all()
    )

    if not lots_with_prices and not agg_with_prices:
        return PortfolioSnapshot(
            lots=[],
            aggregate_positions=[],
            total_net_worth=Decimal(0),
            last_updated=None
        )

    # 3. Calculate and build snapshot
    enriched_lots = []
    enriched_agg = []
    total_net_worth = Decimal(0)
    latest_update = None

    for lot, price_obj in lots_with_prices:
        price = Decimal(str(price_obj.price)) if price_obj else Decimal(0)
        market_value = Decimal(str(lot.quantity)) * price
        
        if price_obj and (latest_update is None or price_obj.last_updated > latest_update):
            latest_update = price_obj.last_updated
            
        enriched_lots.append(EnrichedLot(
            lot=lot,
            current_price=price,
            market_value=market_value
        ))
        total_net_worth += market_value

    for pos, price_obj in agg_with_prices:
        if pos.asset_type == AssetType.Cash:
            price = Decimal("1.00")
            market_value = Decimal(str(pos.quantity))
        else:
            price = Decimal(str(price_obj.price)) if price_obj else Decimal(0)
            market_value = Decimal(str(pos.quantity)) * price
            
            if price_obj and (latest_update is None or price_obj.last_updated > latest_update):
                latest_update = price_obj.last_updated

        enriched_agg.append(EnrichedAggregatePosition(
            position=pos,
            current_price=price,
            market_value=market_value
        ))
        total_net_worth += market_value

    return PortfolioSnapshot(
        lots=enriched_lots,
        aggregate_positions=enriched_agg,
        total_net_worth=total_net_worth,
        last_updated=latest_update
    )

def get_current_net_worth(db: Session, user_id) -> Decimal | None:
    """
    Returns the current net worth for a user.
    """
    snapshot = get_portfolio_snapshot(db, user_id)
    if snapshot is None:
        return None
    return snapshot.total_net_worth

import json
from pathlib import Path


def generate_snapshot_rows(db: Session, user_id, group_by: str = "type") -> tuple[list[list], int, int] | None:
    """
    Generates the 2D array of rows for the portfolio snapshot spreadsheet using SQL joins and aggregation.
    """
    # 1. Fetch all accounts for name mapping
    from models.models import Account, StockPrice, AccountType, Lot, AggregatePosition, AssetType, LotStatus
    accounts = {str(a.id): a for a in db.query(Account).all()}
    
    # 2. Get Account Totals for Sorting (if needed)
    acc_totals = {}
    if str(user_id) != "45a10eec-1398-483e-b7cd-be90fbd2c77c":
        q1 = select(Lot.account_id, func.sum(Lot.quantity * StockPrice.price)).select_from(Lot).join(StockPrice, Lot.ticker == StockPrice.ticker).where(and_(Lot.user_id == user_id, Lot.status == LotStatus.active)).group_by(Lot.account_id)
        q2 = select(AggregatePosition.account_id, func.sum(AggregatePosition.quantity * StockPrice.price)).select_from(AggregatePosition).join(StockPrice, AggregatePosition.ticker == StockPrice.ticker).where(and_(AggregatePosition.user_id == user_id, AggregatePosition.asset_type == AssetType.Equity)).group_by(AggregatePosition.account_id)
        q3 = select(AggregatePosition.account_id, func.sum(AggregatePosition.quantity)).select_from(AggregatePosition).where(and_(AggregatePosition.user_id == user_id, AggregatePosition.asset_type == AssetType.Cash)).group_by(AggregatePosition.account_id)
        acc_totals_res = db.execute(union_all(q1, q2, q3)).all()
        for aid, val in acc_totals_res:
            acc_totals[str(aid)] = acc_totals.get(str(aid), Decimal(0)) + Decimal(str(val))

    # 3. Setup Overrides/Mapping
    mapping = []
    category_order = []
    ticker_order = []
    
    if str(user_id) == "45a10eec-1398-483e-b7cd-be90fbd2c77c":
        overrides_path = Path(__file__).resolve().parent.parent / "core" / "account_overrides.json"
        with open(overrides_path, "r") as f:
            overrides = json.load(f)
        mapping = overrides.get("columns", [])
        category_order = overrides.get("category_order", [])
        ticker_order = overrides.get("ticker_order", [])
    else:
        if group_by == "type":
            taxable_accs = [a.name for a in accounts.values() if a.type == AccountType.taxable]
            retirement_accs = [a.name for a in accounts.values() if a.type == AccountType.retirement]
            mapping = []
            if taxable_accs: mapping.append({"header": "Brokerage / Taxable", "accounts": taxable_accs})
            if retirement_accs: mapping.append({"header": "Retirement", "accounts": retirement_accs})
        elif group_by == "name":
            # Sort accounts by total value descending
            sorted_accounts = sorted(accounts.values(), key=lambda a: acc_totals.get(str(a.id), Decimal(0)), reverse=True)
            mapping = [{"header": a.name, "accounts": [a.name]} for a in sorted_accounts if acc_totals.get(str(a.id), 0) > 0 or a.type.value in ["savings", "checkings", "cma"]]

    num_account_cols = len(mapping)
    mapped_account_ids = set()
    for col in mapping:
        for acc_name in col["accounts"]:
            for acc in accounts.values():
                if acc.name == acc_name:
                    mapped_account_ids.add(str(acc.id))
                    
    cash_accounts = [acc for acc in accounts.values() if str(acc.id) not in mapped_account_ids and acc.type.value in ["savings", "checkings", "cma"]]
    cash_col_header = "Cash ( " + " ".join([a.name for a in cash_accounts]) + " )"
    
    # 3. SQL Aggregation
    # Query for Lots (Active only)
    lots_query = (
        select(
            Lot.ticker,
            Lot.account_id,
            StockPrice.category,
            StockPrice.expense_ratio,
            func.sum(Lot.quantity * StockPrice.price).label("market_value"),
            case((AssetType.Cash == AssetType.Cash, False), else_=False).label("is_cash") # Helper for union
        )
        .join(StockPrice, Lot.ticker == StockPrice.ticker)
        .where(and_(Lot.user_id == user_id, Lot.status == LotStatus.active))
        .group_by(Lot.ticker, Lot.account_id, StockPrice.category, StockPrice.expense_ratio)
    )

    # Query for Aggregate Positions (Equity)
    agg_equity_query = (
        select(
            AggregatePosition.ticker,
            AggregatePosition.account_id,
            StockPrice.category,
            StockPrice.expense_ratio,
            func.sum(AggregatePosition.quantity * StockPrice.price).label("market_value"),
            case((AssetType.Cash == AssetType.Cash, False), else_=False).label("is_cash")
        )
        .join(StockPrice, AggregatePosition.ticker == StockPrice.ticker)
        .where(and_(AggregatePosition.user_id == user_id, AggregatePosition.asset_type == AssetType.Equity))
        .group_by(AggregatePosition.ticker, AggregatePosition.account_id, StockPrice.category, StockPrice.expense_ratio)
    )

    # Query for Aggregate Positions (Cash)
    agg_cash_query = (
        select(
            case((True, "CASH"), else_="CASH").label("ticker"), # Fixed ticker for cash
            AggregatePosition.account_id,
            case((True, "Cash/Cash Equivalents"), else_="Cash/Cash Equivalents").label("category"),
            case((True, 0), else_=0).label("expense_ratio"),
            func.sum(AggregatePosition.quantity).label("market_value"),
            case((True, True), else_=True).label("is_cash")
        )
        .where(and_(AggregatePosition.user_id == user_id, AggregatePosition.asset_type == AssetType.Cash))
        .group_by(AggregatePosition.account_id)
    )

    results = db.execute(union_all(lots_query, agg_equity_query, agg_cash_query)).all()

    # 4. Process Results into Ticker Data
    ticker_data = {} # (category, ticker) -> [bal0, bal1, ..., balN (cash col)]
    cash_balances = [Decimal(0)] * (num_account_cols + 1)
    grand_total_all = Decimal(0)
    total_weighted_exp = Decimal(0)
    
    ticker_exp_ratios = {} # (category, ticker) -> exp_ratio

    def get_col_index(account_id):
        acc = accounts.get(str(account_id))
        if not acc: return -1
        for i, col in enumerate(mapping):
            if acc.name in col["accounts"]: return i
        if str(account_id) in [str(a.id) for a in cash_accounts]: return num_account_cols
        return -1

    for res in results:
        ticker, acc_id, category, exp_ratio, market_value, is_cash = res
        market_value = Decimal(str(market_value))
        exp_ratio = Decimal(str(exp_ratio)) if exp_ratio else Decimal(0)
        
        col_idx = get_col_index(acc_id)
        if col_idx == -1: continue

        if is_cash:
            cash_balances[col_idx] += market_value
        else:
            key = (category, ticker)
            if key not in ticker_data:
                ticker_data[key] = [Decimal(0)] * (num_account_cols + 1)
                ticker_exp_ratios[key] = exp_ratio
            ticker_data[key][col_idx] += market_value
            total_weighted_exp += market_value * exp_ratio

        grand_total_all += market_value

    # 5. Build Header and Rows
    today = datetime.now().strftime("%-m/%-d/%Y")
    header = [today, "Asset/Accounts"] + [col["header"] for col in mapping] + [cash_col_header, "Total", "Expense Ratio"]
    rows = [header]

    def sort_key(key):
        category, ticker = key
        cat_idx = category_order.index(category) if category in category_order else len(category_order)
        tick_idx = ticker_order.index(ticker) if ticker in ticker_order else len(ticker_order)
        return (cat_idx, tick_idx, category, ticker)

    sorted_keys = sorted(ticker_data.keys(), key=sort_key)
    
    for key in sorted_keys:
        category, ticker = key
        balances = ticker_data[key]
        total = sum(balances)
        exp_ratio = ticker_exp_ratios[key]
        row = [category, ticker] + [f"${b:,.2f}" if b != 0 else "" for b in balances] + [f"${total:,.2f}", f"{exp_ratio * 100:.2f}%"]
        rows.append(row)

    # 6. Cash Row
    cash_row_ticker = " ".join([a.name for a in cash_accounts])
    cash_total = sum(cash_balances)
    cash_row = ["Cash/Cash Equivalents", cash_row_ticker] + [f"${b:,.2f}" if b != 0 else "" for b in cash_balances] + [f"${cash_total:,.2f}", "0.00%"]
    rows.append(cash_row)
    
    # 7. Total Row
    total_row = [""] * (len(header) - 2) + [f"${grand_total_all:,.2f}", f"${total_weighted_exp:,.2f}"]
    rows.append(total_row)

    # 8. Category Summary Table
    summary_data = {}
    for key, balances in ticker_data.items():
        summary_data[key[0]] = summary_data.get(key[0], Decimal(0)) + sum(balances)
    summary_data["Cash/Cash Equivalents"] = summary_data.get("Cash/Cash Equivalents", Decimal(0)) + cash_total

    summary_header = ["Category", "Allocation", "Value"]
    summary_rows = [[cat, f"{(summary_data[cat]/grand_total_all if grand_total_all > 0 else 0)*100:.2f}%", f"${summary_data[cat]:,.2f}"] 
                    for cat in sorted(summary_data.keys(), key=lambda c: category_order.index(c) if c in category_order else len(category_order))]
    summary_rows = [summary_header] + summary_rows

    combined_rows = []
    max_r = max(len(rows), len(summary_rows))
    for i in range(max_r):
        combined_rows.append((rows[i] if i < len(rows) else [""] * len(header)) + ["", ""] + (summary_rows[i] if i < len(summary_rows) else ["", "", ""]))
        
    return combined_rows, len(header), 3

def get_category_summary(db: Session, user_id) -> list[dict] | None:
    """
    Returns a list of category allocations (name, value, percentage).
    """
    snapshot = get_portfolio_snapshot(db, user_id)
    if not snapshot:
        return None
        
    summary_data = {}
    total_net_worth = Decimal(0)
    
    # Aggregate from lots
    from models.models import StockPrice
    all_tickers = {l.lot.ticker for l in snapshot.lots} | {p.position.ticker for p in snapshot.aggregate_positions if p.position.asset_type != AssetType.Cash}
    price_info = {p.ticker: p for p in db.query(StockPrice).filter(StockPrice.ticker.in_(all_tickers)).all()}

    for l in snapshot.lots:
        info = price_info.get(l.lot.ticker)
        category = info.category if (info and info.category) else "Unknown"
        if category not in summary_data:
            summary_data[category] = Decimal(0)
        summary_data[category] += l.market_value
        total_net_worth += l.market_value

    for p in snapshot.aggregate_positions:
        if p.position.asset_type == AssetType.Cash:
            category = "Cash/Cash Equivalents"
        else:
            info = price_info.get(p.position.ticker)
            category = info.category if (info and info.category) else "Unknown"
            
        if category not in summary_data:
            summary_data[category] = Decimal(0)
        summary_data[category] += p.market_value
        total_net_worth += p.market_value
        
    result = []
    for cat, val in summary_data.items():
        pct = (val / total_net_worth) if total_net_worth > 0 else Decimal(0)
        result.append({
            "category": cat,
            "value": float(val),
            "percentage": float(pct)
        })
        
    return result
