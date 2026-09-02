from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PaystubLineItemInput(BaseModel):
    description: str
    amount: float = 0.0                # YTD cumulative amount from paystub (or document amount)
    jurisdiction: Optional[str] = None # Optional override ("FED", "CA", "NY")
    locality: Optional[str] = None


class PaystubIngestRequest(BaseModel):
    user_id: UUID
    tax_year: int = 2026
    employer_name: str
    check_date: date
    pay_period_start: Optional[date] = None
    pay_period_end: Optional[date] = None
    external_ref_id: Optional[str] = None
    line_items: List[PaystubLineItemInput]
    raw_payload: Optional[Dict[str, Any]] = Field(default_factory=dict)


class StatePriorYearTaxRecordInput(BaseModel):
    state_code: str                          # e.g., "CA", "NY"
    agi: float                               # State Adjusted Gross Income
    total_tax: float                         # State Total Tax Liability (e.g. CA Form 540 line 64)
    overpayment_applied: float = 0.0         # Refund from prior state return applied to 2026


class PriorYearTaxRecordInput(BaseModel):
    user_id: UUID
    tax_year: int = 2025
    filing_status: str = "single"
    
    # Federal Form 1040 Fields
    fed_agi_line_11b: float
    fed_total_tax_line_24: float
    fed_overpayment_applied_line_36: float = 0.0
    
    # Multi-State Prior Year Returns
    state_records: List[StatePriorYearTaxRecordInput] = Field(default_factory=list)


class TaxLedgerEntryResponse(BaseModel):
    id: UUID
    tax_year: int
    canonical_tag: str
    jurisdiction: str
    locality: Optional[str]
    amount: float
    raw_description: Optional[str]


class TaxDocumentEventResponse(BaseModel):
    id: UUID
    user_id: UUID
    tax_year: int
    doc_type: str
    issuer_name: str
    check_date: Optional[date]
    pay_period_end: Optional[date]
    external_ref_id: Optional[str]
    entries: List[TaxLedgerEntryResponse]
