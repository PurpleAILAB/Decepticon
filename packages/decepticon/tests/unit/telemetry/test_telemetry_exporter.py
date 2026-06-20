"""Tests for decepticon.telemetry.exporter — batching + offline tolerance."""

from __future__ import annotations

import json
from typing import Any

from decepticon.telemetry.exporter import BatchExporter


def _envelope(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "1.0", "events": events}


def test_flushes_when_batch_full() -> None:
    sent: list[bytes] = []
    exp = BatchExporter(
        endpoint="https://gw.example",
        envelope=_envelope,
        batch_size=3,
        flush_interval_s=0,  # disable timer
        transport=lambda _url, body: sent.append(body),
    )
    exp.record({"type": "tool.call", "ts": 1})
    exp.record({"type": "tool.call", "ts": 2})
    assert sent == []  # not full yet
    exp.record({"type": "tool.call", "ts": 3})  # triggers flush
    assert len(sent) == 1
    payload = json.loads(sent[0])
    assert len(payload["events"]) == 3


def test_close_flushes_remainder() -> None:
    sent: list[bytes] = []
    exp = BatchExporter(
        endpoint="https://gw.example",
        envelope=_envelope,
        batch_size=100,
        flush_interval_s=0,
        transport=lambda _url, body: sent.append(body),
    )
    exp.record({"type": "llm.call", "ts": 1})
    exp.close()
    assert len(sent) == 1


def test_offline_failure_is_swallowed() -> None:
    def boom(_url: str, _body: bytes) -> None:
        raise OSError("network down")

    exp = BatchExporter(
        endpoint="https://gw.example",
        envelope=_envelope,
        batch_size=1,
        flush_interval_s=0,
        transport=boom,
    )
    # Must not raise even though transport always fails.
    exp.record({"type": "tool.call", "ts": 1})
    exp.close()


def test_bounded_queue_drops_oldest() -> None:
    sent: list[bytes] = []
    exp = BatchExporter(
        endpoint="https://gw.example",
        envelope=_envelope,
        batch_size=10_000,
        flush_interval_s=0,
        max_queue=5,
        transport=lambda _url, body: sent.append(body),
    )
    for i in range(8):
        exp.record({"type": "tool.call", "ts": i})
    exp.close()
    payload = json.loads(sent[0])
    # only the last 5 survive the bounded buffer
    assert [e["ts"] for e in payload["events"]] == [3, 4, 5, 6, 7]
