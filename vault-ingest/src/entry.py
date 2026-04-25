import uuid
from urllib.parse import urlparse

from js import Object
from pyodide.ffi import to_js
from workers import Request, Response, WorkerEntrypoint

from ai import classify_document
from taxonomy import FULL_TEXT_SCHEMAS, METADATA_SCHEMAS
from budget import add_neurons_consumed, has_budget
from config import load_config
from db import insert_document
from utils import (
    content_type_for_key,
    js_to_py,
    json_dumps,
    markdown_key,
    parsed_key,
    processed_key,
    utc_now_iso,
)

# When persisting to Neon / serving API consumers, avoid JSON `null` on optional
# scalars: use "" / 0 so statements are easy to filter and UIs do not juggle nulls.
def _default_for_meta_scalar(spec: dict) -> str | int | float:
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


def _neon_parsed_view(
    category: str,
    subcategory: str,
    parsed_payload: dict,
) -> dict:
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
    # full_text_or_records stay on R2 (parsed .json) only; Neon keeps lean rows + counts.
    ft = parsed_payload.get("full_text_or_records")
    if (category, subcategory) in FULL_TEXT_SCHEMAS and isinstance(ft, list) and "transaction_count" in spec_map:
        out["metadata"]["transaction_count"] = len(ft)
    return out

RETRY_IN_24_HOURS = 24 * 60 * 60


def _to_js(value):
    return to_js(value, dict_converter=Object.fromEntries)


def _event_key(body: dict) -> str | None:
    obj = body.get("object") or {}
    key = obj.get("key")
    return str(key) if key else None


def _document_id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"r2://vault-ingest/{key}"))


async def _put_json(bucket, key: str, payload: dict) -> None:
    await bucket.put(
        key,
        json_dumps(payload),
        _to_js({"httpMetadata": {"contentType": "application/json"}}),
    )


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        """Optional: trigger processing without R2 event→queue (for e2e / ops).

        POST /__vault_ingest/trigger with JSON ``{"key": "inbox/foo.txt"}`` and header
        ``X-Vault-Ingest-Secret`` equal to the ``VAULT_INGEST_HTTP_SECRET`` worker secret.
        If the secret is unset, this path returns 404.
        """
        u = urlparse(request.url)
        if u.path.rstrip("/") != "/__vault_ingest/trigger":
            return Response("Not found", status=404)
        if request.method != "POST":
            return Response("Method not allowed", status=405)
        secret = str(getattr(self.env, "VAULT_INGEST_HTTP_SECRET", "") or "").strip()
        if not secret:
            return Response("Not found", status=404)
        got = ""
        for name, val in request.headers.items():
            if name.lower() == "x-vault-ingest-secret":
                got = (val or "").strip()
                break
        if got != secret:
            return Response("Unauthorized", status=401)
        try:
            data = await request.json()
        except Exception:
            return Response("Invalid JSON", status=400)
        if not isinstance(data, dict):
            return Response("JSON object required", status=400)
        key = data.get("key")
        if not key or not isinstance(key, str):
            return Response.from_json({"error": "missing string key"}, status=400)
        config = load_config(self.env)
        if not key.startswith(config.inbox_prefix):
            return Response.from_json(
                {"error": f"key must be under {config.inbox_prefix!r}"},
                status=400,
            )
        if not await has_budget(self.env.VAULT_DB, config.daily_neuron_budget):
            return Response("Daily AI budget exhausted", status=503)
        size = data.get("size")
        if size is not None and not isinstance(size, (int, float)):
            size = None
        obj_part: dict = {"key": key}
        if size is not None:
            obj_part["size"] = int(size)
        et = data.get("eventTime")
        fake: dict = {"object": obj_part, "eventTime": et if isinstance(et, str) else None}
        try:
            await self._process_r2_event(self.env, config, fake, key)
        except Exception as exc:
            print(f"HTTP trigger process failed: {exc}")
            return Response.from_json({"error": str(exc)}, status=500)
        return Response.from_json({"ok": True, "key": key})

    async def queue(self, batch, env, ctx):
        worker_env = self.env
        config = load_config(worker_env)

        for msg in batch.messages:
            try:
                body = js_to_py(msg.body)
                if not isinstance(body, dict):
                    print("Ignoring non-object queue message")
                    msg.ack()
                    continue

                key = _event_key(body)
                if not key or not key.startswith(config.inbox_prefix):
                    print(f"Ignoring non-inbox R2 event: {body}")
                    msg.ack()
                    continue

                if not await has_budget(worker_env.VAULT_DB, config.daily_neuron_budget):
                    print("Daily AI neuron budget exhausted; retrying in 24 hours")
                    msg.retry(delaySeconds=RETRY_IN_24_HOURS)
                    continue

                await self._process_r2_event(worker_env, config, body, key)
                msg.ack()
            except Exception as exc:
                print(f"Vault ingest message failed: {exc}")
                msg.retry()

    async def _process_r2_event(self, env, config, body: dict, key: str) -> None:
        bucket = env.VAULT_BUCKET
        obj = await bucket.get(key)
        if obj is None:
            print(f"R2 object is missing; acknowledging stale event for {key}")
            return
        try:
            array_buffer = await obj.arrayBuffer()
        except Exception:
            # R2 can return JavaScript `null` (not equal to Python None).
            print(f"R2 object is missing; acknowledging stale event for {key}")
            return

        metadata = js_to_py(getattr(obj, "httpMetadata", None)) or {}
        content_type = content_type_for_key(key, metadata.get("contentType"))

        classification = await classify_document(
            env,
            config,
            key,
            content_type,
            array_buffer,
        )

        document_id = _document_id(key)
        category = classification["category"]
        subcategory = classification["subcategory"]
        final_key = processed_key(config.processed_prefix, category, document_id, key)
        json_key = parsed_key(config.parsed_prefix, category, document_id, key)
        md_key = markdown_key(config.parsed_prefix, category, document_id, key)

        parsed_payload = classification["parsed_json"]
        # Version is controlled by application code (not model output).
        parsed_payload["schema_version"] = 1

        await _put_json(bucket, json_key, parsed_payload)

        document_text = classification["document_text"]
        await bucket.put(
            md_key,
            document_text,
            _to_js({"httpMetadata": {"contentType": "text/markdown"}}),
        )
        await bucket.put(
            final_key,
            array_buffer,
            _to_js({"httpMetadata": {"contentType": content_type}}),
        )

        neon_payload = _neon_parsed_view(category, subcategory, parsed_payload)

        now = utc_now_iso()
        await insert_document(
            config.neon_connection_string,
            {
                "id": document_id,
                "upload_date": body.get("eventTime") or now,
                "processed_at": now,
                "category": category,
                "subcategory": subcategory,
                "account_id": None,
                "r2_original_path": key,
                "r2_file_path": final_key,
                "r2_parsed_json_path": json_key,
                "r2_markdown_path": md_key,
                "file_size": (body.get("object") or {}).get("size"),
                "ai_model": f"{config.stage1_model} + {config.stage2_model}",
                "parsed_json": neon_payload,
            },
        )

        await add_neurons_consumed(
            env.VAULT_DB,
            classification["neurons_consumed"],
            usage_breakdown=classification.get("usage_breakdown"),
        )
        await bucket.delete(key)
