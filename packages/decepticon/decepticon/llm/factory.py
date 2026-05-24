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

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from decepticon.llm.router import ModelRouter
from decepticon_core.registry import RoleRegistry
from decepticon_core.types.llm import (
    AuthMethod,
    Credentials,
    LLMModelMapping,
    ModelProfile,
    ProxyConfig,
)
from decepticon_core.utils.logging import get_logger

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
    AuthMethod.GROQ_API,
    AuthMethod.TOGETHER_API,
    AuthMethod.FIREWORKS_API,
    AuthMethod.COHERE_API,
    AuthMethod.MOONSHOT_API,
    AuthMethod.ZAI_API,
    AuthMethod.DASHSCOPE_API,
    AuthMethod.GITHUB_MODELS_API,
    AuthMethod.BEDROCK_API,
    AuthMethod.VERTEX_API,
    AuthMethod.AZURE_API,
    AuthMethod.LMSTUDIO_LOCAL,
    AuthMethod.LLAMACPP_LOCAL,
    AuthMethod.CUSTOM_OPENAI_API,
    AuthMethod.CEREBRAS_API,
    AuthMethod.XIAOMI_MIMO_API,
    AuthMethod.OLLAMA_LOCAL,
    AuthMethod.OLLAMA_CLOUD,
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
    # Cloud gateways added in the OpenClaude provider migration. Each
    # routes through LiteLLM's native provider implementation when the
    # corresponding API key is present and not a placeholder.
    AuthMethod.GROQ_API: "GROQ_API_KEY",
    AuthMethod.TOGETHER_API: "TOGETHER_API_KEY",
    AuthMethod.FIREWORKS_API: "FIREWORKS_API_KEY",
    AuthMethod.COHERE_API: "COHERE_API_KEY",
    AuthMethod.MOONSHOT_API: "MOONSHOT_API_KEY",
    AuthMethod.ZAI_API: "ZAI_API_KEY",
    AuthMethod.DASHSCOPE_API: "DASHSCOPE_API_KEY",
    AuthMethod.GITHUB_MODELS_API: "GITHUB_TOKEN",
    AuthMethod.BEDROCK_API: "AWS_ACCESS_KEY_ID",
    # Vertex uses a service-account JSON path; treat the path env var as
    # the credential signal so onboard's "real key" check works on it.
    AuthMethod.VERTEX_API: "GOOGLE_APPLICATION_CREDENTIALS",
    AuthMethod.AZURE_API: "AZURE_API_KEY",
    AuthMethod.CEREBRAS_API: "CEREBRAS_API_KEY",
    AuthMethod.XIAOMI_MIMO_API: "XIAOMI_MIMO_API_KEY",
}

_OAUTH_METHOD_ENV: dict[AuthMethod, str] = {
    AuthMethod.ANTHROPIC_OAUTH: "DECEPTICON_AUTH_CLAUDE_CODE",
    AuthMethod.OPENAI_OAUTH: "DECEPTICON_AUTH_CHATGPT",
    AuthMethod.GOOGLE_OAUTH: "DECEPTICON_AUTH_GEMINI",
    AuthMethod.COPILOT_OAUTH: "DECEPTICON_AUTH_COPILOT",
    AuthMethod.GROK_OAUTH: "DECEPTICON_AUTH_GROK",
    AuthMethod.PERPLEXITY_OAUTH: "DECEPTICON_AUTH_PERPLEXITY",
}

# Vendor-specific API key prefix hints. When the method has a known
# canonical prefix, ``_is_real_key`` requires the value to start with one
# of these strings — protects against placeholder strings the launcher
# didn't emit (e.g. a user pasting ``sk-ant-not-used`` into .env).
_KEY_PREFIX_HINTS: dict[AuthMethod, tuple[str, ...]] = {
    AuthMethod.ANTHROPIC_API: ("sk-ant-",),
    AuthMethod.OPENAI_API: ("sk-",),
    AuthMethod.GOOGLE_API: ("AIza",),
    AuthMethod.XAI_API: ("xai-",),
    AuthMethod.GROQ_API: ("gsk_",),
    AuthMethod.OPENROUTER_API: ("sk-or-",),
    AuthMethod.NVIDIA_API: ("nvapi-",),
    AuthMethod.DEEPSEEK_API: ("sk-",),
    AuthMethod.GITHUB_MODELS_API: ("ghp_", "github_pat_", "gho_", "ghs_"),
}

