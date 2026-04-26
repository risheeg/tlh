"""Provider router: dispatches to Workers AI, Gemini, or Mistral based on model ID."""

from providers.workers_ai import is_workers_ai_model


def _provider_for_model(model: str) -> str:
    if is_workers_ai_model(model):
        return "workers_ai"
    if (model or "").strip().startswith("mistral-"):
        return "mistral"
    return "gemini"


async def classify_document(env, config, key: str, content_type: str, array_buffer) -> dict:
    """Two-stage document classification and extraction.

    Routes to the appropriate provider based on the model name prefix:
    - ``@cf/...`` → Cloudflare Workers AI
    - ``mistral-...`` → Mistral API
    - anything else → Google Gemini

    Both stages must use the same provider.
    """
    p1 = _provider_for_model(config.stage1_model)
    p2 = _provider_for_model(config.stage2_model)
    if p1 != p2:
        raise RuntimeError(
            "AI_STAGE1_MODEL and AI_STAGE2_MODEL must both target the same provider "
            "(Cloudflare ``@cf/...``, Mistral ``mistral-...``, or Google Gemini). "
            f"Got stage1={config.stage1_model!r} ({p1}) vs stage2={config.stage2_model!r} ({p2})."
        )
    if p1 == "workers_ai":
        from providers.workers_ai import classify_with_workers_ai
        return await classify_with_workers_ai(env, config, key, content_type, array_buffer)
    if p1 == "mistral":
        from providers.mistral import classify_with_mistral
        return await classify_with_mistral(env, config, key, content_type, array_buffer)
    from providers.gemini import classify_with_gemini
    return await classify_with_gemini(env, config, key, content_type, array_buffer)
