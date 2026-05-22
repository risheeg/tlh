"""Mistral API path: OCR via Files + OCR endpoints, Chat for classification/extraction."""

import asyncio
import json
import random

from js import Blob, FormData, TextDecoder
from pyodide.http import pyfetch

class MistralRequeueError(Exception):
    def __init__(self, kind, detail=None, retry_after_seconds=None):
        self.kind = kind
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds
        super().__init__(self.__str__())

    def __str__(self):
        parts = [f"Mistral requeue {self.kind}"]
        if self.detail:
            parts.append(f"({self.detail})")
        if self.retry_after_seconds is not None:
            parts.append(f"retry_after={self.retry_after_seconds}s")
        return " ".join(parts)


def mistral_requeue_delay_seconds(err):
    """Determine the Cloudflare Queue requeue delay.

    Priority order:
    1. Exact ``Retry-After`` value from the Mistral API (clamped 1–86 400 s).
    2. Fallback: random 30–60 s.
    """
    if getattr(err, "retry_after_seconds", None) is not None:
        return max(1, min(int(err.retry_after_seconds), 86_400))
    return 30 + random.randint(0, 30)


# ---------------------------------------------------------------------------
# Retry-After header extraction
# ---------------------------------------------------------------------------

def _parse_retry_after(response):
    """Return an integer seconds value from the ``Retry-After`` header, or None."""
    headers = getattr(response, "headers", None)
    hget = getattr(headers, "get", None) if headers else None
    if hget is None:
        return None
    val = hget("Retry-After") or hget("retry-after")
    if not val:
        return None
    s = str(val).strip()
    # Retry-After can be an integer (seconds) or an HTTP-date.
    # Mistral always sends seconds; handle both defensively.
    try:
        return max(0, int(s))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core retry loop
# ---------------------------------------------------------------------------

# Inline budget: total wall-clock seconds the worker may sleep across all
# retries before giving up and requeueing to the Cloudflare Queue.
# asyncio.sleep is FREE on Cloudflare (no CPU cost), so the only hard
# ceiling is the 15-minute queue consumer wall-clock limit.  We use 5 min
# to stay well within that while maximising inline retries (which preserve
# expensive OCR / Stage-1 state that a requeue would redo from scratch).
_INLINE_WALL_BUDGET_S = 300
# Cap on any single inline sleep to keep individual attempts short.
_MAX_SINGLE_SLEEP_S = 15

