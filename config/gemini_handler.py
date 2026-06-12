"""LiteLLM custom handler for Google Gemini Advanced subscription.

Routes requests through Gemini's web backend using OAuth2 bearer tokens from
an authenticated Google One AI Premium subscriber. Enables Gemini 2.5 Pro/Flash
without API billing.

Token sources (checked in order):
  1. GEMINI_ACCESS_TOKEN env var (OAuth2 access token)
  2. ~/.config/gemini/tokens.json

Model names: gemini-sub/gemini-2.5-pro, gemini-sub/gemini-2.5-flash, etc.
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
    oauth_refresh_request,
    read_json_file,
    with_retry_on_401,
    write_json_atomic,
)

_log = logging.getLogger(__name__)

GEMINI_TOKENS_PATH = Path(
    os.environ.get(
        "GEMINI_TOKENS_PATH",
        os.path.expanduser("~/.config/gemini/tokens.json"),
    )
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com"


_gemini_file_cache = FileBackedCache(GEMINI_TOKENS_PATH, read_json_file)


def _load_tokens() -> dict[str, Any] | None:
    access_token = os.environ.get("GEMINI_ACCESS_TOKEN", "").strip()
    if access_token:
        return {"accessToken": access_token, "expiresAt": 0, "source": "env"}

    return _gemini_file_cache.get()


def _refresh_google_token(tokens: dict[str, Any]) -> dict[str, Any]:
    refresh_token = tokens.get("refreshToken")
    client_id = tokens.get("clientId", "")
    client_secret = tokens.get("clientSecret", "")

    if not refresh_token:
        raise litellm.AuthenticationError(
            message="Gemini token expired and no refresh_token available. Re-extract from browser.",
            model="gemini-sub",
            llm_provider="gemini-sub",
        )

    data = oauth_refresh_request(
        "https://oauth2.googleapis.com/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        json_body=False,
        timeout=30,
        provider_label="gemini-sub",
    )

    access_token = data.get("access_token")
    if not access_token or not isinstance(access_token, str):
        raise litellm.AuthenticationError(
            message=(
                "Google OAuth refresh response did not include an access_token — the "
                "refresh_token may be revoked or expired. Re-extract from browser."
            ),
            model="gemini-sub",
            llm_provider="gemini-sub",
        )
    try:
        expires_in = int(data.get("expires_in", 3600) or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    new_tokens = {
        **tokens,
        "accessToken": access_token,
        "expiresAt": int(time.time() + expires_in),
    }

    write_json_atomic(GEMINI_TOKENS_PATH, new_tokens)
    _gemini_file_cache.replace(new_tokens)
    return new_tokens


def get_gemini_access_token(force_refresh: bool = False) -> str:
    if force_refresh:
        _gemini_file_cache.invalidate()
    tokens = _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No Gemini subscription tokens found. Set GEMINI_ACCESS_TOKEN or "
                "create ~/.config/gemini/tokens.json"
            ),
            model="gemini-sub",
            llm_provider="gemini-sub",
        )

    expired = is_timestamp_expired(
        tokens.get("expiresAt"), buffer_seconds=DEFAULT_REFRESH_BUFFER_SECONDS
    )
    if (force_refresh or expired) and tokens.get("refreshToken"):
        tokens = _refresh_google_token(tokens)

    return tokens.get("accessToken", "")


def _map_finish_reason(reason: str | None) -> str:
    """Map a Gemini ``candidates[].finishReason`` to an OpenAI finish_reason.

    Hardcoding ``"stop"`` masked truncation (MAX_TOKENS) and safety stops
    (SAFETY / RECITATION), so callers could not tell a complete answer apart
    from a cut-off one.
    """
    return {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
    }.get(reason or "", "stop")


class GeminiSubHandler(CustomLLM):
    """Routes through Google Gemini with subscription OAuth.

    Model names: gemini-sub/gemini-2.5-pro, gemini-sub/gemini-2.5-flash
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

        # Gemini API uses generateContent endpoint with OAuth bearer
        gemini_messages = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content if isinstance(content, str) else str(content)
                continue

            gemini_role = "model" if role == "assistant" else "user"
            if isinstance(content, str):
                parts = [{"text": content}]
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append({"text": block["text"]})
                    elif isinstance(block, str):
                        parts.append({"text": block})
            else:
                parts = [{"text": str(content)}]

            gemini_messages.append({"role": gemini_role, "parts": parts})

        opts = optional_params or {}
        request_body: dict[str, Any] = {"contents": gemini_messages}

        generation_config: dict[str, Any] = {}
        if "temperature" in opts:
            generation_config["temperature"] = opts["temperature"]
        if "max_tokens" in opts:
            generation_config["maxOutputTokens"] = opts["max_tokens"]
        if "top_p" in opts:
            generation_config["topP"] = opts["top_p"]
        if generation_config:
            request_body["generationConfig"] = generation_config

        if system_instruction:
            request_body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{GEMINI_API_BASE}/v1beta/models/{actual_model}:generateContent"

        def _send(force_refresh: bool) -> httpx.Response:
            access_token = get_gemini_access_token(force_refresh=force_refresh)
            req_headers = {
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
            }
            return _http_post(url, json=request_body, headers=req_headers, timeout=timeout or 600)

        resp = with_retry_on_401(_send)

        if resp.status_code == 401:
            raise litellm.AuthenticationError(
                message=(
                    "Gemini Advanced authentication was rejected. "
                    f"Refresh GEMINI_ACCESS_TOKEN or update ~/.config/gemini/tokens.json. Underlying: {resp.text}"
                ),
                model=model,
                llm_provider="gemini-sub",
            )

        if resp.status_code == 429:
            raise litellm.RateLimitError(
                message=f"Gemini rate limit: {resp.text}",
                model=model,
                llm_provider="gemini-sub",
                response=httpx.Response(status_code=429),
            )

        if resp.status_code != 200:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Gemini API error: {resp.text}",
                model=model,
                llm_provider="gemini-sub",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise litellm.APIError(
                status_code=resp.status_code,
                message=f"Gemini returned a malformed (non-JSON) response: {resp.text[:300]}",
                model=model,
                llm_provider="gemini-sub",
            ) from exc
        if not isinstance(data, dict):
            raise litellm.APIError(
                status_code=resp.status_code,
                message="Gemini response JSON was not an object.",
                model=model,
                llm_provider="gemini-sub",
            )
        candidates = data.get("candidates", [])
        text = ""
        finish_reason = "stop"
        if candidates and isinstance(candidates[0], dict):
            cand = candidates[0]
            content = cand.get("content")
            parts = content.get("parts", []) if isinstance(content, dict) else []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            finish_reason = _map_finish_reason(cand.get("finishReason"))

        usage_meta = data.get("usageMetadata") or {}
        if not isinstance(usage_meta, dict):
            usage_meta = {}

        return ModelResponse(
            id=f"gemini-sub-{actual_model}-{int(time.time())}",
            model=actual_model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": finish_reason,
                }
            ],
            usage={
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            },
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


gemini_sub_handler_instance = GeminiSubHandler()
