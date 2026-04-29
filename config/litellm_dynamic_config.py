"""Dynamic LiteLLM config helpers for user-supplied model IDs.

The checked-in ``config/litellm.yaml`` contains the default Decepticon routes.
Operators can additionally set ``DECEPTICON_MODEL`` / per-role overrides to any
LiteLLM model string (for example ``openrouter/anthropic/claude-3.7-sonnet`` or
``ollama/qwen2.5-coder:32b``).  This module appends only those requested routes
at container startup so the proxy accepts the same model names the agents use.

No secret values are read or logged here; generated routes reference environment
variables using LiteLLM's ``os.environ/NAME`` syntax.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import yaml

# Common LiteLLM provider prefix -> environment variable containing the API key.
# Unknown providers fall back to ``<PROVIDER>_API_KEY`` after normalization, which
# covers most LiteLLM providers without requiring a code change.
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "together": "TOGETHER_API_KEY",
    "together_ai": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "replicate": "REPLICATE_API_TOKEN",
    "minimax": "MINIMAX_API_KEY",
}

ALLOWED_DYNAMIC_PROVIDERS = frozenset(
    {
        *PROVIDER_API_KEY_ENV,
        "ollama",
        "chatgpt",
        "auth",
        "gemini_sub",
        "copilot",
        "grok_sub",
        "pplx_sub",
        "custom",
    }
)

# Environment variables that are model-selection controls, not model names.
_MODEL_CONTROL_SUFFIXES = (
    "PROFILE",
    "PROVIDER",
    "TEMPERATURE",
    "MAX_TOKENS",
)


def _clean_model(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.lower() in {"", "none", "null", "-"}:
        return None
    return cleaned


def _looks_like_model_env_var(name: str) -> bool:
    if name in {"DECEPTICON_MODEL", "DECEPTICON_MODEL_FALLBACK"}:
        return True
    if not name.startswith("DECEPTICON_MODEL_"):
        return False
    suffix = name.removeprefix("DECEPTICON_MODEL_")
    return not suffix.endswith(_MODEL_CONTROL_SUFFIXES)


def _extra_models_from_env(value: str | None) -> set[str]:
    """Parse optional comma-separated or JSON-list extra model IDs."""
    cleaned = _clean_model(value)
    if cleaned is None:
        return set()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        return {model for item in parsed if (model := _clean_model(str(item)))}

    return {model for part in cleaned.split(",") if (model := _clean_model(part))}


def collect_requested_models(env: Mapping[str, str] | None = None) -> set[str]:
    """Collect model IDs requested through DECEPTICON_MODEL* env vars."""
    source = env if env is not None else os.environ
    models: set[str] = set()

    for name, value in source.items():
        if not _looks_like_model_env_var(name):
            continue
        model = _clean_model(value)
        if model is not None:
            models.add(model)

    models.update(_extra_models_from_env(source.get("DECEPTICON_LITELLM_MODELS")))
    return models


def _provider_prefix(model_name: str) -> str:
    return model_name.split("/", 1)[0].lower().replace("-", "_")


def validate_model_name(model_name: str) -> None:
    """Validate user-supplied dynamic model IDs before registering routes."""
    if "/" not in model_name:
        raise ValueError(f"model {model_name!r} must use LiteLLM provider/model format")
    provider = _provider_prefix(model_name)
    if provider == "auth":
        raise ValueError("auth/* routes are not allowed as dynamic API-key model routes")
    if provider not in ALLOWED_DYNAMIC_PROVIDERS:
        raise ValueError(
            f"unsupported model provider {provider!r} for {model_name!r}; "
            "use custom/<model> with CUSTOM_OPENAI_API_BASE for OpenAI-compatible gateways"
        )


def _derived_api_key_env(provider: str) -> str:
    return f"{provider.upper()}_API_KEY"


def build_model_entry(model_name: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build a LiteLLM ``model_list`` entry for a requested model ID.

    The generated route keeps ``model_name`` identical to the string used by the
    agent.  That makes per-role overrides transparent: if an agent asks for
    ``groq/llama-3.3-70b-versatile``, LiteLLM receives exactly that alias.
    """
    validate_model_name(model_name)
    provider = _provider_prefix(model_name)

    if provider == "custom":
        # OpenAI-compatible endpoint with arbitrary model name.  Example:
        #   DECEPTICON_MODEL=custom/qwen3-coder
        #   CUSTOM_OPENAI_API_BASE=https://gateway.example/v1
        actual_model = model_name.split("/", 1)[1]
        params: dict[str, Any] = {
            "model": f"openai/{actual_model}",
            "api_key": "os.environ/CUSTOM_OPENAI_API_KEY",
            "api_base": "os.environ/CUSTOM_OPENAI_API_BASE",
        }
    else:
        params = {"model": model_name}
        if provider == "ollama":
            params["api_base"] = "os.environ/OLLAMA_API_BASE"
        else:
            api_key_env = PROVIDER_API_KEY_ENV.get(provider, _derived_api_key_env(provider))
            params["api_key"] = f"os.environ/{api_key_env}"

    return {"model_name": model_name, "litellm_params": params}


def merge_dynamic_models(
    config: MutableMapping[str, Any], env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Append requested models not already present in a LiteLLM config."""
    merged = copy.deepcopy(dict(config))
    model_list = list(merged.get("model_list") or [])
    existing = {entry.get("model_name") for entry in model_list if isinstance(entry, dict)}

    for model_name in sorted(collect_requested_models(env)):
        validate_model_name(model_name)
        if model_name in existing:
            continue
        model_list.append(build_model_entry(model_name, env))
        existing.add(model_name)

    merged["model_list"] = model_list
    return merged


def write_dynamic_config(config_path: str | Path, output_path: str | Path) -> Path:
    """Read a LiteLLM YAML config, append requested models, and write a copy."""
    source_path = Path(config_path)
    target_path = Path(output_path)

    with source_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    merged = merge_dynamic_models(config, os.environ)

    target_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(target_path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target_path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=False)
    os.chmod(target_path, 0o600)

    return target_path


__all__ = [
    "build_model_entry",
    "collect_requested_models",
    "merge_dynamic_models",
    "validate_model_name",
    "write_dynamic_config",
]
