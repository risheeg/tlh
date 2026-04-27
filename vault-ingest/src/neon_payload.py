"""Neon payload shaping: convert parsed extraction output into the lean JSONB
view stored in the ``vault_ingest.documents`` row."""

from derived_metrics import derive_transaction_metrics
from taxonomy.schemas import FULL_TEXT_SCHEMAS, METADATA_SCHEMAS


def _default_for_meta_scalar(spec: dict) -> str | int | float:
    """When persisting to Neon / serving API consumers, avoid JSON ``null`` on
    optional scalars: use ``""`` / ``0`` so statements are easy to filter and
    UIs do not juggle nulls."""
    typ = spec.get("type")
    if isinstance(typ, list):
        if "string" in typ:
            return ""
        if "number" in typ:
            return 0.0
        if "integer" in typ:
            return 0
        return ""
    if typ == "number":
        return 0.0
    if typ == "integer":
        return 0
    return ""


def _normalize_metadata_no_nulls(
    category: str,
    subcategory: str,
    raw: dict,
) -> dict:
    spec_map = METADATA_SCHEMAS.get((category, subcategory), {})
    out: dict = {}
    for k, spec in spec_map.items():
        v = raw.get(k)
        if v is not None:
            out[k] = v
            continue
        if isinstance(spec.get("type"), list) and "null" in spec.get("type", []):
            out[k] = _default_for_meta_scalar({**spec, "type": [t for t in spec["type"] if t != "null"]})
        else:
            out[k] = _default_for_meta_scalar(spec)
    return out


def neon_parsed_view(
    category: str,
    subcategory: str,
    parsed_payload: dict,
) -> dict:
    """Build the lean JSONB payload stored in ``vault_ingest.documents.parsed_json``.

    ``full_text_or_records`` stays on R2 only; Neon keeps lean rows + counts.
    """
    raw_meta = parsed_payload.get("metadata") or {}
    allowed = set(METADATA_SCHEMAS.get((category, subcategory), {}).keys())
    spec_map = METADATA_SCHEMAS.get((category, subcategory), {})
    clean_raw = {k: v for k, v in raw_meta.items() if k in allowed}
    clean_meta = _normalize_metadata_no_nulls(category, subcategory, clean_raw)
    out: dict = {
        "schema_version": parsed_payload.get("schema_version"),
        "summary": parsed_payload.get("summary") or "",
        "notes": parsed_payload.get("notes") if parsed_payload.get("notes") is not None else "",
        "document_date": (
            parsed_payload.get("document_date")
            if parsed_payload.get("document_date") is not None
            else ""
        ),
        "issuer": parsed_payload.get("issuer") if parsed_payload.get("issuer") is not None else "",
        "metadata": clean_meta,
    }
    ft = parsed_payload.get("full_text_or_records")
    if (category, subcategory) in FULL_TEXT_SCHEMAS and isinstance(ft, list):
        out["metadata"].update(derive_transaction_metrics(category, subcategory, ft))
    return out
