from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    inbox_prefix: str
    processed_prefix: str
    parsed_prefix: str
    daily_neuron_budget: int
    stage1_model: str
    stage2_model: str
    neon_connection_string: str
    # Set when using Google Generative Language API (model IDs like ``gemini-3.1-flash-lite-preview``).
    gemini_api_key: str | None
    # Set when using Mistral API (model IDs like ``mistral-large-latest``).
    mistral_api_key: str | None
    # Preflight caps for the Generative Language API. Stage 1 uses GEMINI_RPM_LIMIT /
    # GEMINI_RPD_LIMIT (e.g. 3.1 Flash Lite). Stage 2 uses GEMINI_STAGE2_* (e.g. Gemini 3
    # Flash ~20 RPD on free tier). If GEMINI_STAGE2_RPM_LIMIT is unset, stage 2 reuses
    # GEMINI_RPM_LIMIT. Set any limit to 0 to disable that pre-flight check.
    gemini_rpm_limit: int
    gemini_rpd_limit: int
    gemini_stage2_rpm_limit: int
    gemini_stage2_rpd_limit: int


def _get_env_value(env, name: str, default: str | None = None) -> str:
    value = getattr(env, name, None)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required Worker secret or variable: {name}")
        return default
    return str(value)


def load_config(env) -> RuntimeConfig:
    raw_gemini = getattr(env, "GEMINI_API_KEY", None)
    gemini_key = str(raw_gemini).strip() if raw_gemini is not None else ""
    raw_mistral = getattr(env, "MISTRAL_API_KEY", None)
    mistral_key = str(raw_mistral).strip() if raw_mistral is not None else ""
    return RuntimeConfig(
        inbox_prefix=_get_env_value(env, "R2_INBOX_PREFIX", "inbox/"),
        processed_prefix=_get_env_value(env, "R2_PROCESSED_PREFIX", "processed/"),
        parsed_prefix=_get_env_value(env, "R2_PARSED_PREFIX", "parsed/"),
        daily_neuron_budget=int(_get_env_value(env, "DAILY_NEURON_BUDGET", "9500")),
        stage1_model=_get_env_value(
            env, "AI_STAGE1_MODEL", "gemini-3.1-flash-lite-preview"
        ),
        stage2_model=_get_env_value(env, "AI_STAGE2_MODEL", "gemini-3-flash-preview"),
        neon_connection_string=_get_env_value(env, "NEON_CONNECTION_STRING"),
        gemini_api_key=gemini_key or None,
        mistral_api_key=mistral_key or None,
        gemini_rpm_limit=int(_get_env_value(env, "GEMINI_RPM_LIMIT", "5")),
        gemini_rpd_limit=int(_get_env_value(env, "GEMINI_RPD_LIMIT", "450")),
        gemini_stage2_rpm_limit=_stage2_rpm_limit(env),
        gemini_stage2_rpd_limit=int(
            _get_env_value(env, "GEMINI_STAGE2_RPD_LIMIT", "19")
        ),
    )


def _stage2_rpm_limit(env) -> int:
    raw = getattr(env, "GEMINI_STAGE2_RPM_LIMIT", None)
    if raw is not None and str(raw).strip() != "":
        return int(str(raw).strip())
    return int(_get_env_value(env, "GEMINI_RPM_LIMIT", "5"))
