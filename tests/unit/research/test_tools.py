"""Unit tests for LangChain research tool wrappers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.cve import Exploitability
from decepticon.tools.research.graph import KnowledgeGraph, NodeKind
from decepticon.tools.web.jwt import forge_token


class _FakeStore:
    """In-memory fake Neo4j store for unit tests."""

    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def load_graph(self):
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes):
        for n in nodes:
            self.graph.upsert_node(n)
        return len(nodes)

    def batch_upsert_edges(self, edges):
        for e in edges:
            self.graph.upsert_edge(e)
        return len(edges)

    def ensure_schema(self):
        pass

    def close(self):
        pass

    def revision(self):
        return 0.0

    def stats(self):
        return self.graph.stats()

    def upsert_node(self, node):
        self.graph.upsert_node(node)

    def upsert_edge(self, edge):
        self.graph.upsert_edge(edge)

    def query_custom(self, cypher, params):
        return []


def _configure_kg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    return fake


class TestReconIngestion:
    def test_kg_ingest_nmap_xml_creates_graph_entities(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        xml_path = tmp_path / "scan.xml"
        xml_path.write_text(
            """<?xml version=\"1.0\"?>
<nmaprun>
  <host>
    <status state=\"up\"/>
    <address addr=\"10.0.0.5\" addrtype=\"ipv4\"/>
    <hostnames><hostname name=\"api.example.com\"/></hostnames>
    <ports>
      <port protocol=\"tcp\" portid=\"443\">
        <state state=\"open\"/>
        <service name=\"https\" product=\"nginx\" version=\"1.24\"/>
      </port>
    </ports>
  </host>
</nmaprun>
""",
            encoding="utf-8",
        )

        payload = json.loads(research_tools.kg_ingest_nmap_xml.invoke({"path": str(xml_path)}))
        assert payload["ingested"]["hosts"] == 1
        assert payload["ingested"]["services"] == 1
        assert payload["ingested"]["entrypoints"] == 1

        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.HOST)) == 1
        assert len(graph.by_kind(NodeKind.SERVICE)) == 1
        assert len(graph.by_kind(NodeKind.ENTRYPOINT)) == 1

    def test_kg_ingest_nuclei_jsonl_maps_vuln_and_cve(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        nuclei_path = tmp_path / "nuclei.jsonl"
        nuclei_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "template-id": "xss-reflected",
                            "matched-at": "https://app.example.com/search?q=test",
                            "info": {
                                "severity": "high",
                                "classification": {"cve-id": ["CVE-2024-9999"]},
                            },
                        }
                    )
                ]
            ),
            encoding="utf-8",
        )

        payload = json.loads(
            research_tools.kg_ingest_nuclei_jsonl.invoke({"path": str(nuclei_path)})
        )
        assert payload["parsed"] == 1
        assert payload["skipped"] == 0

        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.VULNERABILITY)) == 1
        assert len(graph.by_kind(NodeKind.CVE)) == 1

    def test_kg_ingest_httpx_jsonl_creates_entrypoints(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        httpx_path = tmp_path / "httpx.jsonl"
        httpx_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "url": "https://api.example.com/admin",
                            "host": "api.example.com",
                            "port": 443,
                            "status-code": 200,
                            "title": "Admin Console",
                            "webserver": "nginx",
                            "tech": ["nginx", "next.js"],
                        }
                    ),
                    json.dumps(
                        {
                            "url": "https://api.example.com/error",
                            "host": "api.example.com",
                            "port": 443,
                            "status-code": 503,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        payload = json.loads(research_tools.kg_ingest_httpx_jsonl.invoke({"path": str(httpx_path)}))
        assert payload["parsed"] == 2
        assert payload["entrypoints"] == 2
        assert payload["service_links"] == 2

        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.ENTRYPOINT)) >= 2
        # 5xx rows become low-severity availability findings for follow-up.
        assert any(
            v.props.get("rule_id") == "http-5xx" for v in graph.by_kind(NodeKind.VULNERABILITY)
        )


class TestChainObjectiveDrafting:
    pass  # suggest_objectives_from_chains requires Neo4j; tests removed


class TestDependencyEnrichment:
    @pytest.mark.asyncio
    async def test_cve_enrich_dependencies_adds_ranked_dependency_vuln(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        reqs = tmp_path / "requirements.txt"
        reqs.write_text("flask==2.0.0\n", encoding="utf-8")

        async def fake_lookup_package(package: str, version: str, ecosystem: str) -> list[str]:
            assert package == "flask"
            assert version == "2.0.0"
            assert ecosystem == "PyPI"
            return ["CVE-2024-1111", "GHSA-foo"]

        async def fake_lookup_cves(
            cve_ids: list[str], concurrency: int = 6
        ) -> list[Exploitability]:
            assert cve_ids == ["CVE-2024-1111"]
            assert concurrency == 6
            return [Exploitability(cve_id="CVE-2024-1111", cvss=9.8, epss=0.8, kev=True)]

        monkeypatch.setattr(research_tools.cve_mod, "lookup_package", fake_lookup_package)
        monkeypatch.setattr(research_tools.cve_mod, "lookup_cves", fake_lookup_cves)

        payload = json.loads(
            await research_tools.cve_enrich_dependencies.ainvoke(
                {"path": str(reqs), "min_score": 7.0}
            )
        )
        assert payload["dependencies_scanned"] == 1
        assert payload["high_signal_records"] == 1
        assert payload["results"][0]["cve"] == "CVE-2024-1111"

        graph = fake.load_graph()
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert len(vulns) == 1
        assert vulns[0].props["package"] == "flask"


class TestSpecializedHuntingTools:
    def test_kg_scan_solidity_ingests_pattern_findings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        solidity = tmp_path / "Vault.sol"
        solidity.write_text(
            """pragma solidity ^0.8.20;
