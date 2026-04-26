"""Cloudflare Workers AI provider: two-stage classification and extraction."""

from util.js_interop import to_js_obj, js_to_py
from util.json_parse import parse_json_response
from util.paths import path_basename
from util.validation import validate_extraction

from taxonomy import (
    CATEGORIES,
    DOCUMENT_SCHEMA,
    SYSTEM_PROMPT,
    get_extraction_prompt,
    get_targeted_schema,
)

from providers.common import (
    document_to_text,
    get_neuron_rates,
    markdown_breakdown,
    tokens_to_neurons,
)


def _extract_response_text(response: dict) -> str | dict | list:
    content = response.get("response")
    if content is not None:
        return content

    choices = response.get("choices") or []
    if choices:
        first = choices[0]
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content

        # Support for thinking/reasoning models (like Gemma 4 or DeepSeek R1)
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning

        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("text"):
                        parts.append(str(part["text"]))
                    elif part.get("reasoning"):
                        parts.append(str(part["reasoning"]))
            if parts:
                return "\n".join(parts)

    raise RuntimeError(f"Could not find text in AI response: {response}")


def _llm_breakdown(response: dict, model: str) -> dict:
    usage = response.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        total = int(usage.get("total_tokens") or 0)
        prompt_tokens = round(total * 0.8)
        completion_tokens = total - prompt_tokens
    input_rate, output_rate = get_neuron_rates(model)
    return {
        "prompt_tokens":    prompt_tokens,
        "input_neurons":    tokens_to_neurons(prompt_tokens,    input_rate),
        "completion_tokens": completion_tokens,
        "output_neurons":   tokens_to_neurons(completion_tokens, output_rate),
    }


def _stage2_payload(prompt: str, file_name: str, document_text: str, schema: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Source: {file_name}\n\n{document_text}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "extraction",
                "strict": True,
                "schema": schema,
            },
        },
        "temperature": 0,
        "max_tokens": 4096,
    }


async def _run_extraction_with_retry(
    env,
    model: str,
    file_name: str,
    prompt: str,
    document_text: str,
    schema: dict,
    category: str,
    subcategory: str,
) -> tuple[dict, dict, dict | None]:
    """Run Stage-2 extraction, validate the output, and retry once with the
    validation errors appended to the prompt if it was off-schema.

    Returns ``(parsed_json, first_response, retry_response_or_none)``.
    """
    resp = await env.AI.run(model, to_js_obj(_stage2_payload(prompt, file_name, document_text, schema)))
    resp = js_to_py(resp)
    parsed = parse_json_response(_extract_response_text(resp))

    errors = validate_extraction(parsed, schema)
    if not errors:
        return parsed, resp, None

    truncated = errors[:8]
    joined = "\n".join(f"  - {e}" for e in truncated)
    print(
        f"[{file_name}] Stage 2 output did not match schema for "
        f"{category}/{subcategory}; retrying. Errors:\n{joined}"
    )
    correction = (
        f"{prompt}\n\n"
        "Your previous response did not match the required shape. "
        "Fix these specific issues and return ONLY the corrected JSON object:\n"
        f"{joined}"
    )
    retry_resp = await env.AI.run(model, to_js_obj(_stage2_payload(correction, file_name, document_text, schema)))
    retry_resp = js_to_py(retry_resp)
    retry_parsed = parse_json_response(_extract_response_text(retry_resp))

    retry_errors = validate_extraction(retry_parsed, schema)
    if retry_errors:
        remaining = "\n".join(f"  - {e}" for e in retry_errors[:8])
        print(f"[{file_name}] Stage 2 still off-schema after retry:\n{remaining}")

    return retry_parsed, resp, retry_resp


def is_workers_ai_model(model: str) -> bool:
    return (model or "").strip().startswith("@cf/")