# Substring tokens that mark a value as obviously not a real key.
# Catches creative placeholder values that don't match the launcher's
# ``your-…-key-here`` template.
_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "placeholder",
    "not-used",
    "not_used",
    "dummy",
    "fake",
    "example",
)

# Minimum length for any value that should be treated as a real key. All
# vendor-issued keys exceed this — Anthropic ``sk-ant-api03-…`` ≈ 100 chars,
# OpenAI ``sk-…`` ≥ 48 chars, Google ``AIza…`` 39 chars. 24 leaves headroom
# for vendors with shorter formats (Mistral, etc.) without admitting
# obviously-junk values.
_KEY_MIN_LENGTH = 24

# OAuth methods carry a host-side credentials file. Booleans like
# ``DECEPTICON_AUTH_CLAUDE_CODE=true`` are intent (the user enabled the
# subscription) — they don't guarantee the actual file exists. The
# factory verifies file presence + valid JSON before adding a method to
# the chain so a user who ran ``codex logout`` without flipping the
# boolean back doesn't generate a noisy 401-fallback storm.
#
# Each tuple is ordered: primary path first, legacy paths after. Env-var
# overrides take precedence over the literal default. The langgraph
# compose service mounts the Claude + Codex paths read-only so this
# check sees the same files the LiteLLM handlers will read.
_OAUTH_CREDENTIAL_PATHS: dict[AuthMethod, tuple[tuple[str, str], ...]] = {
    AuthMethod.ANTHROPIC_OAUTH: (
        ("CLAUDE_CODE_CREDENTIALS_PATH", "~/.claude/.credentials.json"),
        ("", "~/.config/anthropic/q/tokens.json"),  # legacy emulator path
    ),
    AuthMethod.OPENAI_OAUTH: (("CODEX_AUTH_PATH", "~/.codex/auth.json"),),
    AuthMethod.GOOGLE_OAUTH: (("GEMINI_TOKENS_PATH", "~/.config/gemini/tokens.json"),),
    AuthMethod.COPILOT_OAUTH: (("COPILOT_TOKENS_PATH", "~/.config/copilot/tokens.json"),),
    AuthMethod.GROK_OAUTH: (("GROK_TOKENS_PATH", "~/.config/grok/tokens.json"),),
    AuthMethod.PERPLEXITY_OAUTH: (("PERPLEXITY_TOKENS_PATH", "~/.config/perplexity/tokens.json"),),
}


def _ollama_cloud_configured() -> bool:
    """Return True when the user has wired up Ollama Cloud.

    Either ``OLLAMA_CLOUD_API_BASE`` (preferred — explicit endpoint) or
    ``OLLAMA_CLOUD_MODEL`` is enough to opt in.
    """
    return bool(
        os.getenv("OLLAMA_CLOUD_API_BASE", "").strip()
        or os.getenv("OLLAMA_CLOUD_MODEL", "").strip()
    )


def _ollama_local_configured() -> bool:
    """Return True when the user has wired up local Ollama.

    Either ``OLLAMA_API_BASE`` (preferred — explicit endpoint) or
    ``OLLAMA_MODEL`` (a pulled model id) is enough to opt in. Both
    blank → not configured. Empty/whitespace strings are treated as
    "not set" so a stray ``OLLAMA_API_BASE=`` line in .env doesn't
    silently enable the method.
    """
    return bool(os.getenv("OLLAMA_API_BASE", "").strip() or os.getenv("OLLAMA_MODEL", "").strip())


