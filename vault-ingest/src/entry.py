import uuid

from js import Object
from pyodide.ffi import to_js
from workers import Request, Response, WorkerEntrypoint

from providers import classify_document
from providers.gemini import GeminiRequeueError, gemini_requeue_delay_seconds
from ingest_http import handle_vault_ingest_http_trigger
from storage.budget import add_neurons_consumed, has_budget
from storage.neon import insert_document
from config import load_config
from neon_payload import neon_parsed_view
from util.js_interop import js_to_py, to_js_obj
from util.json_parse import json_dumps
from util.paths import content_type_for_key, markdown_key, parsed_key, processed_key, parse_user_id_from_inbox_key
from util.time import utc_now_iso

RETRY_IN_24_HOURS = 24 * 60 * 60


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
        to_js_obj({"httpMetadata": {"contentType": "application/json"}}),
    )


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        """Optional HTTP trigger; behavior lives in ``ingest_http``."""
        return await handle_vault_ingest_http_trigger(
            self._process_r2_event, request, self.env, to_js_obj
        )

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
                if not key:
                    print(f"Ignoring missing key: {body}")
                    msg.ack()
                    continue

                user_id = parse_user_id_from_inbox_key(key, config.inbox_prefix)
                if not user_id:
                    print(f"Ignoring non-inbox R2 event or missing user_id: {body}")
                    msg.ack()
                    continue

                if not await has_budget(worker_env.VAULT_DB, config.daily_neuron_budget):
                    print("Daily AI neuron budget exhausted; retrying in 24 hours")
                    msg.retry(delaySeconds=RETRY_IN_24_HOURS)
                    continue

                await self._process_r2_event(worker_env, config, body, key, user_id)
                msg.ack()
            except GeminiRequeueError as greq:
                delay = gemini_requeue_delay_seconds(greq)
                print(
                    f"[{key}] Gemini {greq.kind} (requeue{': ' + greq.detail if greq.detail else ''}); "
                    f"msg.retry in {delay}s"
                )
                msg.retry(delaySeconds=delay)
            except Exception as exc:
                err_s = str(exc)
                if len(err_s) > 500:
                    err_s = err_s[:500] + "…"
                print(f"Vault ingest message failed (no retry): {err_s}")
                msg.ack()

    async def _process_r2_event(self, env, config, body: dict, key: str, user_id: str) -> None:
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
        final_key = processed_key(user_id, config.processed_prefix, category, document_id, key)
        json_key = parsed_key(user_id, config.parsed_prefix, category, document_id, key)
        md_key = markdown_key(user_id, config.parsed_prefix, category, document_id, key)

        parsed_payload = classification["parsed_json"]
        # Version is controlled by application code (not model output).
        parsed_payload["schema_version"] = 1

        await _put_json(bucket, json_key, parsed_payload)

        document_text = classification["document_text"]
        await bucket.put(
            md_key,
            document_text,
            to_js_obj({"httpMetadata": {"contentType": "text/markdown"}}),
        )
        await bucket.put(
            final_key,
            array_buffer,
            to_js_obj({"httpMetadata": {"contentType": content_type}}),
        )

        neon_payload = neon_parsed_view(category, subcategory, parsed_payload)

        now = utc_now_iso()
        await insert_document(
            config.neon_connection_string,
            {
                "id": document_id,
                "user_id": user_id,
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
