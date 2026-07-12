"""Standalone LiteLLM custom handler for Claude Code OAuth authentication.

Supports all Anthropic subscription tiers:
  - Claude Free      — rate-limited, Haiku only
  - Claude Pro       — Opus/Sonnet/Haiku, standard rate limits
  - Claude Max       — Opus/Sonnet/Haiku, 20x higher rate limits
  - Claude Team/Enterprise — organization-managed OAuth tokens

The handler reads OAuth tokens from Claude Code CLI credential stores,
auto-refreshes expired tokens, and spoofs Claude Code request headers
so requests are indistinguishable from the native CLI.

This file is mounted into the LiteLLM container alongside litellm.yaml.
No dependency on the ``decepticon`` package — it depends only on the
shared ``oauth_token_store`` helper module mounted alongside it.

Registration in litellm.yaml:
  litellm_settings:
    custom_provider_map:
      - provider: "auth"
        custom_handler: claude_code_handler.claude_code_handler_instance
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import litellm
from http_client import post as _http_post
from litellm import CustomLLM, ModelResponse
from oauth_token_store import (
    DEFAULT_REFRESH_BUFFER_SECONDS,
    FileBackedCache,
    is_timestamp_expired,
    oauth_refresh_request,
    read_json_file,
    with_retry_on_401,
    write_json_atomic,
)

# ── Token storage ────────────────────────────────────────────────────

# Claude Code stores credentials at ~/.claude/.credentials.json (current)
# or ~/.config/anthropic/q/tokens.json (legacy)
CREDENTIALS_PATH = Path(
    os.environ.get(
        "CLAUDE_CODE_CREDENTIALS_PATH",
        os.path.expanduser("~/.claude/.credentials.json"),
    )
)
LEGACY_CREDENTIALS_PATH = Path(os.path.expanduser("~/.config/anthropic/q/tokens.json"))

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
ANTHROPIC_API_BASE = "https://api.anthropic.com"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

OAUTH_TOKEN_PATTERN = "sk-ant-oat01-"


def _is_valid_oauth_token(token: str) -> bool:
    """Validate that a token looks like a Claude OAuth token."""
    return isinstance(token, str) and token.startswith(OAUTH_TOKEN_PATTERN)


def _normalize_credentials(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Pull a usable token dict out of Claude Code's on-disk shapes.

    Resolution order matches the original handler:
      1. ``claudeAiOauth`` nested object (current Claude Code CLI format).
      2. Top-level ``accessToken`` (legacy).
      3. Top-level ``oauthToken`` (emulator format) — copied to
         ``accessToken`` so downstream code only checks one key.
    """
    if "claudeAiOauth" in raw:
        oauth = raw["claudeAiOauth"]
        if isinstance(oauth, dict) and _is_valid_oauth_token(oauth.get("accessToken", "")):
            return oauth
    token = raw.get("accessToken") or raw.get("oauthToken", "")
    if _is_valid_oauth_token(token):
        if "oauthToken" in raw and "accessToken" not in raw:
            raw["accessToken"] = raw["oauthToken"]
        return raw
    return None


def _load_credentials_from_disk(path: Path) -> dict[str, Any] | None:
    """FileBackedCache loader — probes the primary path first, then legacy.

    The cache is keyed on ``CREDENTIALS_PATH`` mtime+size. When that file
    is absent we fall through to ``LEGACY_CREDENTIALS_PATH`` so emulators
    that still write the legacy format keep working — but the cache key
    will be ``None`` (no stat tuple), which means each call re-reads the
    legacy file. That's acceptable: the legacy path is uncommon and the
    parse cost is trivial.
    """
    raw = read_json_file(path)
    if raw is not None:
        normalized = _normalize_credentials(raw)
        if normalized is not None:
            return normalized
    if path != LEGACY_CREDENTIALS_PATH and LEGACY_CREDENTIALS_PATH.exists():
        legacy = read_json_file(LEGACY_CREDENTIALS_PATH)
        if legacy is not None:
            return _normalize_credentials(legacy)
    return None


_credentials_cache = FileBackedCache(CREDENTIALS_PATH, _load_credentials_from_disk)


