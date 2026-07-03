"""
SQLAlchemy ORM models mapping directly to the database schema.
"""
import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

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


class LotStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    ignored = "ignored"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="user")
    lots: Mapped[list["Lot"]] = relationship("Lot", back_populates="user")
    aggregate_positions: Mapped[list["AggregatePosition"]] = relationship(
        "AggregatePosition", back_populates="user"
    )
    cash_holdings: Mapped[list["CashHolding"]] = relationship(
        "CashHolding", back_populates="user"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user"
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="accounts")
    lots: Mapped[list["Lot"]] = relationship("Lot", back_populates="account")
    aggregate_positions: Mapped[list["AggregatePosition"]] = relationship(
        "AggregatePosition", back_populates="account"
    )
    cash_holdings: Mapped[list["CashHolding"]] = relationship(
        "CashHolding", back_populates="account"
    )


class Lot(Base):
    """Individual tax lot. Must be associated with a taxable account."""
    __tablename__ = "lots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=False
    )
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    original_purchase_price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    current_adjusted_basis: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[LotStatus] = mapped_column(
        Enum(LotStatus), nullable=False, default=LotStatus.active
    )
    external_ref_id: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="lots")
    account: Mapped["Account"] = relationship("Account", back_populates="lots")
    history: Mapped[list["LotHistory"]] = relationship("LotHistory", back_populates="lot")


class AggregatePosition(Base):
    """High-level position total for an account (typically retirement accounts)."""
    __tablename__ = "aggregate_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=False
    )
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="aggregate_positions")
    account: Mapped["Account"] = relationship("Account", back_populates="aggregate_positions")


class CashHolding(Base):
    """Simple cash balance for an account."""
    __tablename__ = "cash_holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="cash_holdings")
    account: Mapped["Account"] = relationship("Account", back_populates="cash_holdings")


class StockPrice(Base):
    """Stores the latest price for a stock ticker."""
    __tablename__ = "stock_prices"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    expense_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class StockSplit(Base):
    """Corporate action recording a stock split applied to stored holdings."""
    __tablename__ = "stock_splits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    split_numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    split_denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("ticker", "effective_date", name="uq_stock_split_ticker_effective_date"),
    )


class Transaction(Base):
    """A financial transaction such as buying, selling, or ACATS transfer."""
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    origin_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True
    )
    destination_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="transactions")
    origin_account: Mapped["Account"] = relationship("Account", foreign_keys=[origin_account_id])
    destination_account: Mapped["Account"] = relationship("Account", foreign_keys=[destination_account_id])
    lot_histories: Mapped[list["LotHistory"]] = relationship("LotHistory", back_populates="transaction")


class LotHistory(Base):
    """History of a lot, linking it to various transactions."""
    __tablename__ = "lot_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lots.id"), index=True, nullable=False
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), index=True, nullable=False
    )
    quantity_affected: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    lot: Mapped["Lot"] = relationship("Lot", back_populates="history")
    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="lot_histories")


class PortfolioAggregatedPosition(Base):
    """
    Unified view of aggregated lots and aggregate positions (Book Value).
    This model is mapped to a database VIEW.
    """
    __tablename__ = "portfolio_aggregated_positions"

    holding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True)
    ticker: Mapped[str] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8))
    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 2))
    holding_type: Mapped[str] = mapped_column(String)  # 'lot' or 'aggregate'
    asset_type: Mapped[str] = mapped_column(String)  # 'Equity' or 'Cash'


class PortfolioHoldingEnriched(Base):

    """
    Unified view of lots and aggregate positions, enriched with price data.
    This model is mapped to a database VIEW, not a table.
    """
    __tablename__ = "portfolio_holdings_enriched"

    holding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True)
    ticker: Mapped[str] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8))
    original_purchase_price: Mapped[float | None] = mapped_column(Numeric(18, 8))
    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 2))
    holding_type: Mapped[str] = mapped_column(String)  # 'lot' or 'aggregate'
    asset_type: Mapped[str] = mapped_column(String)  # 'Equity' or 'Cash'
    category: Mapped[str | None] = mapped_column(String)
    expense_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6))
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 2))

    market_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    price_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NetWorthSnapshot(Base):
    """Historical snapshot of total net worth and portfolio breakdown."""
    __tablename__ = "net_worth_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_net_worth: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    
    # Stores breakdown by category, account, asset_type:
    # { "categories": {...}, "accounts": {...}, "asset_types": {...} }
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_user_snapshot_date"),
    )

    user: Mapped["User"] = relationship("User")


class Document(Base):
    """Processed personal document indexed by the vault ingest pipeline."""
    __tablename__ = "documents"
    __table_args__ = {"schema": "vault_ingest"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True
    )
    r2_original_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_parsed_json_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_model: Mapped[str] = mapped_column(String, nullable=False)
    parsed_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

