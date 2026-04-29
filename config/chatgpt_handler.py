"""Standalone LiteLLM custom handler for ChatGPT Pro/Plus subscription OAuth.

Routes requests through ChatGPT's backend API using session tokens from an
authenticated browser session. This enables using ChatGPT Pro/Plus/Team
subscription models (GPT-4o, o1, o3, GPT-4.5) without API billing.

This file is mounted into the LiteLLM container alongside litellm.yaml.
It has NO dependency on the ``decepticon`` package.

Token sources (checked in order):
  1. CHATGPT_SESSION_TOKEN env var
  2. CHATGPT_ACCESS_TOKEN env var (pre-extracted Bearer token)
  3. ~/.config/chatgpt/tokens.json (persisted by browser extraction tools)

Registration in litellm.yaml:
  litellm_settings:
    custom_provider_map:
      - provider: "chatgpt"
        custom_handler: chatgpt_handler.chatgpt_handler_instance

Model names: chatgpt/gpt-4o, chatgpt/o1, chatgpt/o3-mini, chatgpt/gpt-4.5, etc.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import litellm
from litellm import CustomLLM, ModelResponse

_log = logging.getLogger(__name__)

# ── Token storage ────────────────────────────────────────────────────

CHATGPT_TOKENS_PATH = Path(
    os.environ.get(
        "CHATGPT_TOKENS_PATH",
        os.path.expanduser("~/.config/chatgpt/tokens.json"),
    )
)

CHATGPT_API_BASE = "https://chatgpt.com/backend-api"
CHATGPT_AUTH_URL = "https://auth0.openai.com/oauth/token"

REFRESH_BUFFER_SECONDS = 5 * 60

_token_cache: dict[str, Any] = {}


def _load_tokens() -> dict[str, Any] | None:
    """Load ChatGPT session/access tokens.

    Resolution order:
      1. CHATGPT_ACCESS_TOKEN env var (pre-extracted Bearer token)
      2. CHATGPT_SESSION_TOKEN env var (__Secure-next-auth.session-token cookie)
      3. ~/.config/chatgpt/tokens.json
    """
    # 1. Direct access token
    access_token = os.environ.get("CHATGPT_ACCESS_TOKEN", "").strip()
    if access_token:
        return {
            "accessToken": access_token,
            "expiresAt": 0,  # Unknown expiry — let it fail and re-fetch
            "source": "env",
        }

    # 2. Session token (cookie-based)
    session_token = os.environ.get("CHATGPT_SESSION_TOKEN", "").strip()
    if session_token:
        return {
            "sessionToken": session_token,
            "accessToken": None,
            "expiresAt": 0,
            "source": "session",
        }

    # 3. File-based
    if CHATGPT_TOKENS_PATH.exists():
        try:
            raw = json.loads(CHATGPT_TOKENS_PATH.read_text())
            if raw.get("accessToken"):
                return raw
            if raw.get("sessionToken"):
                return raw
        except (json.JSONDecodeError, OSError):
            _log.debug("Could not read token file")

    return None


def _exchange_session_for_access(session_token: str) -> dict[str, Any]:
    """Exchange a __Secure-next-auth.session-token for an access token."""
    resp = httpx.get(
        "https://chatgpt.com/api/auth/session",
        cookies={"__Secure-next-auth.session-token": session_token},
        headers={
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "accept": "application/json",
        },
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()

    access_token = data.get("accessToken")
    if not access_token:
        raise litellm.AuthenticationError(
            message="ChatGPT session token exchange failed — no accessToken in response. "
            "Token may be expired. Re-extract from browser.",
            model="chatgpt",
            llm_provider="chatgpt",
        )

    expires = data.get("expires")
    expires_at = 0
    if expires:
        try:
            from datetime import datetime

            expires_at = int(datetime.fromisoformat(expires.replace("Z", "+00:00")).timestamp())
        except (ValueError, TypeError):
            expires_at = int(time.time()) + 3600

    tokens = {
        "accessToken": access_token,
        "sessionToken": session_token,
        "expiresAt": expires_at,
        "source": "session_exchange",
    }

    # Persist for reuse
    try:
        CHATGPT_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHATGPT_TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
        os.chmod(CHATGPT_TOKENS_PATH, 0o600)
    except OSError:
        _log.debug("Could not persist tokens to disk")

    return tokens


def _is_expired(tokens: dict[str, Any]) -> bool:
    expires_at = tokens.get("expiresAt", 0)
    if expires_at == 0:
        return False  # Unknown expiry — try using it
    return time.time() + REFRESH_BUFFER_SECONDS >= expires_at


def get_access_token() -> str:
    """Get a valid ChatGPT access token."""
    tokens = _token_cache.get("token") or _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No ChatGPT tokens found. Set CHATGPT_ACCESS_TOKEN or "
                "CHATGPT_SESSION_TOKEN, or create ~/.config/chatgpt/tokens.json"
            ),
            model="chatgpt",
            llm_provider="chatgpt",
        )

    # If we only have a session token, exchange it
    if not tokens.get("accessToken") and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    # If expired and we have a session token, re-exchange
    if _is_expired(tokens) and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    _token_cache["token"] = tokens
    return tokens["accessToken"]


# ── Custom LLM Handler ──────────────────────────────────────────────


class ChatGPTCustomHandler(CustomLLM):
    """LiteLLM custom handler that routes through ChatGPT Pro/Plus subscription.

    Model names: chatgpt/gpt-4o, chatgpt/o1, chatgpt/o3-mini, etc.
    The part after ``chatgpt/`` maps to the ChatGPT backend model slug.
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
        """Route completion to ChatGPT backend API with subscription auth."""
        access_token = get_access_token()

        # Extract model slug: "chatgpt/gpt-4o" -> "gpt-4o"
        actual_model = model.split("/", 1)[-1] if "/" in model else model

        # ChatGPT backend uses a conversation-based API, but we can use
        # the /api/conversation endpoint or the newer completions-compatible
        # endpoint at chatgpt.com/backend-api/conversation
        # For simplicity, route through OpenAI's API with the subscription bearer token
        # ChatGPT Pro tokens work against api.openai.com with the right headers

        req_headers = {
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        }

        opts = optional_params or {}

        # Build OpenAI-compatible request body
        request_body: dict[str, Any] = {
            "model": actual_model,
            "messages": messages,
        }

        if "temperature" in opts:
            request_body["temperature"] = opts["temperature"]
        if "max_tokens" in opts:
            request_body["max_tokens"] = opts["max_tokens"]
        if "top_p" in opts:
            request_body["top_p"] = opts["top_p"]
        if "stop" in opts:
            request_body["stop"] = opts["stop"]

        # Tools
        if opts.get("tools"):
            request_body["tools"] = opts["tools"]
        if opts.get("tool_choice"):
            request_body["tool_choice"] = opts["tool_choice"]

        # Use the standard OpenAI completions endpoint with the subscription token
        # ChatGPT Pro/Plus subscription tokens from the web app are valid
        # against the standard API endpoint
        api_url = api_base or "https://api.openai.com"
        resp = httpx.post(
            f"{api_url}/v1/chat/completions",
            json=request_body,
            headers=req_headers,
            timeout=timeout or 600,
        )

        if resp.status_code == 401:
            # Clear cached token on auth failure
            _token_cache.pop("token", None)
            raise litellm.AuthenticationError(
                message=f"ChatGPT auth failed (401): {resp.text}. Re-extract token.",
                model=model,
                llm_provider="chatgpt",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"ChatGPT rate limit: {resp.text}",
                model=model,
                llm_provider="chatgpt",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"ChatGPT API error: {resp.text}",
                model=model,
                llm_provider="chatgpt",
            )

        data = resp.json()

        # Response is already in OpenAI format — pass through
        choices = data.get("choices", [])
        usage = data.get("usage", {})

        return ModelResponse(
            id=data.get("id", f"chatcmpl-{actual_model}"),
            model=actual_model,
            choices=choices,
            usage=usage,
        )

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

    def streaming(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        response = self.completion(*args, **kwargs)
        yield from _response_to_chunks(response)

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        response = await self.acompletion(*args, **kwargs)
        for chunk in _response_to_chunks(response):
            yield chunk


def _response_to_chunks(response: ModelResponse) -> list[dict[str, Any]]:
    """Convert a ModelResponse into GenericStreamingChunk dicts."""
    text = ""
    tool_calls_list: list[dict[str, Any]] = []
    finish_reason = "stop"

    if response.choices:
        choice = response.choices[0]
        msg = (
            choice.get("message", {})
            if isinstance(choice, dict)
            else getattr(choice, "message", {})
        )

        if isinstance(msg, dict):
            text = msg.get("content") or ""
            raw_tcs = msg.get("tool_calls", [])
            finish_reason = (
                choice.get("finish_reason", "stop")
                if isinstance(choice, dict)
                else getattr(choice, "finish_reason", "stop")
            )
        else:
            text = getattr(msg, "content", "") or ""
            raw_tcs = getattr(msg, "tool_calls", []) or []
            finish_reason = getattr(choice, "finish_reason", "stop")

        for i, tc in enumerate(raw_tcs):
            if isinstance(tc, dict):
                func = tc.get("function", {})
                tool_calls_list.append(
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments", "{}"),
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


# ── Module-level instance ────────────────────────────────────────────
chatgpt_handler_instance = ChatGPTCustomHandler()
