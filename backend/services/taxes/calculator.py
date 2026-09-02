from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models.taxes import (
    CanonicalTaxType,
    TaxDocumentEvent,
    TaxLedgerEntry,
    PriorYearTaxRecord,
)


@dataclass
class Form1040Summary:
    tax_year: int
    w2_taxable_wages_line_1a: float
    total_income_line_9: float
    adjustments_line_10: float
    agi_line_11b: float
    standard_deduction_line_12e: float
    taxable_income_line_15: float
    projected_tax_liability_line_24: float
    federal_withholding_line_25a: float
    estimated_tax_payments_line_26: float
    total_payments_line_33: float
    amount_owed_line_37: float
    overpayment_refund_line_34: float
    
    # Safe Harbor Metrics
    safe_harbor_target: float
    safe_harbor_met: bool
    remaining_safe_harbor_shortfall: float
    suggested_quarterly_payment: float


@dataclass
class StateTaxSummary:
    state_code: str
    tax_year: int
    taxable_wages_ytd: float
    withheld_ytd: float
    disability_tax_ytd: float
    projected_state_tax: float
    state_safe_harbor_target: float
    amount_owed: float
    suggested_quarterly_payment: float


@dataclass
class TaxProjectionResult:
    user_id: str
    tax_year: int
    as_of_date: Optional[date]
    documents_count: int
    form_1040: Form1040Summary
    state_summaries: Dict[str, StateTaxSummary]
    canonical_totals: Dict[str, Dict[str, float]] # e.g. {"FED": {"FED_TAXABLE_WAGES": ...}, "CA": {...}}


def calculate_2026_federal_income_tax(taxable_income: float, filing_status: str = "single") -> float:
    """
    Standard IRS Federal Income Tax Brackets for 2026.
    """
    if taxable_income <= 0:
        return 0.0

    # 2026 Single Brackets (Estimated IRS adjustments)
    # 10%: $0 to $11,925
    # 12%: $11,925 to $48,475
    # 22%: $48,475 to $103,350
    # 24%: $103,350 to $197,300
    # 32%: $197,300 to $250,525
    # 35%: $250,525 to $626,350
    # 37%: over $626,350
    brackets = [
        (11925, 0.10),
        (48475, 0.12),
        (103350, 0.22),
        (197300, 0.24),
        (250525, 0.32),
        (626350, 0.35),
        (float("inf"), 0.37),
    ]
    
    tax = 0.0
    prev_bound = 0.0
    for bound, rate in brackets:
        if taxable_income > bound:
            tax += (bound - prev_bound) * rate
            prev_bound = bound
        else:
            tax += (taxable_income - prev_bound) * rate
            break
            
    return round(tax, 2)


def calculate_ca_state_tax(taxable_income: float) -> float:
    """
    California Franchise Tax Board 2025/2026 Single tax brackets.
    """
    if taxable_income <= 0:
        return 0.0

    brackets = [
        (10412, 0.01),
        (24684, 0.02),
        (38959, 0.04),
        (54081, 0.06),
        (68350, 0.08),
        (349137, 0.093),
        (418961, 0.103),
        (698271, 0.113),
        (float("inf"), 0.123),
    ]
    
    tax = 0.0
    prev_bound = 0.0
    for bound, rate in brackets:
        if taxable_income > bound:
            tax += (bound - prev_bound) * rate
            prev_bound = bound
        else:
            tax += (taxable_income - prev_bound) * rate
            break
            
    return round(tax, 2)


