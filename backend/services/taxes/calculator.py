from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models.taxes import (
    CanonicalTaxType,
    TaxDocumentEvent,
    TaxLedgerEntry,
    PriorYearTaxRecord,
)


@dataclass
class TaxBracketBreakdown:
    bracket_rate: float
    bracket_rate_percent: str
    income_in_bracket: float
    tax_for_bracket: float
    cumulative_tax: float
    range_description: str


@dataclass
class Form1040Summary:
    tax_year: int
    w2_taxable_wages_line_1a: float
    total_income_line_9: float
    adjustments_line_10: float
    agi_line_11b: float
    standard_deduction_line_12e: float
    taxable_income_line_15: float
    
    # Tax computation breakdown across brackets
    bracket_breakdowns: List[TaxBracketBreakdown]
    projected_tax_liability_line_24: float
    effective_tax_rate: float
    marginal_tax_rate: float
    
    # Payments & safe harbor
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
    standard_deduction: float
    taxable_income: float
    bracket_breakdowns: List[TaxBracketBreakdown]
    projected_state_tax: float
    effective_tax_rate: float
    withheld_ytd: float
    disability_tax_ytd: float
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
    canonical_totals: Dict[str, Dict[str, float]]


# ---------------------------------------------------------------------------
# Federal Bracket Calculation
# ---------------------------------------------------------------------------

FEDERAL_2026_SINGLE_BRACKETS = [
    (0, 11925, 0.10, "$0 to $11,925"),
    (11925, 48475, 0.12, "$11,925 to $48,475"),
    (48475, 103350, 0.22, "$48,475 to $103,350"),
    (103350, 197300, 0.24, "$103,350 to $197,300"),
    (197300, 250525, 0.32, "$197,300 to $250,525"),
    (250525, 626350, 0.35, "$250,525 to $626,350"),
    (626350, float("inf"), 0.37, "over $626,350"),
]


def calculate_detailed_federal_tax(taxable_income: float, filing_status: str = "single") -> tuple[float, List[TaxBracketBreakdown], float, float]:
    """
    Computes federal tax multiplying income across each progressive bracket tier.
    Returns: (total_tax, bracket_breakdowns, effective_rate, marginal_rate)
    """
    if taxable_income <= 0:
        return 0.0, [], 0.0, 0.0

    breakdowns: List[TaxBracketBreakdown] = []
    total_tax = 0.0
    marginal_rate = 0.10

    for lower, upper, rate, desc in FEDERAL_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            marginal_rate = rate
            income_in_tier = min(taxable_income, upper) - lower
            tax_in_tier = round(income_in_tier * rate, 2)
            total_tax += tax_in_tier
            
            breakdowns.append(TaxBracketBreakdown(
                bracket_rate=rate,
                bracket_rate_percent=f"{int(rate * 100)}%",
                income_in_bracket=round(income_in_tier, 2),
                tax_for_bracket=tax_in_tier,
                cumulative_tax=round(total_tax, 2),
                range_description=desc
            ))
        else:
            break

    total_tax = round(total_tax, 2)
    effective_rate = round((total_tax / taxable_income) * 100, 2) if taxable_income > 0 else 0.0
    return total_tax, breakdowns, effective_rate, round(marginal_rate * 100, 2)


# ---------------------------------------------------------------------------
# California Bracket Calculation
# ---------------------------------------------------------------------------

CA_2026_SINGLE_BRACKETS = [
    (0, 10412, 0.01, "$0 to $10,412"),
    (10412, 24684, 0.02, "$10,412 to $24,684"),
    (24684, 38959, 0.04, "$24,684 to $38,959"),
    (38959, 54081, 0.06, "$38,959 to $54,081"),
    (54081, 68350, 0.08, "$54,081 to $68,350"),
    (68350, 349137, 0.093, "$68,350 to $349,137"),
    (349137, 418961, 0.103, "$349,137 to $418,961"),
    (418961, 698271, 0.113, "$418,961 to $698,271"),
    (698271, float("inf"), 0.123, "over $698,271"),
]


def calculate_detailed_ca_tax(taxable_income: float) -> tuple[float, List[TaxBracketBreakdown], float]:
    """
    Computes California state tax multiplying income across each progressive bracket tier.
    """
    if taxable_income <= 0:
        return 0.0, [], 0.0

    breakdowns: List[TaxBracketBreakdown] = []
    total_tax = 0.0

    for lower, upper, rate, desc in CA_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            income_in_tier = min(taxable_income, upper) - lower
            tax_in_tier = round(income_in_tier * rate, 2)
            total_tax += tax_in_tier
            
            breakdowns.append(TaxBracketBreakdown(
                bracket_rate=rate,
                bracket_rate_percent=f"{rate * 100:.1f}%",
                income_in_bracket=round(income_in_tier, 2),
                tax_for_bracket=tax_in_tier,
                cumulative_tax=round(total_tax, 2),
                range_description=desc
            ))
        else:
            break

    total_tax = round(total_tax, 2)
    effective_rate = round((total_tax / taxable_income) * 100, 2) if taxable_income > 0 else 0.0
    return total_tax, breakdowns, effective_rate


# ---------------------------------------------------------------------------
# Multi-Document Aggregation & Projection Engine
# ---------------------------------------------------------------------------

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

    # 3. For each employer/source, take the latest YTD amounts
    issuer_latest_events: Dict[str, TaxDocumentEvent] = {}
    estimated_payments_total = 0.0

    for ev in events:
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
    adjustments_10 = 0.0
    agi_11b = total_income_9 - adjustments_10
    
    std_deduction_12e = 15750.0 if filing_status == "single" else 31500.0
    taxable_income_15 = max(0.0, agi_11b - std_deduction_12e)
    
    # Detailed Federal progressive brackets calculation
    projected_tax_24, fed_breakdowns, fed_eff_rate, fed_marg_rate = calculate_detailed_federal_tax(
        taxable_income_15, filing_status
    )
    
    # Safe Harbor Calculation (110% for AGI > 150k)
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
        bracket_breakdowns=fed_breakdowns,
        projected_tax_liability_line_24=projected_tax_24,
        effective_tax_rate=fed_eff_rate,
        marginal_tax_rate=fed_marg_rate,
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

    # 5. State Tax Summaries with Progressive Brackets (e.g. CA)
    state_summaries: Dict[str, StateTaxSummary] = {}
    for jur, tags in canonical_totals.items():
        if jur == "FED":
            continue
        
        state_wages = tags.get(CanonicalTaxType.STATE_TAXABLE_WAGES.value, w2_wages_1a)
        state_withheld = tags.get(CanonicalTaxType.STATE_WITHHOLDING.value, 0.0)
        state_sdi = tags.get(CanonicalTaxType.STATE_DISABILITY.value, 0.0)
        
        ca_std_deduction = 5363.0 if jur == "CA" else 0.0
        state_taxable_income = max(0.0, state_wages - ca_std_deduction)
        
        projected_state_tax = 0.0
        state_breakdowns: List[TaxBracketBreakdown] = []
        state_eff_rate = 0.0
        
        if jur == "CA":
            projected_state_tax, state_breakdowns, state_eff_rate = calculate_detailed_ca_tax(state_taxable_income)
        
        # State safe harbor (110% of prior year state tax)
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
            standard_deduction=ca_std_deduction,
            taxable_income=state_taxable_income,
            bracket_breakdowns=state_breakdowns,
            projected_state_tax=projected_state_tax,
            effective_tax_rate=state_eff_rate,
            withheld_ytd=state_withheld,
            disability_tax_ytd=state_sdi,
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
