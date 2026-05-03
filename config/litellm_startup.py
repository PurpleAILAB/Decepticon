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
from codex_handler import codex_handler_instance  # noqa: E402
from copilot_handler import copilot_handler_instance  # noqa: E402
from gemini_handler import gemini_sub_handler_instance  # noqa: E402
from grok_handler import grok_sub_handler_instance  # noqa: E402
from litellm import CustomLLM, ModelResponse  # noqa: E402
from perplexity_handler import perplexity_sub_handler_instance  # noqa: E402

# ── auth/ provider dispatcher ─────────────────────────────────────────
# The ``auth/`` namespace fans out to two underlying handlers:
#   - claude_code_handler  (auth/claude-*)
#   - codex_handler        (auth/gpt-*, auth/o1*, auth/o3*, auth/o4*,
#                           auth/codex-*, auth/chatgpt-*)
# This consolidation avoids the LiteLLM v1.82+ native ``chatgpt`` provider,
# which performs Codex device-code OAuth at proxy startup and would shadow
# a direct ``provider: "chatgpt"`` custom registration.

_CODEX_PREFIXES = ("gpt-", "o1", "o3", "o4", "codex-", "chatgpt-")


def _select_auth_handler(model: str) -> CustomLLM:
    slug = model.split("/", 1)[-1] if "/" in model else model
    slug_lower = slug.lower()
    if slug_lower.startswith("claude-"):
        return claude_code_handler_instance
    if slug_lower.startswith(_CODEX_PREFIXES):
        return codex_handler_instance
    raise litellm.BadRequestError(
        message=(
            f"auth/ provider: model slug {slug!r} did not match any known "
            "subscription handler. Supported prefixes: claude-*, gpt-*, "
            "o1*, o3*, o4*, codex-*, chatgpt-*."
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

print(
    "[decepticon] auth dispatcher (claude_code + codex) + 4 subscription handlers registered",
    flush=True,
)

# Start LiteLLM server with remaining CLI args
# run_server() uses Click which reads sys.argv
sys.argv[0] = "litellm"

from litellm import run_server  # noqa: E402

sys.exit(run_server())
