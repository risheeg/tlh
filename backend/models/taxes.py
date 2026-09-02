import enum
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


class CanonicalTaxType(str, enum.Enum):
    # Federal Income & Wages
    FED_TAXABLE_WAGES = "FED_TAXABLE_WAGES"
    FED_WITHHOLDING = "FED_WITHHOLDING"
    SUPPLEMENTAL_WAGES = "SUPPLEMENTAL_WAGES"
    
    # State & Local
    STATE_TAXABLE_WAGES = "STATE_TAXABLE_WAGES"
    STATE_WITHHOLDING = "STATE_WITHHOLDING"
    STATE_DISABILITY = "STATE_DISABILITY"       # e.g., CA SDI / CAVDI, NY SDI
    LOCAL_WITHHOLDING = "LOCAL_WITHHOLDING"     # e.g., NYC, Yonkers, Philadelphia
    LOCAL_TAXABLE_WAGES = "LOCAL_TAXABLE_WAGES"
    
    # Payroll Pre-Tax Deductions
    PRETAX_401K = "PRETAX_401K"
    PRETAX_HSA = "PRETAX_HSA"
    PRETAX_FSA = "PRETAX_FSA"
    PRETAX_HEALTH_INSURANCE = "PRETAX_HEALTH_INSURANCE"
    PRETAX_TRANSIT = "PRETAX_TRANSIT"
    
    # FICA
    FICA_SOCIAL_SECURITY = "FICA_SOCIAL_SECURITY"
    FICA_MEDICARE = "FICA_MEDICARE"
    
    # Other / Estimated Payments
    ESTIMATED_TAX_PAYMENT = "ESTIMATED_TAX_PAYMENT"
    PRIOR_YEAR_OVERPAYMENT = "PRIOR_YEAR_OVERPAYMENT"


class TaxDocumentType(str, enum.Enum):
    PAYSTUB = "PAYSTUB"
    FORM_W2 = "FORM_W2"
    FORM_1099_INT = "FORM_1099_INT"
    FORM_1099_DIV = "FORM_1099_DIV"
    FORM_1099_B = "FORM_1099_B"
    FORM_1099_MISC_NEC = "FORM_1099_MISC_NEC"
    FORM_1040_PRIOR_YEAR = "FORM_1040_PRIOR_YEAR"
    ESTIMATED_PAYMENT = "ESTIMATED_PAYMENT"


class TaxDocumentEvent(Base):
    """
    Append-only immutable record representing an ingested tax document or paystub.
    """
    __tablename__ = "tax_document_events"
    __table_args__ = {"schema": "taxes"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    tax_year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    doc_type: Mapped[TaxDocumentType] = mapped_column(Enum(TaxDocumentType), nullable=False)
    
    # Source / Issuer metadata
    issuer_name: Mapped[str] = mapped_column(String, index=True, nullable=False)  # e.g., "Atlassian US, Inc."
    check_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    pay_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    pay_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    external_ref_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True) # For idempotent deduplication
    
    # Raw ingested JSON or OCR payload for auditability
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    entries: Mapped[List["TaxLedgerEntry"]] = relationship(
        "TaxLedgerEntry", back_populates="document_event", cascade="all, delete-orphan"
    )


class TaxLedgerEntry(Base):
    """
    Normalized entry created from a TaxDocumentEvent with a CanonicalTaxType and Jurisdiction.
    """
    __tablename__ = "tax_ledger_entries"
    __table_args__ = {"schema": "taxes"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taxes.tax_document_events.id"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    tax_year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    
    canonical_tag: Mapped[CanonicalTaxType] = mapped_column(Enum(CanonicalTaxType), index=True, nullable=False)
    
    # Jurisdiction: "FED", or 2-letter state "CA", "NY", "WA", etc.
    jurisdiction: Mapped[str] = mapped_column(String(10), default="FED", index=True, nullable=False)
    locality: Mapped[str | None] = mapped_column(String(50), nullable=True) # e.g. "NYC"
    
    # Normalized cumulative YTD amount for this canonical tag as of this document
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0, nullable=False)
    
    raw_description: Mapped[str | None] = mapped_column(String, nullable=True) # Original line label from paystub
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    document_event: Mapped["TaxDocumentEvent"] = relationship("TaxDocumentEvent", back_populates="entries")
    user: Mapped["User"] = relationship("User")


class PriorYearTaxRecord(Base):
    """
    Form 1040 and State Tax return baselines from prior tax year for Safe Harbor calculations.
    """
    __tablename__ = "prior_year_tax_records"
    __table_args__ = {"schema": "taxes"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False) # e.g., 2025
    filing_status: Mapped[str] = mapped_column(String(50), default="single", nullable=False)
    
    # Federal Form 1040 key lines
    fed_agi_line_11b: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    fed_total_tax_line_24: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    fed_overpayment_applied_line_36: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0, nullable=False)
    
    # State tax returns dictionary:
    # {
    #   "CA": {"agi": 198139.00, "total_tax": 10500.00, "overpayment_applied": 0.0},
    #   "NY": {"agi": 50000.00, "total_tax": 2500.00, "overpayment_applied": 0.0}
    # }
    state_records: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User")
