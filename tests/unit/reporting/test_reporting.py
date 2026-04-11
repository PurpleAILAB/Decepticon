"""Tests for reporting: HackerOne markdown, Bugcrowd CSV, executive, timeline."""

from __future__ import annotations

from decepticon.tools.reporting.bugcrowd import render_bugcrowd_csv
from decepticon.tools.reporting.executive import render_executive_summary
from decepticon.tools.reporting.hackerone import HackerOneReport, render_hackerone_markdown
from decepticon.tools.reporting.timeline import extract_timeline
from decepticon.tools.research.graph import KnowledgeGraph, Node, NodeKind


def _seeded_graph() -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.upsert_node(
        Node.make(
            NodeKind.VULNERABILITY,
            "SSRF → IMDS chain",
            severity="critical",
            validated=True,
            cvss_score=10.0,
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
            summary="SSRF enables cloud metadata access",
            poc_command="curl https://target/fetch?url=http://169.254.169.254/",
            cwe=["CWE-918"],
            url="/api/fetch",
        )
    )
    g.upsert_node(Node.make(NodeKind.VULNERABILITY, "XSS", severity="low"))
    g.upsert_node(Node.make(NodeKind.CVE, "CVE-2024-1234", score=9.8))
    g.upsert_node(
        Node.make(
            NodeKind.ATTACK_PATH,
            "entry → SSRF → IMDS (cost 1.32)",
            total_cost=1.32,
            length=4,
        )
    )
    return g


class TestHackerOne:
    def test_full_report_structure(self) -> None:
        g = _seeded_graph()
        vuln = g.by_kind(NodeKind.VULNERABILITY)[0]
        md = render_hackerone_markdown(vuln, graph=g)
        assert "# SSRF → IMDS chain" in md
        assert "**Severity:**" in md
        assert "## Summary" in md
        assert "## Steps to Reproduce" in md
        assert "## Proof of Concept" in md
        assert "CVSS:3.1" in md

    def test_in_memory_to_markdown(self) -> None:
        r = HackerOneReport(
            title="Test",
            severity="high",
            cvss_score=7.5,
            summary="x",
            steps=["a", "b"],
            impact="y",
        )
        md = r.to_markdown()
        assert "1. a" in md
        assert "2. b" in md
        assert "Test" in md


class TestBugcrowd:
    def test_csv_has_header_and_rows(self) -> None:
        g = _seeded_graph()
        csv = render_bugcrowd_csv(g, min_severity="low")
        lines = csv.splitlines()
        assert lines[0].startswith("title,severity,cwe")
        # Header + at least the critical + low vuln
        assert len(lines) >= 3

    def test_min_severity_filter(self) -> None:
        g = _seeded_graph()
        csv = render_bugcrowd_csv(g, min_severity="critical")
        lines = csv.splitlines()
        # Only critical should pass
        assert len(lines) == 2


class TestExecutive:
    def test_renders_with_counts(self) -> None:
        g = _seeded_graph()
        md = render_executive_summary(g, engagement_name="acme")
        assert "acme" in md
        assert "CRITICAL" in md
        assert "LOW" in md
        assert "Top Critical Chains" in md
        assert "Top CVE Exposure" in md

    def test_empty_graph(self) -> None:
        g = KnowledgeGraph()
        md = render_executive_summary(g)
        assert "No findings" in md


class TestTimeline:
    def test_nonempty(self) -> None:
        g = _seeded_graph()
        events = extract_timeline(g)
        assert len(events) >= 3
        assert events == sorted(events, key=lambda e: e.ts)
