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


@lru_cache(maxsize=1)
def _draft7_validator_cls():
    return import_module("jsonschema").Draft7Validator


def parse_json_response(response_text: str | dict | list):
    if isinstance(response_text, (dict, list)):
        return response_text

    if not isinstance(response_text, str):
        return response_text

    # Remove reasoning blocks if present.
    response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

    # 1) Happy path.
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # 2) Try a balanced JSON object slice if the model added surrounding text.
    candidate = _extract_balanced_json_object(response_text)
    if candidate:
        try:
            return json.loads(candidate)
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
            return repair_json(target, return_objects=True)
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


def _error_json_path(error) -> str:
    path = "$"
    for part in error.path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_extraction(payload, schema: dict, path: str = "$") -> list[str]:
    """Validate extraction output with jsonschema and return readable errors."""
    del path  # kept for backward-compatible signature
    try:
        Draft7Validator = _draft7_validator_cls()
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'jsonschema'. Run with dependencies from pyproject.toml."
        ) from exc
    validator = Draft7Validator(schema, format_checker=Draft7Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    return [f"{_error_json_path(err)}: {err.message}" for err in errors]


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