async def _fetch_with_retry(url, kwargs_factory, max_retries=5, base_delay=1.0):
    """Time-budget-aware retry loop.

    Instead of a fixed retry count, the loop tracks *cumulative* inline
    sleep time.  As long as the next sleep fits within ``_INLINE_WALL_BUDGET_S``
    the retry happens in-worker (preserving OCR / Stage-1 state).  Once the
    budget is exhausted — or Mistral's ``Retry-After`` exceeds the remaining
    budget — the request is requeued to Cloudflare Queues with a precise delay.

    Decision tree for each retryable response:

    1. Mistral sent ``Retry-After``?
       a. Value fits in remaining wall budget → sleep exactly that long inline.
       b. Value exceeds remaining budget     → requeue to queue with that delay.
    2. No ``Retry-After`` → exponential backoff (capped at ``_MAX_SINGLE_SLEEP_S``).
       a. Fits in remaining budget → sleep inline.
       b. Doesn't fit              → requeue with a jittered 30–60 s delay.
    """
    total_slept = 0.0
    attempt = 0

    while True:
        kwargs = kwargs_factory()

        # ---- network-level failure ----
        try:
            r = await pyfetch(url, **kwargs)
        except Exception as e:
            if max_retries <= 2:
                raise RuntimeError(f"Mistral request failed: {e}")
            delay = min(base_delay * (2 ** attempt), _MAX_SINGLE_SLEEP_S) + random.uniform(0, 0.5)
            if total_slept + delay > _INLINE_WALL_BUDGET_S:
                raise MistralRequeueError("network", detail=str(e))
            print(
                f"[Mistral] Network error {e}, sleeping {delay:.1f}s inline "
                f"(attempt {attempt+1}, {total_slept:.0f}/{_INLINE_WALL_BUDGET_S}s used)"
            )
            await asyncio.sleep(delay)
            total_slept += delay
            attempt += 1
            continue

        # ---- successful response ----
        if not (r.status == 429 or r.status >= 500 or r.status == 404):
            return r

        # ---- retryable HTTP error ----
        text = await r.string()
        if max_retries <= 2:
            raise RuntimeError(f"Mistral HTTP {r.status}: {text[:500]}")

        kind = "rate_limit" if r.status == 429 else "transient"
        retry_after = _parse_retry_after(r)
        remaining_budget = _INLINE_WALL_BUDGET_S - total_slept

        # Decide: sleep inline or requeue to Cloudflare?
        if retry_after is not None:
            # API told us exactly how long to wait.
            if retry_after <= remaining_budget:
                delay = retry_after + random.uniform(0, 1.0)
                print(
                    f"[Mistral] HTTP {r.status} (Retry-After={retry_after}s), "
                    f"sleeping {delay:.1f}s inline (attempt {attempt+1}, "
                    f"{total_slept:.0f}/{_INLINE_WALL_BUDGET_S}s used)"
                )
                await asyncio.sleep(delay)
                total_slept += delay
                attempt += 1
                continue
            else:
                # Too long to wait inline — hand off to the queue.
                raise MistralRequeueError(
                    kind,
                    detail=(
                        f"HTTP {r.status} (Retry-After={retry_after}s "
                        f"exceeds {remaining_budget:.0f}s remaining inline budget)"
                    ),
                    retry_after_seconds=retry_after,
                )
        else:
            # No hint from Mistral — exponential backoff.
            delay = min(base_delay * (2 ** attempt), _MAX_SINGLE_SLEEP_S) + random.uniform(0, 0.5)
            if total_slept + delay <= remaining_budget:
                print(
                    f"[Mistral] HTTP {r.status}, sleeping {delay:.1f}s inline "
                    f"(attempt {attempt+1}, {total_slept:.0f}/{_INLINE_WALL_BUDGET_S}s used)"
                )
                await asyncio.sleep(delay)
                total_slept += delay
                attempt += 1
                continue
            else:
                raise MistralRequeueError(
                    kind,
                    detail=f"HTTP {r.status} {text[:200]} (exhausted {total_slept:.0f}s inline budget)",
                )

from providers.common import (
    document_to_text,
    markdown_breakdown,
)
from util.js_interop import to_js_obj
from util.paths import is_plain_text, path_basename
from util.json_parse import parse_json_response
from util.validation import validate_extraction

from taxonomy import (
    CATEGORIES,
    DOCUMENT_SCHEMA,
    SYSTEM_PROMPT,
    get_extraction_prompt,
    get_targeted_schema,
)

MISTRAL_OCR_MODEL = "mistral-ocr-latest"

_MISTRAL_API_BASE = "https://api.mistral.ai/v1"


def _mistral_ocr_uses_file_upload(content_type):
    lower = (content_type or "").lower()
    if lower == "application/pdf":
        return True
    if lower.startswith("image/"):
        return True
    return False


# ---------------------------------------------------------------------------
# Mistral Files API — upload / delete (private, workspace-scoped)
# ---------------------------------------------------------------------------

async def _mistral_upload_file(api_key, array_buffer, file_name, content_type):
    """Upload a file to Mistral Files API for OCR processing."""
    blob = Blob.new(
        to_js_obj([array_buffer]),
        to_js_obj({"type": content_type}),
    )
    def make_kwargs():
        form = FormData.new()
        form.append("file", blob, file_name)
        form.append("purpose", "ocr")
        return {
            "method": "POST",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "body": form,
        }

    r = await _fetch_with_retry(f"{_MISTRAL_API_BASE}/files", make_kwargs)
    text = await r.string()
    if r.status < 200 or r.status >= 300:
        raise RuntimeError(f"Mistral Files upload HTTP {r.status}: {text[:500]}")
    data = json.loads(text)
    file_id = data.get("id")
    if not file_id:
        raise RuntimeError(f"Mistral Files upload returned no file ID: {data}")
    print(f"[Mistral] Uploaded {file_name} → file_id={file_id}")
    return str(file_id)