def _env_override_tokens() -> dict[str, Any] | None:
    """Honor ``ANTHROPIC_OAUTH_TOKEN`` as a synthetic credentials dict.

    The synthetic dict carries ``expiresAt: 0`` so ``is_timestamp_expired``
    returns False and the refresh path never fires for env-provided tokens.
    """
    env_token = os.environ.get("ANTHROPIC_OAUTH_TOKEN", "").strip()
    if env_token and _is_valid_oauth_token(env_token):
        return {
            "accessToken": env_token,
            "refreshToken": None,
            "expiresAt": 0,  # No expiry info — never auto-refresh
            "scopes": ["user:inference"],
        }
    return None


def _load_tokens() -> dict[str, Any] | None:
    """Resolve a tokens dict using env override → cache → legacy fallback."""
    env_dict = _env_override_tokens()
    if env_dict is not None:
        return env_dict
    return _credentials_cache.get()


def _refresh_token(tokens: dict[str, Any]) -> dict[str, Any]:
    """Synchronously refresh an expired token via the platform OAuth endpoint."""
    data = oauth_refresh_request(
        TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refreshToken"],
            "client_id": CLIENT_ID,
        },
        json_body=True,
        timeout=30,
        provider_label="auth",
    )
    # The refresh endpoint normally returns access_token; a malformed or
    # error-shaped response would otherwise blow up with a raw KeyError.
    # Never interpolate ``data`` here — it carries the freshly minted
    # access / refresh tokens. Report only the missing field name.
    access_token = data.get("access_token")
    if not access_token:
        raise litellm.AuthenticationError(
            message=(
                "Claude Code token refresh response missing field: access_token. "
                "Run 'claude /login' and retry."
            ),
            model="auth",
            llm_provider="auth",
        )

    new_tokens = {
        "accessToken": access_token,
        "refreshToken": data.get("refresh_token") or tokens["refreshToken"],
        "expiresAt": int(time.time() + (data.get("expires_in") or 3600)),
        "scopes": (data.get("scope") or "").split(),
        "updatedAt": int(time.time() * 1000),
    }

    # Persist atomically. The store handles read-only mounts internally;
    # the cache replace keeps the in-process token current for the rest
    # of the container session even when the on-disk write fails.
    write_json_atomic(CREDENTIALS_PATH, new_tokens)
    _credentials_cache.replace(new_tokens)
    return new_tokens


def get_access_token(force_refresh: bool = False) -> str:
    """Return a valid access token, refreshing on demand.

    Resolution order:
      1. ``ANTHROPIC_OAUTH_TOKEN`` env override (never refreshed).
      2. Cached / on-disk tokens; if expired or ``force_refresh`` is True,
         call the platform refresh endpoint and persist the new tokens.

    ``force_refresh`` is set by the 401 retry wrapper when the upstream
    rejects a previously-cached token. We bypass the timestamp check in
    that case because the wallclock TTL may be ahead of the server's
    revocation state.
    """
    if force_refresh:
        _credentials_cache.invalidate()

    tokens = _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message="No Claude Code OAuth tokens found. Run 'decepticon onboard' to authenticate.",
            model="auth",
            llm_provider="auth",
        )

    # ANTHROPIC_OAUTH_TOKEN override carries expiresAt=0 → never expires.
    if force_refresh and tokens.get("refreshToken"):
        tokens = _refresh_token(tokens)
    elif is_timestamp_expired(
        tokens.get("expiresAt"), buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS
    ):
        # Re-read from disk — Claude Code may have already refreshed the token.
        _credentials_cache.invalidate()
        fresh = _load_tokens()
        if fresh is not None and not is_timestamp_expired(
            fresh.get("expiresAt"), buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS
        ):
            tokens = fresh
        elif tokens.get("refreshToken"):
            tokens = _refresh_token(tokens)

    return tokens["accessToken"]


# ── Headers ──────────────────────────────────────────────────────────

REQUIRED_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
    "interleaved-thinking-2025-05-14",
]

# Reasoning defaults for Anthropic thinking models (opus 4.x, sonnet 5).
# These models support adaptive thinking + ``output_config.effort`` (effort
# levels low|medium|high|xhigh|max). Effort follows the vendor's agentic
# guidance — opus at xhigh, sonnet-5 at medium — and is applied ONLY when the
# caller passes no ``thinking`` / effort of its own (optional_params win).
# haiku-4.5 and sonnet-4.6 are omitted: haiku errors on ``output_config.effort``
# and neither is a reasoning default here. Thinking tokens count toward
# ``max_tokens``, so the default output cap below is generous enough for
# reasoning + tool calls (the prior 4096 default truncated adaptive thinking
# before it could emit tool_use, yielding empty ``max_tokens``-stopped turns).
# Per-model env override: ``DECEPTICON_CLAUDE_EFFORT_<MODEL>`` where <MODEL> is
# the slug upper-cased with -/. → _ (e.g. DECEPTICON_CLAUDE_EFFORT_CLAUDE_SONNET_5=high).
_REASONING_EFFORT_DEFAULTS: dict[str, str] = {
    "claude-opus-4-8": "xhigh",
    "claude-opus-4-7": "xhigh",
    "claude-sonnet-5": "medium",
}

