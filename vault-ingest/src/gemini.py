"""Google Gemini API path: HTTP calls, throttling requeue, and two-stage classification."""

import base64
import json
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from js import Object, TextDecoder, Uint8Array
from pyodide.ffi import to_js
from pyodide.http import pyfetch

from gemini_quota import check_gemini_quota, record_gemini_call
from taxonomy import (
    CATEGORIES,
    SYSTEM_PROMPT,
    get_extraction_prompt,
    get_targeted_schema,
)
from utils import (
    is_plain_text,
    parse_json_response,
    path_basename,
    validate_extraction,
)

# Fallback delays for requeues where neither our D1 pre-flight check nor Gemini
# gave us a specific retry hint. Rate limits want a full minute-plus; transient
# overloads can usually be retried sooner.
GEMINI_RETRY_DELAY_SECONDS = 60
GEMINI_RATE_LIMIT_RETRY_BASE_SECONDS = 75
GEMINI_TRANSIENT_RETRY_BASE_SECONDS = 30
GEMINI_RETRY_JITTER_SECONDS = 30
_MAX_RETRY_DELAY_SECONDS = 24 * 3600

# Stage-2 must emit the full JSON (e.g. many ``full_text_or_records`` rows from PDFs). 8192 is too small.
# Gemini 3 Flash supports large outputs; see https://ai.google.dev/gemini-api/docs/gemini-3
GEMINI_STAGE2_MAX_OUTPUT_TOKENS = 65_536


class GeminiRequeueError(Exception):
    """Only raised from the Gemini API path. ``kind`` is ``rate_limit`` (429 / RPM/RPD
    exhausted) or ``transient`` (503 / busy / UNAVAILABLE).

    ``retry_after_seconds`` is a specific wait hint (from the D1 pre-flight check
    or an API ``Retry-After``). ``None`` means "use the caller's default".
    """

    def __init__(self, kind: str, detail: str = "", retry_after_seconds: int | None = None):
        self.kind = kind
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds

    def __str__(self) -> str:
        parts = [f"Gemini requeue {self.kind}"]
        if self.detail:
            parts.append(f"({self.detail})")
        if self.retry_after_seconds is not None:
            parts.append(f"retry_after={self.retry_after_seconds}s")
        return " ".join(parts)


def gemini_requeue_delay_seconds(err: GeminiRequeueError) -> int:
    if err.retry_after_seconds is not None:
        return _bounded_retry_delay(err.retry_after_seconds)
    if err.kind == "rate_limit":
        return _jittered_retry_delay(GEMINI_RATE_LIMIT_RETRY_BASE_SECONDS)
    if err.kind == "transient":
        return _jittered_retry_delay(GEMINI_TRANSIENT_RETRY_BASE_SECONDS)
    return _jittered_retry_delay(GEMINI_RETRY_DELAY_SECONDS)


def _bounded_retry_delay(seconds: int | float) -> int:
    return max(1, min(int(seconds), _MAX_RETRY_DELAY_SECONDS))


def _jittered_retry_delay(base_seconds: int) -> int:
    return _bounded_retry_delay(base_seconds + random.randint(0, GEMINI_RETRY_JITTER_SECONDS))


def _to_js(value):
    return to_js(value, dict_converter=Object.fromEntries)


def _array_buffer_to_bytes(array_buffer) -> bytes:
    return bytes(Uint8Array.new(array_buffer))


def _gemini_uses_inline_data(content_type: str) -> bool:
    lower = (content_type or "").lower()
    if lower == "application/pdf":
        return True
    if lower.startswith("image/"):
        return True
    return False


def _gemini_response_text(data: dict) -> str:
    cands = data.get("candidates") or []
    if not cands:
        err = data.get("error") or data.get("promptFeedback")
        raise RuntimeError(f"Gemini returned no candidates: {data!r}"[:2000])
    first = cands[0]
    if first.get("finishReason") and first.get("finishReason") not in ("STOP", "MAX_TOKENS"):
        reason = first.get("finishReason")
        print(f"Gemini finishReason={reason}")
    parts = (first.get("content") or {}).get("parts") or []
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("text"):
            texts.append(str(p["text"]))
    if not texts:
        raise RuntimeError(f"Gemini response had no text parts: {first!r}"[:2000])
    return "\n".join(texts).strip()


def _gemini_usage_tokens(data: dict) -> dict[str, int]:
    u = data.get("usageMetadata") or {}
    return {
        "prompt_token_count": int(u.get("promptTokenCount") or 0),
        "candidates_token_count": int(u.get("candidatesTokenCount") or 0),
    }