async def _mistral_delete_file(api_key, file_id):
    """Delete a file from Mistral after OCR processing. Best-effort."""
    try:
        r = await _fetch_with_retry(
            f"{_MISTRAL_API_BASE}/files/{file_id}",
            lambda: {
                "method": "DELETE",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            },
            max_retries=2
        )
        if r.status < 200 or r.status >= 300:
            text = await r.string()
            print(f"[Mistral] Warning: failed to delete file {file_id}: HTTP {r.status} {text[:200]}")
        else:
            print(f"[Mistral] Deleted uploaded file {file_id}")
    except Exception as exc:
        print(f"[Mistral] Warning: failed to delete file {file_id}: {exc}")


# ---------------------------------------------------------------------------
# Mistral OCR API
# ---------------------------------------------------------------------------

async def _mistral_ocr(api_key, file_id):
    body = {
        "model": MISTRAL_OCR_MODEL,
        "document": {"type": "file", "file_id": file_id},
    }
    r = await _fetch_with_retry(
        f"{_MISTRAL_API_BASE}/ocr",
        lambda: {
            "method": "POST",
            "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            "body": json.dumps(body),
        }
    )
    text = await r.string()
    if r.status < 200 or r.status >= 300:
        raise RuntimeError(f"Mistral OCR HTTP {r.status}: {text[:500]}")
    data = json.loads(text)
    pages = data.get("pages") or []
    if not pages:
        raise RuntimeError(f"Mistral OCR returned no pages: {data!r}"[:1000])
    parts = []
    for page in pages:
        md = page.get("markdown")
        if md:
            parts.append(str(md))
    if not parts:
        raise RuntimeError("Mistral OCR returned pages but no markdown content")
    usage = data.get("usage_info") or {}
    print(
        f"[Mistral] OCR completed: {len(pages)} pages processed "
        f"(model={data.get('model', MISTRAL_OCR_MODEL)})"
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Document to text — Mistral OCR for PDFs/images, fallback otherwise
# ---------------------------------------------------------------------------

async def _document_to_text_mistral(env, api_key, key, content_type, array_buffer):
    file_name = path_basename(key)
    if is_plain_text(content_type, key):
        text = TextDecoder.new("utf-8").decode(array_buffer)
        return str(text), 0
    if _mistral_ocr_uses_file_upload(content_type):
        file_id = await _mistral_upload_file(api_key, array_buffer, file_name, content_type)
        try:
            markdown = await _mistral_ocr(api_key, file_id)
        finally:
            await _mistral_delete_file(api_key, file_id)
        return markdown, 0
    # Unsupported by Mistral OCR — fall back to Workers AI
    return await document_to_text(env, key, content_type, array_buffer)


# ---------------------------------------------------------------------------
# Mistral Chat Completions API
# ---------------------------------------------------------------------------

def _mistral_response_text(data):
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Mistral returned no choices: {data!r}"[:2000])
    first = choices[0]
    message = first.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise RuntimeError(f"Mistral response had no text content: {first!r}"[:2000])


def _mistral_usage(data):
    u = data.get("usage") or {}
    return {
        "prompt_tokens": int(u.get("prompt_tokens") or 0),
        "completion_tokens": int(u.get("completion_tokens") or 0),
    }


async def _mistral_chat(api_key, model, messages, *, response_format=None, temperature=0, max_tokens=4096):
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_format is not None:
        body["response_format"] = response_format
    r = await _fetch_with_retry(
        f"{_MISTRAL_API_BASE}/chat/completions",
        lambda: {
            "method": "POST",
            "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False),
        }
    )
    text = await r.string()
    if r.status < 200 or r.status >= 300:
        raise RuntimeError(f"Mistral Chat HTTP {r.status}: {text[:500]}")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Stage-2 extraction with validation retry
# ---------------------------------------------------------------------------

async def _run_mistral_extraction_with_retry(api_key, model, file_name, document_text, prompt, schema, category, subcategory):
    def _stage2_messages(system_prompt):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Source: {file_name}\n\n{document_text}"},
        ]

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "extraction", "strict": True, "schema": schema},
    }
    data1 = await _mistral_chat(api_key, model, _stage2_messages(prompt), response_format=response_format, max_tokens=65_536)
    parsed = parse_json_response(_mistral_response_text(data1))
    errors = validate_extraction(parsed, schema)
    if not errors:
        return parsed, data1, None

    truncated = errors[:8]
    joined = "\n".join(f"  - {e}" for e in truncated)
    print(f"[{file_name}] Stage 2 (Mistral) off-schema for {category}/{subcategory}; retrying. Errors:\n{joined}")
    correction = (
        f"{prompt}\n\n"
        "Your previous response did not match the required shape. "
        "Fix these issues and return ONLY the corrected JSON object:\n"
        f"{joined}"
    )
    data2 = await _mistral_chat(api_key, model, _stage2_messages(correction), response_format=response_format, max_tokens=65_536)
    retry_parsed = parse_json_response(_mistral_response_text(data2))
    retry_errors = validate_extraction(retry_parsed, schema)
    if retry_errors:
        remaining = "\n".join(f"  - {e}" for e in retry_errors[:8])
        print(f"[{file_name}] Stage 2 (Mistral) still off-schema after retry:\n{remaining}")
    return retry_parsed, data1, data2


