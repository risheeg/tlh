"""Pure progressive-bracket tax math (no DB access)."""
from __future__ import annotations

from typing import List

from .types import TaxBracketBreakdown

FEDERAL_2026_SINGLE_BRACKETS = [
    (0, 11925, 0.10, "$0 to $11,925"),
    (11925, 48475, 0.12, "$11,925 to $48,475"),
    (48475, 103350, 0.22, "$48,475 to $103,350"),
    (103350, 197300, 0.24, "$103,350 to $197,300"),
    (197300, 250525, 0.32, "$197,300 to $250,525"),
    (250525, 626350, 0.35, "$250,525 to $626,350"),
    (626350, float("inf"), 0.37, "over $626,350"),
]

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


def calculate_detailed_federal_tax(
    taxable_income: float, filing_status: str = "single"
) -> tuple[float, List[TaxBracketBreakdown], float, float]:
    """
    Computes federal tax across each progressive bracket tier.
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

            breakdowns.append(
                TaxBracketBreakdown(
                    bracket_rate=rate,
                    bracket_rate_percent=f"{int(rate * 100)}%",
                    income_in_bracket=round(income_in_tier, 2),
                    tax_for_bracket=tax_in_tier,
                    cumulative_tax=round(total_tax, 2),
                    range_description=desc,
                )
            )
        else:
            break

    total_tax = round(total_tax, 2)
    effective_rate = (
        round((total_tax / taxable_income) * 100, 2) if taxable_income > 0 else 0.0
    )
    return total_tax, breakdowns, effective_rate, round(marginal_rate * 100, 2)


def calculate_detailed_ca_tax(
    taxable_income: float,
) -> tuple[float, List[TaxBracketBreakdown], float]:
    """Computes California state tax across progressive bracket tiers."""
    if taxable_income <= 0:
        return 0.0, [], 0.0

    breakdowns: List[TaxBracketBreakdown] = []
    total_tax = 0.0

    for lower, upper, rate, desc in CA_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            income_in_tier = min(taxable_income, upper) - lower
            tax_in_tier = round(income_in_tier * rate, 2)
            total_tax += tax_in_tier

            breakdowns.append(
                TaxBracketBreakdown(
                    bracket_rate=rate,
                    bracket_rate_percent=f"{rate * 100:.1f}%",
                    income_in_bracket=round(income_in_tier, 2),
                    tax_for_bracket=tax_in_tier,
                    cumulative_tax=round(total_tax, 2),
                    range_description=desc,
                )
            )
        else:
            break

    total_tax = round(total_tax, 2)
    effective_rate = (
        round((total_tax / taxable_income) * 100, 2) if taxable_income > 0 else 0.0
    )
    return total_tax, breakdowns, effective_rate


def calculate_detailed_nys_tax(
    taxable_income: float,
) -> tuple[float, List[TaxBracketBreakdown], float]:
    """Computes New York State tax across progressive bracket tiers."""
    if taxable_income <= 0:
        return 0.0, [], 0.0

    breakdowns: List[TaxBracketBreakdown] = []
    total_tax = 0.0

    for lower, upper, rate, desc in NYS_2026_SINGLE_BRACKETS:
        if taxable_income > lower:
            income_in_tier = min(taxable_income, upper) - lower
            tax_in_tier = round(income_in_tier * rate, 2)
            total_tax += tax_in_tier

            breakdowns.append(
                TaxBracketBreakdown(
                    bracket_rate=rate,
                    bracket_rate_percent=f"{rate * 100:.2f}%",
                    income_in_bracket=round(income_in_tier, 2),
                    tax_for_bracket=tax_in_tier,
                    cumulative_tax=round(total_tax, 2),
                    range_description=desc,
                )
            )
        else:
            break

    total_tax = round(total_tax, 2)
    effective_rate = (
        round((total_tax / taxable_income) * 100, 2) if taxable_income > 0 else 0.0
    )
    return total_tax, breakdowns, effective_rate


def calculate_detailed_nyc_tax(taxable_income: float) -> float:
    """Computes New York City local resident income tax."""
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