def compute_tax_projections_from_logs(
    db: Session,
    user_id: UUID,
    tax_year: int = 2026
) -> TaxProjectionResult:
    """
    Replays all append-only tax document events and aggregates canonical ledger entries into tax forms.
    """
    # 1. Fetch prior year baseline record
    prior_year_record = (
        db.query(PriorYearTaxRecord)
        .filter(
            PriorYearTaxRecord.user_id == user_id,
            PriorYearTaxRecord.tax_year == tax_year - 1
        )
        .first()
    )

    prior_year_tax = float(prior_year_record.fed_total_tax_line_24) if prior_year_record else 0.0
    prior_year_agi = float(prior_year_record.fed_agi_line_11b) if prior_year_record else 0.0
    prior_overpayment = float(prior_year_record.fed_overpayment_applied_line_36) if prior_year_record else 0.0
    filing_status = prior_year_record.filing_status if prior_year_record else "single"

    # 2. Fetch all append-only events for this tax year, grouped by employer/source
    events = (
        db.query(TaxDocumentEvent)
        .filter(
            TaxDocumentEvent.user_id == user_id,
            TaxDocumentEvent.tax_year == tax_year
        )
        .order_by(TaxDocumentEvent.check_date.asc(), TaxDocumentEvent.created_at.asc())
        .all()
    )

    # 3. For each employer/source, take the latest YTD amounts (or sum discrete documents)
    # We maintain canonical totals per jurisdiction: { "FED": {tag: amount}, "CA": {tag: amount} }
    # Group events by issuer
    issuer_latest_events: Dict[str, TaxDocumentEvent] = {}
    estimated_payments_total = 0.0

    for ev in events:
        if ev.doc_type == TaxDocumentEvent:
            pass
        issuer_latest_events[ev.issuer_name] = ev

    # Aggregate canonical tags across all employers (using each employer's latest paystub)
    canonical_totals: Dict[str, Dict[str, float]] = {}

    for issuer, latest_event in issuer_latest_events.items():
        for entry in latest_event.entries:
            jur = entry.jurisdiction
            tag_name = entry.canonical_tag.value
            
            if jur not in canonical_totals:
                canonical_totals[jur] = {}
            
            # Use YTD amount from the latest paystub
            val = float(entry.ytd_amount) if float(entry.ytd_amount) > 0 else float(entry.period_amount)
            canonical_totals[jur][tag_name] = canonical_totals[jur].get(tag_name, 0.0) + val

    # 4. Form 1040 Aggregations
    fed_data = canonical_totals.get("FED", {})
    w2_wages_1a = fed_data.get(CanonicalTaxType.FED_TAXABLE_WAGES.value, 0.0)
    fed_withholding_25a = fed_data.get(CanonicalTaxType.FED_WITHHOLDING.value, 0.0)
    
    total_income_9 = w2_wages_1a
    adjustments_10 = 0.0 # e.g., HSA if contributed outside payroll
    agi_11b = total_income_9 - adjustments_10
    
    std_deduction_12e = 15750.0 if filing_status == "single" else 31500.0
    taxable_income_15 = max(0.0, agi_11b - std_deduction_12e)
    
    projected_tax_24 = calculate_2026_federal_income_tax(taxable_income_15, filing_status)
    
    # Safe Harbor Calculation
    # AGI > $150k -> 110% of prior year total tax
    multiplier = 1.10 if prior_year_agi > 150000 else 1.00
    safe_harbor_target = round(prior_year_tax * multiplier, 2)
    
    total_payments_33 = fed_withholding_25a + estimated_payments_total + prior_overpayment
    
    amount_owed_37 = max(0.0, round(projected_tax_24 - total_payments_33, 2))
    overpayment_refund_34 = max(0.0, round(total_payments_33 - projected_tax_24, 2))
    
    safe_harbor_met = total_payments_33 >= safe_harbor_target
    safe_harbor_shortfall = max(0.0, round(safe_harbor_target - total_payments_33, 2))
    suggested_quarterly = round(safe_harbor_shortfall / 4.0, 2)

    form_1040 = Form1040Summary(
        tax_year=tax_year,
        w2_taxable_wages_line_1a=w2_wages_1a,
        total_income_line_9=total_income_9,
        adjustments_line_10=adjustments_10,
        agi_line_11b=agi_11b,
        standard_deduction_line_12e=std_deduction_12e,
        taxable_income_line_15=taxable_income_15,
        projected_tax_liability_line_24=projected_tax_24,
        federal_withholding_line_25a=fed_withholding_25a,
        estimated_tax_payments_line_26=estimated_payments_total,
        total_payments_line_33=total_payments_33,
        amount_owed_line_37=amount_owed_37,
        overpayment_refund_line_34=overpayment_refund_34,
        safe_harbor_target=safe_harbor_target,
        safe_harbor_met=safe_harbor_met,
        remaining_safe_harbor_shortfall=safe_harbor_shortfall,
        suggested_quarterly_payment=suggested_quarterly,
    )

    # 5. State Tax Summaries (Per state code)
    state_summaries: Dict[str, StateTaxSummary] = {}
    for jur, tags in canonical_totals.items():
        if jur == "FED":
            continue
        
        state_wages = tags.get(CanonicalTaxType.STATE_TAXABLE_WAGES.value, tags.get(CanonicalTaxType.FED_TAXABLE_WAGES.value, 0.0))
        state_withheld = tags.get(CanonicalTaxType.STATE_WITHHOLDING.value, 0.0)
        state_sdi = tags.get(CanonicalTaxType.STATE_DISABILITY.value, 0.0)
        
        projected_state_tax = calculate_ca_state_tax(max(0.0, state_wages - 5363.0)) if jur == "CA" else 0.0
        
        # State safe harbor (e.g. CA is typically 110% of prior year CA tax)
        prior_state_tax = 0.0
        if prior_year_record and prior_year_record.state_records:
            prior_state_tax = float(prior_year_record.state_records.get(jur, {}).get("total_tax", 0.0))
        
        state_safe_harbor = round(prior_state_tax * multiplier, 2)
        state_owed = max(0.0, round(projected_state_tax - state_withheld, 2))
        state_shortfall = max(0.0, round(state_safe_harbor - state_withheld, 2))
        
        state_summaries[jur] = StateTaxSummary(
            state_code=jur,
            tax_year=tax_year,
            taxable_wages_ytd=state_wages,
            withheld_ytd=state_withheld,
            disability_tax_ytd=state_sdi,
            projected_state_tax=projected_state_tax,
            state_safe_harbor_target=state_safe_harbor,
            amount_owed=state_owed,
            suggested_quarterly_payment=round(state_shortfall / 4.0, 2),
        )

    return TaxProjectionResult(
        user_id=str(user_id),
        tax_year=tax_year,
        as_of_date=events[-1].check_date if events else None,
        documents_count=len(events),
        form_1040=form_1040,
        state_summaries=state_summaries,
        canonical_totals=canonical_totals,
    )
