import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base
from .enums import AccountType

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="user")
    lots: Mapped[list["Lot"]] = relationship("Lot", back_populates="user")
    aggregate_positions: Mapped[list["AggregatePosition"]] = relationship("AggregatePosition", back_populates="user")
    cash_holdings: Mapped[list["CashHolding"]] = relationship("CashHolding", back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="accounts")
    lots: Mapped[list["Lot"]] = relationship("Lot", back_populates="account")
    aggregate_positions: Mapped[list["AggregatePosition"]] = relationship("AggregatePosition", back_populates="account")
    cash_holdings: Mapped[list["CashHolding"]] = relationship("CashHolding", back_populates="account")
