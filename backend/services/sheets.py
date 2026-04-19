import gspread
from core.config import settings
from gspread_formatting import *

class GoogleSheetsService:
    def __init__(self):
        self.gc = gspread.service_account(filename=settings.google_application_credentials)
        
        # Price Tracking Sheet
        self.price_sh = self.gc.open_by_key(settings.google_sheet_id)
        self.price_worksheet = self.price_sh.get_worksheet(0)
        
        # Portfolio Snapshot Sheet
        self.snapshot_sh = self.gc.open_by_key(settings.portfolio_snapshot_sheet_id)
        self.snapshot_worksheet = self.snapshot_sh.get_worksheet(0)

    def sync_tickers(self, db, tickers: list[str]):
        """
        Ensures all tickers are present in the Google Sheet.
        Column A: Ticker
        Column B: Price formula (=GOOGLEFINANCE(ticker, "price"))
        """
        from models.models import StockPrice

        existing_data = self.price_worksheet.get_all_values()
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
            
            self.price_worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
        
        return len(new_tickers), warnings

    def fetch_prices(self) -> dict[str, float]:
        """
        Fetches all tickers and their current prices from the sheet.
        """
        data = self.price_worksheet.get_all_values()
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

    def get_last_snapshot_date(self) -> str | None:
        """
        Returns the date string from the first column of the last non-empty row 
        that looks like a header (or just the first column of the last row).
        """
        all_values = self.snapshot_worksheet.get_all_values()
        if not all_values:
            return None
        
        # Iterate backwards to find the last date in column 0
        for row in reversed(all_values):
            if row and row[0]:
                val = row[0].strip()
                # Simple check for M/D/YYYY or MM/DD/YYYY
                parts = val.split('/')
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    return val
        return None

    def append_snapshot(self, rows: list[list], num_main_cols: int, num_summary_cols: int):
        """
        Appends a block of rows to the snapshot worksheet and applies formatting.
        """
        all_values = self.snapshot_worksheet.get_all_values()
        
        # Prepend an empty row for spacing if not starting from scratch
        rows_to_append = [[]] + rows if all_values else rows
        start_row = len(all_values) + (2 if all_values else 1)
        
        self.snapshot_worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        self._apply_formatting(start_row, len(rows), num_main_cols, num_summary_cols)

    def _apply_formatting(self, start_row: int, num_rows: int, num_main_cols: int, num_summary_cols: int):
        """
        Applies colors, bolding, and alignment to the snapshot block.
        """
        end_row = start_row + num_rows - 1
        
        # 1. Main Header Formatting
        main_header_range = f"A{start_row}:{self._col_to_letter(num_main_cols)}{start_row}"
        format_cell_range(self.snapshot_worksheet, main_header_range, cellFormat(
            backgroundColor=color(0.1, 0.45, 0.82), # Dark Blue
            textFormat=textFormat(bold=True, foregroundColor=color(1, 1, 1)),
            horizontalAlignment='CENTER'
        ))
        
        # 2. Summary Header Formatting
        summary_start_col = num_main_cols + 3 # +2 padding
        summary_header_range = f"{self._col_to_letter(summary_start_col)}{start_row}:{self._col_to_letter(summary_start_col + num_summary_cols - 1)}{start_row}"
        format_cell_range(self.snapshot_worksheet, summary_header_range, cellFormat(
            backgroundColor=color(0.11, 0.46, 0.24), # Dark Green
            textFormat=textFormat(bold=True, foregroundColor=color(1, 1, 1)),
            horizontalAlignment='CENTER'
        ))
        
        # 3. Totals Row Formatting (Bold + Light Grey Background)
        total_range = f"A{end_row}:{self._col_to_letter(summary_start_col + num_summary_cols - 1)}{end_row}"
        format_cell_range(self.snapshot_worksheet, total_range, cellFormat(
            backgroundColor=color(0.95, 0.95, 0.95),
            textFormat=textFormat(bold=True)
        ))
        
        # 4. Sub-headers (Category Names)
        # Category names are in Column A. We'll bold any cell in Col A that is not empty.
        category_range = f"A{start_row + 1}:A{end_row - 1}"
        format_cell_range(self.snapshot_worksheet, category_range, cellFormat(textFormat=textFormat(bold=True)))
        
        # 5. Right-align all currency columns
        # Main table currency starts from Col C (3) to num_main_cols
        if num_main_cols >= 3:
            currency_range = f"C{start_row + 1}:{self._col_to_letter(num_main_cols)}{end_row}"
            format_cell_range(self.snapshot_worksheet, currency_range, cellFormat(horizontalAlignment='RIGHT'))
            
        # Summary table value column
        summary_val_col = summary_start_col + 2
        summary_val_range = f"{self._col_to_letter(summary_val_col)}{start_row + 1}:{self._col_to_letter(summary_val_col)}{end_row}"
        format_cell_range(self.snapshot_worksheet, summary_val_range, cellFormat(horizontalAlignment='RIGHT'))

    def _col_to_letter(self, n: int) -> str:
        """Converts column number to letter (1 -> A, 2 -> B, ..., 27 -> AA)"""
        string = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            string = chr(65 + remainder) + string
        return string

sheets_service = GoogleSheetsService()
