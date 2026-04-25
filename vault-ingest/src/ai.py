from js import Blob, Object, TextDecoder
from pyodide.ffi import to_js

from taxonomy import CATEGORIES, DOCUMENT_SCHEMA, SYSTEM_PROMPT
from utils import is_plain_text, js_to_py, parse_json_response, path_basename


def _to_js(value):
    return to_js(value, dict_converter=Object.fromEntries)


def _extract_response_text(response: dict) -> str:
    if response.get("response"):
        return str(response["response"])

    choices = response.get("choices") or []
    if choices:
        first = choices[0]
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(str(part["text"]))
            if parts:
                return "\n".join(parts)

    raise RuntimeError(f"Could not find text in AI response: {response}")


def _usage_neurons(response: dict, conversion_tokens: int) -> int:
    usage = response.get("usage") or {}
    llm_tokens = usage.get("total_tokens")
    if llm_tokens is None:
        llm_tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    llm_tokens = int(llm_tokens or 0)
    return llm_tokens + int(conversion_tokens or 0)


async def _document_to_text(env, key: str, content_type: str, array_buffer) -> tuple[str, int]:
    if is_plain_text(content_type, key):
        text = TextDecoder.new("utf-8").decode(array_buffer)
        return str(text), 0

    blob = Blob.new([array_buffer], {"type": content_type})
    document = _to_js({"name": path_basename(key), "blob": blob})
    result = await env.AI.toMarkdown(document)
    result = js_to_py(result)
    if isinstance(result, list):
        if not result:
            raise RuntimeError("Workers AI Markdown conversion returned no results")
        result = result[0]

    if result.get("format") == "error":
        raise RuntimeError(f"Markdown conversion failed for {key}: {result.get('error')}")

    data = result.get("data")
    if not data:
        raise RuntimeError(f"Markdown conversion produced no text for {key}")

    return str(data), int(result.get("tokens") or 0)


async def classify_document(env, model: str, key: str, content_type: str, array_buffer) -> dict:
    document_text, conversion_tokens = await _document_to_text(env, key, content_type, array_buffer)
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Classify and extract this document. "
                    f"Source filename: {path_basename(key)}\n\n{document_text}"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "vault_document",
                "strict": True,
                "schema": DOCUMENT_SCHEMA,
            },
        },
        "temperature": 0,
        "max_completion_tokens": 8192,
    }

    response = await env.AI.run(model, _to_js(payload))
    response = js_to_py(response)
    parsed = parse_json_response(_extract_response_text(response))

    category = parsed.get("category")
    if category not in CATEGORIES:
        parsed["category"] = "other"
        parsed["subcategory"] = parsed.get("subcategory") or category

    usage = response.get("usage") or {}
    llm_tokens = usage.get("total_tokens")
    if llm_tokens is None:
        llm_tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    
    print(f"[{path_basename(key)}] AI Neurons Used - Docling (Conversion): {conversion_tokens} | LLM Classification: {llm_tokens}")

    return {
        "parsed_json": parsed,
        "category": parsed["category"],
        "subcategory": parsed.get("subcategory"),
        "neurons_consumed": _usage_neurons(response, conversion_tokens),
        "document_text": document_text,
    }
