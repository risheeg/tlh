CATEGORIES = (
    "tax",
    "medical",
    "finance",
    "receipts",
    "career",
    "identity",
    "insurance",
    "property",
    "other",
)

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
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "positions_count": {"type": "integer"},
    },
    ("finance", "statement_credit_card"): {
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "transaction_count": {"type": "integer"},
        "rewards_earned": {"type": "number"},
        "rewards_balance": {"type": "number"},
    },
    **{("finance", sub): {
        "statement_period_start": {"type": "string", "format": "date"},
        "statement_period_end": {"type": "string", "format": "date"},
        "account_type": {"type": "string"},
        "ending_balance": {"type": "number"},
        "transaction_count": {"type": "integer"},
    } for sub in ["statement_bank", "statement_venmo", "statement_retirement", "statement_hsa"]},
    **{("finance", sub): {
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


DOCUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "category",
        "subcategory",
        "summary",
        "notes",
        "document_date",
        "issuer",
        "account_hint",
        "amounts",
        "metadata",
        "confidence",
    ],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "subcategory": {"type": "string"},
        "summary": {
            "type": "string",
            "description": "A universal 1-sentence description/summary of the document."
        },
        "notes": {
            "type": ["string", "null"],
            "description": "Optional extra details, e.g. checking account sign-up bonus, or miscellaneous context.",
        },
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
            "description": "Category-specific fields strictly conforming to the specific subcategory metadata schema.",
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "allOf": []
}

for (cat, sub), meta_props in METADATA_SCHEMAS.items():
    then_properties = {
        "metadata": {
            "type": "object",
            "properties": meta_props,
            "additionalProperties": False
        }
    }
    if meta_props:
        then_properties["metadata"]["required"] = list(meta_props.keys())
    then_required = []
    
    if (cat, sub) in FULL_TEXT_SCHEMAS:
        then_properties["full_text_or_records"] = FULL_TEXT_SCHEMAS[(cat, sub)]
        then_required.append("full_text_or_records")
        
    block = {
        "if": {
            "properties": {"category": {"const": cat}, "subcategory": {"const": sub}}
        },
        "then": {
            "properties": then_properties
        }
    }
    if then_required:
        block["then"]["required"] = then_required
        
    DOCUMENT_SCHEMA["allOf"].append(block)

SYSTEM_PROMPT = """You classify and extract personal vault documents. You will receive the original file name as part of the context.

Return only JSON that conforms to the provided schema. Choose exactly one category and one of its allowed subcategories:
- tax: w2, 1099_consolidated, 1099_div, 1099_int, 1099_b, 1099_r, 1099_sa, 1099_misc, 1099_nec, 1098_mortgage, 5498, tax_return, tax_notice, other_tax.
- medical: visit_summary, lab_result, prescription, bill, eob.
- finance: statement_brokerage, statement_bank, statement_credit_card, statement_venmo, statement_retirement, statement_hsa, trade_confirmation, loan_statement.
- receipts: hsa_eligible, durable_goods, general.
- career: resume, offer_letter, severance_agreement, paystub, performance_review.
- identity: passport, driver_license, birth_certificate, green_card, visa.
- insurance: auto_policy, home_policy, renters_policy, life_policy, health_id_card, claim_document.
- property: vehicle_title, vehicle_registration, real_estate_deed, lease_agreement.
- other: uncategorized.

Prefer concise, high-value extraction over speculative detail. Do not invent values.
Use null when a field is not present. Preserve important line items, transactions,
holdings, tax form boxes, or medical result values in full_text_or_records when requested by the schema.
The "summary" field must be a universal 1-sentence description. Use the "notes" field for any extra unstructured context.
Ensure the "metadata" block exactly matches the specific schema allowed for your chosen subcategory.
"""
