"""Unit tests for the LiteLLM custom OAuth handlers under ``config/``.

These modules live in the LiteLLM container's ``/app`` and import ``litellm``
at module level. The dev test env does not install LiteLLM (a runtime container
dep), so a minimal stub is injected before the handlers are loaded. The
handlers also do ``from oauth_token_store import ...`` by bare name, so the
``config/`` directory is placed on ``sys.path``.

Covered fixes:
  * B9  — codex refresh error must not leak raw token fields
  * B10 — copilot streaming must emit tool_calls + preserve finish_reason
  * B11 — grok streaming must emit tool_calls + preserve finish_reason
  * B13 — gemini must map ``finishReason`` instead of hardcoding ``"stop"``
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_CONFIG_DIR = Path(__file__).resolve().parents[5] / "config"


# ── litellm stub ────────────────────────────────────────────────────────


class _StubLLMError(Exception):
    """Mimics litellm's exception API: keyword ``message`` becomes ``str()``."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        self.message = message
        self.model = kwargs.get("model")
        self.llm_provider = kwargs.get("llm_provider")
        self.status_code = kwargs.get("status_code")
        super().__init__(message)


def _ensure_litellm_stub() -> Any:
    litellm = sys.modules.get("litellm")
    if litellm is None:
        litellm = types.ModuleType("litellm")
        sys.modules["litellm"] = litellm
    # Always (re)install the attributes the handlers need — a prior test module
    # may have registered a thinner stub.
    litellm.AuthenticationError = _StubLLMError
    litellm.RateLimitError = _StubLLMError
    litellm.APIError = _StubLLMError
    if not hasattr(litellm, "CustomLLM"):
        litellm.CustomLLM = type("CustomLLM", (object,), {})
    if not hasattr(litellm, "ModelResponse"):
        litellm.ModelResponse = type("ModelResponse", (object,), {})
    return litellm


_ensure_litellm_stub()
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))


def _ensure_real_oauth_token_store() -> None:
    # The handlers do ``from oauth_token_store import ...`` by bare name. Another
    # test module (test_claude_code_handler_cache_dedup) registers a *partial*
    # stub under that same bare name via ``sys.modules.setdefault``; under
    # ``pytest -n auto`` that stub can land in this worker first and shadow the
    # real module, so symbols like ``DEFAULT_JWT_SKEW_SECONDS`` go missing. Load
    # the real config module from file (it only needs the litellm stub above and
    # the installed httpx) so the handlers resolve against the complete module
    # regardless of collection order.
    existing = sys.modules.get("oauth_token_store")
    if existing is not None and getattr(existing, "__file__", None):
        return
    fake_httpx = sys.modules.get("httpx")
    if fake_httpx is not None and not getattr(fake_httpx, "__file__", None):
        del sys.modules["httpx"]
    spec = importlib.util.spec_from_file_location(
        "oauth_token_store", _CONFIG_DIR / "oauth_token_store.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["oauth_token_store"] = module
    spec.loader.exec_module(module)


_ensure_real_oauth_token_store()


def _load(name: str) -> Any:
    _ensure_litellm_stub()
    _ensure_real_oauth_token_store()
    return importlib.import_module(name)


codex = _load("codex_chatgpt_handler")
claude = _load("claude_code_handler")
copilot = _load("copilot_handler")
grok = _load("grok_handler")
gemini = _load("gemini_handler")
perplexity = _load("perplexity_handler")


def _response(message: dict[str, Any], finish_reason: str = "stop") -> Any:
    """Build a minimal ModelResponse-like object for ``_response_to_chunks``."""
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)
    choice = {"index": 0, "message": message, "finish_reason": finish_reason}
    return SimpleNamespace(choices=[choice], usage=usage)


_TOOL_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "run_shell", "arguments": '{"cmd": "ls"}'},
}


# ── B9: codex refresh must not leak raw token data ──────────────────────


