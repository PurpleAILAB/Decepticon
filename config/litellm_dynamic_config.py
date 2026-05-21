"""Dynamic LiteLLM config helpers for user-supplied model IDs.

The checked-in ``config/litellm.yaml`` contains the default Decepticon routes.
Operators can additionally set ``DECEPTICON_MODEL`` / per-role overrides to any
LiteLLM model string (for example ``openrouter/anthropic/claude-3.7-sonnet`` or
``ollama_chat/qwen3-coder:30b``).  This module appends only those requested routes
at container startup so the proxy accepts the same model names the agents use.

For Ollama only the ``ollama_chat/`` provider is accepted — the legacy
``ollama/`` (``/api/generate``) lacks tool calling per LiteLLM's own
``supports_function_calling`` check, and Decepticon agents always emit tool calls.

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
    "vertex_ai": "GOOGLE_APPLICATION_CREDENTIALS",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "cohere_chat": "COHERE_API_KEY",
    "together": "TOGETHER_API_KEY",
    "together_ai": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "nvidia_nim": "NVIDIA_API_KEY",
    "replicate": "REPLICATE_API_TOKEN",
    "minimax": "MINIMAX_API_KEY",
    # New providers from the OpenClaude migration. LiteLLM ships native
    # support for each — only the env-var mapping needs to be wired here.
    "moonshot": "MOONSHOT_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    # LiteLLM's GitHub Models provider reads GITHUB_API_KEY (not the
    # GitHub-conventional GITHUB_TOKEN). Onboard writes both to the
    # .env so docs that reference GITHUB_TOKEN keep working.
    "github": "GITHUB_API_KEY",
    "lm_studio": "LMSTUDIO_API_KEY",  # LM Studio accepts any string; keep
    # symbolic so validate_model_name() lets the route through.
    "zai": "ZAI_API_KEY",
    # Cerebras Inference — native LiteLLM ``cerebras/`` provider,
    # OpenAI-compatible at api.cerebras.ai/v1.
    "cerebras": "CEREBRAS_API_KEY",
    # Kimi is the user-facing name for the same Moonshot account.
    "kimi": "MOONSHOT_API_KEY",
    # Xiaomi MiMo Open Platform — OpenAI-compatible (/v1/chat/completions).
    # No native LiteLLM provider yet, so routes are registered under the
    # ``openai/`` provider with an api_base override; this entry lets
    # operators set ``DECEPTICON_LITELLM_MODELS=xiaomi_mimo/<id>`` and
    # have validate_model_name() accept it — the actual route is built
    # by build_model_entry() below.
    "xiaomi_mimo": "XIAOMI_MIMO_API_KEY",
}

ALLOWED_DYNAMIC_PROVIDERS = frozenset(
    {
        *PROVIDER_API_KEY_ENV,
        # ``ollama_chat`` (LiteLLM /api/chat) is the only Ollama provider
        # accepted — the legacy ``ollama`` (/api/generate) lacks tool
        # calling and is rejected by validate_model_name() with a
        # remediation hint, before reaching this set.
        "ollama_chat",
        # ``ollama_cloud`` — same ``/api/chat`` tool-calling endpoint but
        # routed through OLLAMA_CLOUD_API_BASE with OLLAMA_CLOUD_API_KEY.
        "ollama_cloud",
        # ``auth/`` is listed but rejected by validate() — kept here so
        # the unrecognized-provider error doesn't fire first and
        # confuse the user with a misleading "use custom/<model>" hint.
        "auth",
        "gemini_sub",
        "copilot",
        "grok_sub",
        "pplx_sub",
        "custom",
        "llamacpp",
    }
)
# ``_provider_prefix`` normalizes ``vertex-ai`` → ``vertex_ai`` already,
# but the bare model id ``vertex_ai/<m>`` carries the underscore form
# directly. Keep a defensive alias entry — the spread above only covers
# what's in PROVIDER_API_KEY_ENV with the same casing.
ALLOWED_DYNAMIC_PROVIDERS = frozenset(ALLOWED_DYNAMIC_PROVIDERS | {"vertex_ai"})

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


def _ollama_model_from_env(source: Mapping[str, str]) -> str | None:
    """Derive ``ollama_chat/<model>`` from OLLAMA_API_BASE / OLLAMA_MODEL.

    Uses ``ollama_chat`` (not legacy ``ollama``) so /api/chat with
    tool calling is hit. Defaults to ``llama3.2`` when only the base
    URL is set, matching the agent factory.

    A user value is treated as already-qualified only when it starts
    with an Ollama provider prefix; a bare slash is not enough,
    because Ollama tags can contain slashes (HF-hosted GGUFs like
    ``hf.co/<author>/<model>:<quant>``).
    """
    base = _clean_model(source.get("OLLAMA_API_BASE"))
    model = _clean_model(source.get("OLLAMA_MODEL"))
    if base is None and model is None:
        return None
    if model is None:
        model = "llama3.2"
    lower = model.lower()
    if lower.startswith("ollama_chat/") or lower.startswith("ollama/"):
        # Pass legacy ``ollama/`` through verbatim — validate_model_name()
        # rejects it with a remediation hint pointing at ``ollama_chat/``.
        # Auto-rewriting would hide the user's mistake and leave a stale
        # ``OLLAMA_MODEL`` line in their .env disagreeing with the proxy.
        return model
    return f"ollama_chat/{model}"


def collect_requested_models(env: Mapping[str, str] | None = None) -> set[str]:
    """Collect model IDs requested through DECEPTICON_MODEL* env vars.

    Also picks up the OSS-friendly ``OLLAMA_MODEL`` shortcut so a user
    can pull any local model and just point the launcher at it without
    learning the LiteLLM model-id syntax.
    """
    source = env if env is not None else os.environ
    models: set[str] = set()

    for name, value in source.items():
        if not _looks_like_model_env_var(name):
            continue
        model = _clean_model(value)
        if model is not None:
            models.add(model)

    models.update(_extra_models_from_env(source.get("DECEPTICON_LITELLM_MODELS")))

    ollama_model = _ollama_model_from_env(source)
    if ollama_model is not None:
        models.add(ollama_model)

    return models


def _provider_prefix(model_name: str) -> str:
    return model_name.split("/", 1)[0].lower().replace("-", "_")


_SUBSCRIPTION_PROVIDER_PREFIXES = frozenset(
    {
        "auth",  # auth/claude-*, auth/gpt-* — Claude Code OAuth + Codex ChatGPT
        "gemini_sub",  # gemini-sub/* — Gemini Advanced subscription
        "copilot",  # copilot/* — Copilot Pro subscription
        "grok_sub",  # grok-sub/* — SuperGrok subscription
        "pplx_sub",  # pplx-sub/* — Perplexity Pro subscription
    }
)


def validate_model_name(model_name: str) -> None:
    """Validate user-supplied dynamic model IDs before registering routes.

    Rejects subscription / OAuth provider prefixes (``auth/*``, ``gemini-sub/*``,
    ``copilot/*``, ``grok-sub/*``, ``pplx-sub/*``) for the API-key registration
    path — those routes are added by ``_inject_subscription_routes`` when the
    matching ``DECEPTICON_AUTH_*`` flag is set, with custom-provider dispatch
    in ``litellm_startup.py``. Trying to register them as API-key routes here
    would produce a phantom ``<PROVIDER>_API_KEY`` env-var lookup that never
    resolves.

    ``merge_dynamic_models`` skips this validation when the model is already
    present in the model_list, so a user setting
    ``DECEPTICON_MODEL=auth/gpt-5.4-mini`` plus ``DECEPTICON_AUTH_CHATGPT=true``
    is fine — the subscription path injected the route first and the requested
    model is satisfied.
    """
    if "/" not in model_name:
        raise ValueError(f"model {model_name!r} must use LiteLLM provider/model format")
    provider = _provider_prefix(model_name)
    if provider in _SUBSCRIPTION_PROVIDER_PREFIXES:
        raise ValueError(
            f"{provider}/* routes are not allowed as dynamic API-key model "
            f"routes. Enable the matching subscription via "
            f"DECEPTICON_AUTH_<provider>=true so the route is registered "
            f"through litellm_startup.py's custom_provider_map instead."
        )
    if provider == "ollama":
        # Legacy ``ollama/`` (/api/generate) lacks tool calling — fail
        # closed since Decepticon agents always emit tool calls.
        slug = model_name.split("/", 1)[1]
        raise ValueError(
            f"model {model_name!r} uses the legacy ollama/ provider, which "
            "routes to /api/generate and does not support tool/function "
            "calling. Decepticon agents always emit tool calls — use "
            f"ollama_chat/{slug} (routes to /api/chat) instead."
        )
    if provider not in ALLOWED_DYNAMIC_PROVIDERS:
        raise ValueError(
            f"unsupported model provider {provider!r} for {model_name!r}; "
            "use custom/<model> with CUSTOM_OPENAI_API_BASE for OpenAI-compatible gateways"
        )


def _derived_api_key_env(provider: str) -> str:
    return f"{provider.upper()}_API_KEY"


def build_model_entry(model_name: str) -> dict[str, Any]:
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
    elif provider == "zai":
        # LiteLLM 1.55+ ships a native ``zai/`` provider — pass the model
        # id through verbatim and let LiteLLM resolve the base URL +
        # ZAI_API_KEY internally.
        params = {
            "model": model_name,
            "api_key": "os.environ/ZAI_API_KEY",
        }
    elif provider == "lm_studio":
        # LM Studio runs locally as an OpenAI-compatible server. The
        # base URL comes from LMSTUDIO_API_BASE (default localhost:1234).
        # No real key is required; LM Studio accepts any string.
        params = {
            "model": model_name,
            "api_base": "os.environ/LMSTUDIO_API_BASE",
            "api_key": "os.environ/LMSTUDIO_API_KEY",
        }
    elif provider == "llamacpp":
        # llama.cpp's llama-server is OpenAI-compatible but is not a
        # native LiteLLM provider, so we remap the route to ``openai/<m>``
        # and point LiteLLM at LLAMACPP_API_BASE. Symmetric to the
        # ``custom/`` branch above; kept as its own provider so a user
        # can have a generic custom OpenAI gateway AND llama.cpp wired
        # at the same time. Issue #151.
        actual_model = model_name.split("/", 1)[1]
        params = {
            "model": f"openai/{actual_model}",
            "api_key": "os.environ/LLAMACPP_API_KEY",
            "api_base": "os.environ/LLAMACPP_API_BASE",
        }
    elif provider == "xiaomi_mimo":
        # Xiaomi MiMo Open Platform — OpenAI-compatible
        # (``/v1/chat/completions``, Bearer auth). No native LiteLLM
        # provider yet; remap to ``openai/<id>`` and override api_base
        # to XIAOMI_MIMO_API_BASE (default points at
        # ``https://platform.xiaomimimo.com/v1``).
        actual_model = model_name.split("/", 1)[1]
        params = {
            "model": f"openai/{actual_model}",
            "api_key": "os.environ/XIAOMI_MIMO_API_KEY",
            "api_base": "os.environ/XIAOMI_MIMO_API_BASE",
        }
    else:
        params = {"model": model_name}
        if provider == "ollama_chat":
            # Ollama runs locally and has no API key. The legacy ``ollama``
            # provider is rejected upstream by validate_model_name so only
            # ``ollama_chat/`` (which routes to /api/chat with tool support)
            # reaches this branch.
            #
            # When OLLAMA_API_BASE is unset, LiteLLM's ``os.environ/<NAME>``
            # syntax resolves to an empty string and the route silently
            # 404s. Pin to ``http://host.docker.internal:11434`` as the
            # write-time default — it works on macOS, Linux, and WSL2
            # (Docker Desktop installs an /etc/hosts alias to the host)
            # and is exactly what the launcher onboard wizard writes.
            # Operators who run docker-without-Desktop on a pure Linux
            # host can override by exporting the env var; the explicit
            # ``os.environ/OLLAMA_API_BASE`` resolution takes effect when
            # the env var IS set, because LiteLLM resolves env-refs at
            # request time.
            if os.environ.get("OLLAMA_API_BASE", "").strip():
                params["api_base"] = "os.environ/OLLAMA_API_BASE"
            else:
                params["api_base"] = "http://host.docker.internal:11434"
        elif provider == "ollama_cloud":
            # Ollama Cloud (https://docs.ollama.com/cloud) — OpenAI-compatible
            # at ``https://ollama.com/v1`` with Bearer auth via OLLAMA_API_KEY.
            # No native LiteLLM ``ollama_cloud/`` provider yet, so remap the
            # route to ``openai/<model>`` with explicit api_base override.
            # ``OLLAMA_CLOUD_API_BASE`` defaults to ``https://ollama.com/v1``
            # but can point at a self-hosted Ollama endpoint that mirrors
            # the cloud OpenAI shape. Same env-empty-fallback pattern as
            # ``ollama_chat`` above — write a literal default URL when the
            # operator hasn't pinned the base, so the route doesn't
            # silently 404 when LiteLLM resolves an empty env-ref.
            actual_model = model_name.split("/", 1)[1]
            cloud_base = (
                "os.environ/OLLAMA_CLOUD_API_BASE"
                if os.environ.get("OLLAMA_CLOUD_API_BASE", "").strip()
                else "https://ollama.com/v1"
            )
            params = {
                "model": f"openai/{actual_model}",
                "api_key": "os.environ/OLLAMA_API_KEY",
                "api_base": cloud_base,
            }
        elif provider == "bedrock":
            # AWS Bedrock — uses AWS SigV4 with three env vars rather
            # than an Authorization header. LiteLLM reads them
            # automatically; we just don't set api_key.
            pass
        elif provider == "vertex_ai":
            # Vertex AI — service-account JSON path + project + location.
            # LiteLLM reads GOOGLE_APPLICATION_CREDENTIALS automatically;
            # only project + location need to be passed through.
            params["vertex_project"] = "os.environ/VERTEXAI_PROJECT"
            params["vertex_location"] = "os.environ/VERTEXAI_LOCATION"
        elif provider == "azure":
            # Azure OpenAI deployment — needs base URL + version.
            params["api_key"] = "os.environ/AZURE_API_KEY"
            params["api_base"] = "os.environ/AZURE_API_BASE"
            params["api_version"] = "os.environ/AZURE_API_VERSION"
        else:
            api_key_env = PROVIDER_API_KEY_ENV.get(provider, _derived_api_key_env(provider))
            params["api_key"] = f"os.environ/{api_key_env}"

    return {"model_name": model_name, "litellm_params": params}


# ── Subscription OAuth routes ───────────────────────────────────────────
# These were previously static in litellm.yaml. LiteLLM's native providers
# (chatgpt, gemini-sub, copilot, grok-sub, pplx-sub) attempt OAuth
# handshakes at startup when they see their routes. If the user hasn't
# enabled the auth method, the handshake blocks → times out → container
# becomes unhealthy. Gating on DECEPTICON_AUTH_* prevents that.

# Shadow pricing for subscription OAuth routes (USD per token, as of
# 2026-05-14). These routes are paid via flat monthly subscriptions
# (ChatGPT Pro/Plus/Team, Gemini Advanced, Copilot Pro, SuperGrok,
# Perplexity Pro), so per-token cost is NOT what the user actually pays.
# We stamp the equivalent paid-API price into ``model_info`` so
# /spend/logs reports an "API-equivalent" USD number — useful for
# comparing benchmark cost across paid and subscription routes
# apples-to-apples. The OSS user's real cash spend stays the
# subscription fee; this number is opportunity cost.
#
# Perplexity Sonar numbers are best-effort against the published rate
# card (Sonar $1/$1, Sonar Pro $3/$15) — search-call surcharge not
# modeled.
_SUBSCRIPTION_SHADOW_PRICING: dict[str, tuple[float, float]] = {
    "auth/gpt-5.5": (0.000005, 0.000030),
    "auth/gpt-5.4": (0.0000025, 0.000015),
    "auth/gpt-5.4-mini": (0.00000075, 0.0000045),
    "auth/gpt-5.3-codex": (0.00000175, 0.000014),
    "gemini-sub/gemini-2.5-pro": (0.00000125, 0.00001),
    "gemini-sub/gemini-2.5-flash": (0.0000003, 0.0000025),
    "copilot/gpt-5.5": (0.000005, 0.000030),
    "copilot/claude-sonnet-4-6": (0.000003, 0.000015),
    "copilot/gpt-5.4-mini": (0.00000075, 0.0000045),
    "copilot/gpt-5.3-codex": (0.00000175, 0.000014),
    "grok-sub/grok-4.3": (0.00000125, 0.0000025),
    "grok-sub/grok-4-1-fast-reasoning": (0.0000002, 0.0000005),
    "pplx-sub/sonar-pro": (0.000003, 0.000015),
    "pplx-sub/sonar": (0.000001, 0.000001),
}


def _with_shadow_pricing(route: dict[str, Any]) -> dict[str, Any]:
    """Attach ``model_info`` shadow pricing to a subscription route, if any.

    Returns the route unchanged when ``model_name`` is not in
    ``_SUBSCRIPTION_SHADOW_PRICING`` — preserves the "subscription is
    free per-token" reading so a future operator who deliberately
    omits a route from the map gets ``$0`` rather than silent default
    pricing from LiteLLM's built-in cost map.
    """
    pricing = _SUBSCRIPTION_SHADOW_PRICING.get(route["model_name"])
    if pricing is None:
        return route
    enriched = dict(route)
    enriched["model_info"] = {
        "input_cost_per_token": pricing[0],
        "output_cost_per_token": pricing[1],
    }
    return enriched


_SUBSCRIPTION_ROUTES: dict[str, list[dict[str, Any]]] = {
    # env flag → model_list entries
    "DECEPTICON_AUTH_CHATGPT": [
        # User-facing model_name stays ``auth/gpt-*`` for consistency with
        # ``auth/claude-*``. The internal LiteLLM route uses the dedicated
        # ``codex-oauth`` custom provider plus the ``oauth-gpt-`` slug
        # sentinel — without the sentinel LiteLLM's main.py:2561 falls
        # into the OpenAI branch (``model in open_ai_chat_completion_models``
        # short-circuits before the custom_llm_provider check) and forwards
        # to api.openai.com regardless of provider. The codex_chatgpt
        # handler strips the ``oauth-`` prefix before sending the model
        # name upstream, so chatgpt.com still receives ``gpt-5.5``.
        {
            "model_name": "auth/gpt-5.5",
            "litellm_params": {"model": "codex-oauth/oauth-gpt-5.5"},
        },
        {
            "model_name": "auth/gpt-5.4",
            "litellm_params": {"model": "codex-oauth/oauth-gpt-5.4"},
        },
        {
            "model_name": "auth/gpt-5.4-mini",
            "litellm_params": {"model": "codex-oauth/oauth-gpt-5.4-mini"},
        },
        # Code-heavy override (option α). gpt-5.3-codex is OpenAI's
        # agentic-coding specialized model (Codex + GPT-5 training
        # stack); register the route here so per-agent env overrides
        # like ``DECEPTICON_MODEL_PATCHER=auth/gpt-5.3-codex`` work
        # without yaml edits. Slug ``gpt-5.3-codex`` IS in
        # open_ai_chat_completion_models, so the sentinel is required.
        {
            "model_name": "auth/gpt-5.3-codex",
            "litellm_params": {"model": "codex-oauth/oauth-gpt-5.3-codex"},
        },
    ],
    "DECEPTICON_AUTH_GEMINI": [
        {
            "model_name": "gemini-sub/gemini-2.5-pro",
            "litellm_params": {"model": "gemini-sub/gemini-2.5-pro"},
        },
        {
            "model_name": "gemini-sub/gemini-2.5-flash",
            "litellm_params": {"model": "gemini-sub/gemini-2.5-flash"},
        },
    ],
    "DECEPTICON_AUTH_COPILOT": [
        # GitHub Copilot retired gpt-4o / o1 / o3-mini on 2025-10-23.
        # Current Copilot model picker exposes (as of 2026-05-14):
        #   OpenAI:   gpt-5 mini, gpt-5.2, gpt-5.2-Codex, gpt-5.3-Codex,
        #             gpt-5.4, gpt-5.4 mini, gpt-5.4 nano, gpt-5.5
        #   Anthropic: Haiku 4.5, Opus 4.5/4.6/4.7, Sonnet 4.5/4.6
        #   Google:    Gemini 2.5 Pro, Gemini 3 Flash (preview)
        #   xAI:       Grok Code Fast 1
        # Default tier picks below avoid the LiteLLM main.py:2561
        # short-circuit by choosing slugs NOT in
        # ``open_ai_chat_completion_models`` — no sentinel needed.
        # ``claude-sonnet-4-6`` is in ``anthropic_models`` but main.py
        # does not early-check that list (only openai's), so it routes
        # cleanly through the ``copilot`` custom provider.
        {
            "model_name": "copilot/gpt-5.5",
            "litellm_params": {"model": "copilot/gpt-5.5"},
        },
        {
            "model_name": "copilot/claude-sonnet-4-6",
            "litellm_params": {"model": "copilot/claude-sonnet-4-6"},
        },
        {
            "model_name": "copilot/gpt-5.4-mini",
            "litellm_params": {"model": "copilot/gpt-5.4-mini"},
        },
        # Code-heavy override (option α). gpt-5.3-codex is in
        # ``open_ai_chat_completion_models``, so the ``oauth-`` slug
        # sentinel is required to dodge the main.py:2561 short-circuit.
        # copilot_handler._upstream_model_slug strips ``oauth-`` before
        # posting to api.githubcopilot.com. Pick via
        # ``DECEPTICON_MODEL_<ROLE>=copilot/gpt-5.3-codex`` for
        # patcher / exploiter / contract_auditor.
        {
            "model_name": "copilot/gpt-5.3-codex",
            "litellm_params": {"model": "copilot/oauth-gpt-5.3-codex"},
        },
    ],
    "DECEPTICON_AUTH_GROK": [
        # grok-3 / grok-3-mini retired by xAI on 2026-05-15. Replaced
        # with the current production lineup: grok-4.3 (flagship) and
        # grok-4-1-fast-reasoning (cost-efficient MID). Both slugs are
        # NOT in ``open_ai_chat_completion_models`` so no sentinel needed.
        {
            "model_name": "grok-sub/grok-4.3",
            "litellm_params": {"model": "grok-sub/grok-4.3"},
        },
        {
            "model_name": "grok-sub/grok-4-1-fast-reasoning",
            "litellm_params": {"model": "grok-sub/grok-4-1-fast-reasoning"},
        },
    ],
    "DECEPTICON_AUTH_PERPLEXITY": [
        {"model_name": "pplx-sub/sonar-pro", "litellm_params": {"model": "pplx-sub/sonar-pro"}},
        {"model_name": "pplx-sub/sonar", "litellm_params": {"model": "pplx-sub/sonar"}},
    ],
}

# Fallback entries for subscription routes — appended to litellm_settings.fallbacks
_SUBSCRIPTION_FALLBACKS: dict[str, list[dict[str, list[str]]]] = {
    "DECEPTICON_AUTH_CHATGPT": [
        {"auth/gpt-5.5": ["auth/gpt-5.4"]},
        {"auth/gpt-5.4": ["auth/gpt-5.4-mini"]},
    ],
    "DECEPTICON_AUTH_GEMINI": [
        {"gemini-sub/gemini-2.5-pro": ["gemini-sub/gemini-2.5-flash"]},
    ],
    "DECEPTICON_AUTH_COPILOT": [
        {"copilot/gpt-5.5": ["copilot/claude-sonnet-4-6"]},
        {"copilot/claude-sonnet-4-6": ["copilot/gpt-5.4-mini"]},
    ],
    "DECEPTICON_AUTH_GROK": [
        {"grok-sub/grok-4.3": ["grok-sub/grok-4-1-fast-reasoning"]},
    ],
    "DECEPTICON_AUTH_PERPLEXITY": [
        {"pplx-sub/sonar-pro": ["pplx-sub/sonar"]},
    ],
}


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


def _inject_subscription_routes(
    config: MutableMapping[str, Any], env: Mapping[str, str] | None = None
) -> None:
    """Conditionally add subscription OAuth model routes and fallbacks.

    Only registers routes for providers whose ``DECEPTICON_AUTH_*`` flag is
    truthy.  This prevents LiteLLM's native OAuth providers from attempting
    device-code or session-token handshakes at startup when the user hasn't
    enabled the auth method.
    """
    source = env if env is not None else os.environ
    model_list = config.setdefault("model_list", [])
    existing = {e.get("model_name") for e in model_list if isinstance(e, dict)}

    settings = config.setdefault("litellm_settings", {})
    fallbacks = settings.setdefault("fallbacks", [])

    for flag, routes in _SUBSCRIPTION_ROUTES.items():
        if not _is_truthy(source.get(flag, "")):
            continue
        for route in routes:
            if route["model_name"] not in existing:
                model_list.append(_with_shadow_pricing(route))
                existing.add(route["model_name"])
        # Add corresponding fallbacks
        for fb in _SUBSCRIPTION_FALLBACKS.get(flag, []):
            if fb not in fallbacks:
                fallbacks.append(fb)


def has_subscription_routes(env: Mapping[str, str] | None = None) -> bool:
    """Return True if any DECEPTICON_AUTH_* flag enables a subscription route.

    Used by ``litellm_startup.py`` to decide whether to regenerate the
    LiteLLM config even when no ``DECEPTICON_MODEL*`` overrides are set —
    a user who only enables ``DECEPTICON_AUTH_CHATGPT=true`` still needs
    the corresponding ``auth/gpt-*`` model_list entries.
    """
    source = env if env is not None else os.environ
    return any(_is_truthy(source.get(flag, "")) for flag in _SUBSCRIPTION_ROUTES)


def merge_dynamic_models(
    config: MutableMapping[str, Any], env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Append requested models not already present in a LiteLLM config."""
    merged = copy.deepcopy(dict(config))

    # Conditionally inject subscription OAuth routes
    _inject_subscription_routes(merged, env)

    model_list = list(merged.get("model_list") or [])
    existing = {entry.get("model_name") for entry in model_list if isinstance(entry, dict)}

    for model_name in sorted(collect_requested_models(env)):
        if model_name in existing:
            # Already registered by ``_inject_subscription_routes`` (or a
            # static entry in litellm.yaml). Skip the API-key validator —
            # ``auth/*`` slugs are deliberately rejected by
            # ``validate_model_name`` for the API-key path even though
            # they are valid subscription targets.
            continue
        validate_model_name(model_name)
        model_list.append(build_model_entry(model_name))
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
    "has_subscription_routes",
    "merge_dynamic_models",
    "validate_model_name",
    "write_dynamic_config",
]
