"""LiteLLM custom handler for xAI SuperGrok subscription.

Routes requests through Grok's API using X Premium+ subscription tokens.
Enables Grok-3/Grok-3-mini access without xAI API billing.

Token sources (checked in order):
  1. GROK_ACCESS_TOKEN env var
  2. GROK_SESSION_TOKEN env var (X.com auth cookie)
  3. ~/.config/grok/tokens.json

Model names: grok-sub/grok-3, grok-sub/grok-3-mini, etc.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import litellm
from litellm import CustomLLM, ModelResponse
from oauth_token_store import (
    DEFAULT_REFRESH_BUFFER_SECONDS,
    FileBackedCache,
    is_timestamp_expired,
    read_json_file,
    with_retry_on_401,
    write_json_atomic,
)

_log = logging.getLogger(__name__)

GROK_TOKENS_PATH = Path(
    os.environ.get(
        "GROK_TOKENS_PATH",
        os.path.expanduser("~/.config/grok/tokens.json"),
    )
)

GROK_API_BASE = "https://api.x.ai"


_grok_file_cache = FileBackedCache(GROK_TOKENS_PATH, read_json_file)


def _load_tokens() -> dict[str, Any] | None:
    access_token = os.environ.get("GROK_ACCESS_TOKEN", "").strip()
    if access_token:
        return {"accessToken": access_token, "expiresAt": 0, "source": "env"}

    session_token = os.environ.get("GROK_SESSION_TOKEN", "").strip()
    if session_token:
        return {
            "sessionToken": session_token,
            "accessToken": None,
            "expiresAt": 0,
            "source": "session",
        }

    return _grok_file_cache.get()


def _exchange_session_for_access(session_token: str) -> dict[str, Any]:
    resp = httpx.get(
        "https://grok.x.ai/api/auth/session",
        cookies={"auth_token": session_token},
        headers={
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        },
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()

    access_token = data.get("accessToken") or data.get("token")
    if not access_token:
        raise litellm.AuthenticationError(
            message="Grok session exchange failed — no token in response. Re-extract from browser.",
            model="grok-sub",
            llm_provider="grok-sub",
        )

    tokens = {
        "accessToken": access_token,
        "sessionToken": session_token,
        "expiresAt": int(time.time()) + 3600,
        "source": "session_exchange",
    }

    write_json_atomic(GROK_TOKENS_PATH, tokens)
    _grok_file_cache.replace(tokens)
    return tokens


def get_grok_access_token(force_refresh: bool = False) -> str:
    if force_refresh:
        _grok_file_cache.invalidate()
    tokens = _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No Grok/SuperGrok tokens found. Set GROK_ACCESS_TOKEN or "
                "GROK_SESSION_TOKEN, or create ~/.config/grok/tokens.json"
            ),
            model="grok-sub",
            llm_provider="grok-sub",
        )

    if not tokens.get("accessToken") and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    expired = is_timestamp_expired(
        tokens.get("expiresAt"), buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS
    )
    if (force_refresh or expired) and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    return tokens.get("accessToken", "")


class GrokSubHandler(CustomLLM):
    """Routes through xAI SuperGrok subscription.

    Model names: grok-sub/grok-3, grok-sub/grok-3-mini
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
        actual_model = model.split("/", 1)[-1] if "/" in model else model

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

        api_url = api_base or GROK_API_BASE

        def _send(force_refresh: bool) -> httpx.Response:
            access_token = get_grok_access_token(force_refresh=force_refresh)
            req_headers = {
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "accept": "application/json",
            }
            return httpx.post(
                f"{api_url}/v1/chat/completions",
                json=request_body,
                headers=req_headers,
                timeout=timeout or 600,
            )

        resp = with_retry_on_401(_send)

        if resp.status_code == 401:
            _grok_file_cache.invalidate()
            raise litellm.AuthenticationError(
                message=(
                    "Grok authentication was rejected. Re-extract the GROK_SESSION_TOKEN "
                    f"cookie from grok.com. Underlying: {resp.text}"
                ),
                model=model,
                llm_provider="grok-sub",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"Grok rate limit: {resp.text}",
                model=model,
                llm_provider="grok-sub",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Grok API error: {resp.text}",
                model=model,
                llm_provider="grok-sub",
            )

        data = resp.json()
        return ModelResponse(
            id=data.get("id", f"grok-sub-{actual_model}"),
            model=actual_model,
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
        )

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        import asyncio
        import functools

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.completion, *args, **kwargs))

    def streaming(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        response = self.completion(*args, **kwargs)
        text = ""
        if response.choices:
            c = response.choices[0]
            msg = c.get("message", {}) if isinstance(c, dict) else getattr(c, "message", {})
            text = (
                msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            ) or ""
        usage = {
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        yield {
            "text": text,
            "is_finished": True,
            "finish_reason": "stop",
            "index": 0,
            "tool_use": None,
            "usage": usage,
        }

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        response = await self.acompletion(*args, **kwargs)
        text = ""
        if response.choices:
            c = response.choices[0]
            msg = c.get("message", {}) if isinstance(c, dict) else getattr(c, "message", {})
            text = (
                msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            ) or ""
        usage = {
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        yield {
            "text": text,
            "is_finished": True,
            "finish_reason": "stop",
            "index": 0,
            "tool_use": None,
            "usage": usage,
        }


grok_sub_handler_instance = GrokSubHandler()