async def classify_with_workers_ai(
    env, config, key: str, content_type: str, array_buffer
) -> dict:
    document_text, conversion_tokens = await document_to_text(env, key, content_type, array_buffer)
    file_name = path_basename(key)

    # --- Stage 1: Classification ---
    print(f"[{file_name}] Stage 1: Classifying with {config.stage1_model}...")
    stage1_payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this document: {file_name}\n\n{document_text[:4000]}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "classification",
                "strict": True,
                "schema": DOCUMENT_SCHEMA,
            },
        },
        "temperature": 0,
    }
    s1_resp = await env.AI.run(config.stage1_model, to_js_obj(stage1_payload))
    s1_resp = js_to_py(s1_resp)
    s1_parsed = parse_json_response(_extract_response_text(s1_resp))

    category = s1_parsed.get("category", "other")
    subcategory = s1_parsed.get("subcategory", "uncategorized")
    if category not in CATEGORIES:
        category = "other"

    # --- Stage 2: Targeted Extraction ---
    print(f"[{file_name}] Stage 2: Extracting {category}/{subcategory} with {config.stage2_model}...")
    targeted_schema = get_targeted_schema(category, subcategory)
    extraction_prompt = get_extraction_prompt(category, subcategory)

    s2_parsed, s2_resp, s2_retry_resp = await _run_extraction_with_retry(
        env,
        config.stage2_model,
        file_name,
        extraction_prompt,
        document_text,
        targeted_schema,
        category,
        subcategory,
    )

    # Neuron breakdown
    llm1 = _llm_breakdown(s1_resp, config.stage1_model)
    llm2 = _llm_breakdown(s2_resp, config.stage2_model)
    llm2_retry = _llm_breakdown(s2_retry_resp, config.stage2_model) if s2_retry_resp else None
    s2_in_neurons  = llm2["input_neurons"]  + (llm2_retry["input_neurons"]  if llm2_retry else 0)
    s2_out_neurons = llm2["output_neurons"] + (llm2_retry["output_neurons"] if llm2_retry else 0)
    s2_in_tokens   = llm2["prompt_tokens"]     + (llm2_retry["prompt_tokens"]     if llm2_retry else 0)
    s2_out_tokens  = llm2["completion_tokens"] + (llm2_retry["completion_tokens"] if llm2_retry else 0)

    md = markdown_breakdown(conversion_tokens)

    total_neurons = llm1["input_neurons"] + llm1["output_neurons"] + \
                    s2_in_neurons + s2_out_neurons + \
                    md["neurons"]

    usage = {
        "markdown_output_tokens": md["tokens"],
        "markdown_neurons":       md["neurons"],
        "stage1_input_tokens":    llm1["prompt_tokens"],
        "stage1_output_tokens":   llm1["completion_tokens"],
        "stage2_input_tokens":    s2_in_tokens,
        "stage2_output_tokens":   s2_out_tokens,
        "stage2_retried":         llm2_retry is not None,
        "llm_neurons":            llm1["input_neurons"] + llm1["output_neurons"] + \
                                  s2_in_neurons + s2_out_neurons,
        "llm_input_tokens":       llm1["prompt_tokens"] + s2_in_tokens,
        "llm_output_tokens":      llm1["completion_tokens"] + s2_out_tokens,
        "llm_input_neurons":      llm1["input_neurons"] + s2_in_neurons,
        "llm_output_neurons":     llm1["output_neurons"] + s2_out_neurons,
    }

    print(
        f"[{file_name}] Total Neurons: {total_neurons:.2f} "
        f"(S1: {usage['stage1_input_tokens']}/{usage['stage1_output_tokens']}, "
        f"S2: {usage['stage2_input_tokens']}/{usage['stage2_output_tokens']}"
        f"{' [retried]' if llm2_retry else ''})"
    )

    return {
        "parsed_json": s2_parsed,
        "category": category,
        "subcategory": subcategory,
        "neurons_consumed": total_neurons,
        "usage_breakdown":  usage,
        "document_text": document_text,
    }
