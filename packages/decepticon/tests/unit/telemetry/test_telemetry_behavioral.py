"""Tests for ground-truth signal capture: findings, phase, HITL, consent."""

from __future__ import annotations

import json
from typing import Any

from decepticon.telemetry.config import (
    TelemetryConfig,
    TelemetryMode,
    persisted_mode,
    resolve_config,
    set_persisted_mode,
)
from decepticon.telemetry.sink import TelemetrySink


def _cfg(mode: TelemetryMode, endpoint: str | None = "https://gw.example") -> TelemetryConfig:
    return TelemetryConfig(
        mode=mode,
        endpoint=endpoint,
        install_id="1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
        version="1.1.13",
        os_name="linux",
    )


def _events(sent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for env in sent for e in env["events"]]


# ── findings (ground-truth structured classification, Tier A) ────────────────


def test_record_finding_forwards_structured_classification() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC), transport=lambda _u, b: sent.append(json.loads(b))
    )
    sink.record_finding(
        severity="high",
        cwe=["CWE-89"],
        mitre=["T1190"],
        phase="initial-access",
        confidence="verified",
        detected=False,
        agent="exploit",
    )
    sink.close()
    ev = _events(sent)[0]
    assert ev["type"] == "finding.created"
    assert ev["severity"] == "high"
    assert ev["cwe"] == ["CWE-89"]
    assert ev["mitre_techniques"] == ["T1190"]
    assert ev["phase"] == "initial-access"
    assert ev["confidence"] == "verified"
    assert ev["detected"] == "no"
    assert ev["agent"] == "exploit"


def test_record_finding_available_at_basic_tier() -> None:
    # Finding classification is structural ground truth → Tier A (basic).
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC), transport=lambda _u, b: sent.append(json.loads(b))
    )
    sink.record_finding(severity="critical")
    sink.close()
    assert sent and sent[0]["tier"] == "A"
    assert _events(sent)[0]["severity"] == "critical"


# ── OPPLAN phase (where the engagement is, Tier A) ───────────────────────────


def test_record_phase_maps_to_opplan_update() -> None:
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC), transport=lambda _u, b: sent.append(json.loads(b))
    )
    sink.record_phase("recon", "pending", "decepticon")
    sink.close()
    ev = _events(sent)[0]
    assert ev["type"] == "opplan.update"
    assert ev["phase"] == "recon"
    # OPPLAN status maps to its own field (not the tool-result ok/error status).
    assert ev["status_objective"] == "pending"
    assert "status" not in ev


# ── persistent consent ───────────────────────────────────────────────────────


def test_persisted_mode_roundtrip(tmp_path) -> None:
    env = {"DECEPTICON_HOME": str(tmp_path)}
    assert persisted_mode(env) is None
    set_persisted_mode(TelemetryMode.RESEARCH, env)
    assert persisted_mode(env) is TelemetryMode.RESEARCH
    cfg = resolve_config({**env, "DECEPTICON_TELEMETRY_ENDPOINT": "https://gw"})
    assert cfg.mode is TelemetryMode.RESEARCH and cfg.enabled is True


def test_off_overrides_persisted_mode(tmp_path) -> None:
    env = {"DECEPTICON_HOME": str(tmp_path)}
    set_persisted_mode(TelemetryMode.RESEARCH, env)
    set_persisted_mode(TelemetryMode.OFF, env)
    assert (
        resolve_config({**env, "DECEPTICON_TELEMETRY_ENDPOINT": "https://gw"}).mode
        is TelemetryMode.OFF
    )


def test_env_overrides_persisted_mode(tmp_path) -> None:
    env = {"DECEPTICON_HOME": str(tmp_path), "DECEPTICON_TELEMETRY": "basic"}
    set_persisted_mode(TelemetryMode.RESEARCH, env)
    assert (
        resolve_config({**env, "DECEPTICON_TELEMETRY_ENDPOINT": "https://gw"}).mode
        is TelemetryMode.BASIC
    )


# ── client runtime dims (arch / py) ──────────────────────────────────────────


def test_envelope_includes_arch_and_py_when_set() -> None:
    sent: list[dict[str, Any]] = []
    cfg = TelemetryConfig(
        mode=TelemetryMode.BASIC,
        endpoint="https://gw.example",
        install_id="1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
        version="1.1.13",
        os_name="linux",
        arch="x86_64",
        py_version="3.13.1",
    )
    sink = TelemetrySink(cfg, transport=lambda _u, b: sent.append(json.loads(b)))
    sink.record_finding(severity="high")
    sink.close()
    client = sent[0]["client"]
    assert client["arch"] == "x86_64"
    assert client["py"] == "3.13.1"


def test_envelope_omits_arch_and_py_when_unset() -> None:
    # Defaults are empty → keys must be absent so the gateway's strict schema
    # never sees an empty value.
    sent: list[dict[str, Any]] = []
    sink = TelemetrySink(
        _cfg(TelemetryMode.BASIC), transport=lambda _u, b: sent.append(json.loads(b))
    )
    sink.record_finding(severity="high")
    sink.close()
    client = sent[0]["client"]
    assert "arch" not in client
    assert "py" not in client


def test_resolve_config_populates_arch_and_py(tmp_path) -> None:
    cfg = resolve_config(
        {
            "DECEPTICON_HOME": str(tmp_path),
            "DECEPTICON_TELEMETRY": "basic",
            "DECEPTICON_TELEMETRY_ENDPOINT": "https://gw",
        }
    )
    # py_version is always the running interpreter's version; arch is the slug or
    # empty (never a schema-violating value).
    assert cfg.py_version.count(".") >= 1
    import re

    assert cfg.arch == "" or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", cfg.arch)
