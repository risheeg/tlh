from pyodide.http import pyfetch
from urllib.parse import urlparse

from utils import json_dumps


INSERT_DOCUMENT_SQL = """
INSERT INTO vault_ingest.documents (
    id,
    upload_date,
    processed_at,
    category,
    subcategory,
    account_id,
    r2_original_path,
    r2_file_path,
    r2_parsed_json_path,
    r2_markdown_path,
    file_size,
    ai_model,
    parsed_json
)
VALUES (
    $1::uuid,
    $2::timestamptz,
    $3::timestamptz,
    $4,
    $5,
    $6::uuid,
    $7,
    $8,
    $9,
    $10,
    $11,
    $12,
    $13::jsonb
)
ON CONFLICT (id) DO UPDATE SET
    upload_date = excluded.upload_date,
    processed_at = excluded.processed_at,
    category = excluded.category,
    subcategory = excluded.subcategory,
    account_id = excluded.account_id,
    r2_original_path = excluded.r2_original_path,
    r2_file_path = excluded.r2_file_path,
    r2_parsed_json_path = excluded.r2_parsed_json_path,
    r2_markdown_path = excluded.r2_markdown_path,
    file_size = excluded.file_size,
    ai_model = excluded.ai_model,
    parsed_json = excluded.parsed_json
"""


def _neon_sql_endpoint(connection_string: str) -> str:
    parsed = urlparse(connection_string)
    host = parsed.hostname
    if not host:
        raise RuntimeError("NEON_CONNECTION_STRING is missing a hostname")
    parts = host.split(".", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected Neon hostname format: {host}")
    return f"https://api.{parts[1]}/sql"


async def execute_neon_sql(connection_string: str, sql: str, params: list) -> dict:
    response = await pyfetch(
        _neon_sql_endpoint(connection_string),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Neon-Connection-String": connection_string,
            "Neon-Raw-Text-Output": "true",
            "Neon-Array-Mode": "true",
        },
        body=json_dumps({"query": sql, "params": params}),
    )
    body = await response.string()
    if response.status >= 400:
        raise RuntimeError(f"Neon SQL-over-HTTP failed ({response.status}): {body}")
    if not body:
        return {}
    try:
        import json

        return json.loads(body)
    except Exception:
        return {"raw": body}


async def insert_document(connection_string: str, document: dict) -> None:
    await execute_neon_sql(
        connection_string,
        INSERT_DOCUMENT_SQL,
        [
            document["id"],
            document["upload_date"],
            document["processed_at"],
            document["category"],
            document.get("subcategory"),
            document.get("account_id"),
            document["r2_original_path"],
            document["r2_file_path"],
            document["r2_parsed_json_path"],
            document.get("r2_markdown_path"),
            document.get("file_size"),
            document["ai_model"],
            json_dumps(document["parsed_json"]),
        ],
    )