def _lmstudio_local_configured() -> bool:
    """Return True when the user has wired up local LM Studio."""
    return bool(
        os.getenv("LMSTUDIO_API_BASE", "").strip() or os.getenv("LMSTUDIO_MODEL", "").strip()
    )


def _llamacpp_local_configured() -> bool:
    """Return True when the user has wired up local llama.cpp llama-server.

    Either ``LLAMACPP_API_BASE`` (preferred — explicit endpoint, e.g.
    ``http://localhost:8080/v1``) or ``LLAMACPP_MODEL`` (a logical model
    name) is enough to opt in. ``LLAMACPP_API_KEY`` is *not* required —
    llama-server accepts any string by default and an unset key resolves
    to a literal placeholder via LiteLLM's env interpolation, which the
    server happily accepts. See issue #151.
    """
    return bool(
        os.getenv("LLAMACPP_API_BASE", "").strip() or os.getenv("LLAMACPP_MODEL", "").strip()
    )


def _custom_openai_configured() -> bool:
    """Return True when the user has wired up a custom OpenAI-compatible
    endpoint. Both ``CUSTOM_OPENAI_API_BASE`` (URL) and
    ``CUSTOM_OPENAI_API_KEY`` (real, non-placeholder) are required —
    a base URL alone won't authenticate, and a key without a URL has
    nowhere to point.
    """
    base = os.getenv("CUSTOM_OPENAI_API_BASE", "").strip()
    key = os.getenv("CUSTOM_OPENAI_API_KEY", "")
    return bool(base) and _is_real_key(key)


def _is_real_key(value: str, method: AuthMethod | None = None) -> bool:
    """Validate that ``value`` looks like a real provider API key.

    Layers, in order:
      1. Strip whitespace; reject empty.
      2. Reject anything shorter than ``_KEY_MIN_LENGTH`` (24 chars) —
         every vendor-issued key exceeds this, while typical placeholders
         (``sk-ant-test``, ``not-set``) do not.
      3. Reject the launcher's template strings (``your-…-key-here``).
      4. Reject values containing obvious placeholder tokens
         (``placeholder``, ``not-used``, ``dummy``, …) — guards against
         creative .env values that escape the launcher template.
      5. When ``method`` is given and ``_KEY_PREFIX_HINTS`` defines a
         canonical prefix for it, require ``value`` to start with one of
         the prefixes. Catches mis-pasted keys (e.g. an OpenAI key in
         the Anthropic slot) before they propagate into the chain.

    ``method=None`` skips the prefix check — kept for callers like
    ``_custom_openai_configured`` where the vendor's expected prefix is
    deployment-specific (any OpenAI-compatible gateway).
    """
    v = value.strip()
    if not v or len(v) < _KEY_MIN_LENGTH:
        return False
    lower = v.lower()
    if lower.startswith("your-") or lower.endswith("-key-here"):
        return False
    if any(token in lower for token in _PLACEHOLDER_TOKENS):
        return False
    if method is not None:
        prefixes = _KEY_PREFIX_HINTS.get(method)
        if prefixes and not any(v.startswith(prefix) for prefix in prefixes):
            return False
    return True


