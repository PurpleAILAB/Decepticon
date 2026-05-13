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
from litellm_dynamic_config import (  # noqa: E402
    collect_requested_models,
    has_subscription_routes,
    write_dynamic_config,
)
from ollama_probe import extract_ollama_models, has_ollama_route, probe  # noqa: E402


def _replace_config_arg() -> None:
    """Append env-requested model routes to the LiteLLM config before boot.

    Also injects subscription OAuth routes (auth/gpt-*) when the
    corresponding ``DECEPTICON_AUTH_*`` flag is enabled, even if no
    ``DECEPTICON_MODEL*`` override is set. Without this second branch a
    user who only enabled ChatGPT subscription auth would never see
    ``auth/gpt-*`` registered and every request would 400.
    """
    requested = collect_requested_models()
    needs_subscription = has_subscription_routes()
    if not requested and not needs_subscription:
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

    parts: list[str] = []
    if requested:
        parts.append(f"{len(requested)} model override(s)")
    if needs_subscription:
        parts.append("subscription OAuth route(s)")
    print(f"[decepticon] registered dynamic config: {', '.join(parts)}", flush=True)


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

import litellm  # noqa: E402
from auth_handler import auth_handler_instance  # noqa: E402
from codex_chatgpt_handler import codex_chatgpt_handler_instance  # noqa: E402
from copilot_handler import copilot_handler_instance  # noqa: E402
from gemini_handler import gemini_sub_handler_instance  # noqa: E402
from grok_handler import grok_sub_handler_instance  # noqa: E402
from perplexity_handler import perplexity_sub_handler_instance  # noqa: E402

# ── Custom provider registration ─────────────────────────────────────
# The ``auth/`` namespace dispatches to per-provider OAuth handlers via
# ``auth_handler.AuthDispatcher`` (currently used for ``claude-*`` only).
#
# Slug-collision rule: whenever a subscription slug matches a name in
# ``litellm.open_ai_chat_completion_models``, ``litellm_dynamic_config``
# aliases the internal model id with an ``oauth-`` sentinel and the
# matching handler strips it before forwarding upstream. Without the
# sentinel LiteLLM's ``main.py:2561`` short-circuit (``model in
# open_ai_chat_completion_models``) fires BEFORE the custom-provider
# dispatch and forwards to api.openai.com regardless of provider name.
# Currently affected:
#   - ChatGPT Codex (auth/gpt-5.5/5.4/5.4-mini/5.3-codex) →
#       codex-oauth/oauth-gpt-<slug>
#   - Copilot opt-in (copilot/gpt-5.3-codex) → copilot/oauth-gpt-5.3-codex
# Default Copilot tier picks (gpt-5.5, claude-sonnet-4-6, gpt-5.4-mini)
# and all other subscription routes (claude-*, gemini-2.5-*, grok-4.*,
# sonar*) use slugs that do NOT collide with open_ai_chat_completion_models
# and pass through their providers directly with no aliasing.

litellm.custom_provider_map = [
    {"provider": "auth", "custom_handler": auth_handler_instance},
    {"provider": "codex-oauth", "custom_handler": codex_chatgpt_handler_instance},
    {"provider": "gemini-sub", "custom_handler": gemini_sub_handler_instance},
    {"provider": "copilot", "custom_handler": copilot_handler_instance},
    {"provider": "grok-sub", "custom_handler": grok_sub_handler_instance},
    {"provider": "pplx-sub", "custom_handler": perplexity_sub_handler_instance},
]

from litellm.utils import custom_llm_setup  # noqa: E402

custom_llm_setup()


print(
    "[decepticon] auth dispatcher (claude_code, codex_chatgpt) + "
    "4 subscription handlers registered",
    flush=True,
)

# Start LiteLLM server with remaining CLI args
# run_server() uses Click which reads sys.argv
sys.argv[0] = "litellm"

from litellm import run_server  # noqa: E402

sys.exit(run_server())
