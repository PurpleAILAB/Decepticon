"""LiteLLM startup script — registers custom OAuth handlers before server start.

LiteLLM's YAML-based custom_provider_map registration is unreliable across
versions (litellm_settings may be skipped when database_url is configured).
This script registers handlers explicitly at module import time.

Usage in docker-compose.yml:
  command: ["python", "/app/litellm_startup.py", "--config", "/app/config.yaml", "--port", "4000"]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Register custom OAuth handler before LiteLLM processes the config
sys.path.insert(0, "/app")
from litellm_dynamic_config import collect_requested_models, write_dynamic_config  # noqa: E402


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

import litellm  # noqa: E402
from chatgpt_handler import chatgpt_handler_instance  # noqa: E402
from claude_code_handler import claude_code_handler_instance  # noqa: E402
from copilot_handler import copilot_handler_instance  # noqa: E402
from gemini_handler import gemini_sub_handler_instance  # noqa: E402
from grok_handler import grok_sub_handler_instance  # noqa: E402
from perplexity_handler import perplexity_sub_handler_instance  # noqa: E402

litellm.custom_provider_map = [
    {"provider": "auth", "custom_handler": claude_code_handler_instance},
    {"provider": "chatgpt", "custom_handler": chatgpt_handler_instance},
    {"provider": "gemini-sub", "custom_handler": gemini_sub_handler_instance},
    {"provider": "copilot", "custom_handler": copilot_handler_instance},
    {"provider": "grok-sub", "custom_handler": grok_sub_handler_instance},
    {"provider": "pplx-sub", "custom_handler": perplexity_sub_handler_instance},
]

from litellm.utils import custom_llm_setup  # noqa: E402

custom_llm_setup()

print("[decepticon] 6 subscription handlers registered", flush=True)

# Start LiteLLM server with remaining CLI args
# run_server() uses Click which reads sys.argv
sys.argv[0] = "litellm"

from litellm import run_server  # noqa: E402

sys.exit(run_server())
