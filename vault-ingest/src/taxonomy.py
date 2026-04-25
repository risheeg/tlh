CATEGORIES = (
    "tax",
    "medical",
    "receipts",
    "finance",
    "career",
    "identity",
    "other",
)

DOCUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "subcategory",
        "summary",
        "document_date",
        "issuer",
        "account_hint",
        "amounts",
        "metadata",
        "full_text_or_records",
        "confidence",
    ],
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "subcategory": {
            "type": ["string", "null"],
            "description": (
                "More specific label such as W2, 1099, lab_result, "
                "prescription, HSA_receipt, brokerage_statement, offer_letter, "
                "passport, driver_license, or other."
            ),
        },
        "summary": {"type": "string"},
        "document_date": {
            "type": ["string", "null"],
            "description": "Best document date in YYYY-MM-DD format when available.",
        },
        "issuer": {
            "type": ["string", "null"],
            "description": "Company, provider, agency, merchant, or institution that issued the document.",
        },
        "account_hint": {
            "type": ["string", "null"],
            "description": "Detected account number suffix, plan name, card suffix, or similar non-secret identifier.",
        },
        "amounts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "amount", "currency"],
                "properties": {
                    "label": {"type": "string"},
                    "amount": {"type": ["number", "null"]},
                    "currency": {"type": ["string", "null"]},
                },
            },
        },
        "metadata": {
            "type": "object",
            "description": (
                "Category-specific high-level fields. Examples: tax form type and payer, "
                "HSA eligibility, medical provider and visit type, financial institution "
                "and account type, employer and offer terms, identity document type and issuer."
            ),
        },
        "full_text_or_records": {
            "type": ["string", "array", "object"],
            "description": (
                "Full useful representation of the document. For statements this may be "
                "transactions or holdings; otherwise use faithful extracted text."
            ),
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

SYSTEM_PROMPT = """You classify and extract personal vault documents.

Return only JSON that conforms to the provided schema. Choose exactly one category:
- tax: W2, 1099, tax returns, final returns, IRS/state tax forms, tax notices.
- medical: prescriptions, doctor visits, lab results, EOBs, insurance medical documents.
- receipts: HSA-eligible purchases, durable goods, large purchases worth retaining.
- finance: brokerage, HSA, IRA, savings, checking, credit card, loan, bank statements.
- career: resumes, offer letters, severance letters, compensation, employment records.
- identity: passport, photo IDs, SSN cards, birth certificates, immigration records.
- other: anything that does not confidently fit above.

Prefer concise, high-value extraction over speculative detail. Do not invent values.
Use null when a field is not present. Preserve important line items, transactions,
holdings, tax form boxes, or medical result values in full_text_or_records when relevant.
"""