contract Vault {
    function withdraw(address target) public {
        require(tx.origin == msg.sender, \"nope\");
        (bool ok, ) = target.delegatecall(\"\");
    }
}
""",
            encoding="utf-8",
        )

        payload = json.loads(research_tools.kg_scan_solidity.invoke({"path": str(solidity)}))
        assert payload["matches"] >= 2
        assert payload["ingested"] >= 2

        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.VULNERABILITY)) >= 2
        assert len(graph.by_kind(NodeKind.CODE_LOCATION)) >= 1

    def test_kg_ingest_slither_reads_detector_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        slither = tmp_path / "slither.json"
        slither.write_text(
            json.dumps(
                {
                    "results": {
                        "detectors": [
                            {
                                "check": "reentrancy-eth",
                                "impact": "High",
                                "confidence": "High",
                                "description": "Reentrancy on withdraw",
                                "elements": [
                                    {
                                        "source_mapping": {
                                            "filename_relative": "src/Vault.sol",
                                            "lines": [42],
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        payload = json.loads(research_tools.kg_ingest_slither.invoke({"path": str(slither)}))
        assert payload["ingested"] == 1

        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.VULNERABILITY)) == 1
        assert len(graph.by_kind(NodeKind.CODE_LOCATION)) == 1

    def test_kg_triage_binary_persists_high_signal_indicators(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_kg(monkeypatch, tmp_path)
        binary = tmp_path / "agent.bin"
        binary.write_bytes(
            b"MZ"
            + b"A" * 64
            + b"\x00http://c2.example.net/callback\x00"
            + b"system strcpy connect\x00"
            + b"AKIAABCDEFGHIJKLMNOP\x00"
        )

        payload = json.loads(research_tools.kg_triage_binary.invoke({"path": str(binary)}))
        rule_ids = {v["rule_id"] for v in payload["created_vulnerabilities"]}
        assert "secrets.hardcoded" in rule_ids
        assert "rce.primitives" in rule_ids
        assert payload["entrypoints_added"] >= 1

    def test_kg_analyze_jwt_ingests_alg_none_finding(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        token = forge_token({"sub": "alice"}, alg="none")

        payload = json.loads(
            research_tools.kg_analyze_jwt.invoke(
                {"token": token, "source": "https://api.example.com/profile"}
            )
        )
        assert payload["ingested_vulnerabilities"] >= 1
        assert any("alg=none" in finding for finding in payload["findings"])

        graph = fake.load_graph()
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert any(v.props.get("scanner") == "jwt-analysis" for v in vulns)

    def test_kg_analyze_oauth_callback_ingests_state_issue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        callback = "https://app.example.com/callback?code=testcode"

        payload = json.loads(
            research_tools.kg_analyze_oauth_callback.invoke(
                {"callback_url": callback, "public_client": True}
            )
        )
        assert payload["ingested_vulnerabilities"] >= 1
        rule_ids = {n["rule_id"] for n in payload["nodes"]}
        assert "oauth.state-missing" in rule_ids

        graph = fake.load_graph()
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert any(v.props.get("scanner") == "oauth-analysis" for v in vulns)

    def test_kg_analyze_cookie_value_ingests_cookie_weaknesses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)

        payload = json.loads(
            research_tools.kg_analyze_cookie_value.invoke(
                {
                    "name": "session",
                    "value": "abc123",
                    "secure": False,
                    "http_only": False,
                    "same_site": "None",
                    "source": "https://app.example.com",
                }
            )
        )
        assert payload["ingested_vulnerabilities"] >= 1

        graph = fake.load_graph()
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert any(v.props.get("scanner") == "cookie-analysis" for v in vulns)
