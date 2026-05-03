"""LiteLLM startup script — registers custom OAuth handlers before server start.

LiteLLM's YAML-based custom_provider_map registration is unreliable across
versions (litellm_settings may be skipped when database_url is configured).
This script registers handlers explicitly at module import time.

Usage in docker-compose.yml:
  command: ["python", "/app/litellm_startup.py", "--config", "/app/config.yaml", "--port", "4000"]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Register custom OAuth handler before LiteLLM processes the config
sys.path.insert(0, "/app")
from litellm_dynamic_config import collect_requested_models, write_dynamic_config  # noqa: E402
from ollama_probe import extract_ollama_models, has_ollama_route, probe  # noqa: E402


def _replace_config_arg() -> None:
    """Append env-requested model routes to the LiteLLM config before boot."""
    requested = collect_requested_models()
    if not requested:
        return

    config_path: str | None = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--config" and idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]
            generated = write_dynamic_config(
                config_path,
                "/tmp/decepticon-litellm/config.generated.yaml",
            )
            sys.argv[idx + 1] = str(generated)
            break
        if arg.startswith("--config="):
            config_path = arg.split("=", 1)[1]
            generated = write_dynamic_config(
                config_path,
                "/tmp/decepticon-litellm/config.generated.yaml",
            )
            sys.argv[idx] = f"--config={generated}"
            break

    if config_path is None:
        default_config = Path("/app/config.yaml")
        if default_config.exists():
            generated = write_dynamic_config(
                default_config,
                "/tmp/decepticon-litellm/config.generated.yaml",
            )
            sys.argv.extend(["--config", str(generated)])

    print(f"[decepticon] registered {len(requested)} dynamic model route(s)", flush=True)


_replace_config_arg()


def _probe_ollama_if_configured() -> None:
    """Best-effort Ollama reachability + tool-capability probe; never
    blocks proxy boot."""
    try:
        requested = collect_requested_models()
        if not has_ollama_route(requested):
            return
        models = extract_ollama_models(requested)
        base = os.environ.get("OLLAMA_API_BASE", "").strip()
        for line in probe(base, models):
            print(f"[decepticon ollama] {line}", flush=True)
    except Exception as exc:  # noqa: BLE001
        # Observability-only — never let a probe bug crash proxy boot.
        print(f"[decepticon ollama] probe failed unexpectedly: {exc}", flush=True)


_probe_ollama_if_configured()

from collections.abc import AsyncIterator, Iterator  # noqa: E402
from typing import Any  # noqa: E402

import litellm  # noqa: E402
from claude_code_handler import claude_code_handler_instance  # noqa: E402
from copilot_handler import copilot_handler_instance  # noqa: E402
from gemini_handler import gemini_sub_handler_instance  # noqa: E402
from grok_handler import grok_sub_handler_instance  # noqa: E402
from litellm import CustomLLM, ModelResponse  # noqa: E402
from perplexity_handler import perplexity_sub_handler_instance  # noqa: E402

# ── auth/ provider dispatcher ─────────────────────────────────────────
# The ``auth/`` namespace is reserved for custom OAuth handlers that do
# not have a suitable native LiteLLM provider. ChatGPT/Codex OAuth now uses
# LiteLLM's native ``chatgpt`` provider via model aliases in litellm.yaml.


def _select_auth_handler(model: str) -> CustomLLM:
    slug = model.split("/", 1)[-1] if "/" in model else model
    slug_lower = slug.lower()
    if slug_lower.startswith("claude-"):
        return claude_code_handler_instance
    raise litellm.BadRequestError(
        message=(
            f"auth/ provider: model slug {slug!r} did not match any known "
            "subscription handler. Supported prefixes: claude-*."
        ),
        model=model,
        llm_provider="auth",
    )


class _AuthDispatcher(CustomLLM):
    def completion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        model = kwargs.get("model") or (args[0] if args else "")
        return _select_auth_handler(model).completion(*args, **kwargs)

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        model = kwargs.get("model") or (args[0] if args else "")
        return await _select_auth_handler(model).acompletion(*args, **kwargs)

    def streaming(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        model = kwargs.get("model") or (args[0] if args else "")
        return _select_auth_handler(model).streaming(*args, **kwargs)

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        model = kwargs.get("model") or (args[0] if args else "")
        async for chunk in _select_auth_handler(model).astreaming(*args, **kwargs):
            yield chunk


_auth_dispatcher_instance = _AuthDispatcher()


litellm.custom_provider_map = [
    {"provider": "auth", "custom_handler": _auth_dispatcher_instance},
    {"provider": "gemini-sub", "custom_handler": gemini_sub_handler_instance},
    {"provider": "copilot", "custom_handler": copilot_handler_instance},
    {"provider": "grok-sub", "custom_handler": grok_sub_handler_instance},
    {"provider": "pplx-sub", "custom_handler": perplexity_sub_handler_instance},
]

from litellm.utils import custom_llm_setup  # noqa: E402

custom_llm_setup()


def _patch_chatgpt_responses_text_aggregation() -> None:
    """Work around ChatGPT Codex /responses SSE final payloads with empty output.

    As of 2026-05-03, LiteLLM's native ``chatgpt`` Responses transformer
    trusts the final ``response.completed`` payload. The Codex backend can
    instead stream all assistant text via ``response.output_text.delta`` while
    leaving ``response.output`` empty in the completed object. Downstream
    OpenAI-compatible clients (LangChain ChatOpenAI with ``use_responses_api``)
    then see a successful response with blank content.

    Aggregate text deltas and synthesize a standard Responses message when the
    upstream completed payload is empty. Keep the original transformer for all
    normal/error cases.

    Skipped entirely when DECEPTICON_AUTH_CHATGPT=false (or unset) to avoid
    importing the chatgpt provider module, which triggers a device-code
    OAuth prompt at startup even when ChatGPT is not configured.
    """
    chatgpt_enabled = os.environ.get("DECEPTICON_AUTH_CHATGPT", "false").strip().lower()
    if chatgpt_enabled not in ("true", "1", "yes"):
        print(
            "[decepticon] chatgpt responses patch skipped (DECEPTICON_AUTH_CHATGPT != true)",
            flush=True,
        )
        return

    try:
        import json

        from litellm.constants import STREAM_SSE_DONE_STRING
        from litellm.llms.chatgpt.responses.transformation import (
            ChatGPTResponsesAPIConfig,
        )
        from litellm.types.llms.openai import ResponsesAPIResponse
        from litellm.utils import CustomStreamWrapper
    except Exception as exc:  # pragma: no cover - startup resilience
        print(f"[decepticon] chatgpt responses patch skipped: {exc}", flush=True)
        return

    original = ChatGPTResponsesAPIConfig.transform_response_api_response
    original_request = ChatGPTResponsesAPIConfig.transform_responses_api_request

    def patched_request(  # type: ignore[no-untyped-def]
        self,
        model: str,
        input: Any,
        response_api_optional_request_params: dict,
        litellm_params: Any,
        headers: dict,
    ) -> dict:
        request = original_request(
            self,
            model=model,
            input=input,
            response_api_optional_request_params=response_api_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
        items = request.get("input")
        if not isinstance(items, list):
            return request

        system_parts: list[str] = []
        filtered: list[Any] = []
        for item in items:
            if not (isinstance(item, dict) and item.get("role") == "system"):
                filtered.append(item)
                continue
            content = item.get("content")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text") or part.get("content")
                        if isinstance(text, str):
                            system_parts.append(text)

        if system_parts:
            existing = request.get("instructions") or ""
            request["instructions"] = (
                "\n\n".join([existing, *system_parts]) if existing else "\n\n".join(system_parts)
            )
            request["input"] = filtered
        return request

    def patched(self, model: str, raw_response: Any, logging_obj: Any):  # type: ignore[no-untyped-def]
        response = original(self, model=model, raw_response=raw_response, logging_obj=logging_obj)
        try:
            if getattr(response, "output", None):
                return response
            body_text = raw_response.text or ""
            if "response.output_text.delta" not in body_text:
                return response

            text_parts: list[str] = []
            for chunk in body_text.splitlines():
                stripped = CustomStreamWrapper._strip_sse_data_from_chunk(chunk)
                if not stripped:
                    continue
                stripped = stripped.strip()
                if not stripped or stripped == STREAM_SSE_DONE_STRING:
                    continue
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        text_parts.append(delta)

            text = "".join(text_parts)
            if not text:
                return response

            payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            payload["output"] = [
                {
                    "id": "msg_decepticon_aggregated",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                            "annotations": [],
                        }
                    ],
                }
            ]
            return ResponsesAPIResponse.model_construct(**payload)
        except Exception:
            return response

    ChatGPTResponsesAPIConfig.transform_responses_api_request = patched_request
    ChatGPTResponsesAPIConfig.transform_response_api_response = patched
    print("[decepticon] patched chatgpt responses text aggregation", flush=True)


_patch_chatgpt_responses_text_aggregation()

print(
    "[decepticon] auth dispatcher (claude_code) + 4 subscription handlers registered",
    flush=True,
)

# Start LiteLLM server with remaining CLI args
# run_server() uses Click which reads sys.argv
sys.argv[0] = "litellm"

from litellm import run_server  # noqa: E402

sys.exit(run_server())
