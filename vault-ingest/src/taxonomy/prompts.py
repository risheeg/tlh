"""System prompts, classification schema, and extraction prompt generation."""

import json

from taxonomy.categories import CATEGORIES
from taxonomy.schemas import FULL_TEXT_SCHEMAS, METADATA_SCHEMAS


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
