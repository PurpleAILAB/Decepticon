"""codex_chatgpt_handler surfaces Responses-API prompt-cache hits.

The ChatGPT/Codex OAuth backend reports cache hits under
``usage.input_tokens_details.cached_tokens``. The handler must re-emit them as
``prompt_tokens_details.cached_tokens`` so LiteLLM bills the cache-read rate.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(__file__).resolve().parents[5] / "config" / "codex_chatgpt_handler.py"


class _CapturingModelResponse:
    """Stand-in for litellm.ModelResponse that records the usage kwarg."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.usage = kwargs.get("usage")


def _load_handler() -> Any:
    fake_litellm = types.ModuleType("litellm")
    fake_litellm.CustomLLM = object
    fake_litellm.ModelResponse = _CapturingModelResponse
    fake_litellm.AuthenticationError = type("AuthenticationError", (Exception,), {})
    fake_litellm.APIError = type("APIError", (Exception,), {})

    fake_oauth = types.ModuleType("oauth_token_store")
    for _name in (
        "DEFAULT_JWT_SKEW_SECONDS",
        "FileBackedCache",
        "decode_jwt_payload",
        "is_jwt_expired",
        "oauth_refresh_request",
        "read_json_file",
        "with_retry_on_401",
        "write_json_atomic",
    ):
        setattr(fake_oauth, _name, (lambda *_a, **_kw: None))
    fake_oauth.DEFAULT_JWT_SKEW_SECONDS = 300

    fake_http = types.ModuleType("http_client")
    fake_http.post = lambda *_a, **_kw: None
    fake_http.async_post = lambda *_a, **_kw: None

    # Force complete fakes while loading the handler, then restore sys.modules
    # so this test neither depends on nor leaks stubs another test installed
    # (the modules are only referenced at import time; we call _model_response
    # only, which touches none of them).
    overrides = {
        "litellm": fake_litellm,
        "oauth_token_store": fake_oauth,
        "http_client": fake_http,
        "httpx": types.ModuleType("httpx"),
    }
    saved = {name: sys.modules.get(name) for name in overrides}
    sys.modules.update(overrides)
    try:
        spec = importlib.util.spec_from_file_location("_codex_handler_src", _MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


_module = _load_handler()
_model_response = _module._model_response

_MSG_OUTPUT = [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]


def test_cached_tokens_surfaced_as_prompt_tokens_details() -> None:
    payload = {
        "output": _MSG_OUTPUT,
        "usage": {
            "input_tokens": 5000,
            "output_tokens": 10,
            "total_tokens": 5010,
            "input_tokens_details": {"cached_tokens": 4800},
        },
    }
    resp = _model_response("gpt-5.5", payload)
    assert resp.usage["prompt_tokens"] == 5000
    assert resp.usage["prompt_tokens_details"] == {"cached_tokens": 4800}


def test_no_cache_field_omits_prompt_tokens_details() -> None:
    payload = {
        "output": _MSG_OUTPUT,
        "usage": {"input_tokens": 5000, "output_tokens": 10, "total_tokens": 5010},
    }
    resp = _model_response("gpt-5.5", payload)
    assert "prompt_tokens_details" not in resp.usage


def test_zero_cached_tokens_omits_prompt_tokens_details() -> None:
    payload = {
        "output": _MSG_OUTPUT,
        "usage": {
            "input_tokens": 5000,
            "output_tokens": 10,
            "total_tokens": 5010,
            "input_tokens_details": {"cached_tokens": 0},
        },
    }
    resp = _model_response("gpt-5.5", payload)
    assert "prompt_tokens_details" not in resp.usage