def _oauth_credentials_present(method: AuthMethod) -> bool:
    """Return True if the host-side credential file for ``method`` exists.

    The factory layer reads this to keep the credentials inventory
    honest — without it, ``DECEPTICON_AUTH_CLAUDE_CODE=true`` plus a
    deleted ``~/.claude/.credentials.json`` would still place the OAuth
    method in every fallback chain, generating one 401 per request.

    Each path is checked in order. ``/dev/null`` (the docker-compose
    fallback when no credentials volume is wired) parses as empty, so
    the JSON-validation step fails closed.
    """
    candidates = _OAUTH_CREDENTIAL_PATHS.get(method)
    if not candidates:
        # Method has no documented file path — fall back to the boolean
        # flag alone for forward compatibility.
        return True
    for env_var, default in candidates:
        raw = os.environ.get(env_var, "").strip() if env_var else ""
        path = Path(raw).expanduser() if raw else Path(default).expanduser()
        try:
            text = path.read_text()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
            continue
        except OSError:
            # ``/dev/null`` reads to empty without raising; other transient
            # I/O errors fall through to the next candidate.
            text = ""
        text = text.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data:
            return True
    return False


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
    priority_explicit = bool(priority_raw.strip())
    if priority_explicit:
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
            if _is_real_key(os.getenv(_API_METHOD_ENV[method], ""), method):
                methods.append(method)
        elif method in _OAUTH_METHOD_ENV:
            # OAuth methods need BOTH the boolean intent and the actual
            # credential file. Without the file check a stale flag (e.g.
            # ``codex logout`` after onboard) generates a 401-fallback
            # storm — see ``_oauth_credentials_present`` for the full
            # rationale.
            if _is_truthy(os.getenv(_OAUTH_METHOD_ENV[method], "")) and _oauth_credentials_present(
                method
            ):
                methods.append(method)
        elif method == AuthMethod.OLLAMA_LOCAL:
            if _ollama_local_configured():
                methods.append(method)
        elif method == AuthMethod.OLLAMA_CLOUD:
            if _ollama_cloud_configured():
                methods.append(method)
        elif method == AuthMethod.LMSTUDIO_LOCAL:
            if _lmstudio_local_configured():
                methods.append(method)
        elif method == AuthMethod.LLAMACPP_LOCAL:
            if _llamacpp_local_configured():
                methods.append(method)
        elif method == AuthMethod.CUSTOM_OPENAI_API:
            if _custom_openai_configured():
                methods.append(method)

    if not methods:
        # Local-only or cloud-only OSS path: a user who set Ollama env vars
        # but didn't write a priority list gets a single-method Ollama chain.
        if _ollama_local_configured():
            log.info(
                "Only OLLAMA_API_BASE/OLLAMA_MODEL detected; "
                "running against local Ollama exclusively"
            )
            return Credentials(methods=[AuthMethod.OLLAMA_LOCAL])
        if _ollama_cloud_configured():
            log.info(
                "Only OLLAMA_CLOUD_API_BASE/OLLAMA_CLOUD_MODEL detected; "
                "running against Ollama Cloud exclusively"
            )
            return Credentials(methods=[AuthMethod.OLLAMA_CLOUD])
        if _lmstudio_local_configured():
            log.info("Only LMSTUDIO_API_BASE/LMSTUDIO_MODEL detected; using LM Studio")
            return Credentials(methods=[AuthMethod.LMSTUDIO_LOCAL])
        if _llamacpp_local_configured():
            log.info("Only LLAMACPP_API_BASE/LLAMACPP_MODEL detected; using llama.cpp")
            return Credentials(methods=[AuthMethod.LLAMACPP_LOCAL])
        if _custom_openai_configured():
            log.info("Only CUSTOM_OPENAI_* detected; using custom OpenAI-compatible endpoint")
            return Credentials(methods=[AuthMethod.CUSTOM_OPENAI_API])
        if priority_explicit:
            # User expressed clear intent (set DECEPTICON_AUTH_PRIORITY) but
            # every listed method failed detection. Surface the root cause
            # at ERROR level — otherwise the silent fallback to
            # all_api_methods() runs through providers the user doesn't
            # have, producing a confusing 401 cascade (often masked as a
            # downstream "rate limit (429)" once the routed-to provider
            # cools down). Return behavior preserved so module imports
            # stay green; real model calls still surface a remediation
            # hint via _reraise_with_actionable_message.
            log.error(
                "DECEPTICON_AUTH_PRIORITY=%r set but no listed method has "
                "detectable credentials. Verify: (1) API keys are "
                "non-placeholder (e.g. ANTHROPIC_API_KEY starts with "
                "'sk-ant-'), (2) OAuth flag matches credential file "
                "(e.g. DECEPTICON_AUTH_CLAUDE_CODE=true requires "
                "~/.claude/.credentials.json to exist and contain a valid "
                "JSON object — a /dev/null mount fails this check). "
                "Falling back to all-API-methods so module imports "
                "remain importable; every model call will 401 until "
                "the priority chain is fixed.",
                priority_raw,
            )
        else:
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


