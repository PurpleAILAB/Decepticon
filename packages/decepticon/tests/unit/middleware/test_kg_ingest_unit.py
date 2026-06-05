"""Unit tests for :mod:`kg_internal.ingest` — driver-free.

Covers the adapter registry, dispatcher error paths, and each built-in
adapter's parse-to-observations behaviour via a stub store that
captures the ``record_observations`` payload without hitting Neo4j.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from decepticon.middleware.kg_internal.ingest import (
    _REGISTRY,
    ScannerAdapter,
    _adapt_httpx_jsonl,
    _adapt_nmap_xml,
    _adapt_nuclei_jsonl,
    _adapt_sarif,
    available_scanners,
    ingest,
    register_adapter,
)

# ── Stub store ──────────────────────────────────────────────────────────


class _StubStore:
    """Captures record_observations payload; returns a fixed shape."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record_observations(
        self,
        observations: list[dict[str, Any]],
        *,
        engagement: str,
        created_by: str,
        source_episode_id: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "observations": list(observations),
                "engagement": engagement,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            }
        )
        return {"created": len(observations), "merged": 0, "edges": 0, "revision": "rev-stub"}


# ── Registry ────────────────────────────────────────────────────────────


def test_built_in_adapters_registered_at_import() -> None:
    """The four built-ins land in the registry without any opt-in."""
    names = set(available_scanners())
    assert {"nmap_xml", "nuclei_jsonl", "httpx_jsonl", "sarif"} <= names


def test_register_adapter_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        register_adapter("", _adapt_nmap_xml)


def test_register_adapter_rejects_non_callable() -> None:
    with pytest.raises(ValueError, match="callable"):
        register_adapter("custom", "not callable")  # type: ignore[arg-type]


def test_register_adapter_overwrites_existing() -> None:
    sentinel: ScannerAdapter = lambda *args, **kwargs: {"sentinel": True}  # noqa: E731
    register_adapter("nuclei_jsonl", sentinel)
    assert _REGISTRY["nuclei_jsonl"] is sentinel
    # restore for downstream tests
    register_adapter("nuclei_jsonl", _adapt_nuclei_jsonl)


# ── ingest dispatcher ───────────────────────────────────────────────────


def test_ingest_unknown_scanner_returns_error_with_available_list() -> None:
    result = ingest(
        "made_up_scanner",
        "/dev/null",
        store=_StubStore(),  # type: ignore[arg-type]
        engagement="acme",
        created_by="t",
        source_episode_id="ep",
    )
    assert "error" in result
    assert "unknown scanner_kind" in result["error"]
    assert "available" in result
    assert "nmap_xml" in result["available"]


def test_ingest_missing_file_returns_error(tmp_path: Path) -> None:
    result = ingest(
        "nmap_xml",
        tmp_path / "does-not-exist.xml",
        store=_StubStore(),  # type: ignore[arg-type]
        engagement="acme",
        created_by="t",
        source_episode_id="ep",
    )
    assert "error" in result
    assert "not found" in result["error"]
    assert result["scanner"] == "nmap_xml"


def test_ingest_wraps_result_with_scanner_and_path(tmp_path: Path) -> None:
    nmap_file = tmp_path / "scan.xml"
    nmap_file.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.1" addrtype="ipv4"/>
            <ports>
              <port portid="80" protocol="tcp">
                <state state="open"/>
                <service name="http"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    result = ingest(
        "nmap_xml",
        nmap_file,
        store=_StubStore(),  # type: ignore[arg-type]
        engagement="acme",
        created_by="recon",
        source_episode_id="ep-1",
    )
    assert result["scanner"] == "nmap_xml"
    assert result["path"] == str(nmap_file)


def test_ingest_adapter_exception_is_captured(tmp_path: Path) -> None:
    def boom(path: Path, store: Any, eng: str, cb: str, sep: str) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    register_adapter("boom", boom)
    f = tmp_path / "x.txt"
    f.write_text("x")
    result = ingest(
        "boom",
        f,
        store=_StubStore(),  # type: ignore[arg-type]
        engagement="acme",
        created_by="t",
        source_episode_id="ep",
    )
    assert "error" in result
    assert "kaboom" in result["error"]


