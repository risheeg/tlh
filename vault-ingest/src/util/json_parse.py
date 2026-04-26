"""JSON parsing, repair, and cleaning helpers."""

import json
import re
from functools import lru_cache
from importlib import import_module

from util.js_interop import js_to_py


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
