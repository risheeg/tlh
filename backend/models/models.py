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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
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
    original_purchase_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    current_adjusted_basis: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[LotStatus] = mapped_column(
        Enum(LotStatus), nullable=False, default=LotStatus.active
    )
    external_ref_id: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="lots")
    account: Mapped["Account"] = relationship("Account", back_populates="lots")


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
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType), nullable=False, default=AssetType.Equity
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="aggregate_positions")
    account: Mapped["Account"] = relationship("Account", back_populates="aggregate_positions")


class StockPrice(Base):
    """Stores the latest price for a stock ticker."""
    __tablename__ = "stock_prices"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