# ── nmap_xml adapter ────────────────────────────────────────────────────


def test_nmap_adapter_extracts_host_service_entrypoint(tmp_path: Path) -> None:
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.1" addrtype="ipv4"/>
            <hostnames><hostname name="target.local"/></hostnames>
            <ports>
              <port portid="80" protocol="tcp">
                <state state="open"/>
                <service name="http" product="nginx" version="1.18"/>
              </port>
              <port portid="22" protocol="tcp">
                <state state="open"/>
                <service name="ssh"/>
              </port>
              <port portid="9999" protocol="tcp">
                <state state="closed"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    result = _adapt_nmap_xml(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    assert result["hosts"] == 1
    assert result["services"] == 2  # 80 + 22, closed port skipped
    assert result["entrypoints"] == 1  # 80 is web, 22 is not

    obs = store.calls[0]["observations"]
    kinds = [o["kind"] for o in obs]
    assert kinds.count("Host") == 1
    assert kinds.count("Service") == 2
    assert kinds.count("Entrypoint") == 1
    # Host must carry its outgoing HOSTS edges to both services.
    host_obs = next(o for o in obs if o["kind"] == "Host")
    assert any(e["kind"] == "HOSTS" for e in host_obs.get("edges_out", []))


def test_nmap_adapter_classifies_ai_port_as_technology(tmp_path: Path) -> None:
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.7" addrtype="ipv4"/>
            <ports>
              <port portid="11434" protocol="tcp">
                <state state="open"/>
                <service name="unknown"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_nmap_xml(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]

    obs = store.calls[0]["observations"]
    tech = next(o for o in obs if o["kind"] == "Technology")
    assert tech["key"] == "ai-runtime:ollama"
    assert tech["props"]["detected_by"] == "port-catalog"
    # The owning Service must RUNS-> the Technology so the planner can traverse.
    svc = next(o for o in obs if o["kind"] == "Service")
    assert {
        "to_key": "ai-runtime:ollama",
        "kind": "RUNS",
        "props": {"detected_by": "port-catalog"},
    } in svc.get("edges_out", [])


def test_nmap_adapter_classifies_ai_runtime_banner_on_nonstandard_port(tmp_path: Path) -> None:
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.9" addrtype="ipv4"/>
            <ports>
              <port portid="8000" protocol="tcp">
                <state state="open"/>
                <service name="http" product="vLLM" version="0.6.3"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_nmap_xml(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    tech = next(o for o in obs if o["kind"] == "Technology")
    assert tech["key"] == "ai-runtime:vllm"
    assert tech["props"]["detected_by"] == "nmap-banner"


def test_nmap_adapter_dedups_port_and_banner_double_hit(tmp_path: Path) -> None:
    # 11434 (port catalog) AND product "Ollama" (banner) both say Ollama;
    # the service must end up with exactly one Technology node + RUNS edge.
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.10" addrtype="ipv4"/>
            <ports>
              <port portid="11434" protocol="tcp">
                <state state="open"/>
                <service name="http" product="Ollama"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_nmap_xml(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    techs = [o for o in obs if o["kind"] == "Technology"]
    assert len(techs) == 1
    assert techs[0]["key"] == "ai-runtime:ollama"
    svc = next(o for o in obs if o["kind"] == "Service")
    assert len(svc["edges_out"]) == 1


def test_nmap_adapter_leaves_non_ai_ports_unclassified(tmp_path: Path) -> None:
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="10.0.0.8" addrtype="ipv4"/>
            <ports>
              <port portid="22" protocol="tcp"><state state="open"/><service name="ssh"/></port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_nmap_xml(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    assert not any(o["kind"] == "Technology" for o in obs)


def test_nmap_adapter_skips_down_hosts(tmp_path: Path) -> None:
    f = tmp_path / "scan.xml"
    f.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="down"/>
            <address addr="10.0.0.99" addrtype="ipv4"/>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )
    store = _StubStore()
    result = _adapt_nmap_xml(f, store, "acme", "t", "ep")  # type: ignore[arg-type]
    assert result == {"hosts": 0, "services": 0, "entrypoints": 0}
    assert store.calls == []


def test_nmap_adapter_handles_malformed_xml(tmp_path: Path) -> None:
    f = tmp_path / "bad.xml"
    f.write_text("not valid XML", encoding="utf-8")
    store = _StubStore()
    result = _adapt_nmap_xml(f, store, "acme", "t", "ep")  # type: ignore[arg-type]
    assert "error" in result


# ── nuclei_jsonl adapter ────────────────────────────────────────────────


def test_nuclei_adapter_extracts_vuln_with_entrypoint(tmp_path: Path) -> None:
    f = tmp_path / "nuclei.jsonl"
    f.write_text(
        json.dumps(
            {
                "template-id": "ssrf-detect",
                "info": {"severity": "high", "tags": ["ssrf", "intrusive"]},
                "matched-at": "https://target.example.com/api/fetch",
                "host": "target.example.com",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = _StubStore()
    result = _adapt_nuclei_jsonl(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    assert result["parsed"] == 1
    assert result["skipped"] == 0
    obs = store.calls[0]["observations"]
    kinds = [o["kind"] for o in obs]
    assert "Vulnerability" in kinds
    assert "Entrypoint" in kinds
    vuln = next(o for o in obs if o["kind"] == "Vulnerability")
    assert vuln["props"]["severity"] == "high"
    assert vuln["props"]["rule_id"] == "ssrf-detect"
    assert "ssrf" in vuln["props"]["tags"]
    # Entrypoint must HAS_VULN edge to the vuln.
    ep = next(o for o in obs if o["kind"] == "Entrypoint")
    assert any(e["kind"] == "HAS_VULN" for e in ep.get("edges_out", []))


def test_nuclei_adapter_skips_bad_json_lines(tmp_path: Path) -> None:
    f = tmp_path / "nuclei.jsonl"
    f.write_text(
        "this is not json\n"
        + json.dumps({"template-id": "x", "info": {"severity": "low"}, "host": "h"})
        + "\n"
        + "garbage\n",
        encoding="utf-8",
    )
    store = _StubStore()
    result = _adapt_nuclei_jsonl(f, store, "acme", "t", "ep")  # type: ignore[arg-type]
    assert result["parsed"] == 1
    assert result["skipped"] == 2


# ── httpx_jsonl adapter ─────────────────────────────────────────────────


def test_httpx_adapter_extracts_host_service_entrypoint(tmp_path: Path) -> None:
    f = tmp_path / "httpx.jsonl"
    f.write_text(
        json.dumps(
            {
                "url": "https://target.example.com:8443/admin",
                "host": "target.example.com",
                "port": 8443,
                "status-code": 200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = _StubStore()
    result = _adapt_httpx_jsonl(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    assert result["parsed"] == 1
    obs = store.calls[0]["observations"]
    kinds = [o["kind"] for o in obs]
    assert "Host" in kinds
    assert "Service" in kinds
    assert "Entrypoint" in kinds


def test_httpx_adapter_classifies_ai_endpoint_path(tmp_path: Path) -> None:
    f = tmp_path / "httpx.jsonl"
    f.write_text(
        json.dumps(
            {
                "url": "http://10.0.0.5:11434/api/tags",
                "host": "10.0.0.5",
                "port": 11434,
                "status-code": 200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_httpx_jsonl(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    tech = next(o for o in obs if o["kind"] == "Technology")
    assert tech["key"] == "ai-runtime:ollama"
    assert tech["props"]["detected_by"] == "endpoint-path"
    svc = next(o for o in obs if o["kind"] == "Service")
    assert any(e["to_key"] == "ai-runtime:ollama" and e["kind"] == "RUNS" for e in svc["edges_out"])


def test_httpx_adapter_classifies_ai_ui_title(tmp_path: Path) -> None:
    f = tmp_path / "httpx.jsonl"
    f.write_text(
        json.dumps(
            {
                "url": "http://10.0.0.6:8188/",
                "host": "10.0.0.6",
                "port": 8188,
                "status-code": 200,
                "title": "ComfyUI",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_httpx_jsonl(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    tech = next(o for o in obs if o["kind"] == "Technology")
    assert tech["key"] == "ai-framework:comfyui"
    assert tech["props"]["guess"] is True
    svc = next(o for o in obs if o["kind"] == "Service")
    assert any(e["to_key"] == "ai-framework:comfyui" for e in svc["edges_out"])


def test_httpx_adapter_ignores_404_and_non_ai_paths(tmp_path: Path) -> None:
    f = tmp_path / "httpx.jsonl"
    f.write_text(
        json.dumps({"url": "http://h:8080/v1/chat/completions", "host": "h", "status-code": 404})
        + "\n"
        + json.dumps({"url": "http://h:8080/", "host": "h", "status-code": 200})
        + "\n",
        encoding="utf-8",
    )
    store = _StubStore()
    _adapt_httpx_jsonl(f, store, "acme", "recon", "ep-1")  # type: ignore[arg-type]
    obs = store.calls[0]["observations"]
    assert not any(o["kind"] == "Technology" for o in obs)


def test_httpx_adapter_skips_rows_without_url(tmp_path: Path) -> None:
    f = tmp_path / "httpx.jsonl"
    f.write_text(json.dumps({"status-code": 200}) + "\n", encoding="utf-8")
    store = _StubStore()
    result = _adapt_httpx_jsonl(f, store, "acme", "t", "ep")  # type: ignore[arg-type]
    assert result["parsed"] == 1
    assert result["skipped"] == 1
    assert result["ingested"] == 0


# ── sarif adapter ───────────────────────────────────────────────────────


def test_sarif_adapter_extracts_vuln_and_code_location(tmp_path: Path) -> None:
    sarif = {
        "runs": [
            {
                "tool": {"driver": {"name": "semgrep"}},
                "results": [
                    {
                        "ruleId": "python.lang.security.audit.sqli",
                        "level": "error",
                        "message": {"text": "SQL injection via string concat"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "app/views.py"},
                                    "region": {"startLine": 42},
                                }
                            }
                        ],
                    }
                ],
            }
        ]
    }
    f = tmp_path / "scan.sarif"
    f.write_text(json.dumps(sarif), encoding="utf-8")
    store = _StubStore()
    result = _adapt_sarif(f, store, "acme", "analyst", "ep-1")  # type: ignore[arg-type]
    assert result["results_processed"] == 1
    obs = store.calls[0]["observations"]
    kinds = [o["kind"] for o in obs]
    assert "Vulnerability" in kinds
    assert "CodeLocation" in kinds
    vuln = next(o for o in obs if o["kind"] == "Vulnerability")
    # SARIF level "error" maps to severity "high".
    assert vuln["props"]["severity"] == "high"
    assert vuln["props"]["scanner"] == "semgrep"
    assert vuln["props"]["file"] == "app/views.py"
    assert vuln["props"]["line"] == 42
    # The Vulnerability node must DEFINED_IN edge to the code location.
    assert any(e["kind"] == "DEFINED_IN" for e in vuln.get("edges_out", []))


def test_sarif_adapter_handles_empty_runs(tmp_path: Path) -> None:
    f = tmp_path / "empty.sarif"
    f.write_text(json.dumps({"runs": []}), encoding="utf-8")
    store = _StubStore()
    result = _adapt_sarif(f, store, "acme", "t", "ep")  # type: ignore[arg-type]
    assert result == {"results_processed": 0, "ingested": 0}
    assert store.calls == []
