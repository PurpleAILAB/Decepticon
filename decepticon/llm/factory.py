"""LLM Factory — creates ChatModel instances via LiteLLM proxy.

All LLM calls route through the LiteLLM Docker proxy for provider abstraction.
Provider API keys are configured in .env / docker-compose.yml.

Architecture:
    LLMFactory(proxy, mapping)
      → get_model("recon")  → ChatOpenAI(model="anthropic/claude-haiku-4-5")
      → get_fallback_models("recon") → [ChatOpenAI(model="openai/gpt-5-nano")]
                                         ↓
                        LiteLLM proxy → Anthropic/OpenAI/Google/etc.

Profile-aware: when no explicit mapping is provided, builds a
credentials-aware mapping from environment variables. The factory
inspects which credentials are configured (non-placeholder API keys
plus the OAuth toggle) and respects ``DECEPTICON_AUTH_PRIORITY`` for
ordering AuthMethods in the fallback chain.
"""

from __future__ import annotations

import os
from enum import Enum

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from decepticon.core.logging import get_logger
from decepticon.llm.models import (
    AuthMethod,
    Credentials,
    LLMModelMapping,
    ModelProfile,
    ProxyConfig,
)
from decepticon.llm.router import ModelRouter

log = get_logger("llm.factory")


# Default ordering when DECEPTICON_AUTH_PRIORITY is not set. OAuth methods
# precede the matching API method so a subscription primary falls back to
# the paid API only when the subscription quota hits — not the other way.
# OLLAMA_LOCAL sits at the end: cloud providers are usually preferred
# (faster, smarter) when both are available; Ollama still gets picked up
# as a last-resort fallback when its env vars are wired but no priority
# list was authored.
_DEFAULT_AUTH_PRIORITY: tuple[AuthMethod, ...] = (
    AuthMethod.ANTHROPIC_OAUTH,
    AuthMethod.ANTHROPIC_API,
    AuthMethod.OPENAI_OAUTH,
    AuthMethod.OPENAI_API,
    AuthMethod.GOOGLE_API,
    AuthMethod.MINIMAX_API,
    AuthMethod.DEEPSEEK_API,
    AuthMethod.XAI_API,
    AuthMethod.MISTRAL_API,
    AuthMethod.OPENROUTER_API,
    AuthMethod.NVIDIA_API,
    AuthMethod.OLLAMA_LOCAL,
)

# Each AuthMethod's detection rule:
#   - API methods: presence of a non-placeholder env var
#   - OAuth methods: an explicit "true" boolean env var (set by the
#     onboard wizard after a successful OAuth handshake)
#   - Local methods: their own env signal (OLLAMA_API_BASE for Ollama)
_API_METHOD_ENV: dict[AuthMethod, str] = {
    AuthMethod.ANTHROPIC_API: "ANTHROPIC_API_KEY",
    AuthMethod.OPENAI_API: "OPENAI_API_KEY",
    AuthMethod.GOOGLE_API: "GEMINI_API_KEY",
    AuthMethod.MINIMAX_API: "MINIMAX_API_KEY",
    AuthMethod.DEEPSEEK_API: "DEEPSEEK_API_KEY",
    AuthMethod.XAI_API: "XAI_API_KEY",
    AuthMethod.MISTRAL_API: "MISTRAL_API_KEY",
    AuthMethod.OPENROUTER_API: "OPENROUTER_API_KEY",
    AuthMethod.NVIDIA_API: "NVIDIA_API_KEY",
}

_OAUTH_METHOD_ENV: dict[AuthMethod, str] = {
    AuthMethod.ANTHROPIC_OAUTH: "DECEPTICON_AUTH_CLAUDE_CODE",
    AuthMethod.OPENAI_OAUTH: "DECEPTICON_AUTH_CHATGPT",
    AuthMethod.GOOGLE_OAUTH: "DECEPTICON_AUTH_GEMINI",
    AuthMethod.COPILOT_OAUTH: "DECEPTICON_AUTH_COPILOT",
    AuthMethod.GROK_OAUTH: "DECEPTICON_AUTH_GROK",
    AuthMethod.PERPLEXITY_OAUTH: "DECEPTICON_AUTH_PERPLEXITY",
}


def _ollama_local_configured() -> bool:
    """Return True when the user has wired up local Ollama.

    Either ``OLLAMA_API_BASE`` (preferred — explicit endpoint) or
    ``OLLAMA_MODEL`` (a pulled model id) is enough to opt in. Both
    blank → not configured. Empty/whitespace strings are treated as
    "not set" so a stray ``OLLAMA_API_BASE=`` line in .env doesn't
    silently enable the method.
    """
    return bool(os.getenv("OLLAMA_API_BASE", "").strip() or os.getenv("OLLAMA_MODEL", "").strip())


