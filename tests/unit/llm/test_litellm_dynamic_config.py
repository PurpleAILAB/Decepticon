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
        "DECEPTICON_MODEL_RECON": "ollama_chat/qwen2.5-coder:32b",
        "DECEPTICON_MODEL_RECON_FALLBACK": "openai/gpt-4.1-mini",
    }

    assert collect_requested_models(env) == {
        "openrouter/anthropic/claude-3.7-sonnet",
        "groq/llama-3.3-70b-versatile",
        "ollama_chat/qwen2.5-coder:32b",
        "openai/gpt-4.1-mini",
    }


def test_build_model_entry_uses_provider_specific_api_key_env() -> None:
    entry = build_model_entry("openrouter/anthropic/claude-3.7-sonnet")

    assert entry["model_name"] == "openrouter/anthropic/claude-3.7-sonnet"
    assert entry["litellm_params"] == {
        "model": "openrouter/anthropic/claude-3.7-sonnet",
        "api_key": "os.environ/OPENROUTER_API_KEY",
    }


def test_build_model_entry_supports_custom_openai_compatible_endpoint() -> None:
    entry = build_model_entry("custom/qwen3-coder")

    assert entry["litellm_params"] == {
        "model": "openai/qwen3-coder",
        "api_key": "os.environ/CUSTOM_OPENAI_API_KEY",
        "api_base": "os.environ/CUSTOM_OPENAI_API_BASE",
    }


def test_build_model_entry_routes_ollama_chat_to_api_base(monkeypatch) -> None:
    """When OLLAMA_API_BASE is set, the route references it via os.environ."""
    monkeypatch.setenv("OLLAMA_API_BASE", "http://host.docker.internal:11434")
    entry = build_model_entry("ollama_chat/qwen3-coder:30b")

    assert entry["litellm_params"] == {
        "model": "ollama_chat/qwen3-coder:30b",
        "api_base": "os.environ/OLLAMA_API_BASE",
    }


def test_build_model_entry_ollama_chat_default_when_env_unset(monkeypatch) -> None:
    """When OLLAMA_API_BASE is unset, fall back to ``host.docker.internal:11434``.

    LiteLLM's ``os.environ/<NAME>`` syntax resolves an unset env var to
    an empty string, which would silently 404 every Ollama request. The
    dynamic config writer pins a sensible default at write time so
    operators who run ``DECEPTICON_LITELLM_MODELS=ollama_chat/<m>``
    without going through the launcher onboard wizard still reach the
    host Ollama instance on macOS, Linux, and WSL2.
    """
    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    entry = build_model_entry("ollama_chat/qwen3-coder:30b")

    assert entry["litellm_params"] == {
        "model": "ollama_chat/qwen3-coder:30b",
        "api_base": "http://host.docker.internal:11434",
    }


def test_validate_model_name_rejects_bare_or_internal_routes() -> None:
    with pytest.raises(ValueError, match="provider/model"):
        validate_model_name("gpt-4.1")
    with pytest.raises(ValueError, match=r"auth/\*"):
        validate_model_name("auth/claude-sonnet-4-6")
    with pytest.raises(ValueError, match="unsupported model provider"):
        validate_model_name("unknown/model")


def test_validate_model_name_rejects_other_subscription_prefixes() -> None:
    """Subscription providers register through ``custom_provider_map`` in
    ``litellm_startup.py`` — admitting them on the API-key dynamic path
    would synthesize a ``<PROVIDER>_API_KEY`` env lookup that never works.
    """
    for slug in (
        "gemini-sub/gemini-2.5-pro",
        "copilot/gpt-5.5",
        "grok-sub/grok-4.3",
        "pplx-sub/sonar",
    ):
        with pytest.raises(ValueError, match="not allowed as dynamic API-key model routes"):
            validate_model_name(slug)


def test_merge_dynamic_models_allows_subscription_model_override() -> None:
    """A user setting ``DECEPTICON_MODEL=auth/gpt-5.4-mini`` together with
    ``DECEPTICON_AUTH_CHATGPT=true`` must succeed — the subscription path
    injects the route first, and the API-key validator is skipped because
    the model is already present in the model_list.
    """
    merged = merge_dynamic_models(
        {"model_list": [], "litellm_settings": {"fallbacks": []}},
        {
            "DECEPTICON_AUTH_CHATGPT": "true",
            "DECEPTICON_MODEL": "auth/gpt-5.4-mini",
        },
    )
    names = {entry["model_name"] for entry in merged["model_list"]}
    assert "auth/gpt-5.4-mini" in names


def test_validate_model_name_rejects_legacy_ollama_with_remediation() -> None:
    """``ollama/`` (legacy /api/generate) does not support tool calling per
    LiteLLM's own ``supports_function_calling`` assertion. Decepticon agents
    always emit tool calls, so accepting it would silently break the first
    request — fail closed at config-merge time and point at ``ollama_chat/``.
    """
    with pytest.raises(ValueError, match="ollama_chat/llama3.2"):
        validate_model_name("ollama/llama3.2")
    with pytest.raises(ValueError, match="tool/function"):
        validate_model_name("ollama/qwen2.5-coder:32b")


