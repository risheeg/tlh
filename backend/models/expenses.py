import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base
from .enums import ExpenseStatus, ReimbursementStatus


class Expense(Base):
    """An expense parsed from a Telegram bot or entered manually."""
    __tablename__ = "expenses"
    __table_args__ = {"schema": "expenses"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True
    )
    
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    merchant: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    category: Mapped[list[str] | None] = mapped_column(ARRAY(String), index=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    trip_identifier: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User")
    account: Mapped["Account"] = relationship("Account")
    parse_detail: Mapped["ExpenseParseDetail"] = relationship(
        "ExpenseParseDetail", back_populates="expense", uselist=False
    )
    reimbursement: Mapped["ExpenseReimbursement"] = relationship(
        "ExpenseReimbursement", back_populates="expense", uselist=False
    )


class ExpenseParseDetail(Base):
    """Stores LLM/Telegram specific metadata for an expense."""
    __tablename__ = "expense_parse_details"
    __table_args__ = {"schema": "expenses"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expenses.expenses.id"), unique=True, index=True, nullable=False
    )
    
    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    parsing_status: Mapped[ExpenseStatus] = mapped_column(
        Enum(ExpenseStatus), nullable=False, default=ExpenseStatus.pending
    )
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(default=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    expense: Mapped["Expense"] = relationship("Expense", back_populates="parse_detail")


class ExpenseReimbursement(Base):
    """Reimbursement state and details for a specific expense."""
    __tablename__ = "expense_reimbursements"
    __table_args__ = {"schema": "expenses"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expenses.expenses.id"), unique=True, index=True, nullable=False
    )
    status: Mapped[ReimbursementStatus] = mapped_column(
        Enum(ReimbursementStatus), nullable=False, default=ReimbursementStatus.to_be_reimbursed
    )
    reimbursed_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    filed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    expense: Mapped["Expense"] = relationship("Expense", back_populates="reimbursement")
