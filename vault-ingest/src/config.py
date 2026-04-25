from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    inbox_prefix: str
    processed_prefix: str
    parsed_prefix: str
    daily_neuron_budget: int
    ai_model: str
    neon_connection_string: str


def _get_env_value(env, name: str, default: str | None = None) -> str:
    value = getattr(env, name, None)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required Worker secret or variable: {name}")
        return default
    return str(value)


def load_config(env) -> RuntimeConfig:
    return RuntimeConfig(
        inbox_prefix=_get_env_value(env, "R2_INBOX_PREFIX", "inbox/"),
        processed_prefix=_get_env_value(env, "R2_PROCESSED_PREFIX", "processed/"),
        parsed_prefix=_get_env_value(env, "R2_PARSED_PREFIX", "parsed/"),
        daily_neuron_budget=int(_get_env_value(env, "DAILY_NEURON_BUDGET", "9500")),
        ai_model=_get_env_value(env, "AI_MODEL", "@cf/google/gemma-4-26b-a4b-it"),
        neon_connection_string=_get_env_value(env, "NEON_CONNECTION_STRING"),
    )
