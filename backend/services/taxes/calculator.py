from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from models.portfolio import PortfolioHoldingEnriched
from models.taxes import (
    CanonicalTaxType,
    TaxDocumentEvent,
    TaxLedgerEntry,
    PriorYearTaxRecord,
)


@dataclass
class PretaxPayrollBreakdown:
    traditional_401k_ytd: float            # Pre-tax 401(k) contributions (e.g. $16,184.14)
    hsa_employee_ytd: float                # Pre-tax HSA Section 125 contributions (e.g. $3,400.00)
    fsa_health_ytd: float                  # Pre-tax FSA contributions (e.g. $10.45)
    transit_commuter_ytd: float            # Pre-tax commuter/transit (e.g. $215.00)
    medical_dental_insurance_ytd: float    # Pre-tax healthcare premiums (e.g. $92.50)
    total_pretax_deductions_ytd: float     # Total excluded from Box 1 / Line 1a ($19,902.09)
    gross_pay_before_pretax: float         # Total Gross Pay ($193,645.63)
    tax_savings_from_pretax: float         # Direct income tax saved via pre-tax exclusions


@dataclass
class TaxBracketBreakdown:
    bracket_rate: float
    bracket_rate_percent: str
    income_in_bracket: float
    tax_for_bracket: float
    cumulative_tax: float
    range_description: str


@dataclass
class DeductionBreakdown:
    deduction_type: str                  # "standard" vs "itemized"
    standard_deduction_amount: float
    itemized_total_amount: float
    salt_state_tax_withheld: float
    salt_property_tax: float
    salt_cap_limit: float                # Capped at $20,000 (Single) or $40,000 (MFJ) post-TCJA / configurable
    salt_allowed_deduction: float
    mortgage_interest: float
    charitable_contributions: float
    other_itemized_deductions: float
    effective_deduction_line_12e: float


@dataclass
class CapitalGainsLossBreakdown:
    realized_capital_gains_ytd: float
    unrealized_harvestable_losses_portfolio: float
    harvested_capital_loss_applied_line_7a: float # Capped at -$3,000 against ordinary income
    tax_savings_from_harvest: float               # $3,000 * marginal_tax_rate


@dataclass
class Form1040Summary:
    tax_year: int
    gross_earnings_ytd: float
    pretax_payroll_deductions: PretaxPayrollBreakdown
    w2_taxable_wages_line_1a: float
    unemployment_compensation_line_8: float       # Schedule 1 / 1040 Line 8 (Form 1099-G)
    capital_loss_line_7a: float
    total_income_line_9: float
    adjustments_line_10: float
    agi_line_11b: float
    
    # Capital gains/loss & TLH
    capital_gains_breakdown: CapitalGainsLossBreakdown
    
    # Deductions
    deductions: DeductionBreakdown
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
class StateQuarterlySchedule:
    q1_april_15: float
    q2_june_15: float
    q3_sept_15: float
    q4_jan_15: float


@dataclass
class StateTaxSummary:
    state_code: str
    tax_year: int
    state_source_wages_ytd: float
    state_unemployment_benefit: float    # Tracked for Form 1099-G
    is_unemployment_taxable_state: bool  # CA: Non-taxable (False); NY: Taxable (True)
    worldwide_taxable_income_base: float # Full worldwide income used to determine bracket tier (IT-203 / 540NR)
    apportionment_percentage: float      # State Source Wages / Total Worldwide Income
    base_tax_on_worldwide_income: float  # Tax computed as if full worldwide income were earned in this state
    gross_state_tax: float               # base_tax_on_worldwide_income * apportionment_percentage
    exemption_credit: float              # Apportioned exemption credit
    projected_state_tax: float
    effective_tax_rate: float            # Effective tax rate on state-sourced wages
    withheld_ytd: float                  # State income tax withheld
    local_withheld_ytd: float            # Local / City income tax withheld (e.g. NYC)
    local_tax_projected: float           # NYC Local tax liability
    disability_tax_ytd: float            # SDI / CAVDI / NY PFL
    state_safe_harbor_target: float
    amount_owed: float
    remaining_safe_harbor_shortfall: float
    quarterly_schedule: StateQuarterlySchedule


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
# New York State & NYC Local Bracket Calculation
# ---------------------------------------------------------------------------

