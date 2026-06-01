"""LiteLLM custom handler for GitHub Copilot subscription.

Routes requests through the GitHub Copilot chat API using the user's
GitHub OAuth token (gho_/ghu_/ghr_). Enables GPT-4o, o1, o3-mini access
via a Copilot Individual / Business / Enterprise subscription without
OpenAI API billing.

Flow:
  1. Resolve a long-lived source GitHub OAuth token from one of the
     paths below.
  2. POST it to https://api.github.com/copilot_internal/v2/token to
     mint a short-lived Copilot bearer (expires ~30 min).
  3. Cache the bearer + expires_at; remint on expiry.
  4. POST to https://api.githubcopilot.com/chat/completions with the
     bearer + the editor headers GitHub's Copilot endpoint requires.

Source-token resolution order (first match wins):
  1. ``COPILOT_ACCESS_TOKEN`` env (treated as a pre-minted Copilot
     bearer — skip the mint step entirely, used by CI).
  2. ``COPILOT_REFRESH_TOKEN`` env (gho_/ghu_/ghr_ source token).
  3. ``~/.config/copilot/tokens.json`` (DF onboard format).
  4. ``~/.config/github-copilot/apps.json`` (VS Code / IntelliJ
     plugin format — the most common path on developer machines
     because the official Copilot CLI / extensions write here).
  5. ``~/.config/github-copilot/hosts.json`` (legacy format used by
     older versions of the Copilot CLI).

User-facing model names: ``copilot/gpt-5.5``, ``copilot/claude-sonnet-4-6``,
``copilot/gpt-5.4-mini``, ``copilot/gpt-5.3-codex``, etc. The exact lineup
follows GitHub Copilot's model picker (gpt-4o / o1 / o3-mini were retired
on 2025-10-23 and have been replaced by the GPT-5 family).

Slugs that collide with ``litellm.open_ai_chat_completion_models``
(currently ``gpt-5.3-codex`` among Copilot's lineup; the default tier
picks above avoid this set) are aliased in ``litellm_dynamic_config.py``
to an internal ``copilot/oauth-<slug>`` form. The ``oauth-`` sentinel
dodges LiteLLM's ``main.py:2561`` short-circuit, which would otherwise
route the bare slug straight to api.openai.com regardless of provider.
This handler strips the sentinel via ``_upstream_model_slug`` before
forwarding to api.githubcopilot.com, so Copilot receives the canonical
name.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import litellm
from http_client import post as _http_post
from litellm import CustomLLM, ModelResponse
from oauth_token_store import (
    DEFAULT_REFRESH_BUFFER_SECONDS,
    FileBackedCache,
    is_timestamp_expired,
    read_json_file,
    with_retry_on_401,
)

_log = logging.getLogger(__name__)

# Where DF's onboard wizard writes refreshed tokens.
COPILOT_TOKENS_PATH = Path(
    os.environ.get(
        "COPILOT_TOKENS_PATH",
        os.path.expanduser("~/.config/copilot/tokens.json"),
    )
)
# Standard plugin paths consulted on every cold cache load.
COPILOT_PLUGIN_APPS = Path(os.path.expanduser("~/.config/github-copilot/apps.json"))
COPILOT_PLUGIN_HOSTS = Path(os.path.expanduser("~/.config/github-copilot/hosts.json"))

GITHUB_TOKEN_MINT_URL = "https://api.github.com/copilot_internal/v2/token"
GITHUB_COPILOT_API_BASE = "https://api.githubcopilot.com"

# Editor headers the Copilot endpoint enforces. Anything not advertising
# itself as a recognized editor is rejected with HTTP 401.
_COPILOT_EDITOR_HEADERS = {
    "Editor-Version": os.environ.get("COPILOT_EDITOR_VERSION", "vscode/1.92.0"),
    "Editor-Plugin-Version": os.environ.get("COPILOT_EDITOR_PLUGIN_VERSION", "copilot-chat/0.20.0"),
    "Copilot-Integration-Id": os.environ.get("COPILOT_INTEGRATION_ID", "vscode-chat"),
    "User-Agent": os.environ.get("COPILOT_USER_AGENT", "GithubCopilot/1.155.0"),
}


def _load_copilot_source(path: Path) -> dict[str, Any] | None:
    """FileBackedCache loader for ``~/.config/copilot/tokens.json``.

    Normalizes whichever shape the on-disk file uses (oauth_token /
    refreshToken / access_token) into a single ``{"source": str}`` dict
    so the caller can branch on a stable key.
    """
    raw = read_json_file(path)
    if raw is None:
        return None
    tok = raw.get("oauth_token") or raw.get("refreshToken") or raw.get("access_token") or ""
    if isinstance(tok, str) and tok.strip():
        return {"source": tok.strip()}
    return None


_copilot_file_cache = FileBackedCache(COPILOT_TOKENS_PATH, _load_copilot_source)


def _read_plugin_source_token() -> str:
    """Return the github oauth_token from the VS Code / IntelliJ plugin
    config, or the empty string if no usable entry exists.

    apps.json layout:
        {"github.com:<appId>": {"oauth_token": "gho_...", "user": "...",
                                 "scopes": [...], ...}}
    Several github.com:* keys may exist (e.g. one per workspace); the
    first entry with a non-empty oauth_token wins.
    """
    for path in (COPILOT_PLUGIN_APPS, COPILOT_PLUGIN_HOSTS):
        if not path.exists():
            continue
        data = read_json_file(path)
        if data is None:
            _log.debug("Could not parse %s", path)
            continue
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            if "github.com" not in key:
                continue
            tok = entry.get("oauth_token") or entry.get("user_token") or ""
            if isinstance(tok, str) and tok.strip():
                return tok.strip()
    return ""


def _resolve_source_token() -> tuple[str, str]:
    """Return (token, kind) where kind is one of:
        "preminted" — token is already a Copilot API bearer (skip mint)
        "github"    — token is a long-lived github oauth (must mint)
    Raises AuthenticationError when nothing is configured.
    """
    pre = os.environ.get("COPILOT_ACCESS_TOKEN", "").strip()
    if pre:
        return pre, "preminted"
    refresh = os.environ.get("COPILOT_REFRESH_TOKEN", "").strip()
    if refresh:
        return refresh, "github"
    cached = _copilot_file_cache.get()
    if cached is not None:
        return cached["source"], "github"
    plugin_token = _read_plugin_source_token()
    if plugin_token:
        return plugin_token, "github"
    raise litellm.AuthenticationError(
        message=(
            "No GitHub Copilot credentials found. Set COPILOT_ACCESS_TOKEN "
            "(pre-minted bearer) or COPILOT_REFRESH_TOKEN (gho_/ghu_/ghr_), "
            "or run `gh auth login --scopes copilot` to populate "
            "~/.config/github-copilot/apps.json."
        ),
        model="copilot",
        llm_provider="copilot",
    )


# Cached state.
#   "copilot_token" — short-lived API bearer
#   "expires_at"    — unix seconds for copilot_token expiry
#   "endpoints"     — optional enterprise endpoint overrides
_token_cache: dict[str, Any] = {}


def _mint_copilot_token(github_token: str) -> dict[str, Any]:
    """Exchange a github oauth token for a short-lived Copilot bearer."""
    resp = _http_post(
        GITHUB_TOKEN_MINT_URL,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/json",
            **_COPILOT_EDITOR_HEADERS,
        },
        timeout=30,
    )
    if resp.status_code == 401:
        raise litellm.AuthenticationError(
            message=(
                "GitHub rejected the source token (401) — your "
                "subscription may have lapsed or the token was revoked. "
                f"Body: {resp.text[:200]}"
            ),
            model="copilot",
            llm_provider="copilot",
        )
    resp.raise_for_status()
    body = resp.json()
    return {
        "copilot_token": body["token"],
        "expires_at": int(body.get("expires_at", 0)),
        "endpoints": body.get("endpoints", {}),
    }


def get_copilot_access_token(force_refresh: bool = False) -> str:
    """Return a valid Copilot API bearer, minting / refreshing as needed."""
    if force_refresh:
        _token_cache.clear()
        _copilot_file_cache.invalidate()
    cached = _token_cache.get("copilot_token")
    expires_at = _token_cache.get("expires_at", 0)
    if (
        cached
        and not force_refresh
        and not is_timestamp_expired(expires_at, buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS)
    ):
        return cached

    source_token, kind = _resolve_source_token()
    if kind == "preminted":
        _token_cache["copilot_token"] = source_token
        _token_cache["expires_at"] = 0  # unknown; trust until 401
        return source_token

    minted = _mint_copilot_token(source_token)
    _token_cache.update(minted)
    return minted["copilot_token"]


def _api_base() -> str:
    """Resolve the Copilot chat API base URL.

    The mint response sometimes carries an ``endpoints.api`` override
    (e.g. enterprise tenants on a custom endpoint). Honor it when
    present; otherwise default to the public api.githubcopilot.com.
    """
    endpoints = _token_cache.get("endpoints") or {}
    if isinstance(endpoints, dict):
        url = endpoints.get("api") or ""
        if isinstance(url, str) and url.strip():
            return url.strip()
    return GITHUB_COPILOT_API_BASE


def _upstream_model_slug(model: str) -> str:
    """Translate a LiteLLM-side model id back to the Copilot model slug.

    Routes that reach this handler:

      - ``copilot/<slug>`` — passthrough for slugs that don't collide with
        LiteLLM's ``open_ai_chat_completion_models``.
      - ``copilot/oauth-<slug>`` — dynamic-config alias for slugs that
        would otherwise bypass to api.openai.com via main.py:2561. The
        ``oauth-`` sentinel is stripped here so api.githubcopilot.com
        receives the canonical model id.
    """
    slug = model.split("/", 1)[-1] if "/" in model else model
    if slug.startswith("oauth-"):
        slug = slug.removeprefix("oauth-")
    return slug


class CopilotHandler(CustomLLM):
    """Routes through GitHub Copilot subscription.

    Model names: copilot/gpt-5.5, copilot/claude-sonnet-4-6,
    copilot/gpt-5.4-mini, copilot/gpt-5.3-codex, etc. The slug after
    ``copilot/`` is forwarded verbatim to api.githubcopilot.com after
    the ``oauth-`` sentinel (if present) is stripped.
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
        actual_model = _upstream_model_slug(model)

        opts = optional_params or {}
        request_body: dict[str, Any] = {"model": actual_model, "messages": messages}

        if "temperature" in opts:
            request_body["temperature"] = opts["temperature"]
        if "max_tokens" in opts:
            request_body["max_tokens"] = opts["max_tokens"]
        if "top_p" in opts:
            request_body["top_p"] = opts["top_p"]
        if "stop" in opts:
            request_body["stop"] = opts["stop"]
        if opts.get("tools"):
            request_body["tools"] = opts["tools"]
        if opts.get("tool_choice"):
            request_body["tool_choice"] = opts["tool_choice"]

        def _send(force_refresh: bool) -> httpx.Response:
            access_token = get_copilot_access_token(force_refresh=force_refresh)
            req_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                **_COPILOT_EDITOR_HEADERS,
            }
            api_url = api_base or _api_base()
            return _http_post(
                f"{api_url}/chat/completions",
                json=request_body,
                headers=req_headers,
                timeout=timeout or 600,
            )

        resp = with_retry_on_401(_send)

        if resp.status_code == 401:
            # Bust both layers — source token may also be invalid.
            _token_cache.clear()
            raise litellm.AuthenticationError(
                message=(
                    "Copilot authentication was rejected. Run `gh auth login --scopes "
                    f"copilot` and retry. Underlying: {resp.text[:300]}"
                ),
                model=model,
                llm_provider="copilot",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"Copilot rate limit: {resp.text[:300]}",
                model=model,
                llm_provider="copilot",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Copilot API error: {resp.text[:300]}",
                model=model,
                llm_provider="copilot",
            )

        data = resp.json()
        return ModelResponse(
            id=data.get("id", f"copilot-{actual_model}"),
            model=actual_model,
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
        )

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        import asyncio
        import functools

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.completion, *args, **kwargs))

    def _response_to_chunks(self, response: ModelResponse) -> list[dict[str, Any]]:
        """Convert a ModelResponse into GenericStreamingChunk dicts.

        Mirrors ``claude_code_handler`` / ``codex_chatgpt_handler``: any
        streamed ``tool_calls`` are emitted as their own chunks and the
        upstream ``finish_reason`` is preserved instead of being hardcoded to
        ``"stop"`` (which previously dropped every tool call).
        """
        text = ""
        tool_calls_list: list[dict[str, Any]] = []
        finish_reason = "stop"

        if response.choices:
            choice = response.choices[0]
            msg = choice.message if hasattr(choice, "message") else choice.get("message", {})

            if isinstance(msg, dict):
                content = msg.get("content")
                raw_tool_calls = msg.get("tool_calls", []) or []
            else:
                content = getattr(msg, "content", None)
                raw_tool_calls = getattr(msg, "tool_calls", []) or []

            finish_reason = (
                choice.get("finish_reason", "stop")
                if isinstance(choice, dict)
                else getattr(choice, "finish_reason", "stop")
            )

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
        response = self.completion(*args, **kwargs)
        yield from self._response_to_chunks(response)

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        response = await self.acompletion(*args, **kwargs)
        for chunk in self._response_to_chunks(response):
            yield chunk


copilot_handler_instance = CopilotHandler()
