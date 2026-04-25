import uuid

from js import Object
from pyodide.ffi import to_js
from workers import WorkerEntrypoint

from ai import classify_document
from budget import add_neurons_consumed, has_budget
from config import load_config
from db import insert_document
from utils import (
    content_type_for_key,
    js_to_py,
    json_dumps,
    parsed_key,
    processed_key,
    utc_now_iso,
)

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

        metadata = js_to_py(getattr(obj, "httpMetadata", None)) or {}
        content_type = content_type_for_key(key, metadata.get("contentType"))
        array_buffer = await obj.arrayBuffer()

        classification = await classify_document(
            env,
            config.ai_model,
            key,
            content_type,
            array_buffer,
        )

        document_id = _document_id(key)
        category = classification["category"]
        final_key = processed_key(config.processed_prefix, category, key)
        json_key = parsed_key(config.parsed_prefix, category, document_id)
        parsed_payload = classification["parsed_json"]

        await _put_json(bucket, json_key, parsed_payload)
        await bucket.put(
            final_key,
            array_buffer,
            _to_js({"httpMetadata": {"contentType": content_type}}),
        )

        now = utc_now_iso()
        await insert_document(
            config.neon_connection_string,
            {
                "id": document_id,
                "upload_date": body.get("eventTime") or now,
                "processed_at": now,
                "category": category,
                "subcategory": classification.get("subcategory"),
                "account_id": None,
                "r2_original_path": key,
                "r2_file_path": final_key,
                "r2_parsed_json_path": json_key,
                "file_size": (body.get("object") or {}).get("size"),
                "ai_model": config.ai_model,
                "parsed_json": parsed_payload,
            },
        )

        await add_neurons_consumed(
            env.VAULT_DB,
            classification["neurons_consumed"],
        )
        await bucket.delete(key)