def test_merge_dynamic_models_rejects_invalid_env_model() -> None:
    with pytest.raises(ValueError, match="provider/model"):
        merge_dynamic_models({"model_list": []}, {"DECEPTICON_MODEL": "gpt-4.1"})


def test_merge_dynamic_models_rejects_legacy_ollama_env() -> None:
    with pytest.raises(ValueError, match="ollama_chat/"):
        merge_dynamic_models(
            {"model_list": []},
            {"DECEPTICON_MODEL_RECON": "ollama/qwen2.5-coder:32b"},
        )


def test_collect_requested_models_wraps_hf_hosted_gguf_with_ollama_chat() -> None:
    """HuggingFace-hosted Ollama models embed slashes in the tag itself
    (``hf.co/<author>/<model>:<quant>``). The resolver must wrap them
    with ``ollama_chat/`` rather than treating the bare slash as a
    provider/model split — otherwise validate_model_name would reject
    ``hf.co`` as an unknown provider.
    """
    env = {
        "OLLAMA_API_BASE": "http://host.docker.internal:11434",
        "OLLAMA_MODEL": "hf.co/lmstudio-community/Qwen3-Coder-30B-GGUF:Q4_K_M",
    }
    models = collect_requested_models(env)
    assert "ollama_chat/hf.co/lmstudio-community/Qwen3-Coder-30B-GGUF:Q4_K_M" in models


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


def test_merge_dynamic_models_registers_only_supported_chatgpt_oauth_routes() -> None:
    merged = merge_dynamic_models(
        {"model_list": [], "litellm_settings": {"fallbacks": []}},
        {"DECEPTICON_AUTH_CHATGPT": "true"},
    )

    # User-facing model_name stays ``auth/gpt-*`` for consistency with
    # ``auth/claude-*``, but the internal litellm_params.model uses the
    # dedicated ``codex-oauth`` custom provider — bare ``auth/gpt-*``
    # makes LiteLLM strip the prefix and route to the native OpenAI
    # provider because the ``gpt-*`` slug collides with OpenAI's aliases.
    entries = {entry["model_name"]: entry["litellm_params"] for entry in merged["model_list"]}
    assert entries == {
        "auth/gpt-5.5": {"model": "codex-oauth/oauth-gpt-5.5"},
        "auth/gpt-5.4": {"model": "codex-oauth/oauth-gpt-5.4"},
        "auth/gpt-5.4-mini": {"model": "codex-oauth/oauth-gpt-5.4-mini"},
        # Code-heavy override route. Registered alongside the tier
        # defaults so per-agent env overrides like
        # ``DECEPTICON_MODEL_PATCHER=auth/gpt-5.3-codex`` work without a
        # yaml edit. The ``oauth-`` slug sentinel is required because
        # ``gpt-5.3-codex`` is in ``open_ai_chat_completion_models``.
        "auth/gpt-5.3-codex": {"model": "codex-oauth/oauth-gpt-5.3-codex"},
    }
    assert "auth/gpt-5-nano" not in entries
    assert merged["litellm_settings"]["fallbacks"] == [
        {"auth/gpt-5.5": ["auth/gpt-5.4"]},
        {"auth/gpt-5.4": ["auth/gpt-5.4-mini"]},
    ]


# ── llama.cpp OpenAI-compatible backend (issue #151) ────────────────────


def test_build_model_entry_routes_llamacpp_to_openai_with_custom_base() -> None:
    """``llamacpp/<model>`` routes through LiteLLM's openai-compatible
    path with ``LLAMACPP_API_BASE`` and ``LLAMACPP_API_KEY``. Symmetric
    to the ``custom/`` branch but kept distinct so users can have BOTH
    a generic custom OpenAI gateway AND llama.cpp configured.
    """
    entry = build_model_entry("llamacpp/qwen2.5-coder-7b-instruct-q4_k_m")

    assert entry["model_name"] == "llamacpp/qwen2.5-coder-7b-instruct-q4_k_m", (
        "model_name must be the agent-facing alias unchanged — per-role "
        "DECEPTICON_MODEL_<ROLE> overrides depend on this passthrough"
    )
    assert entry["litellm_params"] == {
        "model": "openai/qwen2.5-coder-7b-instruct-q4_k_m",
        "api_key": "os.environ/LLAMACPP_API_KEY",
        "api_base": "os.environ/LLAMACPP_API_BASE",
    }


def test_validate_model_name_accepts_llamacpp_prefix() -> None:
    """``llamacpp/`` is in ``ALLOWED_DYNAMIC_PROVIDERS`` so the validator
    must let it through. Pre-fix this would raise the
    ``unsupported model provider`` error.
    """
    # Should not raise.
    validate_model_name("llamacpp/qwen2.5-coder-7b-instruct-q4_k_m")


def test_validate_model_name_rejects_llamacpp_without_model_slug() -> None:
    """Bare ``llamacpp`` (no slash, no model) is still invalid — the
    validator's first check is the provider/model format gate.
    """
    with pytest.raises(ValueError, match="provider/model"):
        validate_model_name("llamacpp")
