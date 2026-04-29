"""Unit tests for dynamic LiteLLM model config generation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "config" / "litellm_dynamic_config.py"
_spec = importlib.util.spec_from_file_location("decepticon_litellm_dynamic_config", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

collect_requested_models = _module.collect_requested_models
build_model_entry = _module.build_model_entry
merge_dynamic_models = _module.merge_dynamic_models
validate_model_name = _module.validate_model_name


def test_collect_requested_models_includes_global_and_role_overrides() -> None:
    env = {
        "DECEPTICON_MODEL": "openrouter/anthropic/claude-3.7-sonnet",
        "DECEPTICON_MODEL_FALLBACK": "groq/llama-3.3-70b-versatile",
        "DECEPTICON_MODEL_RECON": "ollama/qwen2.5-coder:32b",
        "DECEPTICON_MODEL_RECON_FALLBACK": "openai/gpt-4.1-mini",
    }

    assert collect_requested_models(env) == {
        "openrouter/anthropic/claude-3.7-sonnet",
        "groq/llama-3.3-70b-versatile",
        "ollama/qwen2.5-coder:32b",
        "openai/gpt-4.1-mini",
    }


def test_build_model_entry_uses_provider_specific_api_key_env() -> None:
    entry = build_model_entry("openrouter/anthropic/claude-3.7-sonnet", {})

    assert entry["model_name"] == "openrouter/anthropic/claude-3.7-sonnet"
    assert entry["litellm_params"] == {
        "model": "openrouter/anthropic/claude-3.7-sonnet",
        "api_key": "os.environ/OPENROUTER_API_KEY",
    }


def test_build_model_entry_supports_custom_openai_compatible_endpoint() -> None:
    env = {"CUSTOM_OPENAI_API_BASE": "https://llm.example.test/v1"}

    entry = build_model_entry("custom/qwen3-coder", env)

    assert entry["litellm_params"] == {
        "model": "openai/qwen3-coder",
        "api_key": "os.environ/CUSTOM_OPENAI_API_KEY",
        "api_base": "os.environ/CUSTOM_OPENAI_API_BASE",
    }


def test_validate_model_name_rejects_bare_or_internal_routes() -> None:
    with pytest.raises(ValueError, match="provider/model"):
        validate_model_name("gpt-4.1")
    with pytest.raises(ValueError, match=r"auth/\*"):
        validate_model_name("auth/claude-sonnet-4-6")
    with pytest.raises(ValueError, match="unsupported model provider"):
        validate_model_name("unknown/model")


def test_merge_dynamic_models_rejects_invalid_env_model() -> None:
    with pytest.raises(ValueError, match="provider/model"):
        merge_dynamic_models({"model_list": []}, {"DECEPTICON_MODEL": "gpt-4.1"})


def test_merge_dynamic_models_keeps_existing_entries_and_appends_missing() -> None:
    config = {
        "model_list": [
            {
                "model_name": "openai/gpt-4.1",
                "litellm_params": {
                    "model": "openai/gpt-4.1",
                    "api_key": "os.environ/OPENAI_API_KEY",
                },
            }
        ]
    }
    env = {
        "DECEPTICON_MODEL": "openai/gpt-4.1",
        "DECEPTICON_MODEL_RECON": "mistral/mistral-large-latest",
    }

    merged = merge_dynamic_models(config, env)

    assert [entry["model_name"] for entry in merged["model_list"]] == [
        "openai/gpt-4.1",
        "mistral/mistral-large-latest",
    ]
