"""Anthropic SSE → GenericStreamingChunk translation for the OAuth handler.

The handler used to fake streaming: ``astreaming`` awaited the buffered
``acompletion`` and chopped the finished answer into chunks, so every consumer
(LangGraph ``messages`` mode, the run console) saw one all-at-once message.
These tests pin the real behaviour — text arrives as incremental deltas, tool
arguments are reassembled from ``input_json_delta`` fragments, and usage
(including the prompt-cache buckets) survives onto the terminating chunk.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(__file__).resolve().parents[5] / "config" / "claude_code_handler.py"
_spec = importlib.util.spec_from_file_location("_claude_code_handler_stream_src", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None

_FAKE_LITELLM = types.ModuleType("litellm")
_FAKE_LITELLM.CustomLLM = object
_FAKE_LITELLM.ModelResponse = object
_FAKE_OAUTH = types.ModuleType("oauth_token_store")
# `sys.modules.setdefault` means whichever handler test imports first installs
# this stub for the others, so it carries the union of every handler's imports.
_FAKE_OAUTH.DEFAULT_JWT_SKEW_SECONDS = 60
_FAKE_OAUTH.decode_jwt_payload = lambda *_a, **_kw: {}
_FAKE_OAUTH.is_jwt_expired = lambda *_a, **_kw: False
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
_FAKE_HTTP_CLIENT.sync_client = lambda *_a, **_kw: None
_FAKE_HTTP_CLIENT.async_client = lambda *_a, **_kw: None


def _install(name: str, stub: types.ModuleType) -> None:
    """Install ``stub``, or top up whatever another handler test installed first.

    These stubs are process-global: the first handler test to import wins, and
    the others inherit its module. Backfilling missing attributes instead of
    plain ``setdefault`` keeps collection order from deciding whether a handler
    with different imports can load at all.
    """
    existing = sys.modules.setdefault(name, stub)
    for attr, value in vars(stub).items():
        if not attr.startswith("__") and not hasattr(existing, attr):
            setattr(existing, attr, value)


_install("litellm", _FAKE_LITELLM)
_install("oauth_token_store", _FAKE_OAUTH)
_install("httpx", types.ModuleType("httpx"))
_install("http_client", _FAKE_HTTP_CLIENT)

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

_to_chunks = _module._anthropic_sse_to_chunks


def _sse(*events: dict[str, Any]) -> list[str]:
    """Render events the way Anthropic's SSE wire does (httpx strips newlines)."""
    lines: list[str] = []
    for event in events:
        lines.append(f"event: {event['type']}")
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    return lines


def test_text_arrives_as_incremental_deltas() -> None:
    chunks = list(
        _to_chunks(
            _sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 11}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Recon "},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "means "},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "mapping."},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 7},
                },
                {"type": "message_stop"},
            )
        )
    )

    # One chunk per delta — NOT one cumulative blob.
    assert [c["text"] for c in chunks] == ["Recon ", "means ", "mapping.", ""]
    assert [c["is_finished"] for c in chunks] == [False, False, False, True]

    final = chunks[-1]
    assert final["finish_reason"] == "stop"
    assert final["usage"]["prompt_tokens"] == 11
    assert final["usage"]["completion_tokens"] == 7
    assert final["usage"]["total_tokens"] == 18


def test_tool_arguments_are_reassembled_from_json_fragments() -> None:
    chunks = list(
        _to_chunks(
            _sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 3}}},
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "id": "toolu_1", "name": "task"},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": '{"agent"'},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": ': "recon"}'},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 5},
                },
                {"type": "message_stop"},
            )
        )
    )

    tool_chunks = [c for c in chunks if c["tool_use"]]
    assert len(tool_chunks) == 1
    tool = tool_chunks[0]["tool_use"]
    assert tool["id"] == "toolu_1"
    assert tool["function"]["name"] == "task"
    # Fragments only parse once concatenated.
    assert json.loads(tool["function"]["arguments"]) == {"agent": "recon"}
    assert chunks[-1]["finish_reason"] == "tool_calls"


def test_cache_buckets_survive_onto_the_final_chunk() -> None:
    chunks = list(
        _to_chunks(
            _sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 4,
                            "cache_creation_input_tokens": 1024,
                            "cache_read_input_tokens": 2048,
                        }
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "hi"},
                },
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
                {"type": "message_stop"},
            )
        )
    )

    usage = chunks[-1]["usage"]
    assert usage["cache_creation_input_tokens"] == 1024
    assert usage["cache_read_input_tokens"] == 2048


def test_thinking_deltas_and_pings_do_not_leak_into_assistant_text() -> None:
    chunks = list(
        _to_chunks(
            _sse(
                {"type": "ping"},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": "hmm"},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "answer"},
                },
                {"type": "message_stop"},
            )
        )
    )

    assert [c["text"] for c in chunks] == ["answer", ""]


def test_truncated_stream_still_terminates() -> None:
    # Upstream cut before message_stop — the wrapper must still see is_finished
    # once, or LiteLLM's stream wrapper hangs waiting for the terminator.
    chunks = list(
        _to_chunks(
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "partial"},
                },
            )
        )
    )

    assert [c["is_finished"] for c in chunks] == [False, True]


def test_malformed_data_lines_are_skipped() -> None:
    chunks = list(_to_chunks(["data: not-json", "", "data: [DONE]"]))

    # Nothing parsed, but the terminator is still produced.
    assert len(chunks) == 1
    assert chunks[0]["is_finished"] is True
