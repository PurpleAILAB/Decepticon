"""Decepticon configuration — defaults + environment variable overrides.

LLM model assignments are defined in decepticon.llm.models (LLMModelMapping).
This config handles infrastructure settings: proxy connection and Docker sandbox.

Credentials (which provider keys are present, in what priority) are detected
by ``decepticon.llm.factory._resolve_credentials`` directly from environment
variables (``ANTHROPIC_API_KEY`` etc., ``DECEPTICON_PROVIDER_PRIORITY``,
``DECEPTICON_AUTH_CLAUDE_CODE``) and so don't appear in this schema.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from decepticon.llm.models import ModelProfile


def _project_root() -> Path:
    """Project root (where docker-compose.yml lives)."""
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "docker-compose.yml").exists():
        return root
    return Path.cwd()


class LLMConfig(BaseModel):
    """LLM proxy connection configuration."""

    proxy_url: str = "http://localhost:4000"
    proxy_api_key: str = "sk-decepticon-master"
    timeout: int = 120
    max_retries: int = 2


class DockerConfig(BaseModel):
    """Docker sandbox configuration.

    Runtime tuning knobs for the tmux-backed bash tool can be overridden via
    nested env vars, e.g. ``DECEPTICON_DOCKER__POLL_INTERVAL=0.25``.
    """

    sandbox_container_name: str = "decepticon-sandbox"
    sandbox_image: str = "decepticon-sandbox:latest"
    network: str = "decepticon-net"

    # ── tmux session behavior ──
    poll_interval: float = Field(0.5, gt=0.0, description="Seconds between capture-pane polls")
    stall_seconds: float = Field(
        3.0, gt=0.0, description="Seconds of no screen change → treat as interactive prompt"
    )
    max_output_chars: int = Field(
        30_000, gt=0, description="Truncate command output larger than this"
    )
    auto_background_seconds: float = Field(
        60.0, gt=0.0, description="Auto-background a blocking command after this many seconds"
    )
    size_watchdog_chars: int = Field(
        5_000_000, gt=0, description="Force-kill commands producing more than this many chars"
    )
    size_watchdog_interval: float = Field(
        5.0, gt=0.0, description="Seconds between size watchdog checks"
    )


class DecepticonConfig(BaseSettings):
    """Root configuration.

    Set DECEPTICON_MODEL_PROFILE to switch tier presets:
      eco  — per-agent tier (production default)
      max  — every agent on HIGH (high-value targets)
      test — every agent on LOW (development / CI)

    Provider routing is driven by environment variables, not this schema:
      DECEPTICON_PROVIDER_PRIORITY  comma-separated provider order
                                    (default: anthropic,openai,google,minimax)
      DECEPTICON_AUTH_CLAUDE_CODE   "true" → route Anthropic via OAuth
      ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / MINIMAX_API_KEY
                                    detected by the LLM factory; placeholder
                                    values are ignored.
    """

    model_config = {"env_prefix": "DECEPTICON_", "env_nested_delimiter": "__"}

    debug: bool = False
    model_profile: ModelProfile = ModelProfile.ECO
    llm: LLMConfig = Field(default_factory=LLMConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)


def load_config() -> DecepticonConfig:
    """Load config from code defaults + environment variable overrides."""
    return DecepticonConfig()
