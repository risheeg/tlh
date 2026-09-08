import re
from typing import Optional, Tuple
from models.taxes import CanonicalTaxType


# Pattern matchers for normalizing payroll line items (Workday, ADP, Gusto, Justworks, Paychex, etc.)
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
        r"bonus|fy annual bonus|severance|pay in lieu|rsu|flex wallet|kudos|sign on|relocation",
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
        r"medical deduction|dental|vision|benefit\s*-\s*medical",
        CanonicalTaxType.PRETAX_HEALTH_INSURANCE,
        "FED"
    ),
    (
        r"transit|commuter",
        CanonicalTaxType.PRETAX_TRANSIT,
        "FED"
    ),

    # 5. State / City Disability & Paid Family Leave
    (
        r"ca vdi|cavdi|voluntary disability|private disability",
        CanonicalTaxType.PRIVATE_DISABILITY,
        "CA"
    ),
    (
        r"sdi|disability|paid family leave|pfl",
        CanonicalTaxType.STATE_DISABILITY,
        None  # Detected dynamically from state code
    ),

    # 6. Local / City Tax (e.g. NYC City Tax)
    (
        r"city tax.*taxable wages|local.*taxable wages|nyc.*taxable wages",
        CanonicalTaxType.LOCAL_TAXABLE_WAGES,
        None
    ),
    (
        r"city tax|local tax|nyc tax|nyc pit",
        CanonicalTaxType.LOCAL_WITHHOLDING,
        None
    ),

    # 7. State Taxable Wages & Withholding
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
SSN_REGEX = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")


def sanitize_raw_tax_payload(payload: dict) -> dict:
    """
    Recursively scrubs SSNs, bank account numbers, and sensitive PII from payloads before saving.
    """
    clean = {}
    for k, v in payload.items():
        if isinstance(v, str):
            scrubbed = SSN_REGEX.sub("[REDACTED_SSN]", v)
            clean[k] = scrubbed
        elif isinstance(v, dict):
            clean[k] = sanitize_raw_tax_payload(v)
        elif isinstance(v, list):
            clean[k] = [
                sanitize_raw_tax_payload(i) if isinstance(i, dict)
                else (SSN_REGEX.sub("[REDACTED_SSN]", i) if isinstance(i, str) else i)
                for i in v
            ]
        else:
            clean[k] = v
    return clean


def parse_paystub_line_item(description: str) -> Tuple[Optional[CanonicalTaxType], str, Optional[str]]:
    """
    Parses a raw paystub line description into a (CanonicalTaxType, jurisdiction, locality) tuple.
    Default jurisdiction is 'FED' unless a state code is detected.
    """
    cleaned = description.strip()
    cleaned_lower = cleaned.lower()
    
    # Check for state mentions (e.g. "State Tax - CA", "State Tax - NY", "NY State Disability Insurance")
    state_match = STATE_CODE_REGEX.search(cleaned)
    detected_state = state_match.group(1).upper() if state_match else None
    
    # Check for local tax (e.g. "City Tax - NY", "NYC Tax")
    locality = None
    if "city tax" in cleaned_lower or "nyc" in cleaned_lower or "new york city" in cleaned_lower:
        detected_state = detected_state or "NY"
        locality = "NYC"
    
    for pattern, canonical_type, default_jurisdiction in PATTERNS:
        if re.search(pattern, cleaned_lower):
            jurisdiction = detected_state or default_jurisdiction or "FED"
            
            # If it's a state-specific tag and no state was detected, default to FED or leave as general
            if canonical_type in (
                CanonicalTaxType.STATE_WITHHOLDING,
                CanonicalTaxType.STATE_TAXABLE_WAGES,
                CanonicalTaxType.STATE_DISABILITY,
                CanonicalTaxType.LOCAL_WITHHOLDING,
                CanonicalTaxType.LOCAL_TAXABLE_WAGES,
            ):
                jurisdiction = detected_state or "FED"
                
            return canonical_type, jurisdiction, locality
            
    return None, "FED", None