def _is_real_key(value: str) -> bool:
    """Reject empty values and the placeholders shipped in .env.example.

    Onboard-written keys pass; values like ``your-anthropic-key-here``
    or empty strings are treated as "not configured" so the resolved
    Credentials inventory stays honest.

    Match the launcher's IsPlaceholder check (``-key-here`` suffix) so
    a real key that happens to contain the substring elsewhere is not
    accidentally rejected.
    """
    v = value.strip()
    if not v:
        return False
    lower = v.lower()
    if lower.startswith("your-") or lower.endswith("-key-here"):
        return False
    return True


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


def _resolve_credentials() -> Credentials:
    """Build Credentials from environment variables.

    Walks ``DECEPTICON_AUTH_PRIORITY`` (comma-separated AuthMethod
    values; defaults to ``_DEFAULT_AUTH_PRIORITY``) and includes only
    methods whose detection rule passes:

      - API methods: their key env var is set to a non-placeholder
      - OAuth methods: their boolean env var is set truthy

    When **nothing** is detected — typical of CI / dev shells where
    onboard hasn't run — falls back to all four API methods. This keeps
    module-level ``graph = create_X_agent()`` calls importable so the
    test suite (and tools like langgraph Studio) can load agents
    without API keys present. Real LLM calls under that fallback will
    fail at request time with a provider 401, which is the correct
    surface for that misconfiguration.
    """
    priority_raw = os.getenv("DECEPTICON_AUTH_PRIORITY", "")
    if priority_raw.strip():
        priority: list[AuthMethod] = []
        for token in priority_raw.split(","):
            token = token.strip().lower()
            if not token:
                continue
            try:
                priority.append(AuthMethod(token))
            except ValueError:
                log.warning("Unknown method in DECEPTICON_AUTH_PRIORITY: %s", token)
    else:
        priority = list(_DEFAULT_AUTH_PRIORITY)

    methods: list[AuthMethod] = []
    for method in priority:
        if method in _API_METHOD_ENV:
            if _is_real_key(os.getenv(_API_METHOD_ENV[method], "")):
                methods.append(method)
        elif method in _OAUTH_METHOD_ENV:
            if _is_truthy(os.getenv(_OAUTH_METHOD_ENV[method], "")):
                methods.append(method)
        elif method == AuthMethod.OLLAMA_LOCAL:
            if _ollama_local_configured():
                methods.append(method)

    if not methods:
        # Local-only OSS path: a user who set OLLAMA_API_BASE / OLLAMA_MODEL
        # but didn't write a priority list (or whose priority list was all
        # empty placeholders) gets a single-method Ollama chain. Without
        # this branch we'd fall back to ``all_api_methods()`` and every
        # request would fail with 401s on providers the user doesn't have.
        if _ollama_local_configured():
            log.info(
                "Only OLLAMA_API_BASE/OLLAMA_MODEL detected; "
                "running against local Ollama exclusively"
            )
            return Credentials(methods=[AuthMethod.OLLAMA_LOCAL])
        log.info(
            "No credentials detected in environment; using all-API-methods "
            "fallback so module-level agent constructors stay importable"
        )
        return Credentials.all_api_methods()

    return Credentials(methods=methods)


class _ProxiedChatOpenAI(ChatOpenAI):
    """Translate opaque transport/upstream errors into actionable RuntimeError
    messages so LangGraph's serde surfaces something the user can fix instead
    of the generic 'An internal error occurred' wrapper they see in the OSS
    issue tracker.

    Two failure surfaces matter:

      1. **Connection errors** — proxy unreachable. Almost always a Docker
         networking or container-health problem; we point the user at the
         logs.
      2. **Upstream provider errors** — 4xx returned by the actual model
         provider (Anthropic/OpenAI/Ollama/...) and bubbled through LiteLLM.
         These carry a meaningful message but hit the LangGraph runner as
         a generic ``openai.BadRequestError`` whose serialized form gets
         flattened to 'internal error' on the way back to the CLI. We pull
         out the original message and rewrap it.
    """

    def invoke(self, *args, **kwargs):
        try:
            return super().invoke(*args, **kwargs)
        except Exception as exc:
            _reraise_with_actionable_message(exc, self.model_name)
            raise

    async def ainvoke(self, *args, **kwargs):
        try:
            return await super().ainvoke(*args, **kwargs)
        except Exception as exc:
            _reraise_with_actionable_message(exc, self.model_name)
            raise


