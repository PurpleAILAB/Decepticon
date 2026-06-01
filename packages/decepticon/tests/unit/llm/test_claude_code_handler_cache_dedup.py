from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(__file__).resolve().parents[5] / "config" / "claude_code_handler.py"
_spec = importlib.util.spec_from_file_location("_claude_code_handler_src", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None

_FAKE_LITELLM = types.ModuleType("litellm")
_FAKE_LITELLM.CustomLLM = object
_FAKE_LITELLM.ModelResponse = object
_FAKE_OAUTH = types.ModuleType("oauth_token_store")
_FAKE_OAUTH.DEFAULT_REFRESH_BUFFER_SECONDS = 300
_FAKE_OAUTH.FileBackedCache = lambda *_a, **_kw: None
_FAKE_OAUTH.is_timestamp_expired = lambda *_a, **_kw: False
_FAKE_OAUTH.oauth_refresh_request = lambda *_a, **_kw: None
_FAKE_OAUTH.read_json_file = lambda *_a, **_kw: {}
_FAKE_OAUTH.with_retry_on_401 = lambda *_a, **_kw: None
_FAKE_OAUTH.write_json_atomic = lambda *_a, **_kw: None

_FAKE_HTTP_CLIENT = types.ModuleType("http_client")
_FAKE_HTTP_CLIENT.post = lambda *_a, **_kw: None
_FAKE_HTTP_CLIENT.async_post = lambda *_a, **_kw: None

sys.modules.setdefault("litellm", _FAKE_LITELLM)
sys.modules.setdefault("oauth_token_store", _FAKE_OAUTH)
sys.modules.setdefault("httpx", types.ModuleType("httpx"))
sys.modules.setdefault("http_client", _FAKE_HTTP_CLIENT)

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

_cap_cache_control = _module._cap_cache_control


def _cc_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def _plain_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def test_no_change_when_four_or_fewer_blocks() -> None:
    blocks = [_cc_block(f"b{i}") for i in range(4)]
    original = [dict(b) for b in blocks]
    _cap_cache_control(blocks)
    assert blocks == original


def test_five_blocks_distinct_content_strips_middle_only() -> None:
    blocks = [_cc_block(f"block-{i}") for i in range(5)]
    _cap_cache_control(blocks)
    has_cc = [("cache_control" in b) for b in blocks]
    assert has_cc == [True, False, True, True, True], has_cc


def test_five_blocks_with_duplicate_content_strips_exactly_one() -> None:
    dup_text = "identical content"
    blocks = [
        _cc_block("spoof"),
        _cc_block("system-1"),
        _cc_block(dup_text),
        _cc_block(dup_text),
        _cc_block("system-4"),
    ]
    _cap_cache_control(blocks)
    cc_count = sum(1 for b in blocks if "cache_control" in b)
    assert cc_count == 4, f"expected 4 cache_control blocks, got {cc_count}: {blocks}"


def test_no_op_reassignment_removed() -> None:
    blocks = [_cc_block(f"b{i}") for i in range(6)]
    ids_before = [id(b) for b in blocks]
    _cap_cache_control(blocks)
    assert [id(b) for b in blocks] == ids_before


def test_six_blocks_keeps_first_and_last_three() -> None:
    blocks = [_cc_block(f"b{i}") for i in range(6)]
    _cap_cache_control(blocks)
    has_cc = [("cache_control" in b) for b in blocks]
    assert has_cc == [True, False, False, True, True, True], has_cc


def test_plain_blocks_in_middle_not_affected() -> None:
    blocks = [
        _cc_block("spoof"),
        _plain_block("no-cc-1"),
        _cc_block("system-2"),
        _cc_block("system-3"),
        _cc_block("system-4"),
        _cc_block("system-5"),
    ]
    _cap_cache_control(blocks)
    cc_count = sum(1 for b in blocks if "cache_control" in b)
    assert cc_count == 4