# Per-model max output tokens (Anthropic's published caps). Used as the default
# when the caller sends no ``max_tokens`` — e.g. deepagents summarization
# sub-calls, which previously defaulted to 4096 and truncated an adaptive
# thinking pass before it could emit ``tool_use``. ``max_tokens`` is a CEILING
# billed on actual output, not a target (a scoping turn uses ~3K), so handing
# each model its full budget removes truncation risk at no extra cost.
_MODEL_MAX_OUTPUT: dict[str, int] = {
    "claude-opus-4-8": 128000,
    "claude-opus-4-7": 128000,
    "claude-sonnet-5": 128000,
    "claude-sonnet-4-6": 128000,
    "claude-haiku-4-5": 64000,
}
_FALLBACK_MAX_TOKENS = 64000  # <= every known model's cap, safe for unknowns


def _reasoning_params(actual_model: str, opts: dict[str, Any]) -> dict[str, Any]:
    """Anthropic ``thinking`` + ``output_config.effort`` for a request.

    Caller-supplied ``thinking`` wins; otherwise adaptive thinking is enabled
    for the reasoning models in ``_REASONING_EFFORT_DEFAULTS``. Effort accepts
    the Anthropic-native ``output_config.effort`` or the OpenAI-style
    ``reasoning_effort`` alias, falling back to the per-model default
    (env-overridable via ``DECEPTICON_CLAUDE_EFFORT_<MODEL>``). Effort is only
    emitted when thinking is on — it controls thinking depth. Returns the keys
    to merge into the request body ( ``{}`` when the model isn't a reasoner and
    the caller passed nothing).
    """
    out: dict[str, Any] = {}
    thinking = opts.get("thinking")
    if thinking:
        out["thinking"] = thinking
    elif actual_model in _REASONING_EFFORT_DEFAULTS:
        out["thinking"] = {"type": "adaptive"}

    if "thinking" not in out:
        return out

    effort = None
    output_config = opts.get("output_config")
    if isinstance(output_config, dict):
        effort = output_config.get("effort")
    effort = effort or opts.get("reasoning_effort")
    if not effort and actual_model in _REASONING_EFFORT_DEFAULTS:
        env_key = (
            "DECEPTICON_CLAUDE_EFFORT_" + actual_model.replace("-", "_").replace(".", "_").upper()
        )
        effort = os.environ.get(env_key, _REASONING_EFFORT_DEFAULTS[actual_model])
    if effort:
        out["output_config"] = {"effort": effort}
    return out


BASE_HEADERS = {
    "anthropic-version": "2023-06-01",
    "anthropic-dangerous-direct-browser-access": "true",
    "x-stainless-timeout": "600",
    "x-stainless-lang": "js",
    "x-stainless-package-version": "0.80.0",
    "x-stainless-os": "MacOS",
    "x-stainless-arch": "arm64",
    "x-stainless-runtime": "node",
    "x-stainless-runtime-version": "v24.3.0",
    "x-stainless-helper-method": "stream",
    "x-stainless-retry-count": "0",
    "x-app": "cli",
    "user-agent": "claude-cli/2.1.87 (external, cli)",
    "accept-language": "*",
    "sec-fetch-mode": "cors",
}


def _resolve_anthropic_api_base(api_base: str | None) -> str:
    """Allow only Anthropic's API host for OAuth bearer-token requests."""
    if not api_base:
        return ANTHROPIC_API_BASE
    parsed = urlparse(api_base)
    if (
        parsed.scheme == "https"
        and parsed.netloc == "api.anthropic.com"
        and parsed.path in {"", "/"}
    ):
        return ANTHROPIC_API_BASE
    raise litellm.AuthenticationError(
        message="auth provider api_base must be https://api.anthropic.com",
        model="auth",
        llm_provider="auth",
    )


