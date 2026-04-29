"""LiteLLM custom handler for Microsoft Copilot Pro subscription.

Routes requests through the Copilot API using Microsoft account OAuth tokens.
Enables GPT-4o/o1 access via Copilot Pro ($20/mo) without OpenAI API billing.

Token sources (checked in order):
  1. COPILOT_ACCESS_TOKEN env var
  2. COPILOT_REFRESH_TOKEN env var (auto-refreshes via Microsoft OAuth)
  3. ~/.config/copilot/tokens.json

Model names: copilot/gpt-4o, copilot/o1, copilot/o3-mini, etc.
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

COPILOT_TOKENS_PATH = Path(
    os.environ.get(
        "COPILOT_TOKENS_PATH",
        os.path.expanduser("~/.config/copilot/tokens.json"),
    )
)

MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
COPILOT_API_BASE = "https://api.copilot.microsoft.com"
REFRESH_BUFFER_SECONDS = 5 * 60

_token_cache: dict[str, Any] = {}


def _load_tokens() -> dict[str, Any] | None:
    access_token = os.environ.get("COPILOT_ACCESS_TOKEN", "").strip()
    if access_token:
        return {"accessToken": access_token, "expiresAt": 0, "source": "env"}

    refresh_token = os.environ.get("COPILOT_REFRESH_TOKEN", "").strip()
    if refresh_token:
        return {
            "refreshToken": refresh_token,
            "accessToken": None,
            "expiresAt": 0,
            "source": "env_refresh",
        }

    if COPILOT_TOKENS_PATH.exists():
        try:
            return json.loads(COPILOT_TOKENS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            _log.debug("Could not read token file")

    return None


def _is_expired(tokens: dict[str, Any]) -> bool:
    expires_at = tokens.get("expiresAt", 0)
    if expires_at == 0:
        return False
    return time.time() + REFRESH_BUFFER_SECONDS >= expires_at


def _refresh_ms_token(tokens: dict[str, Any]) -> dict[str, Any]:
    refresh_token = tokens.get("refreshToken")
    if not refresh_token:
        raise litellm.AuthenticationError(
            message="Copilot token expired and no refresh_token available.",
            model="copilot",
            llm_provider="copilot",
        )

    client_id = tokens.get("clientId", os.environ.get("COPILOT_CLIENT_ID", ""))
    resp = httpx.post(
        MS_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "scope": "openid profile offline_access",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    new_tokens = {
        **tokens,
        "accessToken": data["access_token"],
        "refreshToken": data.get("refresh_token", refresh_token),
        "expiresAt": int(time.time() + data.get("expires_in", 3600)),
    }

    try:
        COPILOT_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
        COPILOT_TOKENS_PATH.write_text(json.dumps(new_tokens, indent=2))
        os.chmod(COPILOT_TOKENS_PATH, 0o600)
    except OSError:
        _log.debug("Could not persist tokens to disk")

    return new_tokens


def get_access_token() -> str:
    tokens = _token_cache.get("token") or _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No Copilot Pro tokens found. Set COPILOT_ACCESS_TOKEN or "
                "COPILOT_REFRESH_TOKEN, or create ~/.config/copilot/tokens.json"
            ),
            model="copilot",
            llm_provider="copilot",
        )

    if not tokens.get("accessToken") and tokens.get("refreshToken"):
        tokens = _refresh_ms_token(tokens)

    if _is_expired(tokens) and tokens.get("refreshToken"):
        tokens = _refresh_ms_token(tokens)

    _token_cache["token"] = tokens
    return tokens.get("accessToken", "")


class CopilotHandler(CustomLLM):
    """Routes through Microsoft Copilot Pro subscription.

    Model names: copilot/gpt-4o, copilot/o1, copilot/o3-mini
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
        if "top_p" in opts:
            request_body["top_p"] = opts["top_p"]
        if "stop" in opts:
            request_body["stop"] = opts["stop"]
        if opts.get("tools"):
            request_body["tools"] = opts["tools"]
        if opts.get("tool_choice"):
            request_body["tool_choice"] = opts["tool_choice"]

        api_url = api_base or COPILOT_API_BASE
        resp = httpx.post(
            f"{api_url}/v1/chat/completions",
            json=request_body,
            headers=req_headers,
            timeout=timeout or 600,
        )

        if resp.status_code == 401:
            _token_cache.pop("token", None)
            raise litellm.AuthenticationError(
                message=f"Copilot auth failed (401): {resp.text}",
                model=model,
                llm_provider="copilot",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"Copilot rate limit: {resp.text}",
                model=model,
                llm_provider="copilot",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Copilot API error: {resp.text}",
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


copilot_handler_instance = CopilotHandler()
