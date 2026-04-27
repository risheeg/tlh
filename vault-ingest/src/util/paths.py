"""R2 path construction and content-type detection."""

from urllib.parse import quote


def path_basename(key: str) -> str:
    return key.rstrip("/").split("/")[-1] or "document"


def parse_user_id_from_inbox_key(key: str, inbox_prefix: str) -> str | None:
    parts = key.split("/")
    if len(parts) >= 3 and parts[1] == inbox_prefix.strip("/"):
        return parts[0]
    return None


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


def processed_key(user_id: str, prefix: str, category: str, document_id: str, original_key: str) -> str:
    name = path_basename(original_key)
    stem, _, ext = name.rpartition(".")
    stem = quote(stem, safe="._-")
    ext  = quote(ext,  safe="._-")
    return f"{user_id}/{prefix.rstrip('/')}/{category}/{stem}_{document_id}.{ext}"


def parsed_key(user_id: str, prefix: str, category: str, document_id: str, original_key: str) -> str:
    stem = path_basename(original_key).rpartition(".")[0] or path_basename(original_key)
    stem = quote(stem, safe="._-")
    return f"{user_id}/{prefix.rstrip('/')}/{category}/{stem}_{document_id}.json"


def markdown_key(user_id: str, prefix: str, category: str, document_id: str, original_key: str) -> str:
    stem = path_basename(original_key).rpartition(".")[0] or path_basename(original_key)
    stem = quote(stem, safe="._-")
    return f"{user_id}/{prefix.rstrip('/')}/{category}/{stem}_{document_id}.md"
