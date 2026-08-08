from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.cve import Exploitability
from decepticon_core.types.kg import KnowledgeGraph, NodeKind


@pytest.mark.asyncio
async def test_cve_enrichment_records_workspace_evidence(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("flask==2.0.0\n", encoding="utf-8")
    monkeypatch.setenv("DECEPTICON_WORKSPACE_PATH", str(tmp_path))
    graph = KnowledgeGraph()

    @contextmanager
    def fake_transaction():
        yield graph

    async def fake_lookup_package(package: str, version: str, ecosystem: str) -> list[str]:
        assert (package, version, ecosystem) == ("flask", "2.0.0", "PyPI")
        return ["CVE-2024-1111"]

    async def fake_lookup_cves(cve_ids: list[str], concurrency: int = 6) -> list[Exploitability]:
        assert cve_ids == ["CVE-2024-1111"]
        return [Exploitability(cve_id="CVE-2024-1111", cvss=9.8, epss=0.8, kev=True)]

    monkeypatch.setattr(research_tools, "graph_transaction", fake_transaction)
    monkeypatch.setattr(research_tools.cve_mod, "lookup_package", fake_lookup_package)
    monkeypatch.setattr(research_tools.cve_mod, "lookup_cves", fake_lookup_cves)

    payload = json.loads(
        await research_tools.cve_enrich_dependencies.ainvoke(
            {"path": str(manifest), "min_score": 7.0}
        )
    )

    assert payload["manifest_path"] == "requirements.txt"
    assert payload["results"] == [
        {
            "dependency": "flask@2.0.0",
            "ecosystem": "PyPI",
            "cve": "CVE-2024-1111",
            "score": 10.0,
            "severity": "low",
            "raw_severity": "critical",
            "kev": True,
            "dependency_chain": ["flask@2.0.0"],
            "reachability_level": "declared",
        }
    ]
    vulnerability = graph.by_kind(NodeKind.VULNERABILITY)[0]
    assert vulnerability.props["manifest_path"] == "requirements.txt"
    assert vulnerability.props["reachability_level"] == "declared"
    assert vulnerability.props["severity"] == "low"
    assert vulnerability.props["raw_severity"] == "critical"
