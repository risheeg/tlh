"""Metadata and full-text JSON schemas per (category, subcategory) pair."""

from taxonomy.categories import CATEGORIES

METADATA_SCHEMAS = {
    # 1. Tax
    ("tax", "w2"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_consolidated"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_div"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_int"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_b"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_r"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_sa"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_misc"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1099_nec"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "1098_mortgage"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "5498"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "tax_return"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "tax_notice"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},
    ("tax", "other_tax"): {"tax_year": {"type": "integer"}, "taxable_income_amount": {"type": "number"}, "issuer_name": {"type": "string"}},

    # 2. Medical
    **{("medical", sub): {"provider_name": {"type": "string"}} for sub in ["visit_summary", "lab_result", "prescription", "bill", "eob"]},

    # 3. Finance
    ("finance", "statement_brokerage"): {
        "account_number": {"type": "string"},
        "account_hint": {"type": ["string", "null"]},
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "positions_count": {"type": "integer"},
    },
    ("finance", "statement_credit_card"): {
        "account_number": {"type": "string"},
        "account_hint": {"type": ["string", "null"]},
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "transaction_count": {"type": "integer"},
        "rewards_earned": {"type": "number"},
        "rewards_balance": {"type": "number"},
    },
    **{("finance", sub): {
        "account_number": {"type": "string"},
        "account_hint": {"type": ["string", "null"]},
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "transaction_count": {"type": "integer"},
    } for sub in ["statement_bank", "statement_venmo", "statement_retirement", "statement_hsa"]},
    **{("finance", sub): {
        "account_number": {"type": "string"},
        "account_hint": {"type": ["string", "null"]},
        "account_type": {"type": "string"},
    } for sub in ["trade_confirmation", "loan_statement"]},

    # 4. Receipts
    **{("receipts", sub): {
        "return_by_date": {"type": "string", "format": "date"},
        "warranty_expiration_date": {"type": "string", "format": "date"},
        "purchase_description": {"type": "string"},
        "item_category": {"type": "string"},
    } for sub in ["hsa_eligible", "durable_goods", "general"]},

    # 5. Career
    ("career", "resume"): {
        "most_recent_company": {"type": "string"},
        "most_recent_title": {"type": "string"},
    },
    ("career", "offer_letter"): {
        "offer_company_name": {"type": "string"},
        "offer_base_salary": {"type": "number"},
        "offer_bonus": {"type": "number"},
        "offer_equity": {"type": "number"},
        "offer_sign_on": {"type": "number"},
    },
    ("career", "severance_agreement"): {
        "severance_company_name": {"type": "string"},
        "severance_amount": {"type": "number"},
    },
    ("career", "paystub"): {
        "pay_period_end": {"type": "string", "format": "date"},
    },
    ("career", "performance_review"): {},

    # 6. Identity
    **{("identity", sub): {
        "expiration_date": {"type": "string", "format": "date"},
    } for sub in ["passport", "driver_license", "birth_certificate", "green_card", "visa"]},

    # 7. Insurance
    **{("insurance", sub): {
        "policy_number": {"type": "string"},
        "expiration_date": {"type": "string", "format": "date"},
    } for sub in ["auto_policy", "home_policy", "renters_policy", "life_policy", "health_id_card", "claim_document"]},

    # 8. Property
    **{("property", sub): {
        "asset_identifier": {"type": "string"},
    } for sub in ["vehicle_title", "vehicle_registration", "real_estate_deed", "lease_agreement"]},

    # 9. Other
    ("other", "uncategorized"): {},
}

FULL_TEXT_SCHEMAS = {
    ("finance", "statement_brokerage"): {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker_or_name": {"type": "string"},
                        "shares": {"type": "number"},
                        "value": {"type": "number"},
                    },
                    "required": ["ticker_or_name", "shares", "value"],
                    "additionalProperties": False,
                },
            },
            "buys": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "ticker_or_name": {"type": "string"},
                        "shares": {"type": "number"},
                        "price_per_share": {"type": "number"},
                        "total_amount": {"type": "number"},
                        "is_dividend_reinvestment": {"type": "boolean"},
                    },
                    "required": ["date", "ticker_or_name", "shares", "total_amount", "is_dividend_reinvestment"],
                    "additionalProperties": False,
                },
            },
            "sells": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "ticker_or_name": {"type": "string"},
                        "shares": {"type": "number"},
                        "price_per_share": {"type": "number"},
                        "total_amount": {"type": "number"},
                    },
                    "required": ["date", "ticker_or_name", "shares", "total_amount"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["holdings", "buys", "sells"],
        "additionalProperties": False,
    },
}

FULL_TEXT_SCHEMAS[("finance", "statement_retirement")] = FULL_TEXT_SCHEMAS[("finance", "statement_brokerage")]

_bank_transactions_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "format": "date"},
            "description": {"type": "string"},
            "amount": {"type": "number"},
            "type": {"type": "string", "enum": ["credit", "debit"]},
        },
        "required": ["date", "description", "amount", "type"],
        "additionalProperties": False,
    },
}

for sub in ["statement_bank", "statement_credit_card", "statement_venmo", "statement_hsa"]:
    FULL_TEXT_SCHEMAS[("finance", sub)] = _bank_transactions_schema


_UNIVERSAL_PROPS: dict[str, dict] = {
    "summary":        {"type": "string"},
    "notes":          {"type": ["string", "null"]},
    "document_date":  {"type": ["string", "null"], "format": "date"},
    "issuer":         {"type": ["string", "null"]},
}

_UNIVERSAL_REQUIRED: tuple[str, ...] = (
    "summary", "notes", "document_date", "issuer",
)


def get_targeted_schema(category: str, subcategory: str) -> dict:
    """Build a tight JSON schema for a specific (category, subcategory) pair.

    Keep shared top-level fields stable across all categories (`summary`,
    `notes`, `document_date`, `issuer`) and push
    category-specific attributes into `metadata`.
    """
    properties: dict[str, dict] = dict(_UNIVERSAL_PROPS)
    required: list[str] = list(_UNIVERSAL_REQUIRED)

    meta_props = METADATA_SCHEMAS.get((category, subcategory), {})
    properties["metadata"] = {
        "type": "object",
        "properties": meta_props,
        "required": list(meta_props.keys()),
        "additionalProperties": False,
    }
    required.append("metadata")

    if (category, subcategory) in FULL_TEXT_SCHEMAS:
        properties["full_text_or_records"] = FULL_TEXT_SCHEMAS[(category, subcategory)]
        required.append("full_text_or_records")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
