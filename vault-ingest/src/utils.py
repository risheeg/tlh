import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from importlib import import_module
from urllib.parse import quote


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def usage_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def js_to_py(value):
    if hasattr(value, "to_py"):
        return value.to_py()
    return value


def json_dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end <= start:
        return None
    return text[start : end + 1]


@lru_cache(maxsize=1)
def _repair_json_func():
    return import_module("json_repair").repair_json


def is_json_null(value) -> bool:
    """``None`` or JavaScript null from the Workers (Pyodide) runtime."""
    if value is None:
        return True
    try:
        from js import null as js_null

        return value is js_null
    except Exception:
        return type(value).__name__ in ("JsNull", "jsnull", "JSNull")


def deep_coerce_jsnull(value):
    """Recursively replace Pyodide ``js`` null with Python ``None`` (JSON null)."""
    if is_json_null(value):
        return None
    if isinstance(value, dict):
        return {k: deep_coerce_jsnull(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_coerce_jsnull(x) for x in value]
    return value


def parse_json_response(response_text: str | dict | list):
    if isinstance(response_text, (dict, list)):
        return deep_coerce_jsnull(response_text)

    if not isinstance(response_text, str):
        return response_text

    # Remove reasoning blocks if present.
    response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

    # 1) Happy path.
    try:
        return deep_coerce_jsnull(json.loads(response_text))
    except json.JSONDecodeError:
        pass

    # 2) Try a balanced JSON object slice if the model added surrounding text.
    candidate = _extract_balanced_json_object(response_text)
    if candidate:
        try:
            return deep_coerce_jsnull(json.loads(candidate))
        except json.JSONDecodeError:
            pass

    # 3) Library-backed repair for malformed JSON.
    try:
        repair_json = _repair_json_func()
    except ModuleNotFoundError:
        repair_json = None

    for target in [response_text, candidate]:
        if not target:
            continue
        try:
            if repair_json is None:
                continue
            return deep_coerce_jsnull(repair_json(target, return_objects=True))
        except Exception:
            continue

    print(f"JSON Parsing failed for text: {response_text[:1000]}")
    raise ValueError(f"Could not parse model JSON response: {response_text[:160]}...")


_METADATA_BLOCK_RE = re.compile(
    r"^##\s+Metadata\s*\n(?:-\s.*\n)*\s*\n*",
    re.MULTILINE,
)


def strip_document_metadata_block(text: str) -> str:
    """Remove the ``## Metadata`` header + its bullet list that ``env.AI.toMarkdown``
    prepends from PDF file headers (PDFFormatVersion, Creator, Producer, etc.).

    Leaving this in confuses the extractor model: it sees a section literally
    called "Metadata" and copies those keys into the schema's `metadata` field
    instead of extracting the document's own structured metadata.
    """
    return _METADATA_BLOCK_RE.sub("", text, count=1)


_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_ok(value, t: str) -> bool:
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return _is_number(value)
    if t == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, float) and value == int(value):
            return True
        return False
    if t == "boolean":
        return isinstance(value, bool)
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "null":
        return is_json_null(value)
    return False


def _error_json_path(path_parts: list) -> str:
    s = "$"
    for part in path_parts:
        if isinstance(part, int):
            s += f"[{part}]"
        else:
            s += f".{part}"
    return s


def _format_ok_for_string(value, schema: dict) -> bool:
    if schema.get("format") != "date" or not isinstance(value, str):
        return True
    return bool(_DATE_RE.match(value))


def _iter_extraction_schema_errors(  # noqa: C901
    value,
    schema: dict,
    path: list,
) -> list[str]:
    """Subset of JSON Schema draft-7 used by taxonomy: type unions, object props,
    arrays, additionalProperties, required, enum, and format: date. No $ref/oneOf.
    """
    p = _error_json_path(path)
    if "enum" in schema and value not in schema["enum"]:
        return [f"{p}: {value!r} is not one of {schema['enum']!r}"]

    typ = schema.get("type")
    if typ is None:
        return []

    if isinstance(typ, list):
        for t in typ:
            if t == "null" and is_json_null(value):
                return []
        for t in typ:
            if t == "null":
                continue
            if not _type_ok(value, t):
                continue
            if t == "string" and not _format_ok_for_string(value, schema):
                return [f"{p}: {value!r} is not a valid date string (expected YYYY-MM-DD)"]
            return []
        return [f"{p}: {value!r} is not of type {typ!r}"]

    if not _type_ok(value, typ):
        return [f"{p}: {value!r} is not of type {typ!r}"]

    if typ == "string" and not _format_ok_for_string(value, schema):
        return [f"{p}: {value!r} is not a valid date string (expected YYYY-MM-DD)"]

    if typ == "object" and isinstance(value, dict):
        out: list[str] = []
        for key in schema.get("required") or ():
            if key not in value:
                p2 = path + [key]
                out.append(f"{_error_json_path(p2)}: {key!r} is a required property")
        add_ok = bool(schema.get("additionalProperties", True))
        props = schema.get("properties") or {}
        for key in value:
            if key in props or add_ok:
                continue
            p2 = path + [key]
            out.append(f"{_error_json_path(p2)}: additional property {key!r} is not allowed")
        for key, sub in props.items():
            if key in value:
                out.extend(
                    _iter_extraction_schema_errors(
                        value[key],
                        sub,
                        path + [key],
                    )
                )
        return out

    if typ == "array" and isinstance(value, list):
        out = []
        items = schema.get("items")
        if items is not None:
            for i, el in enumerate(value):
                out.extend(
                    _iter_extraction_schema_errors(
                        el,
                        items,
                        path + [i],
                    )
                )
        return out

    return []


def validate_extraction(payload, schema: dict, path: str = "$") -> list[str]:
    """Validate extraction output against a JSON object schema; return error strings."""
    del path
    if not isinstance(schema, dict):
        return ["$: schema must be a JSON object"]
    return _iter_extraction_schema_errors(
        payload,
        schema,
        [],
    )


def path_basename(key: str) -> str:
    return key.rstrip("/").split("/")[-1] or "document"


def content_type_for_key(key: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    lower = key.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".csv"):
        return "text/csv"
    if lower.endswith(".html") or lower.endswith(".htm"):
        return "text/html"
    if lower.endswith(".json"):
        return "application/json"
    return "text/plain"


def is_plain_text(content_type: str, key: str) -> bool:
    lower_type = content_type.lower()
    lower_key = key.lower()
    return (
        lower_type.startswith("text/plain")
        or lower_type.startswith("text/csv")
        or lower_key.endswith((".txt", ".md", ".csv"))
    )


def processed_key(prefix: str, category: str, document_id: str, original_key: str) -> str:
    name = path_basename(original_key)
    stem, _, ext = name.rpartition(".")
    stem = quote(stem, safe="._-")
    ext  = quote(ext,  safe="._-")
    return f"{prefix.rstrip('/')}/{category}/{stem}_{document_id}.{ext}"


def parsed_key(prefix: str, category: str, document_id: str, original_key: str) -> str:
    stem = path_basename(original_key).rpartition(".")[0] or path_basename(original_key)
    stem = quote(stem, safe="._-")
    return f"{prefix.rstrip('/')}/{category}/{stem}_{document_id}.json"


def markdown_key(prefix: str, category: str, document_id: str, original_key: str) -> str:
    stem = path_basename(original_key).rpartition(".")[0] or path_basename(original_key)
    stem = quote(stem, safe="._-")
    return f"{prefix.rstrip('/')}/{category}/{stem}_{document_id}.md"
