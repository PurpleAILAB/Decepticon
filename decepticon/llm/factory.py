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

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

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
_DEFAULT_AUTH_PRIORITY: tuple[AuthMethod, ...] = (
    AuthMethod.ANTHROPIC_OAUTH,
    AuthMethod.ANTHROPIC_API,
    AuthMethod.OPENAI_API,
    AuthMethod.GOOGLE_API,
    AuthMethod.MINIMAX_API,
)

# Each AuthMethod's detection rule:
#   - API methods: presence of a non-placeholder env var
#   - OAuth methods: an explicit "true" boolean env var (set by the
#     onboard wizard after a successful OAuth handshake)
_API_METHOD_ENV: dict[AuthMethod, str] = {
    AuthMethod.ANTHROPIC_API: "ANTHROPIC_API_KEY",
    AuthMethod.OPENAI_API: "OPENAI_API_KEY",
    AuthMethod.GOOGLE_API: "GEMINI_API_KEY",
    AuthMethod.MINIMAX_API: "MINIMAX_API_KEY",
}

_OAUTH_METHOD_ENV: dict[AuthMethod, str] = {
    AuthMethod.ANTHROPIC_OAUTH: "DECEPTICON_AUTH_CLAUDE_CODE",
}


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

    if not methods:
        log.info(
            "No credentials detected in environment; using all-API-methods "
            "fallback so module-level agent constructors stay importable"
        )
        return Credentials.all_api_methods()

    return Credentials(methods=methods)


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
        """Create a ChatOpenAI instance routed through LiteLLM proxy."""
        return ChatOpenAI(
            model=model,
            base_url=self._proxy.url,
            api_key=self._proxy.api_key,
            temperature=temperature,
            timeout=self._proxy.timeout,
            max_retries=self._proxy.max_retries,
        )

    async def health_check(self) -> bool:
        """Check if the LiteLLM proxy is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._proxy.url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def create_llm(
    role: str,
    config: object | None = None,
    profile: ModelProfile | str | None = None,
) -> BaseChatModel:
    """Convenience function — creates primary model for a role.

    Backward-compatible wrapper around LLMFactory.
    The `config` parameter is accepted but ignored (kept for call-site compat).
    Pass `profile` to override the config-level model profile.
    """
    factory = LLMFactory(profile=profile)
    role_str = role.value if hasattr(role, "value") else role
    return factory.get_model(role_str)
