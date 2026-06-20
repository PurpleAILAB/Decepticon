"""Tests for decepticon.telemetry.sink — consent-gated end-to-end behavior."""

from __future__ import annotations

import json
from typing import Any

from decepticon.telemetry.config import TelemetryConfig, TelemetryMode
from decepticon.telemetry.sink import TelemetrySink


def _cfg(mode: TelemetryMode, endpoint: str | None) -> TelemetryConfig:
    return TelemetryConfig(
        mode=mode,
        endpoint=endpoint,
        install_id="1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
        version="1.1.13",
        os_name="linux",
    )


def test_disabled_sink_is_noop() -> None:
    sink = TelemetrySink(_cfg(TelemetryMode.OFF, None))
    assert sink.enabled is False
    sink.record("tool.call", {"tool": "bash"}, "recon")  # must not raise / not send
    sink.flush()


def test_enabled_sink_maps_and_ships() -> None:
    sent: list[bytes] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC, "https://gw.example"), transport=lambda _u, b: sent.append(b)
    )
    assert sink.enabled is True
    sink.record("tool.call", {"tool": "bash", "args": {"command": "<str:23>"}}, "recon")
    sink.record("tool.result", {"tool": "bash", "status": "success", "output_chars": 2048}, "recon")
    sink.close()

    assert len(sent) == 1
    env = json.loads(sent[0])
    assert env["schema_version"] == "1.0"
    assert env["tier"] == "A"
    assert env["install_id"] == "1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1"
    assert env["client"] == {"decepticon_version": "1.1.13", "os": "linux"}
    types = [e["type"] for e in env["events"]]
    assert types == ["tool.call", "tool.result"]
    assert "args" not in env["events"][0]  # structure dropped
    assert env["events"][1]["status"] == "ok" and env["events"][1]["output_bucket"] == "1k-10k"


def test_extended_sink_sends_tier_b() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.EXTENDED, "https://gw.example"),
        transport=lambda _u, b: sent.append(json.loads(b)),
    )
    sink.record("agent.turn", {"category": "sqli", "attack_phase": "exploitation"}, "exploit")
    sink.close()
    env = sent[0]
    assert env["tier"] == "B"
    assert env["events"][0]["category"] == "sqli"


def test_fail_closed_drops_tier_c_leak() -> None:
    sent: list[bytes] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC, "https://gw.example"), transport=lambda _u, b: sent.append(b)
    )
    # A regressed payload whose tool field is actually a raw IP — must be dropped,
    # not shipped, by the client-side Tier-C scan.
    sink.record("tool.call", {"tool": "10.0.0.5"}, "recon")
    sink.close()
    assert sent == []  # nothing left the process


def test_preview_returns_exact_payload() -> None:
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC, "https://gw.example"), transport=lambda _u, _b: None
    )
    sample = [
        {"type": "tool.call", "ts": 1.0, "agent": "recon", "payload": {"tool": "nmap"}},
        {
            "type": "tool.call",
            "ts": 2.0,
            "agent": "recon",
            "payload": {"tool": "10.0.0.5"},
        },  # leak -> excluded
    ]
    env = sink.preview(sample)
    assert len(env["events"]) == 1  # the leaky one is filtered from the preview
    assert env["events"][0]["tool"] == "nmap"
