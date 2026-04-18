import gspread
from core.config import settings

class GoogleSheetsService:
    def __init__(self):
        self.gc = gspread.service_account(filename=settings.google_application_credentials)
        self.sh = self.gc.open_by_key(settings.google_sheet_id)
        self.worksheet = self.sh.get_worksheet(0)  # Use the first sheet

    def sync_tickers(self, db, tickers: list[str]):
        """
        Ensures all tickers are present in the Google Sheet.
        Column A: Ticker
        Column B: Price formula (=GOOGLEFINANCE(ticker, "price"))
        """
        from models.models import StockPrice

        existing_data = self.worksheet.get_all_values()
        existing_tickers = {row[0].upper() for row in existing_data if row}

        new_tickers = [t.upper() for t in tickers if t.upper() not in existing_tickers]

        warnings = []
        if new_tickers:
            rows_to_add = []
            # Fetch existing exchange mappings from database
            stock_prices = db.query(StockPrice).filter(StockPrice.ticker.in_(new_tickers)).all()
            exchange_map = {sp.ticker: sp.exchange for sp in stock_prices if sp.exchange}

            for t in new_tickers:
                exchange = exchange_map.get(t)
                if not exchange:
                    warnings.append(f"No exchange mapping found for {t}. Using plain ticker.")
                
                formula_ticker = f"{exchange}:{t}" if exchange else t
                rows_to_add.append([t, f'=GOOGLEFINANCE("{formula_ticker}", "price")'])
            
            self.worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
        
        return len(new_tickers), warnings

    def fetch_prices(self) -> dict[str, float]:
        """
        Fetches all tickers and their current prices from the sheet.
        """
        data = self.worksheet.get_all_values()
        prices = {}
        for row in data:
            if len(row) >= 2:
                ticker = row[0].upper()
                price_str = row[1].replace("$", "").replace(",", "")
                try:
                    prices[ticker] = float(price_str)
                except ValueError:
                    # Might be the header or formula hasn't loaded yet
                    continue
        return prices

sheets_service = GoogleSheetsService()