def _model_is_deepseek_thinking(model: str) -> bool:
    """Return True for DeepSeek V4 models and legacy deepseek-reasoner.

    DeepSeek V4 (pro **and** flash) plus legacy deepseek-reasoner use
    thinking mode by default and return ``reasoning_content`` in assistant
    messages. The API **requires** ``reasoning_content`` to be passed back
    in subsequent tool turns — omitting it triggers the upstream 400:
        "The reasoning_content in the thinking mode must be passed back to the API."
    DeepSeek's own docs state ``deepseek-reasoner`` is the deprecated alias
    for ``deepseek-v4-flash`` thinking mode, so flash also needs this
    treatment. Closes #201, #220.
    See: https://api-docs.deepseek.com/guides/thinking_mode
    """
    slug = model.rsplit("/", 1)[-1].lower()
    return slug in ("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-reasoner")


def _model_is_nvidia_nim(model: str) -> bool:
    """Return True for any nvidia_nim/* route.

    NVIDIA NIM's OpenAI-compatible endpoint rejects ``messages[].content``
    as a list-of-parts (the OpenAI v1 multimodal shape) with:
        400 invalid_request_error
        loc=('body','messages',0,'content')
        msg="Input should be a valid string"
    LangChain ChatOpenAI serializes structured content (tool results,
    multipart system blocks) as that exact list shape, so every agent
    run on an NIM route 400s on the first turn. Flatten list-of-text
    parts to a single string before the request leaves the proxy.
    """
    return model.lower().startswith("nvidia_nim/")


