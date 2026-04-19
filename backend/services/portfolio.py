from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from models.models import Lot, AggregatePosition, StockPrice, LotStatus, AssetType
from schemas.portfolio import EnrichedLot, EnrichedAggregatePosition, PortfolioSnapshot

def get_portfolio_snapshot(db: Session, user_id) -> PortfolioSnapshot | None:
    """
    Returns a snapshot of the user's portfolio with current prices and market values.
    Only returns if ALL stock prices for the user's EQUITY tickers have been updated in the last 24 hours.
    """
    # 1. Fetch data
    lots = db.query(Lot).filter(Lot.user_id == user_id, Lot.status == LotStatus.active).all()
    agg_positions = db.query(AggregatePosition).filter(AggregatePosition.user_id == user_id).all()
    
    # 2. Get tickers and prices (only for Equity)
    # Assume all lots are Equity
    equity_tickers = {l.ticker for l in lots} | {p.ticker for p in agg_positions if p.asset_type == AssetType.Equity}
    
    if not equity_tickers and not agg_positions:
        return PortfolioSnapshot(
            lots=[],
            aggregate_positions=[],
            total_net_worth=Decimal(0),
            last_updated=None
        )
        
    prices = {p.ticker: p for p in db.query(StockPrice).filter(StockPrice.ticker.in_(equity_tickers)).all()}
    
    # 3. Check freshness (ALL equity prices must be updated in last 24h)
    now = datetime.now(timezone.utc)
    fresh_threshold = now - timedelta(hours=24)
    
    # Verify all equity tickers have a price record and all those records are fresh
    all_equity_have_prices = all(t in prices for t in equity_tickers)
    all_prices_fresh = all(
        p.last_updated >= fresh_threshold 
        for p in prices.values()
    )
    
    if not all_equity_have_prices or not all_prices_fresh:
        return None

    # 4. Enrich data and calculate net worth
    enriched_lots = []
    total_net_worth = Decimal(0)
    latest_update = None
    
    for lot in lots:
        price_obj = prices.get(lot.ticker)
        price = Decimal(str(price_obj.price)) if price_obj else None
        market_value = Decimal(str(lot.quantity)) * price if price is not None else Decimal(0)
        
        if price_obj and (latest_update is None or price_obj.last_updated > latest_update):
            latest_update = price_obj.last_updated
            
        enriched_lots.append(EnrichedLot(
            lot=lot,
            current_price=price,
            market_value=market_value
        ))
        total_net_worth += market_value
        
    enriched_agg = []
    for pos in agg_positions:
        if pos.asset_type == AssetType.Cash:
            price = Decimal("1.00")
            market_value = Decimal(str(pos.quantity))
            # Cash doesn't have a "latest_update" from StockPrice
        else:
            price_obj = prices.get(pos.ticker)
            price = Decimal(str(price_obj.price)) if price_obj else None
            market_value = Decimal(str(pos.quantity)) * price if price is not None else Decimal(0)
            
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
