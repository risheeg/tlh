from sqlalchemy.orm import Session
from datetime import datetime, timezone
from models.models import Lot, AggregatePosition, StockPrice
from services.sheets import sheets_service

def sync_stock_prices(db: Session):
    """
    Orchestrates the price synchronization process:
    1. Collects all tickers from lots and aggregate_positions.
    2. Syncs tickers to Google Sheets.
    3. Fetches latest prices from Google Sheets.
    4. Updates the stock_prices table in Neon.
    """
    # 1. Collect tickers
    lot_tickers = db.query(Lot.ticker).distinct().all()
    agg_tickers = db.query(AggregatePosition.ticker).distinct().all()
    
    all_tickers = {t[0] for t in lot_tickers} | {t[0] for t in agg_tickers}
    
    if not all_tickers:
        return {"added_to_sheet": 0, "updated_in_db": 0}

    # 2. Sync to sheet
    added_to_sheet = sheets_service.sync_tickers(list(all_tickers))

    # 3. Fetch from sheet
    prices = sheets_service.fetch_prices()

    # 4. Update Database
    updated_count = 0
    for ticker, price in prices.items():
        if ticker in all_tickers:
            existing_price = db.get(StockPrice, ticker)
            if existing_price:
                existing_price.price = price
                existing_price.last_updated = datetime.now(timezone.utc)
            else:
                new_price = StockPrice(
                    ticker=ticker,
                    price=price,
                    last_updated=datetime.now(timezone.utc)
                )
                db.add(new_price)
            updated_count += 1
    
    db.commit()
    return {
        "added_to_sheet": added_to_sheet,
        "updated_in_db": updated_count,
        "total_tickers_requested": len(all_tickers)
    }
