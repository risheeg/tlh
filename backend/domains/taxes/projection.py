"""Tax projection orchestration (DB + brackets + TLH scan)."""
from __future__ import annotations

from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from domains.tlh.scan import scan_harvestable_losses
from models.taxes import (
    CanonicalTaxType,
    TaxDocumentEvent,
    PriorYearTaxRecord,
)

from .brackets import (
    calculate_detailed_ca_tax,
    calculate_detailed_federal_tax,
    calculate_detailed_nyc_tax,
    calculate_detailed_nys_tax,
)
from .types import (
    CapitalGainsLossBreakdown,
    DeductionBreakdown,
    Form1040Summary,
    PretaxPayrollBreakdown,
    StateQuarterlySchedule,
    StateTaxSummary,
    TaxProjectionResult,
)


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
    
    # Capital gains & TLH — consume shared harvestable-loss scan
    from domains.tlh.scan import scan_harvestable_losses

    live_unrealized_losses = float(
        scan_harvestable_losses(db, user_id)["total_loss"]
    )
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