class TestCodexRefreshNoSecretLeak:
    def test_missing_fields_message_lists_names_not_values(self, monkeypatch) -> None:
        # Response is missing access_token / id_token but carries a secret
        # refresh_token. The error must name the missing fields only.
        secret = "SECRET-REFRESH-VALUE-do-not-leak"
        monkeypatch.setattr(
            codex,
            "oauth_refresh_request",
            lambda *a, **k: {"refresh_token": secret, "scope": "openid"},
        )
        with pytest.raises(codex.litellm.AuthenticationError) as exc:
            codex._refresh_tokens({"tokens": {"refresh_token": "old-refresh"}})
        message = exc.value.message
        assert "access_token" in message
        assert "id_token" in message
        assert secret not in message
        assert "refresh_token" not in message

    def test_partial_response_names_only_the_absent_field(self, monkeypatch) -> None:
        # access_token present, id_token missing → only id_token reported.
        monkeypatch.setattr(
            codex,
            "oauth_refresh_request",
            lambda *a, **k: {"access_token": "AT", "refresh_token": "SECRET"},
        )
        with pytest.raises(codex.litellm.AuthenticationError) as exc:
            codex._refresh_tokens({"tokens": {"refresh_token": "old"}})
        message = exc.value.message
        assert "id_token" in message
        assert "access_token" not in message
        assert "SECRET" not in message


# ── B10 / B11: streaming must preserve tool calls + finish_reason ───────


@pytest.mark.parametrize(
    "handler", [copilot.copilot_handler_instance, grok.grok_sub_handler_instance]
)
class TestStreamingToolCalls:
    def test_tool_calls_are_emitted_not_dropped(self, handler) -> None:
        resp = _response(
            {"role": "assistant", "content": "", "tool_calls": [_TOOL_CALL]},
            finish_reason="tool_calls",
        )
        chunks = handler._response_to_chunks(resp)
        tool_chunks = [c for c in chunks if c["tool_use"] is not None]
        assert len(tool_chunks) == 1
        assert tool_chunks[0]["tool_use"]["function"]["name"] == "run_shell"
        assert tool_chunks[0]["finish_reason"] == "tool_calls"
        assert tool_chunks[0]["is_finished"] is True

    def test_text_then_tool_call_ordering(self, handler) -> None:
        resp = _response(
            {"role": "assistant", "content": "thinking", "tool_calls": [_TOOL_CALL]},
            finish_reason="tool_calls",
        )
        chunks = handler._response_to_chunks(resp)
        assert chunks[0]["text"] == "thinking"
        assert chunks[0]["tool_use"] is None
        assert chunks[0]["is_finished"] is False
        assert chunks[-1]["tool_use"] is not None

    def test_finish_reason_is_preserved_for_plain_text(self, handler) -> None:
        # A truncated completion must not be reported as a clean "stop".
        resp = _response({"role": "assistant", "content": "partial"}, finish_reason="length")
        chunks = handler._response_to_chunks(resp)
        assert len(chunks) == 1
        assert chunks[0]["finish_reason"] == "length"
        assert chunks[0]["text"] == "partial"
        assert chunks[0]["tool_use"] is None


# ── B13: gemini finishReason mapping ────────────────────────────────────


class TestGeminiFinishReason:
    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("STOP", "stop"),
            ("MAX_TOKENS", "length"),
            ("SAFETY", "content_filter"),
            ("RECITATION", "content_filter"),
            ("OTHER", "stop"),
            (None, "stop"),
            ("", "stop"),
        ],
    )
    def test_map_finish_reason(self, reason, expected) -> None:
        assert gemini._map_finish_reason(reason) == expected


# ── error-proofing: brittle provider-response parsing ───────────────────


class _ParseResp:
    """Minimal httpx.Response stand-in for handler parsing paths."""

    def __init__(self, status_code=200, json_data=None, text="", raise_json=False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._raise_json = raise_json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "https://example.test"), response=self
            )

    def json(self):
        if self._raise_json:
            raise ValueError("Expecting value")
        return self._json_data


class TestCopilotMintHardening:
    def test_missing_token_raises_actionable_error_without_leaking_source(self, monkeypatch):
        secret = "gho_SUPER_SECRET_SOURCE_TOKEN"
        monkeypatch.setattr(
            copilot, "_http_post", lambda *a, **k: _ParseResp(200, {"expires_at": 123})
        )
        with pytest.raises(copilot.litellm.AuthenticationError) as exc:
            copilot._mint_copilot_token(secret)
        assert "subscription" in exc.value.message.lower()
        assert secret not in exc.value.message

    def test_non_json_mint_response_degrades_cleanly(self, monkeypatch):
        monkeypatch.setattr(
            copilot,
            "_http_post",
            lambda *a, **k: _ParseResp(200, raise_json=True, text="<html>gateway</html>"),
        )
        with pytest.raises(copilot.litellm.AuthenticationError):
            copilot._mint_copilot_token("gho_x")

    def test_garbage_expires_at_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(
            copilot,
            "_http_post",
            lambda *a, **k: _ParseResp(200, {"token": "ct", "expires_at": "not-a-number"}),
        )
        minted = copilot._mint_copilot_token("gho_x")
        assert minted["copilot_token"] == "ct"
        assert minted["expires_at"] == 0


