import re
from typing import Optional, Tuple
from models.taxes import CanonicalTaxType


# Pattern matchers for normalizing payroll line items (Workday, ADP, Gusto, etc.)
PATTERNS = [
    # 1. Federal Withholding & Taxable Wages
    (
        r"federal withholding\s*-\s*taxable wages|fed taxable gross|fit wages|fed taxable",
        CanonicalTaxType.FED_TAXABLE_WAGES,
        "FED"
    ),
    (
        r"federal withholding|federal income tax|\bfit\b|fed tax withheld",
        CanonicalTaxType.FED_WITHHOLDING,
        "FED"
    ),
    
    # 2. Supplemental Earnings
    (
        r"bonus|fy annual bonus|severance|pay in lieu|rsu|flex wallet|kudos",
        CanonicalTaxType.SUPPLEMENTAL_WAGES,
        "FED"
    ),

    # 3. FICA Taxes
    (
        r"oasdi|social security|fed oasdi",
        CanonicalTaxType.FICA_SOCIAL_SECURITY,
        "FED"
    ),
    (
        r"medicare|fed med",
        CanonicalTaxType.FICA_MEDICARE,
        "FED"
    ),

    # 4. Pre-tax Deductions
    (
        r"401k$|401\(k\)|traditional 401k|pre-tax 401k",
        CanonicalTaxType.PRETAX_401K,
        "FED"
    ),
    (
        r"health savings account|hsa\b",
        CanonicalTaxType.PRETAX_HSA,
        "FED"
    ),
    (
        r"fsa health|flexible spending",
        CanonicalTaxType.PRETAX_FSA,
        "FED"
    ),
    (
        r"medical deduction|dental|vision",
        CanonicalTaxType.PRETAX_HEALTH_INSURANCE,
        "FED"
    ),
    (
        r"transit|commuter",
        CanonicalTaxType.PRETAX_TRANSIT,
        "FED"
    ),

    # 5. State Taxes & Disability
    (
        r"ca vdi|cavdi|sdi|disability",
        CanonicalTaxType.STATE_DISABILITY,
        None  # Detected dynamically from state code
    ),
    (
        r"state.*taxable wages|sit wages",
        CanonicalTaxType.STATE_TAXABLE_WAGES,
        None  # Detected dynamically
    ),
    (
        r"state tax|state withholding|\bsit\b|\bpit\b",
        CanonicalTaxType.STATE_WITHHOLDING,
        None  # Detected dynamically
    ),
]

STATE_CODE_REGEX = re.compile(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b", re.IGNORECASE)


def parse_paystub_line_item(description: str) -> Tuple[Optional[CanonicalTaxType], str, Optional[str]]:
    """
    Parses a raw paystub line description into a (CanonicalTaxType, jurisdiction, locality) tuple.
    Default jurisdiction is 'FED' unless a state code is detected.
    """
    cleaned = description.strip()
    cleaned_lower = cleaned.lower()
    
    # Check for state mentions (e.g. "State Tax - CA", "CA VDI - CAVDI", "NY SIT")
    state_match = STATE_CODE_REGEX.search(cleaned)
    detected_state = state_match.group(1).upper() if state_match else None
    
    # Check for local tax (e.g. "NYC Tax")
    locality = None
    if "nyc" in cleaned_lower or "new york city" in cleaned_lower:
        detected_state = "NY"
        locality = "NYC"
    
    for pattern, canonical_type, default_jurisdiction in PATTERNS:
        if re.search(pattern, cleaned_lower):
            jurisdiction = detected_state or default_jurisdiction or "FED"
            
            # If it's a state-specific tag and no state was detected, default to FED or leave as general
            if canonical_type in (CanonicalTaxType.STATE_WITHHOLDING, CanonicalTaxType.STATE_TAXABLE_WAGES, CanonicalTaxType.STATE_DISABILITY):
                jurisdiction = detected_state or "CA" # fallback or user default state
                
            return canonical_type, jurisdiction, locality
            
    return None, "FED", None