def _model_drops_temperature(model: str) -> bool:
    """Return True if the LiteLLM model id rejects the ``temperature`` param.

    Anthropic deprecated ``temperature`` for Claude Opus 4.7 — the request
    gets a 400 from the upstream API regardless of the proxy path. Match
    on the Opus 4.x family across every namespace we route through:

      anthropic/claude-opus-4-7
      auth/claude-opus-4-7
      openrouter/anthropic/claude-opus-4-7

    Rather than enumerate paths we look at the model slug suffix, which
    keeps this honest for openrouter-mirrored variants and any future
    Opus 4.x build added to METHOD_MODELS.
    """
    slug = model.rsplit("/", 1)[-1].lower()
    return slug.startswith("claude-opus-4")


def _reraise_if_connection_error(exc: Exception) -> None:
    err_type = type(exc).__name__
    if any(
        kw in err_type.lower() for kw in ("connect", "timeout", "refused", "unreachable")
    ) or any(
        kw in str(exc).lower()
        for kw in ("connection refused", "connect error", "proxy", "unreachable")
    ):
        raise RuntimeError(
            f"LLM proxy unreachable ({err_type}): {exc}. "
            f"Check 'decepticon logs litellm' for details."
        ) from exc


def _reraise_with_actionable_message(exc: Exception, model_name: str) -> None:
    """Translate transport + upstream errors into a useful RuntimeError.

    Connection failures still go through ``_reraise_if_connection_error``
    (the original signal). For 4xx errors that LiteLLM forwards from the
    upstream provider, we extract the inner message — LiteLLM nests it
    inside the response payload — and re-raise with a clear "model X
    failed because Y" framing plus a remediation hint.

    Critically, this is the place to disambiguate the four classes the
    OSS user actually sees as 'internal error':

      - 400 BadRequestError (e.g. deprecated param, model_group not found)
      - 401 AuthenticationError (key missing/invalid for the routed provider)
      - 404 NotFoundError (model not registered in litellm.yaml)
      - 429 RateLimitError (provider quota hit)
    """
    _reraise_if_connection_error(exc)

    err_type = type(exc).__name__
    msg = str(exc)
    msg_lower = msg.lower()

    # LiteLLM puts a recognizable prefix in the inner message when the
    # proxy ran out of fallback options for a model_group — issue #107.
    # Surface this distinctly so users know *why* the request couldn't be
    # retried somewhere else.
    if "no fallback model group found" in msg_lower:
        raise RuntimeError(
            f"Model '{model_name}' failed and no provider fallback was "
            f"available for it. Either configure another auth method in "
            f"DECEPTICON_AUTH_PRIORITY or fix the upstream error.\n"
            f"Underlying: {msg}"
        ) from exc

    if "badrequest" in err_type.lower() or "code: 400" in msg_lower:
        raise RuntimeError(
            f"Model '{model_name}' rejected the request (400). "
            f"This usually means a parameter the model no longer supports "
            f"(e.g. temperature on Claude Opus 4.7). Underlying: {msg}"
        ) from exc

    if (
        "authentication" in err_type.lower()
        or "code: 401" in msg_lower
        or "invalid_api_key" in msg_lower
    ):
        raise RuntimeError(
            f"Model '{model_name}' rejected your credentials (401). "
            f"Check the API key for that provider in ~/.decepticon/.env, "
            f"or run 'decepticon onboard --reset'.\nUnderlying: {msg}"
        ) from exc

    if "ratelimit" in err_type.lower() or "code: 429" in msg_lower:
        raise RuntimeError(
            f"Model '{model_name}' hit the provider's rate limit (429). "
            f"Add another method to DECEPTICON_AUTH_PRIORITY so the agent "
            f"can fall back when this happens.\nUnderlying: {msg}"
        ) from exc

    if "notfound" in err_type.lower() or "code: 404" in msg_lower:
        raise RuntimeError(
            f"Model '{model_name}' is not registered in the LiteLLM proxy "
            f"(404). For local Ollama, set OLLAMA_MODEL to something you "
            f"actually pulled ('ollama list'). For cloud providers, check "
            f"that the model id matches config/litellm.yaml.\n"
            f"Underlying: {msg}"
        ) from exc


