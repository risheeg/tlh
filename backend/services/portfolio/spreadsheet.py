import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from .schemas import SpreadsheetConfig, TickerBalancesResult
from .queries import _get_account_market_values, _fetch_aggregated_holdings

def _get_spreadsheet_config(db: Session, user_id, accounts: dict, group_by: str) -> SpreadsheetConfig:
    """Determines the spreadsheet layout and categorizes all accounts."""
    from models.models import AccountType
    
    mapping = []
    category_order = []
    ticker_order = []
    
    # 1. Determine Primary Mapping & Orders
    is_primary_user = str(user_id) == "45a10eec-1398-483e-b7cd-be90fbd2c77c"
    if is_primary_user:
        overrides_path = Path(__file__).resolve().parent.parent.parent / "core" / "account_overrides.json"
        if overrides_path.exists():
            with open(overrides_path, "r") as f:
                overrides = json.load(f)
            mapping = overrides.get("columns", [])
            category_order = overrides.get("category_order", [])
            ticker_order = overrides.get("ticker_order", [])
    
    if not mapping: # Default dynamic grouping
        if group_by == "type":
            for header, acc_type in [("Brokerage / Taxable", AccountType.taxable), ("Retirement", AccountType.retirement)]:
                names = [a.name for a in accounts.values() if a.type == acc_type]
                if names:
                    mapping.append({"header": header, "accounts": names})
        elif group_by == "name":
            account_market_values = _get_account_market_values(db, user_id)
            sorted_accounts = sorted(
                accounts.values(), 
                key=lambda account: account_market_values.get(str(account.id), Decimal(0)), 
                reverse=True
            )
            mapping = [
                {"header": account.name, "accounts": [account.name]} 
                for account in sorted_accounts 
                if account_market_values.get(str(account.id), Decimal(0)) > 0
            ]

    # 2. Identify Cash and Unmapped accounts
    mapped_account_ids = {
        str(account.id) for column in mapping 
        for account_name in column["accounts"] 
        for account in accounts.values() 
        if account.name == account_name
    }
    
    cash_accounts = [
        account for account in accounts.values() 
        if str(account.id) not in mapped_account_ids 
        and account.type.value in ["savings", "checkings", "cma"]
    ]
    
    unmapped_accounts = [
        account for account in accounts.values()
        if str(account.id) not in mapped_account_ids
        and account not in cash_accounts
    ]
    
    return SpreadsheetConfig(
        mapping=mapping,
        category_order=category_order,
        ticker_order=ticker_order,
        cash_accounts=cash_accounts,
        unmapped_accounts=unmapped_accounts
    )

def _get_ticker_balances(db: Session, user_id, config: SpreadsheetConfig, accounts) -> TickerBalancesResult:
    """Fetches and aggregates portfolio balances into the spreadsheet structure."""
    num_mapping_columns = len(config.mapping)
    
    # Column layout: [Mapping Columns...] [Optional: Other Column] [Cash Column]
    has_unmapped = len(config.unmapped_accounts) > 0
    num_data_columns = num_mapping_columns + (1 if has_unmapped else 0)
    cash_column_index = num_data_columns
    
    aggregated_results = _fetch_aggregated_holdings(db, user_id)

    ticker_balances = {}
    ticker_expense_ratios = {}
    cash_balances_per_column = [Decimal(0)] * (num_data_columns + 1)
    
    def get_column_index(account_id):
        account = accounts[str(account_id)]
        for i, column in enumerate(config.mapping):
            if account.name in column["accounts"]:
                return i
        if account in config.unmapped_accounts:
            return num_mapping_columns
        if account in config.cash_accounts:
            return cash_column_index
        
        # This should be unreachable if the categorization logic is correct
        raise ValueError(f"Account {account.name} ({account.id}) could not be mapped to any column.")

    for result in aggregated_results:
        column_index = get_column_index(result.account_id)
        
        market_value = Decimal(str(result.market_value))
        if result.is_cash:
            cash_balances_per_column[column_index] += market_value
        else:
            key = (result.category, result.ticker)
            if key not in ticker_balances:
                ticker_balances[key] = [Decimal(0)] * (num_data_columns + 1)
                ticker_expense_ratios[key] = Decimal(str(result.expense_ratio or 0))
            ticker_balances[key][column_index] += market_value

    return TickerBalancesResult(
        ticker_balances=ticker_balances,
        ticker_expense_ratios=ticker_expense_ratios,
        cash_balances_per_column=cash_balances_per_column,
        cash_accounts=cash_accounts,
        unmapped_accounts=unmapped_accounts
    )

def generate_snapshot_rows(db: Session, user_id, group_by: str = "type") -> list[list] | None:
    """High-level orchestrator for generating spreadsheet rows."""
    from models.models import Account
    accounts = {str(account.id): account for account in db.query(Account).filter(Account.user_id == user_id).all()}
    
    # 1. Configuration & Data Fetching
    config = _get_spreadsheet_config(db, user_id, accounts, group_by)
    result = _get_ticker_balances(db, user_id, config, accounts)

    if not result.ticker_balances and not any(result.cash_balances_per_column):
        return None

    # 2. Build Holdings Table
    num_mapping_columns = len(config.mapping)
    cash_header = f"Cash ( {' '.join(account.name for account in result.cash_accounts)} )"
    
    header = [datetime.now().strftime("%-m/%-d/%Y"), "Asset/Accounts"] + [column["header"] for column in config.mapping]
    if result.unmapped_accounts:
        header.append(f"Other ({' '.join(account.name for account in result.unmapped_accounts)})")
    header += [cash_header, "Total", "Expense Ratio"]
    
    rows = [header]
    category_order_map = {category: i for i, category in enumerate(config.category_order)}
    ticker_order_map = {ticker: i for i, ticker in enumerate(config.ticker_order)}
    
    # Sort the tickers based on: 1. Custom Category Order, 2. Custom Ticker Order, 3. Category Name, 4. Ticker Name
    sorted_ticker_keys = sorted(
        result.ticker_balances.keys(), 
        key=lambda k: (category_order_map.get(k[0], 999), ticker_order_map.get(k[1], 999), k[0], k[1])
    )
    
    for category, ticker in sorted_ticker_keys:
        balances = result.ticker_balances[(category, ticker)]
        total_value = sum(balances)
        expense_ratio = result.ticker_expense_ratios[(category, ticker)]
        
        row = [category, ticker] + [f"${balance:,.2f}" if balance != 0 else "" for balance in balances] + [f"${total_value:,.2f}", f"{expense_ratio * 100:.2f}%"]
        rows.append(row)

    # 3. Cash & Totals
    cash_total_value = sum(result.cash_balances_per_column)
    cash_accounts_names = " ".join(account.name for account in result.cash_accounts)
    rows.append(
        ["Cash/Cash Equivalents", cash_accounts_names] + 
        [f"${balance:,.2f}" if balance != 0 else "" for balance in result.cash_balances_per_column] + 
        [f"${cash_total_value:,.2f}", "0.00%"]
    )
    
    total_portfolio_value = sum(sum(balances) for balances in result.ticker_balances.values()) + cash_total_value
    total_weighted_expense = sum(sum(result.ticker_balances[key]) * result.ticker_expense_ratios[key] for key in result.ticker_balances)
    
    total_row = [""] * (len(header) - 2) + [f"${total_portfolio_value:,.2f}", f"${total_weighted_expense:,.2f}"]
    rows.append(total_row)

    return rows