# ---------------------------------------------------------------------------
# Two-stage pipeline
# ---------------------------------------------------------------------------

async def classify_with_mistral(env, config, key, content_type, array_buffer):
    if not config.mistral_api_key:
        raise RuntimeError("Set Worker secret MISTRAL_API_KEY to use a Mistral model.")
    api_key = config.mistral_api_key
    file_name = path_basename(key)

    # --- Document to Markdown ---
    document_text, conversion_tokens = await _document_to_text_mistral(env, api_key, key, content_type, array_buffer)

    # --- Stage 1: Classification ---
    print(f"[{file_name}] Stage 1: Classifying with Mistral {config.stage1_model}...")
    s1_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Classify this document: {file_name}\n\n{document_text[:4000]}"},
    ]
    s1_response_format = {
        "type": "json_schema",
        "json_schema": {"name": "classification", "strict": True, "schema": DOCUMENT_SCHEMA},
    }
    s1_data = await _mistral_chat(api_key, config.stage1_model, s1_messages, response_format=s1_response_format, max_tokens=1024)
    s1_parsed = parse_json_response(_mistral_response_text(s1_data))

    category = s1_parsed.get("category", "other")
    subcategory = s1_parsed.get("subcategory", "uncategorized")
    if category not in CATEGORIES:
        category = "other"

    # --- Stage 2: Targeted Extraction ---
    print(f"[{file_name}] Stage 2: Extracting {category}/{subcategory} with Mistral {config.stage2_model}...")
    targeted_schema = get_targeted_schema(category, subcategory)
    extraction_prompt = get_extraction_prompt(category, subcategory)
    s2_parsed, s2_data, s2_retry_data = await _run_mistral_extraction_with_retry(
        api_key, config.stage2_model, file_name, document_text,
        extraction_prompt, targeted_schema, category, subcategory,
    )

    # --- Usage tracking ---
    u1 = _mistral_usage(s1_data)
    u2 = _mistral_usage(s2_data)
    u2r = _mistral_usage(s2_retry_data) if s2_retry_data else None
    s2_in = u2["prompt_tokens"] + (u2r["prompt_tokens"] if u2r else 0)
    s2_out = u2["completion_tokens"] + (u2r["completion_tokens"] if u2r else 0)
    total_llm_in = u1["prompt_tokens"] + s2_in
    total_llm_out = u1["completion_tokens"] + s2_out

    md = markdown_breakdown(conversion_tokens)

    usage = {
        "markdown_output_tokens":  md["tokens"],
        "markdown_neurons":        md["neurons"],
        "stage1_input_tokens":     u1["prompt_tokens"],
        "stage1_output_tokens":    u1["completion_tokens"],
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
        f"[{file_name}] Mistral token totals (S1: {u1['prompt_tokens']}/"
        f"{u1['completion_tokens']}, S2: {s2_in}/{s2_out}"
        f"{'[retried]' if s2_retry_data else ''}); Cloudflare neurons recorded as 0 (Mistral usage is on the Mistral API quota)."
    )

    return {
        "parsed_json": s2_parsed,
        "category": category,
        "subcategory": subcategory,
        "neurons_consumed": 0.0,
        "usage_breakdown":  usage,
        "document_text":     document_text,
    }
