"""Unit tests for the LiteLLM Claude Code custom handler.

The module under test lives at ``config/claude_code_handler.py`` and is
mounted into the LiteLLM container — it is not part of the ``decepticon``
package, so we import it via ``importlib.util.spec_from_file_location``
the same way ``test_oauth_token_store.py`` does.

These tests focus on ``_env_override_tokens`` — the synthetic-credentials
path that lets users bypass the file-based refresh flow (and the
host-Claude-Code refresh race) by providing a long-lived OAuth token
via env var.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# ``claude_code_handler`` imports ``litellm`` at module level. The dev test
# env does not install LiteLLM (it's a runtime container dep), so we inject
# a minimal stub before loading the module. Mirror the approach in
# ``test_oauth_token_store.py``.
if "litellm" not in sys.modules:
    _litellm = types.ModuleType("litellm")

    class _AuthenticationError(Exception):
        def __init__(self, message: str = "", model: str = "", llm_provider: str = "") -> None:
            super().__init__(message)
            self.message = message
            self.model = model
            self.llm_provider = llm_provider

    class _CustomLLM:
        pass

    class _ModelResponse:
        pass

    _litellm.AuthenticationError = _AuthenticationError  # type: ignore[attr-defined]
    _litellm.CustomLLM = _CustomLLM  # type: ignore[attr-defined]
    _litellm.ModelResponse = _ModelResponse  # type: ignore[attr-defined]
    sys.modules["litellm"] = _litellm

# ``claude_code_handler`` imports the sibling ``oauth_token_store`` module
# by bare name (``from oauth_token_store import ...``). Make sure both
# resolve from the same ``config/`` directory.
_CONFIG_DIR = Path(__file__).resolve().parents[5] / "config"
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))

_HANDLER_PATH = _CONFIG_DIR / "claude_code_handler.py"
_spec = importlib.util.spec_from_file_location("decepticon_claude_code_handler", _HANDLER_PATH)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

_env_override_tokens = _module._env_override_tokens


# A token that passes ``_is_valid_oauth_token`` (must start with sk-ant-oat01-).
VALID_TOKEN = "sk-ant-oat01-" + "x" * 80


# ── _env_override_tokens ─────────────────────────────────────────────


def test_env_override_recognizes_anthropic_oauth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy Decepticon-internal env var name still works (regression guard)."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_OAUTH_TOKEN", VALID_TOKEN)
    creds = _env_override_tokens()
    assert creds is not None
    assert creds["accessToken"] == VALID_TOKEN
    assert creds["refreshToken"] is None
    assert creds["expiresAt"] == 0


def test_env_override_recognizes_claude_code_oauth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """``CLAUDE_CODE_OAUTH_TOKEN`` is the official Claude Code env var name
    (produced by ``claude setup-token``). Decepticon should honor it the
    same way it honors ``ANTHROPIC_OAUTH_TOKEN``.
    """
    monkeypatch.delenv("ANTHROPIC_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", VALID_TOKEN)
    creds = _env_override_tokens()
    assert creds is not None
    assert creds["accessToken"] == VALID_TOKEN
    assert creds["refreshToken"] is None
    assert creds["expiresAt"] == 0


def test_env_override_returns_none_when_no_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert _env_override_tokens() is None


def test_env_override_rejects_malformed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    assert _env_override_tokens() is None


def test_env_override_prefers_claude_code_when_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both env vars are set, ``CLAUDE_CODE_OAUTH_TOKEN`` wins because
    it's the official upstream name. This is documented behavior, not
    accidental — preserve the ordering.
    """
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_OAUTH_TOKEN", raising=False)
    anthropic_token = "sk-ant-oat01-" + "a" * 80
    claude_token = "sk-ant-oat01-" + "c" * 80
    monkeypatch.setenv("ANTHROPIC_OAUTH_TOKEN", anthropic_token)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", claude_token)
    creds = _env_override_tokens()
    assert creds is not None
    assert creds["accessToken"] == claude_token
