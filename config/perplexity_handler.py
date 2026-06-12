"""LiteLLM custom handler for Perplexity Pro subscription.

Routes requests through Perplexity's API using Pro subscription session tokens.
Enables Sonar Pro access without Perplexity API billing.

Token sources (checked in order):
  1. PERPLEXITY_SESSION_TOKEN env var (session cookie from perplexity.ai)
  2. PERPLEXITY_ACCESS_TOKEN env var (pre-extracted Bearer token)
  3. ~/.config/perplexity/tokens.json

Model names: pplx-sub/sonar-pro, pplx-sub/sonar, etc.
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
from http_client import post as _http_post
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

PERPLEXITY_TOKENS_PATH = Path(
    os.environ.get(
        "PERPLEXITY_TOKENS_PATH",
        os.path.expanduser("~/.config/perplexity/tokens.json"),
    )
)

PERPLEXITY_API_BASE = "https://api.perplexity.ai"


_pplx_file_cache = FileBackedCache(PERPLEXITY_TOKENS_PATH, read_json_file)


def _load_tokens() -> dict[str, Any] | None:
    access_token = os.environ.get("PERPLEXITY_ACCESS_TOKEN", "").strip()
    if access_token:
        return {"accessToken": access_token, "expiresAt": 0, "source": "env"}

    session_token = os.environ.get("PERPLEXITY_SESSION_TOKEN", "").strip()
    if session_token:
        return {
            "sessionToken": session_token,
            "accessToken": None,
            "expiresAt": 0,
            "source": "session",
        }

    return _pplx_file_cache.get()


def _exchange_session_for_access(session_token: str) -> dict[str, Any]:
    try:
        resp = httpx.get(
            "https://www.perplexity.ai/api/auth/session",
            cookies={"next-auth.session-token": session_token},
            headers={
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise litellm.AuthenticationError(
            message=(
                f"Perplexity session exchange was rejected (HTTP {exc.response.status_code}) — "
                "the PERPLEXITY_SESSION_TOKEN cookie is expired or invalid. Re-extract it from the browser."
            ),
            model="pplx-sub",
            llm_provider="pplx-sub",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise litellm.AuthenticationError(
            message=f"Perplexity session exchange failed: {exc}. Re-extract the cookie from the browser.",
            model="pplx-sub",
            llm_provider="pplx-sub",
        ) from exc

    if not isinstance(data, dict):
        raise litellm.AuthenticationError(
            message="Perplexity session exchange returned an unexpected response shape. Re-extract from browser.",
            model="pplx-sub",
            llm_provider="pplx-sub",
        )

    access_token = data.get("accessToken") or data.get("token")
    if not access_token:
        raise litellm.AuthenticationError(
            message="Perplexity session exchange failed. Re-extract cookie from browser.",
            model="pplx-sub",
            llm_provider="pplx-sub",
        )

    tokens = {
        "accessToken": access_token,
        "sessionToken": session_token,
        "expiresAt": int(time.time()) + 3600,
        "source": "session_exchange",
    }

    write_json_atomic(PERPLEXITY_TOKENS_PATH, tokens)
    _pplx_file_cache.replace(tokens)
    return tokens


def get_perplexity_access_token(force_refresh: bool = False) -> str:
    if force_refresh:
        _pplx_file_cache.invalidate()
    tokens = _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No Perplexity Pro tokens found. Set PERPLEXITY_ACCESS_TOKEN or "
                "PERPLEXITY_SESSION_TOKEN, or create ~/.config/perplexity/tokens.json"
            ),
            model="pplx-sub",
            llm_provider="pplx-sub",
        )

    if not tokens.get("accessToken") and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    expired = is_timestamp_expired(
        tokens.get("expiresAt"), buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS
    )
    if (force_refresh or expired) and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    return tokens.get("accessToken", "")


class PerplexitySubHandler(CustomLLM):
    """Routes through Perplexity Pro subscription.

    Model names: pplx-sub/sonar-pro, pplx-sub/sonar
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

        api_url = api_base or PERPLEXITY_API_BASE

        def _send(force_refresh: bool) -> httpx.Response:
            access_token = get_perplexity_access_token(force_refresh=force_refresh)
            req_headers = {
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "accept": "application/json",
            }
            return _http_post(
                f"{api_url}/chat/completions",
                json=request_body,
                headers=req_headers,
                timeout=timeout or 600,
            )

        resp = with_retry_on_401(_send)

        if resp.status_code == 401:
            _pplx_file_cache.invalidate()
            raise litellm.AuthenticationError(
                message=(
                    "Perplexity Pro authentication was rejected. Re-extract the "
                    f"PERPLEXITY_SESSION_TOKEN cookie. Underlying: {resp.text}"
                ),
                model=model,
                llm_provider="pplx-sub",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"Perplexity rate limit: {resp.text}",
                model=model,
                llm_provider="pplx-sub",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Perplexity API error: {resp.text}",
                model=model,
                llm_provider="pplx-sub",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Perplexity returned a malformed (non-JSON) response: {resp.text[:300]}",
                model=model,
                llm_provider="pplx-sub",
            ) from exc
        if not isinstance(data, dict):
            raise litellm.APIError(
                status_code=resp.status_code,
                message="Perplexity response JSON was not an object.",
                model=model,
                llm_provider="pplx-sub",
            )
        return ModelResponse(
            id=data.get("id", f"pplx-sub-{actual_model}"),
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


perplexity_sub_handler_instance = PerplexitySubHandler()
