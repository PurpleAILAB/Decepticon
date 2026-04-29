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
No dependency on the ``decepticon`` package.

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
from litellm import CustomLLM, ModelResponse

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

REFRESH_BUFFER_SECONDS = 5 * 60
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
ANTHROPIC_API_BASE = "https://api.anthropic.com"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

OAUTH_TOKEN_PATTERN = "sk-ant-oat01-"

_cached_token: dict[str, Any] | None = None


def _is_valid_oauth_token(token: str) -> bool:
    """Validate that a token looks like a Claude OAuth token."""
    return isinstance(token, str) and token.startswith(OAUTH_TOKEN_PATTERN)


def _load_tokens() -> dict[str, Any] | None:
    """Load tokens following the same resolution order as the reference impl.

    Resolution order (matching not-claude-code-emulator):
      1. ``ANTHROPIC_OAUTH_TOKEN`` environment variable
      2. ``~/.claude/.credentials.json`` (Claude Code CLI current format)
      3. ``~/.config/anthropic/q/tokens.json`` (legacy / emulator format)
    """
    # 1. Environment variable
    env_token = os.environ.get("ANTHROPIC_OAUTH_TOKEN", "").strip()
    if env_token and _is_valid_oauth_token(env_token):
        return {
            "accessToken": env_token,
            "refreshToken": None,
            "expiresAt": 0,  # No expiry info — never auto-refresh
            "scopes": ["user:inference"],
        }

    # 2+3. File-based stores
    for path in (CREDENTIALS_PATH, LEGACY_CREDENTIALS_PATH):
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())
            # Current format: nested under claudeAiOauth
            if "claudeAiOauth" in raw:
                oauth = raw["claudeAiOauth"]
                if _is_valid_oauth_token(oauth.get("accessToken", "")):
                    return oauth
            # Legacy format: top-level accessToken or oauthToken
            token = raw.get("accessToken") or raw.get("oauthToken", "")
            if _is_valid_oauth_token(token):
                if "oauthToken" in raw and "accessToken" not in raw:
                    raw["accessToken"] = raw["oauthToken"]
                return raw
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _is_expired(tokens: dict[str, Any]) -> bool:
    """Check if token is expired or near expiry."""
    expires_at = tokens.get("expiresAt", 0)
    # expiresAt may be in milliseconds (Claude Code CLI format) or seconds
    if expires_at > 1e12:
        expires_at = expires_at / 1000
    return time.time() + REFRESH_BUFFER_SECONDS >= expires_at


def _refresh_token(tokens: dict[str, Any]) -> dict[str, Any]:
    """Synchronously refresh an expired token."""
    resp = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refreshToken"],
            "client_id": CLIENT_ID,
        },
        headers={"content-type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    new_tokens = {
        "accessToken": data["access_token"],
        "refreshToken": data.get("refresh_token", tokens["refreshToken"]),
        "expiresAt": int(time.time() + data.get("expires_in", 3600)),
        "scopes": data.get("scope", "").split(),
        "updatedAt": int(time.time() * 1000),
    }

    # Save refreshed tokens
    try:
        CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_PATH.write_text(json.dumps(new_tokens, indent=2))
        os.chmod(CREDENTIALS_PATH, 0o600)
    except OSError:
        pass  # Read-only mount — token will be refreshed again next call

    return new_tokens


def get_access_token() -> str:
    """Get a valid access token, refreshing if needed.

    When the cached token is expired, re-read from disk first — Claude Code
    CLI continuously refreshes tokens in ~/.claude/.credentials.json, so a
    fresh token may already be available without needing to call the refresh
    endpoint ourselves.
    """
    global _cached_token  # noqa: PLW0603

    tokens = _cached_token or _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message="No Claude Code OAuth tokens found. Run 'decepticon onboard' to authenticate.",
            model="auth",
            llm_provider="auth",
        )

    if _is_expired(tokens):
        # Re-read from disk — Claude Code may have already refreshed the token
        fresh = _load_tokens()
        if fresh and not _is_expired(fresh):
            tokens = fresh
        else:
            tokens = _refresh_token(tokens)

    _cached_token = tokens
    return tokens["accessToken"]


# ── Headers ──────────────────────────────────────────────────────────

REQUIRED_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
    "interleaved-thinking-2025-05-14",
]

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


# ── Custom LLM Handler ──────────────────────────────────────────────


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
        access_token = get_access_token()

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
        # Limit cache_control blocks to 4 (Anthropic API max)
        if len(system_blocks) > 4:
            keep = [system_blocks[0]] + system_blocks[-(4 - 1) :]
            for block in system_blocks:
                if block not in keep and "cache_control" in block:
                    del block["cache_control"]
            system_blocks = [system_blocks[0]] + system_blocks[1:]

        request_body: dict[str, Any] = {
            "model": actual_model,
            "messages": api_messages,
            "system": system_blocks,
            "max_tokens": opts.get("max_tokens", 4096),
        }
        if "temperature" in opts:
            request_body["temperature"] = opts["temperature"]
        if "top_p" in opts:
            request_body["top_p"] = opts["top_p"]
        if "stop" in opts:
            request_body["stop_sequences"] = opts["stop"]

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

        # Build headers — OAuth Bearer (NOT x-api-key)
        req_headers = _build_headers(access_token)

        # Direct HTTP call to Anthropic Messages API. Never honor arbitrary
        # api_base values here: this request carries an OAuth bearer token.
        api_url = _resolve_anthropic_api_base(api_base)
        resp = httpx.post(
            f"{api_url}/v1/messages?beta=true",
            content=body_str,
            headers=req_headers,
            timeout=timeout or 600,
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

        data = resp.json()

        # Convert Anthropic response to LiteLLM ModelResponse (OpenAI format)
        content_blocks = data.get("content", [])

        # Extract text content
        text_parts = [block["text"] for block in content_blocks if block.get("type") == "text"]
        response_text = "\n".join(text_parts) if text_parts else None

        # Extract tool_use blocks → OpenAI tool_calls format
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block["name"],
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

        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("input_tokens", 0)
        output_tokens = usage_data.get("output_tokens", 0)

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
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
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

        usage = {
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

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