class _DeepSeekThinkingChatOpenAI(_ProxiedChatOpenAI):
    """ChatOpenAI subclass that preserves DeepSeek ``reasoning_content``.

    DeepSeek V4 Pro's thinking mode returns ``reasoning_content`` alongside
    ``content`` in assistant messages. When tool calls are present, this field
    **must** be passed back in all subsequent API requests. LangChain's default
    message converters silently drop it in both directions:

    1. Response → AIMessage: ``reasoning_content`` is not extracted
    2. AIMessage → request dict: ``reasoning_content`` is not serialized

    This class patches both directions by:
    - Storing ``reasoning_content`` in ``AIMessage.additional_kwargs``
    - Injecting it back into request dicts for assistant messages
    - Passing ``extra_body={"thinking": {"type": "enabled"}}`` and
      ``reasoning_effort="high"`` on every request
    """

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Inject reasoning_content into outbound assistant messages."""
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # Inject DeepSeek thinking mode params
        extra_body = payload.get("extra_body") or {}
        extra_body["thinking"] = {"type": "enabled"}
        payload["extra_body"] = extra_body
        payload["reasoning_effort"] = "high"

        # Walk the messages array and inject reasoning_content from
        # additional_kwargs back into assistant message dicts so the
        # DeepSeek API sees them.
        for msg in payload.get("messages", []):
            if msg.get("role") != "assistant":
                continue
            # The source AIMessage stashes reasoning_content in
            # additional_kwargs; _convert_message_to_dict does not
            # serialize it. Find the original AIMessage and inject.
            # We also check if the dict already has it (future-proofing
            # in case LangChain adds native support).
            if "reasoning_content" not in msg:
                # Try to find matching AIMessage from the input
                if isinstance(input_, list):
                    for lc_msg in input_:
                        if isinstance(lc_msg, AIMessage) and lc_msg.additional_kwargs.get(
                            "reasoning_content"
                        ):
                            # Match by content — the dict's content came from this message
                            msg_content = msg.get("content") or ""
                            lc_content = lc_msg.content or ""
                            if str(msg_content) == str(lc_content) or (
                                msg.get("tool_calls") and lc_msg.tool_calls
                            ):
                                msg["reasoning_content"] = lc_msg.additional_kwargs[
                                    "reasoning_content"
                                ]
                                break

        return payload

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        """Wrap _generate to preserve reasoning_content in the response."""
        result = super()._generate(messages, *args, **kwargs)
        # _create_chat_result already handled extraction; this is a no-op safety net.
        return result

    async def _agenerate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        """Wrap _agenerate to preserve reasoning_content in the response."""
        result = await super()._agenerate(messages, *args, **kwargs)
        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> Any:
        """Intercept streaming chunks to capture ``reasoning_content``.

        DeepSeek sends ``reasoning_content`` inside ``choices[0].delta``
        during streaming.  LangChain's ``_convert_delta_to_message_chunk``
        ignores it, so it never reaches ``AIMessageChunk.additional_kwargs``.

        We call the parent to build the ``ChatGenerationChunk`` normally,
        then fish ``reasoning_content`` out of the raw delta dict and inject
        it into the chunk message's ``additional_kwargs``.  When LangChain
        aggregates chunks via ``AIMessageChunk.__add__``, ``merge_dicts``
        concatenates the string fragments into the full reasoning trace,
        which ``_get_request_payload`` then injects back into the API
        request on subsequent turns.
        """
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        # Extract reasoning_content from the raw delta
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        if choices:
            delta = choices[0].get("delta") or {}
            rc = delta.get("reasoning_content")
            if rc and isinstance(gen_chunk.message, AIMessage):
                gen_chunk.message.additional_kwargs.setdefault("reasoning_content", "")
                gen_chunk.message.additional_kwargs["reasoning_content"] += rc

        return gen_chunk

    def _create_chat_result(self, response: Any, generation_info: dict | None = None) -> Any:
        """Override to capture ``reasoning_content`` from the response dict.

        ``_create_chat_result`` receives either the raw OpenAI ``ChatCompletion``
        object or its ``.model_dump()`` dict.  Either way, each choice's
        ``message`` dict contains ``reasoning_content`` (the OpenAI SDK v1.x
        preserves it via ``model_extra``).  LangChain's ``_convert_dict_to_message``
        ignores it, so we fish it out of the response dict and inject it into
        the resulting ``AIMessage.additional_kwargs`` after the parent builds
        the ``ChatResult``.
        """
        # Get the response as a dict so we can access reasoning_content
        import openai as _openai

        if isinstance(response, _openai.BaseModel):
            response_dict = response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        elif isinstance(response, dict):
            response_dict = response
        else:
            response_dict = {}

        result = super()._create_chat_result(response, generation_info)

        # Pair up choices with generations and inject reasoning_content
        choices = response_dict.get("choices") or []
        for choice, generation in zip(choices, result.generations):
            msg = getattr(generation, "message", None)
            if not isinstance(msg, AIMessage):
                continue
            if msg.additional_kwargs.get("reasoning_content"):
                continue
            rc = (choice.get("message") or {}).get("reasoning_content")
            if rc:
                msg.additional_kwargs["reasoning_content"] = rc

        return result


class _NvidiaNIMChatOpenAI(_ProxiedChatOpenAI):
    """ChatOpenAI subclass that flattens content to a string for NVIDIA NIM.

    NIM's OpenAI-compat endpoint requires ``messages[].content`` to be a
    plain string. LangChain ChatOpenAI emits the OpenAI v1 multipart shape
    (``[{"type":"text","text":"..."}, ...]``) whenever a message has more
    than one part (tool result + reasoning preamble, multi-block system).
    NIM 400s on that shape. Re-pack each list into the concatenated text
    just before the request leaves the proxy. Image/audio parts are
    preserved untouched — those still get rejected upstream, but the
    error then becomes the upstream feature-gap rather than a contract
    mismatch.
    """

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for msg in payload.get("messages", []):
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            text_parts: list[str] = []
            non_text: list[Any] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") in (None, "text", "input_text", "output_text"):
                        text = part.get("text") or part.get("content") or ""
                        if isinstance(text, str) and text:
                            text_parts.append(text)
                        continue
                    non_text.append(part)
                elif isinstance(part, str):
                    if part:
                        text_parts.append(part)
                else:
                    non_text.append(part)
            if non_text:
                # Leave multimodal parts to the upstream provider's
                # rejection — collapsing them would silently drop data.
                continue
            msg["content"] = "".join(text_parts)
        return payload


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
        from decepticon_core.utils.config import load_config

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
        from decepticon_core.utils.config import load_config

        return load_config().model_profile

    @property
    def proxy_url(self) -> str:
        return self._proxy.url

    @property
    def router(self) -> ModelRouter:
        return self._router

    def _resolve_default_role(self, role: str, explicit: str | None) -> str | None:
        """Pick ``default_role`` for ``ModelRouter.get_assignment``.

        Resolution order:
          1. caller-supplied ``explicit`` wins (existing behavior)
          2. otherwise consult ``RoleRegistry`` for an
             ``llm_role_fallback`` registered against ``role``
          3. otherwise None (router will raise if it can't resolve)

        Closes spec §8 gap #5 — plugin-shipped roles (e.g. SaaS
        ``apt``) no longer need every call site to thread
        ``default_role`` through manually; the registration spec
        carries it.
        """
        if explicit is not None:
            return explicit
        spec = RoleRegistry.get(role)
        if spec is None:
            return None
        return spec.llm_role_fallback

    def get_model(self, role: str, *, default_role: str | None = None) -> BaseChatModel:
        """Get the primary ChatModel for a role. Cached per role.

        ``default_role`` lets plugin orchestrators inherit an OSS role's
        assignment when their custom role is not in ``AGENT_TIERS`` —
        e.g. ``LLMFactory().get_model("decepticon-pro", default_role="decepticon")``.

        When the caller leaves ``default_role`` unset, the factory consults
        ``decepticon_core.registry.RoleRegistry`` for the role's registered
        ``llm_role_fallback`` and uses that. This is how plugin-shipped
        roles such as the SaaS ``apt`` orchestrator stop needing every call
        site to thread ``default_role="decepticon"`` through manually
        (closes spec §8 gap #5).
        """
        if role in self._cache:
            return self._cache[role]

        default_role = self._resolve_default_role(role, default_role)
        assignment = self._router.get_assignment(role, default_role=default_role)
        log.info(
            "Creating LLM for role '%s' → model '%s' via %s",
            role,
            assignment.primary,
            self._proxy.url,
        )

        model = self._create_chat_model(assignment.primary, assignment.temperature)
        self._cache[role] = model
        return model

    def get_fallback_models(
        self, role: str, *, default_role: str | None = None
    ) -> list[BaseChatModel]:
        """Build the full ordered list of fallback ChatModel instances.

        Each entry mirrors one entry from the agent's credentials chain
        beyond the primary. The agent passes the result via
        ``ModelFallbackMiddleware(*models)``, which tries them in order
        until one succeeds. ``default_role`` works as in ``get_model``.
        """
        default_role = self._resolve_default_role(role, default_role)
        assignment = self._router.get_assignment(role, default_role=default_role)
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
        kwargs: dict[str, Any] = {
            "model": model,
            "base_url": self._proxy.url,
            "api_key": SecretStr(self._proxy.api_key),
            "timeout": self._proxy.timeout,
            "max_retries": self._proxy.max_retries,
        }
        if _model_drops_temperature(model):
            kwargs["disabled_params"] = {"temperature": None}
        elif _model_is_deepseek_thinking(model):
            # DeepSeek V4 Pro thinking mode rejects temperature.
            kwargs["disabled_params"] = {"temperature": None}
        else:
            kwargs["temperature"] = temperature
        if _model_is_deepseek_thinking(model):
            return _DeepSeekThinkingChatOpenAI(**kwargs)
        if _model_is_nvidia_nim(model):
            return _NvidiaNIMChatOpenAI(**kwargs)
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
