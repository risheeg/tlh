import json


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


# Original big schema for Step 1 (Classification)
DOCUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "subcategory",
    ],
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "subcategory": {"type": "string"},
    },
}

SYSTEM_PROMPT = """You classify personal vault documents. Return ONLY a JSON object.
DO NOT include any reasoning, thinking, preamble, or notes.
Example response: {"category": "finance", "subcategory": "statement_credit_card"}

Categories and subcategories:
- tax: w2, 1099_consolidated, 1099_div, 1099_int, 1099_b, 1099_r, 1099_sa, 1099_misc, 1099_nec, 1098_mortgage, 5498, tax_return, tax_notice, other_tax.
- medical: visit_summary, lab_result, prescription, bill, eob.
- finance: statement_brokerage, statement_bank, statement_credit_card, statement_venmo, statement_retirement, statement_hsa, trade_confirmation, loan_statement.
- receipts: hsa_eligible, durable_goods, general.
- career: resume, offer_letter, severance_agreement, paystub, performance_review.
- identity: passport, driver_license, birth_certificate, green_card, visa.
- insurance: auto_policy, home_policy, renters_policy, life_policy, health_id_card, claim_document.
- property: vehicle_title, vehicle_registration, real_estate_deed, lease_agreement.
- other: uncategorized.
"""

_TYPE_HINTS = {
    "string": '"<string>"',
    "number": "<number>",
    "integer": "<integer>",
    "boolean": "<true|false>",
}


def _value_placeholder(prop: dict) -> str:
    t = prop.get("type")
    if isinstance(t, list):
        nullable = "null" in t
        non_null = next((x for x in t if x != "null"), "string")
        base = _TYPE_HINTS.get(non_null, '"<string>"')
        return f"{base} | null" if nullable else base
    if prop.get("format") == "date":
        return '"<YYYY-MM-DD>"'
    if "enum" in prop:
        return " | ".join(json.dumps(v) for v in prop["enum"])
    return _TYPE_HINTS.get(t, '"<value>"')


def _render_object_shape(properties: dict, indent: int = 2) -> str:
    pad = " " * indent
    lines = ["{"]
    items = list(properties.items())
    for i, (name, spec) in enumerate(items):
        placeholder = _value_placeholder(spec)
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'{pad}"{name}": {placeholder}{comma}')
    lines.append(" " * (indent - 2) + "}")
    return "\n".join(lines)


def _render_full_text_shape(schema: dict) -> str | None:
    """Render a concise example for the full_text_or_records schema."""
    if schema.get("type") == "array":
        item = schema.get("items", {})
        props = item.get("properties", {})
        if props:
            return f"[\n    {_render_object_shape(props, indent=6)}\n  ]"
    if schema.get("type") == "object":
        return _render_object_shape(schema.get("properties", {}), indent=4)
    return None


def get_extraction_prompt(category: str, subcategory: str) -> str:
    meta_props = METADATA_SCHEMAS.get((category, subcategory), {})
    metadata_shape = _render_object_shape(meta_props, indent=4) if meta_props else "{}"

    full_text_suffix = ""
    if (category, subcategory) in FULL_TEXT_SCHEMAS:
        rendered = _render_full_text_shape(FULL_TEXT_SCHEMAS[(category, subcategory)])
        if rendered:
            full_text_suffix = f',\n  "full_text_or_records": {rendered}'

    shape = (
        "{\n"
        '  "summary": "<one-sentence plain-English summary>",\n'
        '  "notes": "<anything unusual or null>",\n'
        '  "document_date": "<YYYY-MM-DD or null>",\n'
        '  "issuer": "<issuing company/institution name or null>",\n'
        f'  "metadata": {metadata_shape}'
        f"{full_text_suffix}\n"
        "}"
    )

    extra_rules: list[str] = []
    if (category, subcategory) in FULL_TEXT_SCHEMAS:
        ft_schema = FULL_TEXT_SCHEMAS[(category, subcategory)]
        if ft_schema.get("type") == "array":
            item_props = (ft_schema.get("items") or {}).get("properties", {})
            if "type" in item_props and item_props["type"].get("enum"):
                extra_rules.append(
                    '- For transaction `type`: use "credit" for payments/returns '
                    '(money coming IN to the account holder) and "debit" for '
                    'purchases/charges/fees (money going OUT).'
                )
        extra_rules.append(
            "- Extract EVERY transaction/holding/row into full_text_or_records as structured objects, NOT as raw strings."
        )

    rules_list = [
        "- Output ONLY the raw JSON object. No reasoning, no preamble, no markdown fences.",
        "- Use YYYY-MM-DD for all dates. Top-level `notes` / `document_date` / `issuer` may be null if truly unknown. Inside `metadata` and `full_text_or_records` never use null: use 0 for unknown numbers, \"\" for unknown strings, and YYYY-MM-DD or \"\" for dates.",
        "- The top-level keys must be EXACTLY the ones shown above — do not add or rename any.",
        "- The `metadata` block must contain EXACTLY the keys listed above, nothing more and nothing less.",
        "- Do NOT put PDF file headers (PDFFormatVersion, Creator, Author, Producer, IsLinearized, etc.) anywhere in the output.",
        "- Document-specific values like account numbers or period dates belong INSIDE `metadata` under their canonical names, not at the top level.",
        *extra_rules,
    ]
    rules = "\n".join(rules_list)

    return f"""Extract details for a {category}/{subcategory} document.

Return a JSON object with EXACTLY this shape:
{shape}

Rules:
{rules}
"""
