"""Decepticon configuration — defaults + environment variable overrides.

LLM model assignments are defined in decepticon_core.types.llm (LLMModelMapping).
This config handles infrastructure settings: proxy connection.

Sandbox transport is HTTP-only and configured via SANDBOX_URL /
SANDBOX_TOKEN env vars consumed directly by
``decepticon.backends.factory.build_sandbox_backend`` — no schema field needed.

Credentials (which provider keys are present, in what priority) are detected
by ``decepticon.llm.factory._resolve_credentials`` directly from environment
variables (``ANTHROPIC_API_KEY`` etc., ``DECEPTICON_PROVIDER_PRIORITY``,
``DECEPTICON_AUTH_CLAUDE_CODE``) and so don't appear in this schema.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from decepticon_core.types.llm import ModelProfile


def _project_root() -> Path:
    """Project root (where docker-compose.yml lives)."""
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "docker-compose.yml").exists():
        return root
    return Path.cwd()


_LOCAL_PROXY_KEY = "sk-decepticon-master"  # nosemgrep: decepticon-no-hardcoded-default-key


class LLMConfig(BaseModel):
    """LLM proxy connection configuration.

    ``proxy_api_key`` defaults to the local-dev placeholder so the
    Decepticon Python package can be imported without setting any env
    var (module-level agent constructors build LLMs at import time).
    Production deployments override via DECEPTICON_LLM__PROXY_API_KEY.
    """

    proxy_url: str = "http://localhost:4000"
    proxy_api_key: str = _LOCAL_PROXY_KEY
    timeout: int = 120
    max_retries: int = 2


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


def load_config() -> DecepticonConfig:
    """Load config from code defaults + environment variable overrides."""
    return DecepticonConfig()
