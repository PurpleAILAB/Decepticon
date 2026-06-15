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


class TestActionableMessage403Forbidden:
    """403 PermissionDenied is a distinct fatal class. Before the fix the
    helper had no branch for it, so it fell through to the caller's bare
    ``raise`` — surfacing the raw provider exception (no remediation, and the
    un-redacted body could leak an echoed Authorization header)."""

    def test_403_by_status_attr_gives_actionable_message(self):
        exc = _exc_with_status("PermissionDeniedError", 403, "Error code: 403 - forbidden")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "refused access (403)" in msg
        assert "non-retryable provider error" in msg
        assert "DECEPTICON_AUTH_PRIORITY" in msg

    def test_403_message_only_gives_actionable_message(self):
        exc = Exception("litellm.PermissionDeniedError: Error code: 403 - region not allowed")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "openai/gpt-5.5")
        assert "refused access (403)" in str(info.value)

    def test_403_redacts_echoed_bearer_token(self):
        exc = _exc_with_status(
            "PermissionDeniedError",
            403,
            "Error code: 403 - Authorization: Bearer sk-ant-FORBIDDENLEAKTOKEN12345",
        )
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "anthropic/claude-opus-4-7")
        msg = str(info.value)
        assert "sk-ant-FORBIDDENLEAKTOKEN12345" not in msg
        assert "FORBIDDENLEAKTOKEN12345" not in msg
        assert "[REDACTED]" in msg


class TestUnclassifiedErrorSecretNet:
    """Final safety net: an *unclassified* provider error (no 4xx branch
    matched) whose body echoes a credential must be re-wrapped with the
    scrubbed text instead of re-raised verbatim — otherwise the caller's
    trailing ``raise`` would leak the secret into CLI output / logs."""

    def test_unclassified_500_with_bearer_is_redacted_and_wrapped(self):
        # 500 is retryable and not special-cased in the actionable branches,
        # so it lands on the fallthrough. The echoed token must not survive.
        exc = Exception(
            "Error code: 500 - upstream error; sent Authorization: Bearer "
            "sk-LEAKYINTERNALSERVERTOKEN9999"
        )
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "openai/gpt-5.5")
        msg = str(info.value)
        assert "sk-LEAKYINTERNALSERVERTOKEN9999" not in msg
        assert "LEAKYINTERNALSERVERTOKEN9999" not in msg
        assert "[REDACTED]" in msg
        assert "unclassified provider error" in msg

    def test_unclassified_with_api_key_kwarg_is_redacted(self):
        exc = Exception("weird upstream blob api_key=sk-ANOTHERLEAKEDVALUE0001 happened")
        with pytest.raises(RuntimeError) as info:
            _reraise_with_actionable_message(exc, "openai/gpt-5.5")
        assert "sk-ANOTHERLEAKEDVALUE0001" not in str(info.value)
        assert "[REDACTED]" in str(info.value)

    def test_unrelated_error_without_credential_passes_through(self):
        # No credential shape → helper must NOT raise; caller re-raises the
        # original exception with its traceback intact (regression guard for
        # the safety net's narrow trigger). A long model id alone (which the
        # broad >=24-char redaction pattern matches) must not trip it.
        exc = ValueError("planner produced no model for anthropic/claude-opus-4-7-experimental")
        # Returns None (no raise).
        assert _reraise_with_actionable_message(exc, "anthropic/claude-opus-4-7") is None