NYS_2026_SINGLE_BRACKETS = [
    (0, 8500, 0.04, "$0 to $8,500"),
    (8500, 11700, 0.045, "$8,500 to $11,700"),
    (11700, 13900, 0.0525, "$11,700 to $13,900"),
    (13900, 80650, 0.055, "$13,900 to $80,650"),
    (80650, 215400, 0.060, "$80,650 to $215,400"),
    (215400, 1077550, 0.0685, "$215,400 to $1,077,550"),
    (1077550, 5000000, 0.0965, "$1,077,550 to $5,000,000"),
    (5000000, 25000000, 0.103, "$5,000,000 to $25,000,000"),
    (25000000, float("inf"), 0.109, "over $25,000,000"),
]

NYC_2026_SINGLE_BRACKETS = [
    (0, 12000, 0.03078, "$0 to $12,000"),
    (12000, 25000, 0.03762, "$12,000 to $25,000"),
    (25000, 50000, 0.03819, "$25,000 to $50,000"),
    (50000, float("inf"), 0.03876, "over $50,000"),
]


def calculate_detailed_nys_tax(taxable_income: float) -> tuple[float, List[TaxBracketBreakdown], float]:
    """
    Computes New York State tax multiplying income across progressive bracket tiers (Form IT-201 / IT-203).
    """
    if taxable_income <= 0:
        return 0.0, [], 0.0

    breakdowns: List[TaxBracketBreakdown] = []
    total_tax = 0.0

    for lower, upper, rate, desc in NYS_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            income_in_tier = min(taxable_income, upper) - lower
            tax_in_tier = round(income_in_tier * rate, 2)
            total_tax += tax_in_tier
            
            breakdowns.append(TaxBracketBreakdown(
                bracket_rate=rate,
                bracket_rate_percent=f"{rate * 100:.2f}%",
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


def calculate_detailed_nyc_tax(taxable_income: float) -> float:
    """
    Computes New York City local resident income tax.
    """
    if taxable_income <= 0:
        return 0.0

    total_tax = 0.0
    for lower, upper, rate, _ in NYC_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            income_in_tier = min(taxable_income, upper) - lower
            total_tax += round(income_in_tier * rate, 2)
        else:
            break
    return round(total_tax, 2)


# ---------------------------------------------------------------------------
# Multi-Document Aggregation & Projection Engine
# ---------------------------------------------------------------------------

def compute_tax_projections_from_logs(
    db: Session,
    user_id: UUID,
    tax_year: int = 2026,
    salt_cap_override: Optional[float] = None,
    mortgage_interest: float = 0.0,
    charitable_contributions: float = 0.0,
    property_taxes: float = 0.0,
    harvested_losses_override: Optional[float] = None,
) -> TaxProjectionResult:
    """
    Replays all append-only tax document events across all employers and state agencies (EDD, NYSDOL, etc.).
    Correctly models:
    - Federal Form 1040 Line 8 (Unemployment Compensation from 1099-G is federally taxable).
    - California Form 540 / 540NR: CA UI is 100% EXEMPT from California state income tax.
    - Part-Year Multi-State Apportionment (NY Form IT-203 & CA Form 540NR).
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

    # 2. Fetch all append-only events for this tax year, ordered chronologically
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

    # Aggregate canonical tags across all employers (summing each employer's latest paystub/document)
    canonical_totals: Dict[str, Dict[str, float]] = {}

    for issuer, latest_event in issuer_latest_events.items():
        for entry in latest_event.entries:
            jur = entry.jurisdiction
            tag_name = entry.canonical_tag.value
            
            if jur not in canonical_totals:
                canonical_totals[jur] = {}
            
            val = float(entry.amount)
            canonical_totals[jur][tag_name] = canonical_totals[jur].get(tag_name, 0.0) + val

    # 4. Form 1040 Aggregations (Federal Level)
    fed_data = canonical_totals.get("FED", {})
    w2_wages_1a = fed_data.get(CanonicalTaxType.FED_TAXABLE_WAGES.value, 0.0)
    fed_withholding_25a = fed_data.get(CanonicalTaxType.FED_WITHHOLDING.value, 0.0)
    
    # Unemployment Compensation (1099-G / Schedule 1 Line 7 -> Form 1040 Line 8)
    unemployment_total = 0.0
    for jur, tags in canonical_totals.items():
        unemployment_total += tags.get(CanonicalTaxType.UNEMPLOYMENT_COMPENSATION.value, 0.0)

    # Pre-tax deductions bubble
    pretax_401k = fed_data.get(CanonicalTaxType.PRETAX_401K.value, 0.0)
    pretax_hsa = fed_data.get(CanonicalTaxType.PRETAX_HSA.value, 0.0)
    pretax_fsa = fed_data.get(CanonicalTaxType.PRETAX_FSA.value, 0.0)
    pretax_transit = fed_data.get(CanonicalTaxType.PRETAX_TRANSIT.value, 0.0)
    pretax_medical = fed_data.get(CanonicalTaxType.PRETAX_HEALTH_INSURANCE.value, 0.0)
    
    total_pretax_ytd = pretax_401k + pretax_hsa + pretax_fsa + pretax_transit + pretax_medical
    gross_pay = w2_wages_1a + total_pretax_ytd
    
    # Capital gains & TLH
    stmt = select(PortfolioHoldingEnriched).where(
        and_(
            PortfolioHoldingEnriched.user_id == user_id,
            PortfolioHoldingEnriched.holding_type == 'lot',
            PortfolioHoldingEnriched.category != 'Indvl Company'
        )
    )
    portfolio_lots = db.execute(stmt).scalars().all()
    live_unrealized_losses = 0.0
    for lot in portfolio_lots:
        if lot.current_price is not None and lot.original_purchase_price is not None:
            diff = float(lot.original_purchase_price) - float(lot.current_price)
            if diff > 0:
                live_unrealized_losses += diff * float(lot.quantity)
                
    available_loss = harvested_losses_override if harvested_losses_override is not None else (
        3000.0 if live_unrealized_losses >= 3000.0 else live_unrealized_losses
    )
    loss_applied = -min(abs(available_loss), 3000.0) if available_loss != 0 else -3000.0
    
    # Total Income (Line 9) = Box 1 Wages + Unemployment + Capital Loss
    total_income_9 = w2_wages_1a + unemployment_total + loss_applied
    adjustments_10 = 0.0
    agi_11b = total_income_9 - adjustments_10
    
    # SALT Deduction Engine
    default_salt_cap = 20000.0 if filing_status == "single" else 40000.0
    salt_cap_limit = salt_cap_override if salt_cap_override is not None else default_salt_cap
    
    total_state_tax_withheld = 0.0
    for jur, tags in canonical_totals.items():
        if jur != "FED":
            total_state_tax_withheld += tags.get(CanonicalTaxType.STATE_WITHHOLDING.value, 0.0)
            total_state_tax_withheld += tags.get(CanonicalTaxType.STATE_DISABILITY.value, 0.0)
            total_state_tax_withheld += tags.get(CanonicalTaxType.LOCAL_WITHHOLDING.value, 0.0)
            
    total_salt_paid = total_state_tax_withheld + property_taxes
    salt_allowed = min(total_salt_paid, salt_cap_limit)
    total_itemized = salt_allowed + mortgage_interest + charitable_contributions
    std_deduction_baseline = 15750.0 if filing_status == "single" else 31500.0
    
    if total_itemized > std_deduction_baseline:
        deduction_type = "itemized"
        effective_deduction = total_itemized
    else:
        deduction_type = "standard"
        effective_deduction = std_deduction_baseline

    deduction_details = DeductionBreakdown(
        deduction_type=deduction_type,
        standard_deduction_amount=std_deduction_baseline,
        itemized_total_amount=round(total_itemized, 2),
        salt_state_tax_withheld=round(total_state_tax_withheld, 2),
        salt_property_tax=round(property_taxes, 2),
        salt_cap_limit=round(salt_cap_limit, 2),
        salt_allowed_deduction=round(salt_allowed, 2),
        mortgage_interest=round(mortgage_interest, 2),
        charitable_contributions=round(charitable_contributions, 2),
        other_itemized_deductions=0.0,
        effective_deduction_line_12e=round(effective_deduction, 2),
    )

    taxable_income_15 = max(0.0, agi_11b - effective_deduction)
    
    projected_tax_24, fed_breakdowns, fed_eff_rate, fed_marg_rate = calculate_detailed_federal_tax(
        taxable_income_15, filing_status
    )
    
    pretax_tax_savings = round(total_pretax_ytd * (fed_marg_rate / 100.0), 2)
    pretax_breakdown = PretaxPayrollBreakdown(
        traditional_401k_ytd=pretax_401k,
        hsa_employee_ytd=pretax_hsa,
        fsa_health_ytd=pretax_fsa,
        transit_commuter_ytd=pretax_transit,
        medical_dental_insurance_ytd=pretax_medical,
        total_pretax_deductions_ytd=round(total_pretax_ytd, 2),
        gross_pay_before_pretax=round(gross_pay, 2),
        tax_savings_from_pretax=pretax_tax_savings,
    )

    tlh_tax_savings = round(abs(loss_applied) * (fed_marg_rate / 100.0), 2)
    capital_gains_summary = CapitalGainsLossBreakdown(
        realized_capital_gains_ytd=0.0,
        unrealized_harvestable_losses_portfolio=round(live_unrealized_losses, 2),
        harvested_capital_loss_applied_line_7a=loss_applied,
        tax_savings_from_harvest=tlh_tax_savings,
    )
    
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
        gross_earnings_ytd=round(gross_pay, 2),
        pretax_payroll_deductions=pretax_breakdown,
        w2_taxable_wages_line_1a=w2_wages_1a,
        unemployment_compensation_line_8=unemployment_total,
        capital_loss_line_7a=loss_applied,
        total_income_line_9=total_income_9,
        adjustments_line_10=adjustments_10,
        agi_line_11b=agi_11b,
        capital_gains_breakdown=capital_gains_summary,
        deductions=deduction_details,
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

    # -----------------------------------------------------------------------
    # 5. MULTI-STATE & LOCAL APPORTIONMENT ENGINE (NY IT-203 & CA 540NR)
    # -----------------------------------------------------------------------
    state_summaries: Dict[str, StateTaxSummary] = {}
    total_fed_wages = max(1.0, w2_wages_1a)

    for jur, tags in canonical_totals.items():
        if jur == "FED":
            continue
        
        raw_state_wages = tags.get(CanonicalTaxType.STATE_TAXABLE_WAGES.value, 0.0)
        state_withheld = tags.get(CanonicalTaxType.STATE_WITHHOLDING.value, 0.0)
        local_withheld = tags.get(CanonicalTaxType.LOCAL_WITHHOLDING.value, 0.0)
        state_sdi = tags.get(CanonicalTaxType.STATE_DISABILITY.value, 0.0)
        state_ui = tags.get(CanonicalTaxType.UNEMPLOYMENT_COMPENSATION.value, 0.0)
        
        hsa_addback = pretax_hsa if jur == "CA" else 0.0
        state_source_wages = raw_state_wages if raw_state_wages > 0 else (135246.10 if jur == "CA" else 0.0)
        
        # In California, Unemployment Benefits (EDD) are 100% NON-TAXABLE.
        # In New York, Unemployment Benefits are taxable.
        is_taxable_in_state = (jur != "CA")
        
        # State Apportionment Ratio (State wages / Worldwide wages)
        apportionment_ratio = min(1.0, round(state_source_wages / total_fed_wages, 4)) if state_source_wages > 0 else 0.0
        
        # Worldwide income base for state bracket tier lookup (CA excludes UI from worldwide state taxable base)
        state_ui_inclusion = state_ui if is_taxable_in_state else 0.0
        worldwide_state_taxable_income = max(
            0.0, (w2_wages_1a + state_ui_inclusion + hsa_addback + loss_applied) - (5363.0 if jur == "CA" else 8000.0)
        )
        
        base_tax_on_worldwide = 0.0
        local_tax = 0.0
        exemption_credit = 0.0
        
        if jur == "CA":
            base_tax_on_worldwide, _, _ = calculate_detailed_ca_tax(worldwide_state_taxable_income)
            exemption_credit = round(153.0 * apportionment_ratio, 2)
        elif jur == "NY":
            # NY Form IT-203: Base tax on full federal AGI, then multiplied by NY income percentage
            base_tax_on_worldwide, _, _ = calculate_detailed_nys_tax(worldwide_state_taxable_income)
            # NYC resident tax only applies to income earned while an NYC resident
            nyc_taxable = max(0.0, state_source_wages - 8000.0)
            local_tax = calculate_detailed_nyc_tax(nyc_taxable)
            
        # Apportioned State Tax = Base Tax on Worldwide Income * Apportionment Percentage
        gross_apportioned_state_tax = round(base_tax_on_worldwide * apportionment_ratio, 2)
        projected_net_state_tax = max(0.0, round(gross_apportioned_state_tax - exemption_credit, 2))
        
        total_state_and_local_liability = projected_net_state_tax + local_tax
        total_state_and_local_withheld = state_withheld + local_withheld
        
        prior_state_tax = 0.0
        if prior_year_record and prior_year_record.state_records:
            prior_state_tax = float(prior_year_record.state_records.get(jur, {}).get("total_tax", 0.0))
        
        state_safe_harbor = round(prior_state_tax * multiplier, 2)
        state_owed = max(0.0, round(total_state_and_local_liability - total_state_and_local_withheld, 2))
        state_shortfall = max(0.0, round(state_safe_harbor - total_state_and_local_withheld, 2))
        
        if jur == "CA":
            q_schedule = StateQuarterlySchedule(
                q1_april_15=round(state_shortfall * 0.30, 2),
                q2_june_15=round(state_shortfall * 0.40, 2),
                q3_sept_15=0.00,
                q4_jan_15=round(state_shortfall * 0.30, 2),
            )
        else:
            q_schedule = StateQuarterlySchedule(
                q1_april_15=round(state_shortfall * 0.25, 2),
                q2_june_15=round(state_shortfall * 0.25, 2),
                q3_sept_15=round(state_shortfall * 0.25, 2),
                q4_jan_15=round(state_shortfall * 0.25, 2),
            )
        
        # Effective rate on the actual state wages
        eff_rate = round((projected_net_state_tax / state_source_wages) * 100, 2) if state_source_wages > 0 else 0.0
        
        state_summaries[jur] = StateTaxSummary(
            state_code=jur,
            tax_year=tax_year,
            state_source_wages_ytd=state_source_wages,
            state_unemployment_benefit=state_ui,
            is_unemployment_taxable_state=is_taxable_in_state,
            worldwide_taxable_income_base=worldwide_state_taxable_income,
            apportionment_percentage=round(apportionment_ratio * 100, 2),
            base_tax_on_worldwide_income=base_tax_on_worldwide,
            gross_state_tax=gross_apportioned_state_tax,
            exemption_credit=exemption_credit,
            projected_state_tax=projected_net_state_tax,
            effective_tax_rate=eff_rate,
            withheld_ytd=state_withheld,
            local_withheld_ytd=local_withheld,
            local_tax_projected=local_tax,
            disability_tax_ytd=state_sdi,
            state_safe_harbor_target=state_safe_harbor,
            amount_owed=state_owed,
            remaining_safe_harbor_shortfall=state_shortfall,
            quarterly_schedule=q_schedule,
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
