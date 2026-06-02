"""Unit tests for ``_classify_provider_error`` + fatal-vs-retryable labelling.

Background: ``_reraise_with_actionable_message`` already handles 400/401/404/429,
but a caller (or human reading CLI output) cannot tell *retryable* (worth a
fallback hop) from *fatal* (no auth swap will fix it). The classifier returns
a tiny tag so the surfaced message can drop the misleading
"configure another auth method" hint on fatal cases while preserving today's
behavior for transient ones (#107 follow-up).
"""

from __future__ import annotations

import httpx
import pytest

from decepticon.llm.factory import (
    LLMTimeoutError,
    _classify_provider_error,
    _reraise_with_actionable_message,
)


def _exc_with_status(name: str, status: int, msg: str = "") -> Exception:
    """Build a synthetic provider-style exception that mirrors what LiteLLM /
    openai surface in the wild — class name encodes the error kind and a
    ``status_code`` attribute matches ``openai.APIStatusError``.
    """
    cls = type(name, (Exception,), {})
    exc = cls(msg or f"Error code: {status}")
    exc.status_code = status  # type: ignore[attr-defined]
    return exc


class TestClassifyProviderErrorRetryable:
    """Transient failures the agent (or LiteLLM retry layer) can recover from."""

    def test_429_rate_limit_is_retryable(self):
        assert _classify_provider_error(_exc_with_status("RateLimitError", 429)) == "retryable"

    def test_503_service_unavailable_is_retryable(self):
        assert (
            _classify_provider_error(_exc_with_status("ServiceUnavailableError", 503))
            == "retryable"
        )

    def test_500_internal_server_error_is_retryable(self):
        assert _classify_provider_error(_exc_with_status("InternalServerError", 500)) == "retryable"

    def test_llm_timeout_error_is_retryable(self):
        assert _classify_provider_error(LLMTimeoutError("timed out after 600s")) == "retryable"

    def test_httpx_connect_error_is_retryable(self):
        assert _classify_provider_error(httpx.ConnectError("connection refused")) == "retryable"

    def test_httpx_read_timeout_is_retryable(self):
        assert _classify_provider_error(httpx.ReadTimeout("read timed out")) == "retryable"

    def test_message_only_5xx_is_retryable(self):
        # No status_code attribute; classifier must fall back to message regex
        # (LiteLLM surface for proxied errors).
        exc = Exception("litellm.APIError: Error code: 502 - upstream bad gateway")
        assert _classify_provider_error(exc) == "retryable"


class TestClassifyProviderErrorFatal:
    """4xx auth/config failures — no retry, no auth swap, will fix nothing."""

    def test_400_bad_request_is_fatal(self):
        assert _classify_provider_error(_exc_with_status("BadRequestError", 400)) == "fatal"

    def test_401_authentication_is_fatal(self):
        assert _classify_provider_error(_exc_with_status("AuthenticationError", 401)) == "fatal"

    def test_403_forbidden_is_fatal(self):
        assert _classify_provider_error(_exc_with_status("PermissionDeniedError", 403)) == "fatal"

    def test_404_not_found_is_fatal(self):
        assert _classify_provider_error(_exc_with_status("NotFoundError", 404)) == "fatal"

    def test_message_only_400_is_fatal(self):
        exc = Exception("Error code: 400 - parameter 'temperature' is deprecated")
        assert _classify_provider_error(exc) == "fatal"


class TestActionableMessageFatalLabel:
    """Integration with ``_reraise_with_actionable_message``: fatal classes
    must carry the ``non-retryable provider error`` marker so callers /
    operators stop chasing transient explanations."""

    def test_400_message_labelled_non_retryable(self):
        exc = _exc_with_status(
            "BadRequestError",
            400,
            "Error code: 400 - temperature is deprecated",
        )
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "non-retryable provider error" in msg
        # Existing remediation text preserved (regression).
        assert "rejected the request (400)" in msg

    def test_401_message_labelled_non_retryable(self):
        exc = _exc_with_status("AuthenticationError", 401, "Error code: 401 - invalid_api_key")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "openai/gpt-5.5")
        msg = str(info.value)
        assert "non-retryable provider error" in msg
        assert "credentials (401)" in msg

    def test_404_message_labelled_non_retryable(self):
        exc = _exc_with_status("NotFoundError", 404, "Error code: 404 - model not found")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "ollama_chat/nope")
        msg = str(info.value)
        assert "non-retryable provider error" in msg
        assert "404" in msg

    def test_429_message_unchanged_retryable_path(self):
        # Retryable branch must NOT acquire the fatal label — would mislead
        # operators into thinking the rate-limit isn't recoverable.
        exc = _exc_with_status("RateLimitError", 429, "Error code: 429")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "non-retryable provider error" not in msg
        assert "rate limit (429)" in msg
