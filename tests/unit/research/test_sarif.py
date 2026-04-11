"""Unit tests for SARIF → KnowledgeGraph ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from decepticon.tools.research.graph import KnowledgeGraph, NodeKind, Severity
from decepticon.tools.research.sarif import ingest_sarif, ingest_sarif_file


def _minimal_run(rule_id: str, severity_tag: str, level: str) -> dict:
    return {
        "tool": {
            "driver": {
                "name": "semgrep",
                "rules": [
                    {
                        "id": rule_id,
                        "shortDescription": {"text": "Test"},
                        "fullDescription": {"text": "Long desc"},
                        "help": {"text": "fix it"},
                        "properties": {
                            "tags": ["cwe:CWE-89", severity_tag],
                            "security-severity": "8.5",
                        },
                    }
                ],
            }
        },
        "results": [
            {
                "ruleId": rule_id,
                "level": level,
                "message": {"text": "Tainted input reaches sink"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": "app/views.py"},
                            "region": {"startLine": 42, "endLine": 44},
                        }
                    }
                ],
            }
        ],
    }


class TestIngest:
    def test_basic_result_creates_nodes(self) -> None:
        g = KnowledgeGraph()
        n = ingest_sarif({"runs": [_minimal_run("sqli", "HIGH", "error")]}, g)
        assert n == 1
        vulns = g.by_kind(NodeKind.VULNERABILITY)
        assert len(vulns) == 1
        vuln = vulns[0]
        assert vuln.props["file"] == "app/views.py"
        assert vuln.props["start_line"] == 42
        assert "CWE-89" in vuln.props["cwe"]
        assert vuln.props["scanner"] == "semgrep"

    def test_security_severity_trumps_level(self) -> None:
        run = _minimal_run("x", "HIGH", "note")  # note would normally be info
        g = KnowledgeGraph()
        ingest_sarif({"runs": [run]}, g)
        vuln = g.by_kind(NodeKind.VULNERABILITY)[0]
        # security-severity=8.5 → HIGH via _severity_from_score
        assert vuln.props["severity"] == Severity.HIGH.value

    def test_code_location_and_file_nodes_created(self) -> None:
        g = KnowledgeGraph()
        ingest_sarif({"runs": [_minimal_run("x", "HIGH", "error")]}, g)
        assert len(g.by_kind(NodeKind.CODE_LOCATION)) == 1
        assert len(g.by_kind(NodeKind.SOURCE_FILE)) == 1

    def test_scanner_hint_overrides_driver(self) -> None:
        g = KnowledgeGraph()
        ingest_sarif(
            {"runs": [_minimal_run("x", "HIGH", "error")]},
            g,
            scanner_hint="custom-scanner",
        )
        vuln = g.by_kind(NodeKind.VULNERABILITY)[0]
        assert vuln.props["scanner"] == "custom-scanner"

    def test_dedup_across_scans(self) -> None:
        g = KnowledgeGraph()
        sarif = {"runs": [_minimal_run("x", "HIGH", "error")]}
        ingest_sarif(sarif, g)
        ingest_sarif(sarif, g)  # re-ingest same file
        # Same (scanner, rule, file, line) → single vuln node
        assert len(g.by_kind(NodeKind.VULNERABILITY)) == 1

    def test_multiple_results_ingested(self) -> None:
        run = _minimal_run("sqli", "HIGH", "error")
        run["results"].append(
            {
                "ruleId": "xss",
                "level": "warning",
                "message": {"text": "DOM XSS"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": "ui/index.js"},
                            "region": {"startLine": 10},
                        }
                    }
                ],
            }
        )
        g = KnowledgeGraph()
        n = ingest_sarif({"runs": [run]}, g)
        assert n == 2
        assert len(g.by_kind(NodeKind.VULNERABILITY)) == 2

    def test_result_without_location(self) -> None:
        run = _minimal_run("rule", "HIGH", "error")
        run["results"][0]["locations"] = []
        g = KnowledgeGraph()
        ingest_sarif({"runs": [run]}, g)
        # Still creates a vuln; no code_location/file nodes
        assert len(g.by_kind(NodeKind.VULNERABILITY)) == 1
        assert len(g.by_kind(NodeKind.CODE_LOCATION)) == 0


class TestIngestFile:
    def test_reads_sarif_from_disk(self, tmp_path: Path) -> None:
        sarif = {"runs": [_minimal_run("sqli", "HIGH", "error")]}
        path = tmp_path / "report.sarif"
        path.write_text(json.dumps(sarif), encoding="utf-8")
        g = KnowledgeGraph()
        n = ingest_sarif_file(path, g)
        assert n == 1

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        g = KnowledgeGraph()
        n = ingest_sarif_file(tmp_path / "missing.sarif", g)
        assert n == 0

    def test_corrupt_file_returns_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.sarif"
        path.write_text("not json", encoding="utf-8")
        g = KnowledgeGraph()
        n = ingest_sarif_file(path, g)
        assert n == 0