class TestGeminiRefreshHardening:
    def test_missing_access_token_raises_without_leaking_refresh(self, monkeypatch):
        secret = "REFRESH-SECRET-do-not-leak"
        monkeypatch.setattr(
            gemini, "oauth_refresh_request", lambda *a, **k: {"expires_in": 3600, "scope": "x"}
        )
        with pytest.raises(gemini.litellm.AuthenticationError) as exc:
            gemini._refresh_google_token({"refreshToken": secret})
        assert "access_token" in exc.value.message
        assert secret not in exc.value.message


@pytest.mark.parametrize(
    ("mod", "fn"),
    [
        (grok, "_exchange_session_for_access"),
        (perplexity, "_exchange_session_for_access"),
    ],
)
class TestSessionExchangeHardening:
    def test_rejected_cookie_raises_auth_error_not_raw_traceback(self, monkeypatch, mod, fn):
        session = "SESSION-COOKIE-SECRET"
        monkeypatch.setattr(mod.httpx, "get", lambda *a, **k: _ParseResp(401, text="unauthorized"))
        with pytest.raises(mod.litellm.AuthenticationError) as exc:
            getattr(mod, fn)(session)
        assert "401" in exc.value.message
        assert session not in exc.value.message

    def test_non_json_session_response_degrades_cleanly(self, monkeypatch, mod, fn):
        monkeypatch.setattr(
            mod.httpx, "get", lambda *a, **k: _ParseResp(200, raise_json=True, text="not json")
        )
        with pytest.raises(mod.litellm.AuthenticationError):
            getattr(mod, fn)("SESSION")


@pytest.mark.parametrize(
    ("mod", "handler", "model"),
    [
        (copilot, copilot.copilot_handler_instance, "copilot/gpt-5"),
        (grok, grok.grok_sub_handler_instance, "grok-sub/grok-4.3"),
        (gemini, gemini.gemini_sub_handler_instance, "gemini-sub/gemini-2.5-pro"),
        (perplexity, perplexity.perplexity_sub_handler_instance, "pplx-sub/sonar-pro"),
    ],
)
class TestCompletionMalformedResponse:
    def test_non_json_200_raises_api_error(self, monkeypatch, mod, handler, model):
        monkeypatch.setattr(
            mod,
            "with_retry_on_401",
            lambda send, **k: _ParseResp(200, raise_json=True, text="<html>oops</html>"),
        )
        with pytest.raises(mod.litellm.APIError):
            handler.completion(model=model, messages=[{"role": "user", "content": "hi"}])

    def test_non_dict_json_200_raises_api_error(self, monkeypatch, mod, handler, model):
        monkeypatch.setattr(
            mod,
            "with_retry_on_401",
            lambda send, **k: _ParseResp(200, json_data=["not", "an", "object"]),
        )
        with pytest.raises(mod.litellm.APIError):
            handler.completion(model=model, messages=[{"role": "user", "content": "hi"}])


# ── Claude refresh hardening: malformed refresh response ────────────────


class _FakeResp:
    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestClaudeRefreshHardening:
    def test_missing_access_token_raises_clean_auth_error(self, monkeypatch) -> None:
        # A refresh response without access_token must not blow up with a
        # raw KeyError, and must never echo the token payload back.
        secret = "sk-ant-oat01-LEAKED-REFRESH"
        monkeypatch.setattr(
            claude,
            "oauth_refresh_request",
            lambda *a, **k: {"refresh_token": secret, "expires_in": 3600},
        )
        with pytest.raises(claude.litellm.AuthenticationError) as exc:
            claude._refresh_token({"refreshToken": "old"})
        message = exc.value.message
        assert "access_token" in message
        assert secret not in message

    def test_null_expires_in_and_scope_do_not_crash(self, monkeypatch) -> None:
        # expires_in / scope arriving as null must not raise TypeError /
        # AttributeError; defaults apply.
        monkeypatch.setattr(
            claude,
            "oauth_refresh_request",
            lambda *a, **k: {
                "access_token": "sk-ant-oat01-new",
                "expires_in": None,
                "scope": None,
            },
        )
        monkeypatch.setattr(claude, "write_json_atomic", lambda *a, **k: True)
        monkeypatch.setattr(claude._credentials_cache, "replace", lambda *a, **k: None)
        new = claude._refresh_token({"refreshToken": "old"})
        assert new["accessToken"] == "sk-ant-oat01-new"
        assert new["scopes"] == []
        assert isinstance(new["expiresAt"], int)
        # refreshToken falls back to the prior value when absent from response.
        assert new["refreshToken"] == "old"


