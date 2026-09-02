import enum

class AccountType(str, enum.Enum):
    taxable = "taxable"
    retirement = "retirement"
    savings = "savings"
    checkings = "checkings"
    cma = "cma"

class AssetType(str, enum.Enum):
    Equity = "Equity"
    Cash = "Cash"

class TransactionType(str, enum.Enum):
    buying = "buying"
    selling = "selling"
    acats = "acats"
    fee = "fee"

class LotStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    ignored = "ignored"

class ExpenseStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    needs_review = "needs_review"
    failed = "failed"

class ReimbursementStatus(str, enum.Enum):
    to_be_reimbursed = "to_be_reimbursed"
    filed = "filed"
    received = "received"