class LLMFactory:
    """Creates and caches LangChain ChatModel instances per agent role.

    Routes all models through LiteLLM proxy. Supports primary + fallback
    model resolution via ModelRouter.

    When constructed without an explicit mapping, builds one from the
    user's credentials inventory and the model profile from
    DecepticonConfig (env: ``DECEPTICON_MODEL_PROFILE``).
    """

    def __init__(
        self,
        proxy: ProxyConfig | None = None,
        mapping: LLMModelMapping | None = None,
        credentials: Credentials | None = None,
        profile: ModelProfile | str | None = None,
    ):
        self._proxy = proxy or self._resolve_proxy_config()
        if mapping is not None:
            self._mapping = mapping
        else:
            creds = credentials if credentials is not None else _resolve_credentials()
            resolved_profile = profile if profile is not None else self._resolve_profile()
            self._mapping = LLMModelMapping.from_credentials_and_profile(creds, resolved_profile)
        self._router = ModelRouter(self._mapping)
        self._cache: dict[str, BaseChatModel] = {}

    @staticmethod
    def _resolve_proxy_config() -> ProxyConfig:
        """Resolve proxy config from DecepticonConfig (env vars)."""
        from decepticon.core.config import load_config

        config = load_config()
        return ProxyConfig(
            url=config.llm.proxy_url,
            api_key=config.llm.proxy_api_key,
            timeout=config.llm.timeout,
            max_retries=config.llm.max_retries,
        )

    @staticmethod
    def _resolve_profile() -> ModelProfile:
        """Resolve the model profile from DecepticonConfig (env var)."""
        from decepticon.core.config import load_config

        return load_config().model_profile

    @property
    def proxy_url(self) -> str:
        return self._proxy.url

    @property
    def router(self) -> ModelRouter:
        return self._router

    def get_model(self, role: str) -> BaseChatModel:
        """Get the primary ChatModel for a role. Cached per role."""
        if role in self._cache:
            return self._cache[role]

        assignment = self._router.get_assignment(role)
        log.info(
            "Creating LLM for role '%s' → model '%s' via %s",
            role,
            assignment.primary,
            self._proxy.url,
        )

        model = self._create_chat_model(assignment.primary, assignment.temperature)
        self._cache[role] = model
        return model

    def get_fallback_models(self, role: str) -> list[BaseChatModel]:
        """Build the full ordered list of fallback ChatModel instances.

        Each entry mirrors one entry from the agent's credentials chain
        beyond the primary. The agent passes the result via
        ``ModelFallbackMiddleware(*models)``, which tries them in order
        until one succeeds.
        """
        assignment = self._router.get_assignment(role)
        if not assignment.fallbacks:
            return []

        log.info(
            "Creating %d fallback LLM(s) for role '%s' → %s",
            len(assignment.fallbacks),
            role,
            assignment.fallbacks,
        )
        return [
            self._create_chat_model(model, assignment.temperature) for model in assignment.fallbacks
        ]

    def _create_chat_model(self, model: str, temperature: float) -> BaseChatModel:
        """Create a proxied ChatOpenAI instance routed through LiteLLM proxy.

        Claude Opus 4.7+ rejects ``temperature`` with a 400 invalid_request
        error regardless of how the request is routed — the model is wired
        to extended-thinking defaults that don't accept the parameter.
        Match every Opus 4.7 surface (anthropic/, auth/, openrouter/...)
        and drop the field from the OpenAI request payload via
        ``disabled_params``. Just omitting our own kwarg is not enough —
        ChatOpenAI synthesizes a default temperature when the field is
        unset, so the param still goes on the wire.

        The LiteLLM proxy also drops temperature for opus entries via
        ``additional_drop_params`` (config/litellm.yaml) — that's the
        belt-and-suspenders for any future client that bypasses this
        factory.
        """
        kwargs: dict[str, object] = {
            "model": model,
            "base_url": self._proxy.url,
            "api_key": SecretStr(self._proxy.api_key),
            "timeout": self._proxy.timeout,
            "max_retries": self._proxy.max_retries,
        }
        if _model_drops_temperature(model):
            kwargs["disabled_params"] = {"temperature": None}
        else:
            kwargs["temperature"] = temperature
        return _ProxiedChatOpenAI(**kwargs)

    async def health_check(self) -> bool:
        """Check if the LiteLLM proxy is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._proxy.url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def create_llm(
    role: object,
    config: object | None = None,
    profile: ModelProfile | str | None = None,
) -> BaseChatModel:
    """Convenience function — creates primary model for a role.

    Backward-compatible wrapper around LLMFactory.
    The `config` parameter is accepted but ignored (kept for call-site compat).
    Pass `profile` to override the config-level model profile.
    """
    _ = config
    factory = LLMFactory(profile=profile)
    role_str = str(role.value) if isinstance(role, Enum) else str(role)
    return factory.get_model(role_str)