def _build_headers(access_token: str) -> dict[str, str]:
    """Build full Anthropic API headers with OAuth + spoofing."""
    headers = dict(BASE_HEADERS)
    headers["authorization"] = f"Bearer {access_token}"
    headers["anthropic-beta"] = ",".join(REQUIRED_BETAS)
    headers["content-type"] = "application/json"
    headers["accept"] = "application/json"
    return headers


def _cap_cache_control(system_blocks: list[dict[str, Any]], max_blocks: int = 4) -> None:
    if len(system_blocks) <= max_blocks:
        return
    keep_indices = {0} | set(range(len(system_blocks) - (max_blocks - 1), len(system_blocks)))
    for i, block in enumerate(system_blocks):
        if i not in keep_indices and "cache_control" in block:
            del block["cache_control"]


def _add_conversation_cache_control(
    api_messages: list[dict[str, Any]], max_breakpoints: int = 1
) -> None:
    """Cache the conversation prefix (tool-result / history bulk), not just the
    system prompt. Stamp ``cache_control`` on the last content block of the
    final message: one tail breakpoint is enough because Anthropic's ≤20-block
    lookback matches the previous turn's prefix and serves it at 0.1×, writing
    only the new delta (incremental / auto-advancing caching). Strings are
    promoted to a text block (Anthropic ignores message-level cache_control on
    string content). Stays within the global 4-breakpoint budget — the system
    prompt is capped to leave room (see the call site)."""
    stamped = 0
    for msg in reversed(api_messages):
        if stamped >= max_breakpoints:
            break
        content = msg.get("content")
        if isinstance(content, str):
            if not content:
                continue
            msg["content"] = [
                {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
            ]
            stamped += 1
        elif isinstance(content, list) and content:
            last_blk = content[-1]
            if isinstance(last_blk, dict):
                last_blk["cache_control"] = {"type": "ephemeral"}
                stamped += 1


class ClaudeCodeCustomHandler(CustomLLM):
    """LiteLLM custom handler that routes requests through Claude Code OAuth.

    Model names: auth/claude-opus-4-7, auth/claude-sonnet-4-6, etc.
    The part after the ``/`` maps to the actual Anthropic model ID.
    """

    def completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_prompt_dict: dict[str, Any] | None = None,
        model_response: ModelResponse | None = None,
        print_verbose: Any = None,
        encoding: Any = None,
        logging_obj: Any = None,
        optional_params: dict[str, Any] | None = None,
        acompletion: bool | None = None,
        timeout: float | None = None,
        litellm_params: dict[str, Any] | None = None,
        logger_fn: Any = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Route completion directly to Anthropic Messages API with OAuth.

        Unlike API-key auth (x-api-key header), OAuth uses
        Authorization: Bearer header + Claude Code spoofing headers.
        This makes the request indistinguishable from a real Claude Code session.
        """
        # Extract actual Anthropic model ID
        # "auth/claude-sonnet-4-6" -> "claude-sonnet-4-6"
        actual_model = model.split("/", 1)[-1] if "/" in model else model

        # Convert OpenAI message format to Anthropic format
        # Key differences:
        #   - system messages → top-level "system" param
        #   - role "tool" → role "user" with tool_result content block
        #   - assistant tool_calls → assistant with tool_use content blocks
        # NOTE: billing header (x-anthropic-billing-header / CCH) intentionally omitted.
        # Including it triggers a Claude Code entitlement check on Anthropic's side that
        # rejects Sonnet/Opus for OAuth subscription tokens (even with a valid CCH).
        # Haiku bypasses the check; higher models do not. Plain spoof text works for all.
        spoof_text = "You are Claude Code, Anthropic's official CLI for Claude."
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": spoof_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")

            if role == "system":
                content = msg["content"]
                if isinstance(content, str):
                    system_blocks.append(
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    )
                elif isinstance(content, list):
                    # LangGraph sends [{"type":"text","text":"..."},...]
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            system_blocks.append(
                                {
                                    "type": "text",
                                    "text": block["text"],
                                    "cache_control": {"type": "ephemeral"},
                                }
                            )
                        elif isinstance(block, str):
                            system_blocks.append(
                                {
                                    "type": "text",
                                    "text": block,
                                    "cache_control": {"type": "ephemeral"},
                                }
                            )

            elif role == "tool":
                # OpenAI: {"role":"tool","content":"...","tool_call_id":"..."}
                # Anthropic: {"role":"user","content":[{"type":"tool_result","tool_use_id":"...","content":"..."}]}
                import re

                raw_id = msg.get("tool_call_id", "") or "tool_result"
                tool_use_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_id)
                tool_content = msg.get("content", "")
                if isinstance(tool_content, list):
                    # LangGraph may send list of content blocks
                    parts = []
                    for block in tool_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block["text"])
                        elif isinstance(block, str):
                            parts.append(block)
                    tool_content = "\n".join(parts)
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": str(tool_content),
                            }
                        ],
                    }
                )

            elif role == "assistant" and msg.get("tool_calls"):
                # OpenAI: {"role":"assistant","tool_calls":[{"function":{"name":"...","arguments":"..."}}]}
                # Anthropic: {"role":"assistant","content":[{"type":"tool_use","id":"...","name":"...","input":{}}]}
                content_blocks: list[dict[str, Any]] = []
                # Keep any text content
                msg_content = msg.get("content")
                if msg_content:
                    if isinstance(msg_content, str):
                        content_blocks.append({"type": "text", "text": msg_content})
                    elif isinstance(msg_content, list):
                        for block in msg_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                content_blocks.append(block)
                for tc in msg["tool_calls"]:
                    # Handle both OpenAI format {"function":{"name","arguments"}}
                    # and LangGraph format {"name","args","id"}
                    if isinstance(tc, dict):
                        func = tc.get("function", {})
                        tc_name = func.get("name") or tc.get("name") or "unknown_tool"
                        tc_id = tc.get("id") or f"tool_{tc_name}"
                        args_raw = func.get("arguments") or tc.get("args", {})
                    else:
                        tc_name = getattr(tc, "name", "unknown_tool") or "unknown_tool"
                        tc_id = getattr(tc, "id", f"tool_{tc_name}") or f"tool_{tc_name}"
                        args_raw = getattr(tc, "args", {})

                    # Ensure id matches Anthropic pattern ^[a-zA-Z0-9_-]+$
                    import re

                    tc_id = re.sub(r"[^a-zA-Z0-9_-]", "_", tc_id) if tc_id else f"tool_{tc_name}"

                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    if not isinstance(args, dict):
                        args = {}

                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc_id,
                            "name": tc_name,
                            "input": args,
                        }
                    )
                api_messages.append({"role": "assistant", "content": content_blocks})

            else:
                # For other roles (user, human), strip Anthropic-incompatible fields
                # Anthropic doesn't support "name" field on any message
                cleaned_msg = {k: v for k, v in msg.items() if k != "name"}
                api_messages.append(cleaned_msg)

        # Build Anthropic Messages API request body
        opts = optional_params or {}
        # Global cap is 4 cache_control breakpoints. Reserve 1 for the
        # conversation tail (below) so the 58:1 tool-result/history bulk gets
        # cached, not just the system prompt; cap the system to the other 3.
        _cap_cache_control(system_blocks, max_blocks=3)
        _add_conversation_cache_control(api_messages, max_breakpoints=1)

        request_body: dict[str, Any] = {
            "model": actual_model,
            "messages": api_messages,
            "system": system_blocks,
            "max_tokens": opts.get("max_tokens")
            or _MODEL_MAX_OUTPUT.get(actual_model, _FALLBACK_MAX_TOKENS),
        }
        if "temperature" in opts:
            request_body["temperature"] = opts["temperature"]
        if "top_p" in opts:
            request_body["top_p"] = opts["top_p"]
        if "stop" in opts:
            request_body["stop_sequences"] = opts["stop"]

        request_body.update(_reasoning_params(actual_model, opts))

        # Tools — convert from OpenAI format to Anthropic format
        openai_tools = opts.get("tools")
        if openai_tools:
            anthropic_tools = []
            for t in openai_tools:
                func = t.get("function", {})
                anthropic_tools.append(
                    {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )
            request_body["tools"] = anthropic_tools

        tool_choice = opts.get("tool_choice")
        if tool_choice:
            if tool_choice == "auto":
                request_body["tool_choice"] = {"type": "auto"}
            elif tool_choice == "required":
                request_body["tool_choice"] = {"type": "any"}
            elif tool_choice == "none":
                pass  # Anthropic doesn't have "none", just omit tools
            elif isinstance(tool_choice, dict) and "function" in tool_choice:
                request_body["tool_choice"] = {
                    "type": "tool",
                    "name": tool_choice["function"]["name"],
                }

        body_str = json.dumps(request_body)

        # Direct HTTP call to Anthropic Messages API. Never honor arbitrary
        # api_base values here: this request carries an OAuth bearer token.
        api_url = _resolve_anthropic_api_base(api_base)

        def _send(force_refresh: bool) -> httpx.Response:
            access_token = get_access_token(force_refresh=force_refresh)
            req_headers = _build_headers(access_token)
            return _http_post(
                f"{api_url}/v1/messages?beta=true",
                content=body_str,
                headers=req_headers,
                timeout=timeout or 600,
            )

        resp = with_retry_on_401(_send)

        if resp.status_code == 401:
            raise litellm.AuthenticationError(
                message=(
                    "Claude Code authentication was rejected. Run 'claude /login' "
                    f"and retry. Underlying: {resp.text}"
                ),
                model=model,
                llm_provider="auth",
            )

        if resp.status_code == 429:
            # Parse retry-after header (seconds or milliseconds)
            retry_after = None
            retry_after_ms = resp.headers.get("retry-after-ms")
            if retry_after_ms:
                try:
                    retry_after = int(retry_after_ms) / 1000
                except ValueError:
                    pass
            if retry_after is None:
                retry_after_raw = resp.headers.get("retry-after")
                if retry_after_raw:
                    try:
                        retry_after = int(retry_after_raw)
                    except ValueError:
                        retry_after = 30  # default
            raise litellm.RateLimitError(
                message=f"Rate limit exceeded: {resp.text}",
                model=model,
                llm_provider="auth",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Anthropic API error: {resp.text}",
                model=model,
                llm_provider="auth",
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=(f"Anthropic API returned a non-JSON response: {resp.text[:500]}"),
                model=model,
                llm_provider="auth",
            ) from exc
        if not isinstance(data, dict):
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Anthropic API response was not a JSON object: {resp.text[:500]}",
                model=model,
                llm_provider="auth",
            )

        # Convert Anthropic response to LiteLLM ModelResponse (OpenAI format).
        # ``content``/``usage`` may be absent or explicitly null on edge
        # responses; ``.get(k) or default`` keeps iteration/arithmetic safe.
        content_blocks = data.get("content") or []
        if not isinstance(content_blocks, list):
            content_blocks = []

        # Extract text content
        text_parts = [
            block["text"]
            for block in content_blocks
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        response_text = "\n".join(text_parts) if text_parts else None

        # Extract tool_use blocks → OpenAI tool_calls format
        tool_calls = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        # Build message dict
        message: dict[str, Any] = {"role": "assistant"}
        if response_text:
            message["content"] = response_text
        else:
            message["content"] = None
        if tool_calls:
            message["tool_calls"] = tool_calls

        usage_data = data.get("usage") or {}
        input_tokens = usage_data.get("input_tokens") or 0
        output_tokens = usage_data.get("output_tokens") or 0
        # Anthropic reports *non-cached* input in ``input_tokens``; cached-prefix
        # reads and cache writes are separate buckets. LiteLLM's cost path derives
        # text_tokens = prompt_tokens − cache buckets, so prompt_tokens MUST include
        # them or cache tokens are dropped from spend logs and cost clamps wrong.
        cache_creation_tokens = usage_data.get("cache_creation_input_tokens") or 0
        cache_read_tokens = usage_data.get("cache_read_input_tokens") or 0
        prompt_tokens = input_tokens + cache_creation_tokens + cache_read_tokens

        # Map finish_reason: tool_use → tool_calls (OpenAI convention)
        stop_reason = data.get("stop_reason", "end_turn")
        if stop_reason == "tool_use":
            finish_reason = "tool_calls"
        else:
            finish_reason = _map_stop_reason(stop_reason)

        response = ModelResponse(
            id=data.get("id", f"chatcmpl-{actual_model}"),
            model=actual_model,
            choices=[
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            usage={
                # ``Usage(**usage)`` maps these top-level Anthropic cache fields
                # onto ``prompt_tokens_details`` + top-level attrs, so LiteLLM's
                # generic cost path prices cache reads (0.1×) / writes (1.25×).
                "prompt_tokens": prompt_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": prompt_tokens + output_tokens,
                "cache_creation_input_tokens": cache_creation_tokens,
                "cache_read_input_tokens": cache_read_tokens,
            },
        )

        return response

    async def acompletion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_prompt_dict: dict[str, Any] | None = None,
        model_response: ModelResponse | None = None,
        print_verbose: Any = None,
        encoding: Any = None,
        logging_obj: Any = None,
        optional_params: dict[str, Any] | None = None,
        acompletion: bool | None = None,
        timeout: float | None = None,
        litellm_params: dict[str, Any] | None = None,
        logger_fn: Any = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Async variant — runs sync completion in a thread to avoid blocking."""
        import asyncio
        import functools

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self.completion,
                model=model,
                messages=messages,
                api_base=api_base,
                optional_params=optional_params,
                timeout=timeout,
            ),
        )

    def _response_to_chunks(self, response: ModelResponse) -> list[dict[str, Any]]:
        """Convert a ModelResponse into GenericStreamingChunk dicts."""
        text = ""
        tool_calls_list = []
        finish_reason = "stop"

        if response.choices:
            choice = response.choices[0]
            msg = choice.message if hasattr(choice, "message") else choice.get("message", {})

            # Extract content
            if isinstance(msg, dict):
                content = msg.get("content")
                raw_tool_calls = msg.get("tool_calls", [])
                finish_reason = (
                    choice.get("finish_reason", "stop")
                    if isinstance(choice, dict)
                    else getattr(choice, "finish_reason", "stop")
                )
            else:
                content = getattr(msg, "content", None)
                raw_tool_calls = getattr(msg, "tool_calls", []) or []
                finish_reason = getattr(choice, "finish_reason", "stop")

            if content and isinstance(content, str):
                text = content

            for i, tc in enumerate(raw_tool_calls):
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    tc_id = tc.get("id", f"call_{i}")
                    tc_name = func.get("name", "")
                    tc_args = func.get("arguments", "{}")
                else:
                    tc_id = getattr(tc, "id", f"call_{i}")
                    func = getattr(tc, "function", None)
                    tc_name = getattr(func, "name", "") if func else ""
                    tc_args = getattr(func, "arguments", "{}") if func else "{}"

                tool_calls_list.append(
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc_name,
                            "arguments": tc_args
                            if isinstance(tc_args, str)
                            else json.dumps(tc_args),
                        },
                        "index": i,
                    }
                )

        usage: dict[str, Any] = {
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        # Propagate cache buckets so litellm's stream_chunk_builder records + prices
        # them on the completed streaming response (it reads these keys directly).
        if response.usage is not None:
            _cc = getattr(response.usage, "cache_creation_input_tokens", None)
            _cr = getattr(response.usage, "cache_read_input_tokens", None)
            if _cc:
                usage["cache_creation_input_tokens"] = _cc
            if _cr:
                usage["cache_read_input_tokens"] = _cr

        chunks: list[dict[str, Any]] = []

        if tool_calls_list:
            # Yield text chunk first if any
            if text:
                chunks.append(
                    {
                        "text": text,
                        "is_finished": False,
                        "finish_reason": "",
                        "index": 0,
                        "tool_use": None,
                        "usage": None,
                    }
                )
            # Yield each tool call as a separate chunk
            for i, tc in enumerate(tool_calls_list):
                is_last = i == len(tool_calls_list) - 1
                chunks.append(
                    {
                        "text": "",
                        "is_finished": is_last,
                        "finish_reason": "tool_calls" if is_last else "",
                        "index": 0,
                        "tool_use": tc,
                        "usage": usage if is_last else None,
                    }
                )
        else:
            chunks.append(
                {
                    "text": text,
                    "is_finished": True,
                    "finish_reason": finish_reason or "stop",
                    "index": 0,
                    "tool_use": None,
                    "usage": usage,
                }
            )

        return chunks

    def streaming(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Sync streaming — call completion and yield as chunks."""
        response = self.completion(*args, **kwargs)
        yield from self._response_to_chunks(response)

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        """Async streaming — call acompletion and yield as chunks."""
        response = await self.acompletion(*args, **kwargs)
        for chunk in self._response_to_chunks(response):
            yield chunk


def _map_stop_reason(anthropic_reason: str) -> str:
    """Map Anthropic stop_reason to OpenAI-style finish_reason."""
    return {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
    }.get(anthropic_reason, "stop")


# ── Module-level instance ────────────────────────────────────────────
# LiteLLM's custom_provider_map resolves the handler via get_instance_fn()
# which imports the module attribute. Some LiteLLM versions call the class
# directly (missing 'self'). Exporting a pre-built instance avoids this.
claude_code_handler_instance = ClaudeCodeCustomHandler()
