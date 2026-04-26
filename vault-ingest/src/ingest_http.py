"""POST /__vault_ingest/trigger — run ingest without an R2 event (e2e / ops)."""

from urllib.parse import urlparse

from workers import Response

from storage.budget import has_budget
from config import load_config
from providers.gemini import GeminiRequeueError, gemini_requeue_delay_seconds

TRIGGER_PATH = "/__vault_ingest/trigger"
_SECRET_HEADER = "x-vault-ingest-secret"


def _path_is_trigger(request_url: str) -> bool:
    return urlparse(request_url).path.rstrip("/") == TRIGGER_PATH


def _x_vault_ingest_secret(request) -> str:
    for name, val in request.headers.items():
        if str(name).lower() == _SECRET_HEADER:
            return (val or "").strip()
    return ""


def _err_body(msg: str, max_len: int = 500) -> str:
    if len(msg) <= max_len:
        return msg
    return msg[:max_len] + "…"


async def _handle_provider_requeue(
    env,
    to_js,
    body: dict,
    key: str,
    *,
    provider: str,
    kind: str,
    detail: str,
    delay: int,
) -> Response:
    """Shared response shape for Gemini requeue outcomes from the HTTP trigger.

    Tries to re-enqueue on ``VAULT_INGEST`` (``202``) so the original request can
    ack the client; falls back to ``503`` with a retry hint if sending to the
    queue fails.
    """
    reason = f"{provider}_requeue"
    print(
        f"[{key}] {provider.capitalize()} {kind} (requeue"
        f"{': ' + detail if detail else ''}); scheduling {delay}s (HTTP trigger)"
    )
    q = getattr(env, "VAULT_INGEST", None)
    if q is not None:
        try:
            await q.send(to_js(body), delaySeconds=delay)
            return Response.from_json(
                {
                    "ok": True,
                    "requeued": True,
                    "reason": reason,
                    "provider": provider,
                    "requeue_kind": kind,
                    "requeue_detail": detail,
                    "delay_seconds": delay,
                    "key": key,
                },
                status=202,
            )
        except Exception as send_err:
            print(f"[{key}] requeue to VAULT_INGEST failed: {send_err!s}")
    return Response.from_json(
        {
            "error": reason,
            "provider": provider,
            "requeue_kind": kind,
            "requeue_detail": detail,
            "retry_in_seconds": delay,
            "key": key,
        },
        status=503,
    )


async def handle_vault_ingest_http_trigger(
    process_r2_event,
    request,
    env,
    to_js,
) -> Response:
    """``process_r2_event`` is ``async (env, config, body: dict, key: str) -> None``."""
    if not _path_is_trigger(request.url):
        return Response("Not found", status=404)
    if request.method != "POST":
        return Response("Method not allowed", status=405)

    secret = str(getattr(env, "VAULT_INGEST_HTTP_SECRET", "") or "").strip()
    if not secret:
        return Response("Not found", status=404)
    if _x_vault_ingest_secret(request) != secret:
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

    config = load_config(env)
    if not key.startswith(config.inbox_prefix):
        return Response.from_json(
            {"error": f"key must be under {config.inbox_prefix!r}"},
            status=400,
        )
    if not await has_budget(env.VAULT_DB, config.daily_neuron_budget):
        return Response("Daily AI budget exhausted", status=503)

    size = data.get("size")
    if size is not None and not isinstance(size, (int, float)):
        size = None
    obj: dict = {"key": key}
    if size is not None:
        obj["size"] = int(size)
    et = data.get("eventTime")
    body: dict = {
        "object": obj,
        "eventTime": et if isinstance(et, str) else None,
    }

    try:
        await process_r2_event(env, config, body, key)
    except GeminiRequeueError as greq:
        return await _handle_provider_requeue(
            env,
            to_js,
            body,
            key,
            provider="gemini",
            kind=greq.kind,
            detail=greq.detail,
            delay=gemini_requeue_delay_seconds(greq),
        )
    except Exception as exc:
        err_s = _err_body(str(exc))
        print(f"HTTP trigger process failed: {err_s}")
        return Response.from_json({"error": err_s}, status=500)

    return Response.from_json({"ok": True, "key": key})
