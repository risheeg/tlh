"""Shared helpers for all AI providers: document conversion, neuron pricing, JS interop."""

from js import Blob, TextDecoder

from util.js_interop import to_js_obj
from util.paths import is_plain_text, path_basename
from util.json_parse import strip_document_metadata_block
from util.js_interop import js_to_py


# ---------------------------------------------------------------------------
# ArrayBuffer → bytes (used by Gemini and Mistral for inline data / uploads)
# ---------------------------------------------------------------------------

def array_buffer_to_bytes(array_buffer) -> bytes:
    from js import Uint8Array
    return bytes(Uint8Array.new(array_buffer))


# ---------------------------------------------------------------------------
# Cloudflare Workers AI neuron conversion rates (neurons per 1 million tokens)
# Source: https://developers.cloudflare.com/workers-ai/platform/pricing/
# Rates: (input_neurons_per_M, output_neurons_per_M)
# ---------------------------------------------------------------------------
_MODEL_NEURON_RATES: dict[str, tuple[int, int]] = {
    "@cf/google/gemma-4-26b-a4b-it":               (9_091,  27_273),
    "@cf/google/gemma-3-12b-it":                   (31_371, 50_560),
    "@cf/meta/llama-3.1-8b-instruct":              (25_608, 75_147),
    "@cf/meta/llama-3.1-8b-instruct-fast":         (4_119,  34_868),
    "@cf/meta/llama-3.1-8b-instruct-fp8-fast":     (4_119,  34_868),
    "@cf/meta/llama-3.2-3b-instruct":              (4_625,  30_475),
    "@cf/meta/llama-3.2-1b-instruct":              (2_457,  18_252),
    "@cf/meta/llama-3.1-70b-instruct-fp8-fast":    (26_668, 204_805),
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast":    (26_668, 204_805),
    "@cf/meta/llama-4-scout-17b-16e-instruct":     (24_545, 77_273),
    "@cf/mistralai/mistral-small-3.1-24b-instruct":(31_876, 50_488),
    "@cf/qwen/qwen3-30b-a3b-fp8":                  (4_625,  30_475),
    "@cf/qwen/qwen2.5-coder-32b-instruct":         (60_000, 90_909),
    "@cf/openai/gpt-oss-120b":                     (31_818, 68_182),
    "@cf/openai/gpt-oss-20b":                      (18_182, 27_273),
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b":(45_170, 443_756),
}

# Fallback rate used when the model is not in the table above.
_FALLBACK_NEURON_RATE: tuple[int, int] = (9_091, 27_273)


def tokens_to_neurons(tokens: int, rate_per_million: int) -> float:
    return round(tokens * rate_per_million / 1_000_000, 4)


def get_neuron_rates(model: str) -> tuple[int, int]:
    """Return ``(input_rate, output_rate)`` for a given model ID."""
    return _MODEL_NEURON_RATES.get(model, _FALLBACK_NEURON_RATE)


# Vision model for Markdown conversion (used for neuron pricing only)
_MARKDOWN_NEURONS_PER_M_OUTPUT_TOKENS: int = 50_560


def markdown_breakdown(conversion_tokens: int) -> dict:
    neurons = tokens_to_neurons(conversion_tokens, _MARKDOWN_NEURONS_PER_M_OUTPUT_TOKENS)
    return {"tokens": conversion_tokens, "neurons": neurons}


# ---------------------------------------------------------------------------
# Document → Markdown text (via Workers AI toMarkdown)
# ---------------------------------------------------------------------------

async def document_to_text(env, key: str, content_type: str, array_buffer) -> tuple[str, int]:
    """Convert a document to Markdown using Workers AI ``toMarkdown``.

    Plain text files are decoded directly; everything else goes through the
    Cloudflare Workers AI Markdown conversion binding.

    Returns ``(markdown_text, conversion_tokens)``.
    """
    if is_plain_text(content_type, key):
        text = TextDecoder.new("utf-8").decode(array_buffer)
        return str(text), 0

    blob = Blob.new(to_js_obj([array_buffer]), to_js_obj({"type": content_type}))
    document = to_js_obj({"name": path_basename(key), "blob": blob})
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

    # env.AI.toMarkdown prepends a "## Metadata" section containing PDF file
    # headers (PDFFormatVersion, Creator, Producer, etc.). Strip it so the
    # extraction model does not copy those keys into the schema's `metadata`.
    cleaned = strip_document_metadata_block(str(data))
    return cleaned, int(result.get("tokens") or 0)
