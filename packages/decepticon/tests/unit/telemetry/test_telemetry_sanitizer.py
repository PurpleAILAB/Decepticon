"""Tests for decepticon.telemetry.sanitizer — mapping + Tier-C no-leak gate."""

from __future__ import annotations

import pytest

from decepticon.telemetry.sanitizer import event_to_tier_a, scan_tier_c


def test_tool_call_keeps_only_tool() -> None:
    rec = {
        "type": "tool.call",
        "ts": 1.0,
        "agent": "recon",
        "payload": {"tool": "bash", "args": {"command": "<str:23>", "timeout": 30}},
    }
    ev = event_to_tier_a(rec)
    assert ev == {"type": "tool.call", "ts": 1.0, "agent": "recon", "tool": "bash"}
    assert "args" not in ev  # argument structure never forwarded


def test_tool_result_normalizes_status_and_buckets_output() -> None:
    ev = event_to_tier_a(
        {
            "type": "tool.result",
            "ts": 2.0,
            "payload": {"tool": "bash", "status": "success", "output_chars": 2048},
        }
    )
    assert ev is not None
    assert ev["status"] == "ok"  # success -> ok
    assert ev["output_bucket"] == "1k-10k"  # exact size bucketed


def test_command_status_is_dropped() -> None:
    ev = event_to_tier_a(
        {"type": "tool.result", "ts": 1.0, "payload": {"tool": "x", "status": "command"}}
    )
    assert ev is not None
    assert "status" not in ev


def test_llm_call_maps_model_and_msgs_bucket() -> None:
    ev = event_to_tier_a(
        {"type": "llm.call", "ts": 1.0, "payload": {"messages": 12, "model": "claude-opus-4-8"}}
    )
    assert ev is not None
    assert ev["model"] == "claude-opus-4-8"
    assert ev["msgs_bucket"] == "10-50"


def test_mitre_cwe_cve_passthrough_when_present() -> None:
    ev = event_to_tier_a(
        {
            "type": "finding.created",
            "ts": 1.0,
            "payload": {
                "tool": "validate_finding",
                "mitre_techniques": ["T1046"],
                "cwe": ["CWE-89"],
                "cve": ["CVE-2021-44228"],
            },
        }
    )
    assert ev is not None
    assert ev["mitre_techniques"] == ["T1046"]
    assert ev["cwe"] == ["CWE-89"]
    assert ev["cve"] == ["CVE-2021-44228"]


def test_malformed_mitre_dropped() -> None:
    ev = event_to_tier_a(
        {"type": "agent.turn", "ts": 1.0, "payload": {"mitre_techniques": ["not-a-technique"]}}
    )
    assert ev is not None
    assert "mitre_techniques" not in ev


def test_unknown_event_type_dropped() -> None:
    assert event_to_tier_a({"type": "mystery.event", "ts": 1.0, "payload": {}}) is None


# ── Tier-C no-leak gate (mirrors the gateway corpus) ─────────────────────────

FORBIDDEN = [
    ("ipv4", {"tool": "10.0.0.5"}),
    ("domain", {"tool": "target.example.com"}),
    ("email", "admin@corp.internal"),
    ("aws_access_key", "AKIAIOSFODNN7EXAMPLE"),
    ("private_key", "-----BEGIN RSA PRIVATE KEY-----"),
    ("user_pass", "admin:hunter2@db"),
    ("jwt", "eyJhbGciOi.eyJzdWIiOiI.SflKxwRJSMeKKF2QT4"),
]


@pytest.mark.parametrize("_klass,payload", FORBIDDEN)
def test_tier_c_caught(_klass: str, payload: object) -> None:
    hit = scan_tier_c(payload)
    assert hit is not None
    assert hit[1] != ""  # path reported


def test_tier_c_never_returns_the_value() -> None:
    hit = scan_tier_c({"events": [{"deep": "10.20.30.40"}]})
    assert hit is not None
    assert "10.20.30.40" not in str(hit)


def test_clean_tier_a_passes() -> None:
    clean = {
        "type": "tool.call",
        "ts": 1.0,
        "agent": "recon",
        "tool": "nmap",
        "status": "ok",
        "cwe": ["CWE-89"],
    }
    assert scan_tier_c(clean) is None
