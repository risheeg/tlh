"""Tax projection result types (no business logic)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


@dataclass
class PretaxPayrollBreakdown:
    traditional_401k_ytd: float  # Pre-tax 401(k) contributions
    hsa_employee_ytd: float  # Pre-tax HSA Section 125 contributions
    fsa_health_ytd: float  # Pre-tax FSA contributions
    transit_commuter_ytd: float  # Pre-tax commuter/transit
    medical_dental_insurance_ytd: float  # Pre-tax healthcare premiums
    total_pretax_deductions_ytd: float  # Total excluded from Box 1 / Line 1a
    gross_pay_before_pretax: float  # Total Gross Pay
    tax_savings_from_pretax: float  # Direct income tax saved via pre-tax exclusions


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
    deduction_type: str  # "standard" vs "itemized"
    standard_deduction_amount: float
    itemized_total_amount: float
    salt_state_tax_withheld: float
    salt_property_tax: float
    salt_cap_limit: float  # Capped at $20,000 (Single) or $40,000 (MFJ)
    salt_allowed_deduction: float
    mortgage_interest: float
    charitable_contributions: float
    other_itemized_deductions: float
    effective_deduction_line_12e: float


@dataclass
class CapitalGainsLossBreakdown:
    realized_capital_gains_ytd: float
    unrealized_harvestable_losses_portfolio: float
    harvested_capital_loss_applied_line_7a: float  # Capped at -$3,000 against ordinary income
    tax_savings_from_harvest: float  # $3,000 * marginal_tax_rate


@dataclass
class Form1040Summary:
    tax_year: int
    gross_earnings_ytd: float
    pretax_payroll_deductions: PretaxPayrollBreakdown
    w2_taxable_wages_line_1a: float
    unemployment_compensation_line_8: float  # Schedule 1 / 1040 Line 8 (Form 1099-G)
    capital_loss_line_7a: float
    total_income_line_9: float
    adjustments_line_10: float
    agi_line_11b: float
    capital_gains_breakdown: CapitalGainsLossBreakdown
    deductions: DeductionBreakdown
    taxable_income_line_15: float
    bracket_breakdowns: List[TaxBracketBreakdown]
    projected_tax_liability_line_24: float
    effective_tax_rate: float
    marginal_tax_rate: float
    federal_withholding_line_25a: float
    estimated_tax_payments_line_26: float
    total_payments_line_33: float
    amount_owed_line_37: float
    overpayment_refund_line_34: float
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
    state_unemployment_benefit: float  # Tracked for Form 1099-G
    is_unemployment_taxable_state: bool  # CA: Non-taxable (False); NY: Taxable (True)
    worldwide_taxable_income_base: float  # Full worldwide income for bracket tier
    apportionment_percentage: float  # State Source Wages / Total Worldwide Income
    base_tax_on_worldwide_income: float
    gross_state_tax: float  # base_tax * apportionment_percentage
    exemption_credit: float
    projected_state_tax: float
    effective_tax_rate: float  # Effective tax rate on state-sourced wages
    withheld_ytd: float
    local_withheld_ytd: float
    local_tax_projected: float
    disability_tax_ytd: float  # SDI / CAVDI / NY PFL
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
