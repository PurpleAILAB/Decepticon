"""LiteLLM custom handler for Google Gemini Advanced subscription.

Routes requests through Gemini's web backend using session cookies from an
authenticated Google One AI Premium subscriber. Enables Gemini 2.5 Pro/Flash
without API billing.

Token sources (checked in order):
  1. GEMINI_ACCESS_TOKEN env var (OAuth2 access token)
  2. GEMINI_SESSION_COOKIES env var (JSON-encoded cookie dict)
  3. ~/.config/gemini/tokens.json

Model names: gemini-sub/gemini-2.5-pro, gemini-sub/gemini-2.5-flash, etc.
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

GEMINI_TOKENS_PATH = Path(
    os.environ.get(
        "GEMINI_TOKENS_PATH",
        os.path.expanduser("~/.config/gemini/tokens.json"),
    )
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
REFRESH_BUFFER_SECONDS = 5 * 60

_token_cache: dict[str, Any] = {}


def _load_tokens() -> dict[str, Any] | None:
    access_token = os.environ.get("GEMINI_ACCESS_TOKEN", "").strip()
    if access_token:
        return {"accessToken": access_token, "expiresAt": 0, "source": "env"}

    cookies_json = os.environ.get("GEMINI_SESSION_COOKIES", "").strip()
    if cookies_json:
        try:
            cookies = json.loads(cookies_json)
            if isinstance(cookies, dict):
                return {"cookies": cookies, "source": "env_cookies"}
        except json.JSONDecodeError:
            _log.debug("Malformed GEMINI_SESSION_COOKIES JSON")

    if GEMINI_TOKENS_PATH.exists():
        try:
            return json.loads(GEMINI_TOKENS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            _log.debug("Could not read token file")

    return None


def _is_expired(tokens: dict[str, Any]) -> bool:
    expires_at = tokens.get("expiresAt", 0)
    if expires_at == 0:
        return False
    return time.time() + REFRESH_BUFFER_SECONDS >= expires_at


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

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    new_tokens = {
        **tokens,
        "accessToken": data["access_token"],
        "expiresAt": int(time.time() + data.get("expires_in", 3600)),
    }

    try:
        GEMINI_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GEMINI_TOKENS_PATH.write_text(json.dumps(new_tokens, indent=2))
        os.chmod(GEMINI_TOKENS_PATH, 0o600)
    except OSError:
        _log.debug("Could not persist tokens to disk")

    return new_tokens


def get_access_token() -> str:
    tokens = _token_cache.get("token") or _load_tokens()
    if tokens is None:
        raise litellm.AuthenticationError(
            message=(
                "No Gemini subscription tokens found. Set GEMINI_ACCESS_TOKEN or "
                "create ~/.config/gemini/tokens.json"
            ),
            model="gemini-sub",
            llm_provider="gemini-sub",
        )

    if _is_expired(tokens) and tokens.get("refreshToken"):
        tokens = _refresh_google_token(tokens)

    _token_cache["token"] = tokens
    return tokens.get("accessToken", "")


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
        access_token = get_access_token()
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

        req_headers = {
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        }

        url = f"{GEMINI_API_BASE}/v1beta/models/{actual_model}:generateContent"
        resp = httpx.post(url, json=request_body, headers=req_headers, timeout=timeout or 600)

        if resp.status_code == 401:
            _token_cache.pop("token", None)
            raise litellm.AuthenticationError(
                message=f"Gemini auth failed (401): {resp.text}",
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

        data = resp.json()
        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})

        return ModelResponse(
            id=f"gemini-sub-{actual_model}-{int(time.time())}",
            model=actual_model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
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
