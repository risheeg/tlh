import json
from datetime import datetime, timezone
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


def parse_json_response(response_text: str):
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(response_text[start : end + 1])
        raise


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


def processed_key(prefix: str, category: str, original_key: str) -> str:
    name = path_basename(original_key)
    return f"{prefix.rstrip('/')}/{category}/{quote(name, safe='._-')}"


def parsed_key(prefix: str, category: str, document_id: str) -> str:
    return f"{prefix.rstrip('/')}/{category}/{document_id}.json"


def markdown_key(prefix: str, category: str, document_id: str) -> str:
    return f"{prefix.rstrip('/')}/{category}/{document_id}.md"
