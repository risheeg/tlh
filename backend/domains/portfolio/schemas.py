from dataclasses import dataclass
from decimal import Decimal

@dataclass
class SpreadsheetConfig:
    """Configuration for the spreadsheet layout and account groupings."""
    mapping: list
    category_order: list
    ticker_order: list
    cash_accounts: list
    unmapped_accounts: list


@dataclass
class TickerBalancesResult:
    """Container for the results of the ticker balance aggregation."""
    
    # Mapping of (category, ticker) -> list of market values for each spreadsheet column
    ticker_balances: dict[tuple[str, str], list[Decimal]]
    
    # Mapping of (category, ticker) -> expense ratio of that specific ticker
    ticker_expense_ratios: dict[tuple[str, str], Decimal]
    
    # Sum of all cash holdings (is_cash=True) for each column in the spreadsheet
    cash_balances_per_column: list[Decimal]
    
    # List of accounts identified as bank-style cash (e.g., Savings, Checkings)
    cash_accounts: list
    
    # List of accounts that were neither mapped nor categorized as cash (safety catch)
    unmapped_accounts: list
