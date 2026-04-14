"""Tests for the Tier 2 kg_ingest_* functions (Kali tool output parsers)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.research import tools as research_tools
from decepticon.tools.research.graph import KnowledgeGraph, NodeKind


class _FakeStore:
    def __init__(self):
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


def _configure_kg(monkeypatch, tmp_path):
    from decepticon.tools.research import _state as state

    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    return fake


class TestKgIngestDnsx:
    def test_creates_host_nodes_with_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "dnsx.jsonl"
        out.write_text(
            "\n".join(
                [
                    json.dumps({"host": "api.example.com", "a": ["10.0.0.1"]}),
                    json.dumps({"host": "web.example.com", "cname": ["edge.cdn.example.net"]}),
                ]
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_dnsx.invoke({"path": str(out)}))
        assert payload["hosts_added"] == 2
        graph = fake.load_graph()
        labels = {n.label for n in graph.by_kind(NodeKind.HOST)}
        assert "api.example.com" in labels
        assert "web.example.com" in labels
        assert "edge.cdn.example.net" in labels

    def test_missing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_kg(monkeypatch, tmp_path)
        payload = json.loads(
            research_tools.kg_ingest_dnsx.invoke({"path": str(tmp_path / "missing")})
        )
        assert "error" in payload


class TestKgIngestKatana:
    def test_creates_url_entrypoints(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "katana.jsonl"
        out.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "endpoint": "https://example.com/admin",
                            "method": "GET",
                        }
                    ),
                    json.dumps(
                        {
                            "endpoint": "https://example.com/login",
                            "method": "POST",
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_katana.invoke({"path": str(out)}))
        assert payload["urls_added"] == 2
        graph = fake.load_graph()
        urls = {n.label for n in graph.by_kind(NodeKind.URL)}
        assert "https://example.com/admin" in urls
        assert "https://example.com/login" in urls


class TestKgIngestMasscan:
    def test_parses_array_format(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "masscan.json"
        out.write_text(
            json.dumps(
                [
                    {
                        "ip": "10.0.0.5",
                        "ports": [
                            {"port": 80, "proto": "tcp", "status": "open"},
                            {"port": 443, "proto": "tcp", "status": "open"},
                        ],
                    },
                    {
                        "ip": "10.0.0.6",
                        "ports": [{"port": 22, "proto": "tcp", "status": "open"}],
                    },
                ]
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_masscan.invoke({"path": str(out)}))
        assert payload["hosts_added"] == 2
        assert payload["services_added"] == 3
        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.HOST)) == 2
        assert len(graph.by_kind(NodeKind.SERVICE)) == 3


class TestKgIngestFfuf:
    def test_creates_url_nodes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "ffuf.json"
        out.write_text(
            json.dumps(
                {
                    "results": [
                        {"url": "https://example.com/admin", "status": 200, "length": 1024},
                        {"url": "https://example.com/api", "status": 401, "length": 50},
                    ]
                }
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_ffuf.invoke({"path": str(out)}))
        assert payload["urls_added"] == 2
        graph = fake.load_graph()
        urls = {n.label for n in graph.by_kind(NodeKind.URL)}
        assert "https://example.com/admin" in urls


class TestKgIngestTestssl:
    def test_creates_high_severity_vulns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "testssl.json"
        out.write_text(
            json.dumps(
                [
                    {
                        "id": "heartbleed",
                        "severity": "CRITICAL",
                        "finding": "Heartbleed (CVE-2014-0160) detected",
                    },
                    {"id": "tls1_0", "severity": "HIGH", "finding": "TLS 1.0 enabled"},
                    {"id": "cipher_suites_ok", "severity": "OK", "finding": "Modern ciphers"},
                ]
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_testssl.invoke({"path": str(out)}))
        assert payload["vulns_added"] == 2
        graph = fake.load_graph()
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert len(vulns) == 2

    def test_links_to_host_when_target_passed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "testssl.json"
        out.write_text(
            json.dumps(
                [
                    {
                        "id": "heartbleed",
                        "severity": "CRITICAL",
                        "finding": "Heartbleed detected",
                    },
                ]
            ),
            encoding="utf-8",
        )
        payload = json.loads(
            research_tools.kg_ingest_testssl.invoke(
                {"path": str(out), "target": "api.example.com:443"}
            )
        )
        assert payload["vulns_added"] == 1
        assert payload["linked_to_host"] == 1
        graph = fake.load_graph()
        hosts = graph.by_kind(NodeKind.HOST)
        vulns = graph.by_kind(NodeKind.VULNERABILITY)
        assert len(hosts) == 1
        assert hosts[0].label == "api.example.com"
        # Vuln reachable from host via HAS_VULN
        out_edges = [e for e in graph.edges.values() if e.src == hosts[0].id]
        assert any(e.dst == vulns[0].id for e in out_edges)

    def test_reads_target_from_envelope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "testssl.json"
        out.write_text(
            json.dumps(
                {
                    "targetHost": "tls.example.com",
                    "scanResult": [
                        {
                            "vulnerabilities": [
                                {
                                    "id": "cbc_chacha",
                                    "severity": "HIGH",
                                    "finding": "Weak CBC suites",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        payload = json.loads(research_tools.kg_ingest_testssl.invoke({"path": str(out)}))
        assert payload["vulns_added"] == 1
        assert payload["linked_to_host"] == 1
        graph = fake.load_graph()
        assert len(graph.by_kind(NodeKind.HOST)) == 1


class TestKgIngestCrackmapexec:
    def test_parses_success_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "cme.log"
        out.write_text(
            "SMB         10.0.0.10       445    DC01             [+] CORP\\alice:Password1!\n"
            "SMB         10.0.0.10       445    DC01             [+] CORP\\bob:Spring2024 (Pwn3d!)\n"
            "SMB         10.0.0.11       445    SRV01            [-] CORP\\eve:wrong\n",
            encoding="utf-8",
        )
        payload = json.loads(
            research_tools.kg_ingest_crackmapexec.invoke({"path": str(out), "protocol": "smb"})
        )
        assert payload["creds_added"] == 2
        assert payload["admin_creds_added"] == 1
        graph = fake.load_graph()
        creds = graph.by_kind(NodeKind.CREDENTIAL)
        assert len(creds) == 2


class TestKgIngestAsrep:
    def test_parses_krb5asrep_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _configure_kg(monkeypatch, tmp_path)
        out = tmp_path / "asrep.txt"
        out.write_text(
            "$krb5asrep$23$alice@CORP.LOCAL:abcdef0123456789$abcdef\n"
            "$krb5asrep$23$bob@CORP.LOCAL:fedcba9876543210$fedcba\n"
            "ignored line\n",
            encoding="utf-8",
        )
        payload = json.loads(
            research_tools.kg_ingest_asrep_hashes.invoke({"path": str(out), "domain": "CORP"})
        )
        assert payload["asrep_hashes_added"] == 2
        graph = fake.load_graph()
        creds = graph.by_kind(NodeKind.CREDENTIAL)
        assert len(creds) == 2
        assert all("krb5asrep" in str(c.props.get("secret_type", "")) for c in creds)
        # Regression guard: the label must be the username, not the
        # encrypted-timestamp hex tail (old $4 off-by-one).
        labels = {c.label for c in creds}
        assert "CORP.LOCAL\\alice" in labels
        assert "CORP.LOCAL\\bob" in labels
