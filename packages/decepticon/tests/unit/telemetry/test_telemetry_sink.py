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


def test_research_sink_tags_tier_r() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.RESEARCH, "https://gw.example"),
        transport=lambda _u, b: sent.append(json.loads(b)),
    )
    sink.record("tool.call", {"tool": "nmap"}, "recon")
    sink.close()
    env = sent[0]
    assert env["tier"] == "R"
    assert env["events"][0]["tool"] == "nmap"


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


def test_record_step_is_research_only() -> None:
    sent: list[bytes] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC, "https://gw.example"), transport=lambda _u, b: sent.append(b)
    )
    sink.record_step({"kind": "model", "reasoning": "try SQLi on <HOST_1>"}, "exploit")
    sink.close()
    assert sent == []  # trajectory capture requires research consent


def test_record_step_masks_identifiers_and_forwards() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.RESEARCH, "https://gw.example"),
        transport=lambda _u, b: sent.append(json.loads(b)),
    )
    # raw reasoning with a target IP + creds — must be masked, not dropped/leaked
    sink.record_step(
        {"kind": "model", "step": 1, "reasoning": "exploit 10.0.0.5 with creds admin:P@ss!2024"},
        "exploit",
    )
    sink.close()
    env = sent[0]
    assert env["tier"] == "R"
    ev = env["events"][0]
    assert ev["type"] == "trajectory.step" and ev["kind"] == "model"
    blob = json.dumps(env)
    assert "10.0.0.5" not in blob and "P@ss!2024" not in blob  # masked
    assert "<IP_1>" in ev["reasoning"] and "SQLi" not in blob  # structure kept, identifiers gone


def test_record_step_stable_across_steps() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.RESEARCH, "https://gw.example"),
        transport=lambda _u, b: sent.append(json.loads(b)),
    )
    sink.record_step({"kind": "model", "reasoning": "recon 10.0.0.5"}, "recon")
    sink.record_step({"kind": "tool", "observation": "10.0.0.5 port 445 open"}, "recon")
    sink.close()
    evs = [e for env in sent for e in env["events"]]
    # same IP → same placeholder across two separate steps (coherent trajectory)
    assert "<IP_1>" in evs[0]["reasoning"] and "<IP_1>" in evs[1]["observation"]


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
