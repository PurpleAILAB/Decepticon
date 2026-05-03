"""Unit tests for the container-side Ollama probe at config/ollama_probe.py.

config/ isn't a Python package — load via importlib, same pattern as
test_litellm_dynamic_config.py.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "config" / "ollama_probe.py"
_MODULE_NAME = "decepticon_ollama_probe"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
# Register in sys.modules BEFORE exec_module: Python 3.13's
# ``@dataclass`` walks ``sys.modules[cls.__module__].__dict__`` to
# resolve forward references, and crashes with AttributeError on a
# missing entry. ``test_litellm_dynamic_config.py`` happens to work
# without this only because it doesn't define any dataclasses.
sys.modules[_MODULE_NAME] = _module
_spec.loader.exec_module(_module)

ProbeResult = _module.ProbeResult
extract_ollama_models = _module.extract_ollama_models
has_ollama_route = _module.has_ollama_route
probe = _module.probe
reachability = _module.reachability
tool_capability = _module.tool_capability


# ── Fake response / opener helpers ────────────────────────────────────


class _FakeResponse:
    """Stand-in for an ``http.client.HTTPResponse``-shaped object."""

    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def _opener_returning(response: _FakeResponse) -> Any:
    """Return an opener that yields ``response`` regardless of input."""

    def _opener(url_or_request: Any, timeout: float) -> _FakeResponse:
        del url_or_request, timeout
        return response

    return _opener


def _opener_raising(exc: BaseException) -> Any:
    def _opener(url_or_request: Any, timeout: float) -> _FakeResponse:
        del url_or_request, timeout
        raise exc

    return _opener


# ── has_ollama_route ──────────────────────────────────────────────────


class TestHasOllamaRoute:
    def test_detects_ollama_chat_provider(self) -> None:
        assert has_ollama_route(["ollama_chat/llama3.2"]) is True

    def test_detects_legacy_ollama_provider(self) -> None:
        # Detection is provider-prefix based — even though ollama/ is
        # rejected by validate_model_name, a stray entry should still
        # signal that the probe should run (so the operator gets a
        # diagnostic instead of silence).
        assert has_ollama_route(["ollama/llama3.2"]) is True

    def test_ignores_non_ollama_routes(self) -> None:
        assert has_ollama_route(["openai/gpt-5", "anthropic/claude-haiku-4-5"]) is False

    def test_empty_iterable(self) -> None:
        assert has_ollama_route([]) is False

    def test_mixed_iterable_with_one_ollama(self) -> None:
        assert has_ollama_route(["openai/gpt-5", "ollama_chat/qwen3-coder:30b"]) is True


# ── extract_ollama_models ─────────────────────────────────────────────


class TestExtractOllamaModels:
    def test_strips_provider_prefix(self) -> None:
        assert extract_ollama_models(["ollama_chat/qwen3-coder:30b"]) == ["qwen3-coder:30b"]

    def test_skips_non_ollama_entries(self) -> None:
        assert extract_ollama_models(
            ["openai/gpt-5", "ollama_chat/llama3.2", "anthropic/claude"]
        ) == ["llama3.2"]

    def test_skips_provider_only_entries(self) -> None:
        assert extract_ollama_models(["ollama_chat/"]) == []

    def test_preserves_input_order(self) -> None:
        # Stable ordering matters for deterministic probe output.
        ids = ["ollama_chat/a", "ollama_chat/b", "ollama_chat/c"]
        assert extract_ollama_models(ids) == ["a", "b", "c"]


# ── reachability ──────────────────────────────────────────────────────


class TestReachability:
    def test_empty_base_url_is_diagnosed(self) -> None:
        result = reachability("")
        assert result.ok is False
        assert result.message is not None
        assert "empty" in result.message.lower()

    def test_localhost_is_rejected_with_loopback_hint(self) -> None:
        result = reachability("http://localhost:11434")
        assert result.ok is False
        assert result.message is not None
        assert "host.docker.internal" in result.message
        assert "localhost" in result.message.lower()

    def test_127_0_0_1_is_rejected(self) -> None:
        result = reachability("http://127.0.0.1:11434")
        assert result.ok is False
        assert result.message is not None
        assert "host.docker.internal" in result.message

    def test_ipv6_loopback_is_rejected(self) -> None:
        result = reachability("http://[::1]:11434")
        assert result.ok is False
        assert result.message is not None

    def test_connection_refused_suggests_ollama_host_zero(self) -> None:
        opener = _opener_raising(
            urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        )
        result = reachability("http://host.docker.internal:11434", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "OLLAMA_HOST=0.0.0.0" in result.message

    def test_dns_failure_points_to_extra_hosts(self) -> None:
        opener = _opener_raising(
            urllib.error.URLError(socket.gaierror("Name or service not known"))
        )
        result = reachability("http://host.docker.internal:11434", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "extra_hosts" in result.message

    def test_success_returns_ok_with_no_message(self) -> None:
        opener = _opener_returning(_FakeResponse(status=200))
        result = reachability("http://host.docker.internal:11434", opener=opener)
        assert result.ok is True
        assert result.message is None

    def test_non_2xx_status_is_reported(self) -> None:
        opener = _opener_returning(_FakeResponse(status=500))
        result = reachability("http://host.docker.internal:11434", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "500" in result.message

    def test_http_error_4xx_is_reported(self) -> None:
        opener = _opener_raising(
            urllib.error.HTTPError(
                url="http://host.docker.internal:11434/api/tags",
                code=403,
                msg="Forbidden",
                hdrs=None,  # type: ignore[arg-type]
                fp=BytesIO(b""),
            )
        )
        result = reachability("http://host.docker.internal:11434", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "403" in result.message


# ── tool_capability ───────────────────────────────────────────────────


def _show_response(capabilities: list[str] | None = None, **extra: Any) -> _FakeResponse:
    body: dict[str, Any] = dict(extra)
    if capabilities is not None:
        body["capabilities"] = capabilities
    return _FakeResponse(status=200, body=json.dumps(body).encode("utf-8"))


class TestToolCapability:
    def test_empty_inputs_short_circuit(self) -> None:
        assert tool_capability("", "qwen3-coder").ok is False
        assert tool_capability("http://host.docker.internal:11434", "").ok is False

    def test_capabilities_with_tools_passes(self) -> None:
        opener = _opener_returning(_show_response(["completion", "tools"]))
        result = tool_capability(
            "http://host.docker.internal:11434", "qwen3-coder:30b", opener=opener
        )
        assert result.ok is True
        assert result.message is None

    def test_capabilities_without_tools_fails_with_remediation(self) -> None:
        opener = _opener_returning(_show_response(["completion"]))
        result = tool_capability("http://host.docker.internal:11434", "gemma:2b", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "gemma:2b" in result.message
        assert "'tools'" in result.message

    def test_missing_capabilities_field_returns_soft_hint(self) -> None:
        # Older Ollama versions don't ship capabilities — we can't
        # determine tool support, so we don't block, but we surface a
        # hint pointing at the version mismatch.
        opener = _opener_returning(_show_response())  # no capabilities key
        result = tool_capability("http://host.docker.internal:11434", "llama3.2", opener=opener)
        assert result.ok is True
        assert result.message is not None
        assert "0.3" in result.message

    def test_404_indicates_model_not_pulled(self) -> None:
        opener = _opener_raising(
            urllib.error.HTTPError(
                url="http://host.docker.internal:11434/api/show",
                code=404,
                msg="Not Found",
                hdrs=None,  # type: ignore[arg-type]
                fp=BytesIO(b""),
            )
        )
        result = tool_capability(
            "http://host.docker.internal:11434", "qwen3-coder:30b", opener=opener
        )
        assert result.ok is False
        assert result.message is not None
        assert "ollama pull qwen3-coder:30b" in result.message

    def test_non_json_body_is_diagnosed(self) -> None:
        opener = _opener_returning(_FakeResponse(status=200, body=b"<html>nope</html>"))
        result = tool_capability("http://host.docker.internal:11434", "llama3.2", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "non-JSON" in result.message

    def test_transport_error_uses_shared_classifier(self) -> None:
        opener = _opener_raising(urllib.error.URLError(ConnectionRefusedError("refused")))
        result = tool_capability("http://host.docker.internal:11434", "llama3.2", opener=opener)
        assert result.ok is False
        assert result.message is not None
        assert "OLLAMA_HOST=0.0.0.0" in result.message


# ── probe (composition) ───────────────────────────────────────────────


class TestProbeComposition:
    def test_unreachable_short_circuits_before_capability_check(self) -> None:
        # Reachability fails (localhost) — we should NOT attempt /api/show
        # for each model; one diagnostic line is enough.
        lines = probe(
            "http://localhost:11434",
            ["llama3.2", "qwen3-coder:30b"],
        )
        assert len(lines) == 1
        assert "host.docker.internal" in lines[0]

    def test_reachable_with_tool_capable_models_yields_no_lines(self) -> None:
        # Build an opener that returns OK for /api/tags AND the show
        # response for either model.
        tags_response = _FakeResponse(status=200, body=b'{"models":[]}')
        show_response = _show_response(["completion", "tools"])

        def _opener(url_or_request: Any, timeout: float) -> _FakeResponse:
            del timeout
            url = (
                url_or_request.full_url
                if hasattr(url_or_request, "full_url")
                else str(url_or_request)
            )
            if url.endswith("/api/tags"):
                return tags_response
            return show_response

        lines = probe(
            "http://host.docker.internal:11434",
            ["llama3.2"],
            opener=_opener,
        )
        assert lines == []

    def test_reachable_but_model_lacks_tools_is_reported(self) -> None:
        tags_response = _FakeResponse(status=200, body=b'{"models":[]}')
        show_response = _show_response(["completion"])

        def _opener(url_or_request: Any, timeout: float) -> _FakeResponse:
            del timeout
            url = (
                url_or_request.full_url
                if hasattr(url_or_request, "full_url")
                else str(url_or_request)
            )
            return tags_response if url.endswith("/api/tags") else show_response

        lines = probe(
            "http://host.docker.internal:11434",
            ["gemma:2b"],
            opener=_opener,
        )
        assert len(lines) == 1
        assert "gemma:2b" in lines[0]
        assert "'tools'" in lines[0]


# ── ProbeResult dataclass ─────────────────────────────────────────────


def test_probe_result_is_immutable() -> None:
    result = ProbeResult(ok=True)
    with pytest.raises(Exception):
        result.ok = False  # type: ignore[misc]
