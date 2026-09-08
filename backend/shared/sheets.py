import gspread
from gspread_formatting import *

from core.config import settings


class GoogleSheetsService:
    """Google Sheets client. Price sheet uses process env; snapshot can be per-user."""

    def __init__(
        self,
        *,
        credentials=None,
        credentials_filename: str | None = None,
        price_sheet_id: str | None = None,
        snapshot_sheet_id: str | None = None,
        init_price_sheet: bool = True,
        init_snapshot_sheet: bool = True,
    ):
        if credentials is not None:
            self.gc = gspread.service_account_from_dict(credentials)
        else:
            filename = credentials_filename or settings.google_application_credentials
            self.gc = gspread.service_account(filename=filename)

        self.price_worksheet = None
        self.snapshot_worksheet = None

        if init_price_sheet:
            sheet_id = price_sheet_id or settings.google_sheet_id
            self.price_sh = self.gc.open_by_key(sheet_id)
            self.price_worksheet = self.price_sh.get_worksheet(0)

        if init_snapshot_sheet and (
            snapshot_sheet_id or getattr(settings, "portfolio_snapshot_sheet_id", None)
        ):
            snap_id = snapshot_sheet_id or settings.portfolio_snapshot_sheet_id
            if snap_id:
                self.snapshot_sh = self.gc.open_by_key(snap_id)
                self.snapshot_worksheet = self.snapshot_sh.get_worksheet(0)

    def sync_tickers(self, db, tickers: list[str]):
        """
        Ensures all tickers are present in the Google Sheet.
        Column A: Ticker
        Column B: Price formula (=GOOGLEFINANCE(ticker, "price"))
        """
        from models.portfolio import StockPrice

        if self.price_worksheet is None:
            raise RuntimeError("Price worksheet is not configured for this Sheets client.")

        existing_data = self.price_worksheet.get_all_values()
        existing_tickers = {row[0].upper() for row in existing_data if row}

        new_tickers = [t.upper() for t in tickers if t.upper() not in existing_tickers]

        warnings = []
        if new_tickers:
            rows_to_add = []
            stock_prices = (
                db.query(StockPrice).filter(StockPrice.ticker.in_(new_tickers)).all()
            )
            exchange_map = {sp.ticker: sp.exchange for sp in stock_prices if sp.exchange}

            for t in new_tickers:
                exchange = exchange_map.get(t)
                if not exchange:
                    warnings.append(
                        f"No exchange mapping found for {t}. Using plain ticker."
                    )

                formula_ticker = f"{exchange}:{t}" if exchange else t
                rows_to_add.append(
                    [t, f'=GOOGLEFINANCE("{formula_ticker}", "price")']
                )

            self.price_worksheet.append_rows(
                rows_to_add, value_input_option="USER_ENTERED"
            )

        return len(new_tickers), warnings

    def fetch_prices(self) -> dict[str, float]:
        """Fetches all tickers and their current prices from the sheet."""
        if self.price_worksheet is None:
            raise RuntimeError("Price worksheet is not configured for this Sheets client.")

        data = self.price_worksheet.get_all_values()
        prices = {}
        for row in data:
            if len(row) >= 2:
                ticker = row[0].upper()
                price_str = row[1].replace("$", "").replace(",", "")
                try:
                    prices[ticker] = float(price_str)
                except ValueError:
                    continue
        return prices

    def get_last_snapshot_date(self) -> str | None:
        """Returns the date string from the first column of the last dated header row."""
        if self.snapshot_worksheet is None:
            return None

        all_values = self.snapshot_worksheet.get_all_values()
        if not all_values:
            return None

        for row in reversed(all_values):
            if row and row[0]:
                val = row[0].strip()
                parts = val.split("/")
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    return val
        return None

    def append_snapshot(self, rows: list[list]):
        """Appends a block of rows to the snapshot worksheet and applies formatting."""
        if self.snapshot_worksheet is None:
            raise RuntimeError(
                "Snapshot worksheet is not configured for this Sheets client."
            )

        all_values = self.snapshot_worksheet.get_all_values()

        rows_to_append = [[]] + rows if all_values else rows
        start_row = len(all_values) + (2 if all_values else 1)

        self.snapshot_worksheet.append_rows(
            rows_to_append, value_input_option="USER_ENTERED"
        )
        self._apply_formatting(start_row, len(rows), len(rows[0]))

    def _apply_formatting(self, start_row: int, num_rows: int, num_cols: int):
        end_row = start_row + num_rows - 1

        header_range = f"A{start_row}:{self._col_to_letter(num_cols)}{start_row}"
        format_cell_range(
            self.snapshot_worksheet,
            header_range,
            cellFormat(
                backgroundColor=color(0.1, 0.45, 0.82),
                textFormat=textFormat(bold=True, foregroundColor=color(1, 1, 1)),
                horizontalAlignment="CENTER",
            ),
        )

        total_range = f"A{end_row}:{self._col_to_letter(num_cols)}{end_row}"
        format_cell_range(
            self.snapshot_worksheet,
            total_range,
            cellFormat(
                backgroundColor=color(0.95, 0.95, 0.95),
                textFormat=textFormat(bold=True),
            ),
        )

        category_range = f"A{start_row + 1}:A{end_row - 1}"
        format_cell_range(
            self.snapshot_worksheet,
            category_range,
            cellFormat(textFormat=textFormat(bold=True)),
        )

        if num_cols >= 3:
            currency_range = (
                f"C{start_row + 1}:{self._col_to_letter(num_cols)}{end_row}"
            )
            format_cell_range(
                self.snapshot_worksheet,
                currency_range,
                cellFormat(horizontalAlignment="RIGHT"),
            )

    def _col_to_letter(self, n: int) -> str:
        string = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            string = chr(65 + remainder) + string
        return string


def sheets_service_for_user(
    credentials: dict, snapshot_sheet_id: str
) -> GoogleSheetsService:
    """Build a Sheets client for a user's snapshot workbook (no price sheet)."""
    return GoogleSheetsService(
        credentials=credentials,
        snapshot_sheet_id=snapshot_sheet_id,
        init_price_sheet=False,
        init_snapshot_sheet=True,
    )


_sheets_service: GoogleSheetsService | None = None


def get_sheets_service() -> GoogleSheetsService:
    """Lazy process-global client for the shared price feed."""
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = GoogleSheetsService()
    return _sheets_service


# Back-compat alias used by prices.py and scratch scripts.
class _SheetsServiceProxy:
    def __getattr__(self, name):
        return getattr(get_sheets_service(), name)


sheets_service = _SheetsServiceProxy()
