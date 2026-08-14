"""Unit tests for the retrospective tool-diversity analysis.

Covers ``_analyze_tool_diversity`` — the measurement behind the retro
report's Tool Utilization section — and its wiring into
``retro_analyze_events``.
"""

from __future__ import annotations

import json

from decepticon.tools.research.retrospective import (
    _analyze_tool_diversity,
    retro_analyze_events,
)


def _bash_call(agent: str, progs: list[str] | None, ts: float = 1.0) -> dict:
    payload: dict = {"tool": "bash", "args": {"command": "<str:10>"}}
    if progs:
        payload["progs"] = progs
    return {"type": "tool.call", "ts": ts, "agent": agent, "payload": payload}


def _tool_call(agent: str, tool: str, ts: float = 1.0) -> dict:
    return {"type": "tool.call", "ts": ts, "agent": agent, "payload": {"tool": tool}}


def _issues_by_category(issues: list[dict], category: str) -> list[dict]:
    return [i for i in issues if i.get("category") == category]


# ── stats block ──────────────────────────────────────────────────────────


def test_stats_block_reports_programs_and_per_agent_breakdown():
    events = [
        _bash_call("recon", ["nmap", "curl"]),
        _bash_call("recon", ["curl"]),
        _bash_call("exploit", ["sqlmap", "python3"]),
        _tool_call("exploit", "cve_lookup"),
    ]
    issues, stats = _analyze_tool_diversity(events)

    assert stats["bash_calls"] == 3
    assert stats["programs_used"] == {"curl": 2, "nmap": 1, "sqlmap": 1, "python3": 1}
    assert sorted(stats["security_programs_used"]) == ["nmap", "sqlmap"]
    assert stats["web_scanners_used"] == []
    assert stats["per_agent"]["recon"]["programs"] == {"curl": 2, "nmap": 1}
    assert stats["per_agent"]["exploit"]["distinct_tools"] == ["bash", "cve_lookup"]
    # Small engagement — below the activity floors, no under-use verdicts.
    assert _issues_by_category(issues, "tool_underuse") == []


def test_empty_events_produce_empty_stats_and_no_issues():
    issues, stats = _analyze_tool_diversity([])
    assert issues == []
    assert stats["bash_calls"] == 0
    assert stats["programs_used"] == {}


# ── arsenal-never-touched verdict ────────────────────────────────────────


def test_handrolled_only_engagement_fires_high_severity_underuse():
    # 25 bash calls, generic utilities captured (proving capture works),
    # zero security programs.
    events = [_bash_call("exploit", ["curl", "python3"], ts=float(i)) for i in range(25)]
    issues, stats = _analyze_tool_diversity(events)

    underuse = _issues_by_category(issues, "tool_underuse")
    severities = {i["severity"] for i in underuse}
    # High: arsenal never touched. Medium: curl probing with no web
    # scanner. Low: exploit specialty tools unused. All three fire.
    assert severities == {"high", "medium", "low"}
    high = next(i for i in underuse if i["severity"] == "high")
    assert "hand-rolled" in high["title"]
    assert stats["security_programs_used"] == []


def test_arsenal_used_suppresses_arsenal_verdict():
    events = [_bash_call("recon", ["curl"], ts=float(i)) for i in range(24)]
    events.append(_bash_call("recon", ["ffuf"]))
    issues, _ = _analyze_tool_diversity(events)

    high = [i for i in _issues_by_category(issues, "tool_underuse") if i["severity"] == "high"]
    assert high == []


def test_zero_progs_at_all_does_not_fire_arsenal_verdict():
    """Pre-capture logs carry no progs field at all; with no generic
    utilities recorded either, capture liveness is unproven — the
    arsenal/web-scanner verdicts stay silent. (The specialty-tool verdict
    still fires: LangChain tool usage is visible without progs.)"""
    events = [_bash_call("recon", None, ts=float(i)) for i in range(25)]
    issues, _ = _analyze_tool_diversity(events)
    underuse = _issues_by_category(issues, "tool_underuse")
    assert {i["severity"] for i in underuse} == {"low"}


# ── web scanner verdict ──────────────────────────────────────────────────


def test_web_probing_without_scanners_fires_medium():
    # 12 curl probes + nmap (suppresses the arsenal verdict, not the
    # web-scanner one).
    events = [_bash_call("recon", ["curl"], ts=float(i)) for i in range(12)]
    events.append(_bash_call("recon", ["nmap"]))
    issues, _ = _analyze_tool_diversity(events)

    medium = [i for i in _issues_by_category(issues, "tool_underuse") if i["severity"] == "medium"]
    assert any("content-discovery" in i["title"] for i in medium)


def test_web_probing_with_scanner_fires_nothing():
    events = [_bash_call("recon", ["curl"], ts=float(i)) for i in range(12)]
    events.append(_bash_call("recon", ["feroxbuster"]))
    issues, _ = _analyze_tool_diversity(events)
    underuse = _issues_by_category(issues, "tool_underuse")
    # No arsenal verdict (feroxbuster is a security program), no
    # web-scanner verdict. Only the low-severity specialty-tool verdict
    # may fire (recon used none of its structured tools).
    assert {i["severity"] for i in underuse} <= {"low"}


# ── specialty-tool verdict ───────────────────────────────────────────────


def test_specialty_tools_never_used_fires_low():
    # recon made ≥10 tool calls but used none of its structured tools.
    events = [_bash_call("recon", ["nmap"], ts=float(i)) for i in range(12)]
    issues, _ = _analyze_tool_diversity(events)

    low = [i for i in _issues_by_category(issues, "tool_underuse") if i["severity"] == "low"]
    assert len(low) == 1
    assert "recon" in low[0]["title"]
    assert "web_search" in low[0]["evidence"]["unused_tools"]


def test_specialty_tool_use_suppresses_verdict():
    events = [_bash_call("recon", ["nmap"], ts=float(i)) for i in range(11)]
    events.append(_tool_call("recon", "web_search"))
    events.append(_tool_call("recon", "extract_urls_from_js"))
    issues, _ = _analyze_tool_diversity(events)

    low = [i for i in _issues_by_category(issues, "tool_underuse") if i["severity"] == "low"]
    assert len(low) == 1  # still fires — other specialty tools remain unused
    unused = low[0]["evidence"]["unused_tools"]
    assert "web_search" not in unused
    assert "extract_urls_from_js" not in unused


def test_low_activity_agent_skips_specialty_verdict():
    events = [_bash_call("recon", ["nmap"], ts=1.0) for _ in range(3)]
    issues, _ = _analyze_tool_diversity(events)
    assert _issues_by_category(issues, "tool_underuse") == []


# ── wiring into retro_analyze_events ─────────────────────────────────────


def test_retro_analyze_events_includes_tool_diversity(tmp_path):
    events = [_bash_call("exploit", ["curl"], ts=float(i)) for i in range(25)]
    (tmp_path / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8"
    )

    out = json.loads(retro_analyze_events.invoke({"workspace": str(tmp_path)}))

    assert out["status"] == "analyzed"
    assert out["tool_diversity"]["bash_calls"] == 25
    assert out["tool_diversity"]["programs_used"] == {"curl": 25}
    categories = {i["category"] for i in out["issues"]}
    assert "tool_underuse" in categories