# ── Claude completion: brittle provider-response parsing ─────────────────


class TestClaudeCompletionParsing:
    def _patch_send(self, monkeypatch, resp) -> None:
        monkeypatch.setattr(claude, "with_retry_on_401", lambda send: resp)

    def test_non_json_200_body_raises_api_error_not_traceback(self, monkeypatch) -> None:
        import json as _json

        resp = _FakeResp(
            200, payload=_json.JSONDecodeError("x", "<html>", 0), text="<html>oops</html>"
        )
        self._patch_send(monkeypatch, resp)
        with pytest.raises(claude.litellm.APIError):
            claude.claude_code_handler_instance.completion(
                model="auth/claude-x", messages=[{"role": "user", "content": "hi"}]
            )

    def test_null_content_and_usage_do_not_crash(self, monkeypatch) -> None:
        # content/usage explicitly null must not raise TypeError on iteration
        # or token arithmetic.
        captured: dict[str, Any] = {}

        class _DummyModelResponse:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)

        monkeypatch.setattr(claude, "ModelResponse", _DummyModelResponse)
        resp = _FakeResp(
            200,
            payload={"content": None, "usage": None, "stop_reason": "end_turn", "id": "msg_1"},
        )
        self._patch_send(monkeypatch, resp)
        claude.claude_code_handler_instance.completion(
            model="auth/claude-x", messages=[{"role": "user", "content": "hi"}]
        )
        assert captured["usage"]["total_tokens"] == 0
        assert captured["choices"][0]["message"]["content"] is None

    def test_tool_use_block_missing_name_does_not_keyerror(self, monkeypatch) -> None:
        captured: dict[str, Any] = {}

        class _DummyModelResponse:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)

        monkeypatch.setattr(claude, "ModelResponse", _DummyModelResponse)
        resp = _FakeResp(
            200,
            payload={
                "content": [{"type": "tool_use", "id": "t1", "input": {"a": 1}}],
                "usage": {"input_tokens": 2, "output_tokens": 3},
                "stop_reason": "tool_use",
            },
        )
        self._patch_send(monkeypatch, resp)
        claude.claude_code_handler_instance.completion(
            model="auth/claude-x", messages=[{"role": "user", "content": "hi"}]
        )
        tool_calls = captured["choices"][0]["message"]["tool_calls"]
        assert tool_calls[0]["function"]["name"] == ""
        assert captured["choices"][0]["finish_reason"] == "tool_calls"


# ── Codex input parsing: object-form tool_calls ─────────────────────────


class TestCodexResponsesInput:
    def test_object_form_tool_call_does_not_attributeerror(self) -> None:
        class _Fn:
            name = "run_shell"
            arguments = '{"cmd": "ls"}'

        class _TC:
            id = "call_obj"
            function = _Fn()

        msg = {"role": "assistant", "tool_calls": [_TC()]}
        items, _instr = codex._responses_input([msg])
        fc = [i for i in items if i.get("type") == "function_call"]
        assert len(fc) == 1
        assert fc[0]["call_id"] == "call_obj"
        assert fc[0]["name"] == "run_shell"
        assert fc[0]["arguments"] == '{"cmd": "ls"}'


# ── Codex stream error classification ───────────────────────────────────


class TestCodexCompletedPayloadErrors:
    def test_null_error_does_not_surface_literal_none(self) -> None:
        sse = 'data: {"type": "error", "error": null}\n'
        resp = _FakeResp(200, text=sse)
        with pytest.raises(codex.litellm.APIError) as exc:
            codex._completed_payload(resp)
        assert exc.value.message != "None"

    def test_error_dict_without_message_is_serialized(self) -> None:
        sse = 'data: {"type": "response.failed", "response": {"error": {"code": "boom"}}}\n'
        resp = _FakeResp(200, text=sse)
        with pytest.raises(codex.litellm.APIError) as exc:
            codex._completed_payload(resp)
        assert "boom" in exc.value.message

    def test_empty_stream_uses_fallback_message(self) -> None:
        resp = _FakeResp(200, text="")
        with pytest.raises(codex.litellm.APIError) as exc:
            codex._completed_payload(resp)
        assert "completed" in exc.value.message.lower()