def _gemini_embedded_error_is_rate_limit(err: dict) -> bool:
    """True for 429 / explicit rate throttling. Checked before :func:`_gemini_embedded_error_is_transient`."""
    code = err.get("code")
    if isinstance(code, int) and code == 429:
        return True
    msg = str(err.get("message") or "").lower()
    if "too many requests" in msg:
        return True
    if "rate" in msg and "limit" in msg:
        return True
    return False


def _gemini_embedded_error_is_transient(err: dict) -> bool:
    """True for model busy / high demand / UNAVAILABLE (not 429)."""
    if _gemini_embedded_error_is_rate_limit(err):
        return False
    code = err.get("code")
    if isinstance(code, int) and code in (502, 503, 504):
        return True
    status = (err.get("status") or "")
    if isinstance(status, str) and status.upper() in (
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "ABORTED",
    ):
        return True
    msg = str(err.get("message") or "").lower()
    for frag in (
        "high demand",
        "spikes in demand",
        "try again later",
        "temporarily unavailable",
    ):
        if frag in msg:
            return True
    if "unavailable" in msg and "rate" not in msg and "limit" not in msg:
        return True
    if "overloaded" in msg:
        return True
    return False


def _response_retry_after_seconds(response) -> int | None:
    """Parse HTTP ``Retry-After`` if Gemini sends one (seconds or HTTP-date)."""
    headers = getattr(response, "headers", None)
    get = getattr(headers, "get", None)
    if get is None:
        return None
    value = get("Retry-After") or get("retry-after")
    if not value:
        return None
    s = str(value).strip()
    if s.isdigit():
        return _bounded_retry_delay(int(s))
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _bounded_retry_delay((dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def _gemini_retry_info_seconds(err: dict) -> int | None:
    """Parse ``google.rpc.RetryInfo.retryDelay`` values like ``"60s"``."""
    for detail in err.get("details") or ():
        if not isinstance(detail, dict):
            continue
        typ = str(detail.get("@type") or "")
        if not typ.endswith("google.rpc.RetryInfo"):
            continue
        delay = str(detail.get("retryDelay") or "").strip()
        if not delay.endswith("s"):
            continue
        try:
            return _bounded_retry_delay(float(delay[:-1]))
        except Exception:
            continue
    return None


async def _gemini_generate(
    api_key: str,
    model: str,
    system_text: str,
    user_parts: list[dict],
    *,
    max_output_tokens: int = 8192,
    db=None,
) -> dict:
    """Call ``generateContent``; returns the parsed JSON body as a ``dict``.

    When ``db`` is provided (the D1 binding), every outcome is recorded in
    ``gemini_request_log`` so :func:`gemini_quota.check_gemini_quota` can make
    accurate pre-flight decisions on the next message.
    """
    enc_model = quote(model, safe="")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{enc_model}:generateContent"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": [
            {
                "role": "user",
                "parts": user_parts,
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    r = await pyfetch(
        url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        body=json.dumps(body, ensure_ascii=False),
    )
    text = await r.string()

    api_retry_after = _response_retry_after_seconds(r)

    async def _raise_requeue(
        kind: str,
        detail: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        # Record the failed call so the quota ledger reflects reality even
        # when the API rejected us (important: Google counts rejected RPM
        # attempts against the quota as well).
        if db is not None:
            await record_gemini_call(db, model=model, outcome=kind)
        raise GeminiRequeueError(
            kind,
            detail,
            retry_after_seconds=retry_after_seconds or api_retry_after,
        )

    if r.status < 200 or r.status >= 300:
        retry_info = None
        payload = {}
        ge = None
        try:
            payload = json.loads(text) if text else {}
            ge = payload.get("error")
            if isinstance(ge, dict):
                retry_info = _gemini_retry_info_seconds(ge)
        except Exception:
            pass
        if r.status == 429:
            await _raise_requeue("rate_limit", "http_429", retry_info)
        # 524 = Cloudflare "origin timeout" (long-running upstream, including some
        # Google API edge paths). Treat like other transient HTTP failures.
        if r.status in (502, 503, 504, 524):
            await _raise_requeue("transient", f"http_{r.status}", retry_info)
        try:
            if isinstance(ge, dict):
                if _gemini_embedded_error_is_rate_limit(ge):
                    await _raise_requeue("rate_limit", f"http_{r.status}_body", retry_info)
                if _gemini_embedded_error_is_transient(ge):
                    await _raise_requeue("transient", f"http_{r.status}_body", retry_info)
        except GeminiRequeueError:
            raise
        except Exception:
            pass
        if db is not None:
            await record_gemini_call(db, model=model, outcome="error")
        snippet = (text or "").replace("\n", " ").strip()[:240]
        raise RuntimeError(f"Gemini API HTTP {r.status}: {snippet}")
    data = json.loads(text) if text else {}
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            retry_info = _gemini_retry_info_seconds(err)
            if _gemini_embedded_error_is_rate_limit(err):
                await _raise_requeue("rate_limit", "error_body", retry_info)
            if _gemini_embedded_error_is_transient(err):
                await _raise_requeue("transient", "error_body", retry_info)
        if db is not None:
            await record_gemini_call(db, model=model, outcome="error")
        raise RuntimeError(f"Gemini API error: {err}")
    if db is not None:
        await record_gemini_call(db, model=model, outcome="ok")
    return data


def _build_gemini_user_parts(
    file_name: str,
    content_type: str,
    text_or_none: str | None,
    inline_mime: str | None,
    inline_b64: str | None,
    user_message: str,
) -> list[dict]:
    """Full document: text, or a single inline blob (e.g. PDF) plus the task text."""
    parts: list[dict] = []
    if text_or_none is not None:
        parts.append({"text": f"Source: {file_name} ({content_type})\n\n{text_or_none}"})
    else:
        if not inline_mime or not inline_b64:
            raise RuntimeError("Gemini: internal error; expected inline data or text")
        parts.append(
            {
                "inline_data": {
                    "mime_type": inline_mime,
                    "data": inline_b64,
                }
            }
        )
    parts.append({"text": user_message})
    return parts


async def _document_context_for_gemini(
    env, key: str, content_type: str, array_buffer
) -> tuple[str, str | None, str | None, str | None, int]:
    """Build inputs for the Gemini API: full plain text, or a single inline blob
    (PDF, images), or Workers ``toMarkdown`` text for other formats.

    Returns ``(r2_stored_text, text_full, inline_mime, inline_b64, md_tokens)``.
    """
    from ai import _document_to_text  # noqa: PLC0415 — after ``ai`` finishes loading; avoids import cycle

    file_name = path_basename(key)
    if is_plain_text(content_type, key):
        text = TextDecoder.new("utf-8").decode(array_buffer)
        full = str(text)
        return full, full, None, None, 0

    if _gemini_uses_inline_data(content_type):
        raw = _array_buffer_to_bytes(array_buffer)
        b64 = base64.b64encode(raw).decode("ascii")
        note = f"[Full file sent to Gemini as {content_type} — {file_name}]\n"
        return note, None, content_type, b64, 0

    document_text, conversion_tokens = await _document_to_text(env, key, content_type, array_buffer)
    return document_text, document_text, None, None, conversion_tokens


async def _run_gemini_extraction_with_retry(
    api_key: str,
    model: str,
    file_name: str,
    content_type: str,
    text_full: str | None,
    inline_mime: str | None,
    inline_b64: str | None,
    prompt: str,
    schema: dict,
    category: str,
    subcategory: str,
    *,
    db=None,
) -> tuple[dict, dict, dict | None]:
    """Run Gemini Stage-2 extraction; retry with validation errors in the system prompt if needed."""
    user_message = "Extract structured data from the file above. Return only one JSON object as specified by the system instruction."
    parts = _build_gemini_user_parts(
        file_name, content_type, text_full, inline_mime, inline_b64, user_message
    )
    data1 = await _gemini_generate(
        api_key, model, prompt, parts, max_output_tokens=GEMINI_STAGE2_MAX_OUTPUT_TOKENS, db=db
    )
    raw1 = _gemini_response_text(data1)
    parsed = parse_json_response(raw1)
    errors = validate_extraction(parsed, schema)
    if not errors:
        return parsed, data1, None

    truncated = errors[:8]
    joined = "\n".join(f"  - {e}" for e in truncated)
    print(
        f"[{file_name}] Stage 2 (Gemini) off-schema for {category}/{subcategory}; retrying. Errors:\n{joined}"
    )
    correction = (
        f"{prompt}\n\n"
        "Your previous response did not match the required shape. "
        "Fix these issues and return ONLY the corrected JSON object:\n"
        f"{joined}"
    )
    data2 = await _gemini_generate(
        api_key, model, correction, parts, max_output_tokens=GEMINI_STAGE2_MAX_OUTPUT_TOKENS, db=db
    )
    raw2 = _gemini_response_text(data2)
    retry_parsed = parse_json_response(raw2)
    retry_errors = validate_extraction(retry_parsed, schema)
    if retry_errors:
        remaining = "\n".join(f"  - {e}" for e in retry_errors[:8])
        print(f"[{file_name}] Stage 2 (Gemini) still off-schema after retry:\n{remaining}")
    return retry_parsed, data1, data2


async def _assert_gemini_quota_available(
    db,
    config,
    file_name: str,
    *,
    model: str,
    rpm_limit: int,
    rpd_limit: int,
    expected_calls: int = 1,
) -> None:
    ok, wait_s, reason = await check_gemini_quota(
        db,
        rpm_limit=rpm_limit,
        rpd_limit=rpd_limit,
        model=model,
        expected_calls=expected_calls,
    )
    if ok:
        return
    print(f"[{file_name}] Gemini pre-flight: {reason}; requeueing in {wait_s}s")
    kind = "rate_limit" if reason.startswith(("rpm_", "rpd_")) else "transient"
    raise GeminiRequeueError(kind, reason, retry_after_seconds=wait_s)


async def _classify_with_gemini(
    env,
    config,
    key: str,
    content_type: str,
    array_buffer,
) -> dict:
    from ai import _markdown_breakdown  # noqa: PLC0415

    if not config.gemini_api_key:
        raise RuntimeError(
            "Set Worker secret GEMINI_API_KEY to use a Gemini model (e.g. gemini-3.1-flash-lite-preview). "
        )
    api_key = config.gemini_api_key
    db = getattr(env, "VAULT_DB", None)
    file_name = path_basename(key)

    r2_stored, text_full, inline_mime, inline_b64, conversion_tokens = await _document_context_for_gemini(
        env, key, content_type, array_buffer
    )

    # --- Stage 1: full document in request (no 4000-char cap) ---
    print(f"[{file_name}] Stage 1: Classifying with Gemini {config.stage1_model}...")
    s1_user = (
        f"File name: {file_name}.\n"
        "Classify this document. Return only JSON with \"category\" and \"subcategory\" as specified in the system instruction."
    )
    s1_parts = _build_gemini_user_parts(
        file_name, content_type, text_full, inline_mime, inline_b64, s1_user
    )
    if db is not None:
        await _assert_gemini_quota_available(
            db,
            config,
            file_name,
            model=config.stage1_model,
            rpm_limit=config.gemini_rpm_limit,
            rpd_limit=config.gemini_rpd_limit,
            expected_calls=1,
        )
    s1_data = await _gemini_generate(
        api_key, config.stage1_model, SYSTEM_PROMPT, s1_parts, max_output_tokens=1024, db=db
    )
    s1_parsed = parse_json_response(_gemini_response_text(s1_data))

    category = s1_parsed.get("category", "other")
    subcategory = s1_parsed.get("subcategory", "uncategorized")
    if category not in CATEGORIES:
        category = "other"

    print(f"[{file_name}] Stage 2: Extracting {category}/{subcategory} with Gemini {config.stage2_model}...")
    targeted_schema = get_targeted_schema(category, subcategory)
    extraction_prompt = get_extraction_prompt(category, subcategory)
    if db is not None:
        await _assert_gemini_quota_available(
            db,
            config,
            file_name,
            model=config.stage2_model,
            rpm_limit=config.gemini_stage2_rpm_limit,
            rpd_limit=config.gemini_stage2_rpd_limit,
            expected_calls=2,
        )
    s2_parsed, s2_data, s2_retry_data = await _run_gemini_extraction_with_retry(
        api_key,
        config.stage2_model,
        file_name,
        content_type,
        text_full,
        inline_mime,
        inline_b64,
        extraction_prompt,
        targeted_schema,
        category,
        subcategory,
        db=db,
    )

    u1 = _gemini_usage_tokens(s1_data)
    u2 = _gemini_usage_tokens(s2_data)
    u2r = _gemini_usage_tokens(s2_retry_data) if s2_retry_data else None
    s2_in = u2["prompt_token_count"] + (u2r["prompt_token_count"] if u2r else 0)
    s2_out = u2["candidates_token_count"] + (u2r["candidates_token_count"] if u2r else 0)
    md = _markdown_breakdown(conversion_tokens)

    total_llm_in = u1["prompt_token_count"] + s2_in
    total_llm_out = u1["candidates_token_count"] + s2_out

    usage = {
        "markdown_output_tokens":  md["tokens"],
        "markdown_neurons":        md["neurons"],
        "stage1_input_tokens":     u1["prompt_token_count"],
        "stage1_output_tokens":    u1["candidates_token_count"],
        "stage2_input_tokens":     s2_in,
        "stage2_output_tokens":    s2_out,
        "stage2_retried":          s2_retry_data is not None,
        "llm_neurons":             0.0,
        "llm_input_tokens":        total_llm_in,
        "llm_output_tokens":       total_llm_out,
        "llm_input_neurons":       0.0,
        "llm_output_neurons":      0.0,
    }

    print(
        f"[{file_name}] Gemini token totals (S1: {u1['prompt_token_count']}/"
        f"{u1['candidates_token_count']}, S2: {s2_in}/{s2_out}"
        f"{' [retried]' if s2_retry_data else ''}); Cloudflare neurons recorded as 0 (Gemini usage is on the Google AI quota)."
    )

    return {
        "parsed_json": s2_parsed,
        "category": category,
        "subcategory": subcategory,
        "neurons_consumed": 0.0,
        "usage_breakdown":  usage,
        "document_text":     r2_stored,
    }
