"""Mistral API path: OCR via Files + OCR endpoints, Chat for classification/extraction."""

import json

from js import Blob, FormData, TextDecoder, Uint8Array
from pyodide.http import pyfetch

from providers.common import (
    array_buffer_to_bytes,
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

async def _mistral_upload_file(api_key, raw_bytes, file_name, content_type):
    """Upload a file to Mistral Files API for OCR processing."""
    blob = Blob.new(
        to_js_obj([Uint8Array.new(to_js_obj(list(raw_bytes)))]),
        to_js_obj({"type": content_type}),
    )
    form = FormData.new()
    form.append("file", blob, file_name)
    form.append("purpose", "ocr")
    r = await pyfetch(
        f"{_MISTRAL_API_BASE}/files",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        body=form,
    )
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
        r = await pyfetch(
            f"{_MISTRAL_API_BASE}/files/{file_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
    r = await pyfetch(
        f"{_MISTRAL_API_BASE}/ocr",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=json.dumps(body),
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
        raw = array_buffer_to_bytes(array_buffer)
        file_id = await _mistral_upload_file(api_key, raw, file_name, content_type)
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
    r = await pyfetch(
        f"{_MISTRAL_API_BASE}/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=json.dumps(body, ensure_ascii=False),
    )
    text = await r.string()
    if r.status == 429:
        raise RuntimeError(f"Mistral rate limited (429): {text[:300]}")
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
