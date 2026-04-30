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

PERPLEXITY_TOKENS_PATH = Path(
    os.environ.get(
        "PERPLEXITY_TOKENS_PATH",
        os.path.expanduser("~/.config/perplexity/tokens.json"),
    )
)

PERPLEXITY_API_BASE = "https://api.perplexity.ai"
REFRESH_BUFFER_SECONDS = 5 * 60

_token_cache: dict[str, Any] = {}


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

    if PERPLEXITY_TOKENS_PATH.exists():
        try:
            return json.loads(PERPLEXITY_TOKENS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            _log.debug("Could not read token file")

    return None


def _exchange_session_for_access(session_token: str) -> dict[str, Any]:
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

    try:
        PERPLEXITY_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERPLEXITY_TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
        os.chmod(PERPLEXITY_TOKENS_PATH, 0o600)
    except OSError:
        _log.debug("Could not persist tokens to disk")

    return tokens


def _is_expired(tokens: dict[str, Any]) -> bool:
    expires_at = tokens.get("expiresAt", 0)
    if expires_at == 0:
        return False
    return time.time() + REFRESH_BUFFER_SECONDS >= expires_at


def get_access_token() -> str:
    tokens = _token_cache.get("token") or _load_tokens()
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

    if _is_expired(tokens) and tokens.get("sessionToken"):
        tokens = _exchange_session_for_access(tokens["sessionToken"])

    _token_cache["token"] = tokens
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
        access_token = get_access_token()
        actual_model = model.split("/", 1)[-1] if "/" in model else model

        req_headers = {
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
            "accept": "application/json",
        }

        opts = optional_params or {}
        request_body: dict[str, Any] = {"model": actual_model, "messages": messages}

        if "temperature" in opts:
            request_body["temperature"] = opts["temperature"]
        if "max_tokens" in opts:
            request_body["max_tokens"] = opts["max_tokens"]

        api_url = api_base or PERPLEXITY_API_BASE
        resp = httpx.post(
            f"{api_url}/chat/completions",
            json=request_body,
            headers=req_headers,
            timeout=timeout or 600,
        )

        if resp.status_code == 401:
            _token_cache.pop("token", None)
            raise litellm.AuthenticationError(
                message=f"Perplexity auth failed (401): {resp.text}",
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

        data = resp.json()
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
