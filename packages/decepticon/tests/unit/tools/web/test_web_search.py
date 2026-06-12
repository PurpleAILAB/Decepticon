"""Tests for the RoE-gated ``web_search`` tool (ADR-0008)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from decepticon.middleware._audit_sink import RoEAuditSink
from decepticon.tools.web import search as ws_mod
from decepticon.tools.web.search import (
    WebSearchResult,
    _parse_ddg_html,
    _unwrap_ddg_href,
    run_web_search,
    web_search,
)

_asyncio = pytest.mark.asyncio


DDG_FIXTURE = """
<html><body>
<div class="result"><h2>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
</h2><a class="result__snippet" href="https://example.com/a">Snippet about A &amp; friends</a></div>

<div class="result"><h2>
  <a class="result__a" href="https://example.com/b">Example B</a>
</h2><a class="result__snippet" href="https://example.com/b">Snippet B</a></div>

<div class="result"><h2>
  <a class="result__a" href="https://evilcorp.com/x">Evil C</a>
</h2><a class="result__snippet" href="https://evilcorp.com/x">Snippet C</a></div>
</body></html>
"""


def _write_roe(workspace: Path, machine_enforcement: dict[str, Any]) -> None:
    (workspace / "plan").mkdir(parents=True, exist_ok=True)
    (workspace / "plan" / "roe.json").write_text(
        json.dumps({"machine_enforcement": machine_enforcement}), encoding="utf-8"
    )


def _audit_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_parse_ddg_html_extracts_three_results() -> None:
    results = _parse_ddg_html(DDG_FIXTURE, limit=10)
    assert [r.url for r in results] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://evilcorp.com/x",
    ]
    assert results[0].title == "Example A"
    assert "friends" in results[0].snippet
    assert all(r.source == "duckduckgo" for r in results)


def test_unwrap_ddg_href_handles_uddg_wrapper() -> None:
    assert _unwrap_ddg_href("https://example.com/x") == "https://example.com/x"
    assert (
        _unwrap_ddg_href("//duckduckgo.com/l/?uddg=https%3A%2F%2Ftarget.com%2Fy")
        == "https://target.com/y"
    )
    assert (
        _unwrap_ddg_href("//html.duckduckgo.com/l/?uddg=https%3A%2F%2Ftarget.com%2Fy")
        == "https://target.com/y"
    )
    # Attacker lookalike domain bypass attempt should NOT unwrap:
    assert (
        _unwrap_ddg_href("//duckduckgo.com.attacker.com/l/?uddg=https%3A%2F%2Ftarget.com%2Fy")
        == "https://duckduckgo.com.attacker.com/l/?uddg=https%3A%2F%2Ftarget.com%2Fy"
    )


@_asyncio
async def test_web_search_happy_path_returns_typed_results(monkeypatch, tmp_path: Path) -> None:
    async def fake_fetch(query: str, *, timeout_s: float) -> str:
        assert "test" in query
        assert timeout_s == 5.0
        return DDG_FIXTURE

    monkeypatch.setattr(ws_mod, "_fetch_ddg", fake_fetch)

    sink = RoEAuditSink(path=tmp_path / "audit.jsonl")
    out = await run_web_search(
        "site:example.com test",
        max_results=3,
        workspace_path=str(tmp_path),
        engagement="acme-2026",
        objective="obj-1",
        sink=sink,
    )

    assert out["query"] == "site:example.com test"
    assert len(out["results"]) == 3
    assert out["filtered_count"] == 0
    assert out["results"][0]["url"].startswith("https://")
    expected_keys = {"title", "url", "snippet", "source"}
    assert set(out["results"][0].keys()) == expected_keys

    events = [e for e in _audit_lines(tmp_path / "audit.jsonl") if "event" in e]
    queries = [e for e in events if e["event"] == "web_search.query"]
    assert len(queries) == 1
    assert queries[0]["result_count"] == 3
    assert queries[0]["filtered_count"] == 0


@_asyncio
async def test_web_search_filters_out_of_scope_hosts(monkeypatch, tmp_path: Path) -> None:
    async def fake_fetch(query: str, *, timeout_s: float) -> str:
        return DDG_FIXTURE

    monkeypatch.setattr(ws_mod, "_fetch_ddg", fake_fetch)
    _write_roe(tmp_path, {"mode": "enforce", "in_scope": ["*.example.com", "example.com"]})

    sink = RoEAuditSink(path=tmp_path / "audit.jsonl")
    out = await run_web_search(
        "anything",
        workspace_path=str(tmp_path),
        engagement="acme-2026",
        objective="obj-1",
        sink=sink,
    )

    hosts = {r["url"] for r in out["results"]}
    assert "https://evilcorp.com/x" not in hosts
    assert len(out["results"]) == 2
    assert out["filtered_count"] == 1

    events = _audit_lines(tmp_path / "audit.jsonl")
    filtered = [e for e in events if e.get("event") == "web_search.result_filtered"]
    assert len(filtered) == 1
    assert filtered[0]["host"] == "evilcorp.com"
    assert filtered[0]["decision"] == "refuse"


@_asyncio
async def test_web_search_timeout_collapses_to_error(monkeypatch, tmp_path: Path) -> None:
    async def boom(query: str, *, timeout_s: float) -> str:
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(ws_mod, "_fetch_ddg", boom)

    sink = RoEAuditSink(path=tmp_path / "audit.jsonl")
    out = await run_web_search(
        "site:example.com test",
        workspace_path=str(tmp_path),
        sink=sink,
    )

    assert out["results"] == []
    assert "TimeoutException" in out["error"]

    errors = [
        e for e in _audit_lines(tmp_path / "audit.jsonl") if e.get("event") == "web_search.error"
    ]
    assert len(errors) == 1
    assert "TimeoutException" in errors[0]["error"]


@_asyncio
async def test_web_search_empty_query_short_circuits() -> None:
    out = await run_web_search("   ", workspace_path=None)
    assert out["results"] == []
    assert out["error"] == "empty query"


@_asyncio
async def test_web_search_tool_wrapper_returns_json(monkeypatch, tmp_path: Path) -> None:
    async def fake_fetch(query: str, *, timeout_s: float) -> str:
        return DDG_FIXTURE

    monkeypatch.setattr(ws_mod, "_fetch_ddg", fake_fetch)
    monkeypatch.setenv("DECEPTICON_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DECEPTICON_ROE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

    raw = await web_search.ainvoke({"query": "site:example.com test", "max_results": 3})
    payload = json.loads(raw)
    assert payload["query"] == "site:example.com test"
    assert len(payload["results"]) == 3


def test_dataclass_shape_is_stable() -> None:
    r = WebSearchResult(title="t", url="https://x", snippet="s")
    assert r.source == "duckduckgo"
    assert r.title == "t"


_META_FIXTURE = """
<html><body>
<div class="result"><h2>
  <a class="result__a" href="https://example.com/ok">OK</a>
</h2><a class="result__snippet" href="https://example.com/ok">ok</a></div>

<div class="result"><h2>
  <a class="result__a" href="http://169.254.169.254/latest/meta-data/">IMDS</a>
</h2><a class="result__snippet" href="http://169.254.169.254/latest/meta-data/">imds</a></div>
</body></html>
"""


@_asyncio
async def test_web_search_drops_cloud_metadata_even_without_scope(
    monkeypatch, tmp_path: Path
) -> None:
    # Regression: with no in_scope/out_of_scope configured, the tool must
    # still drop the always-on forbidden destinations (cloud-metadata/IMDS),
    # otherwise an unscoped engagement leaks SSRF-bait URLs to the agent.
    async def fake_fetch(query: str, *, timeout_s: float) -> str:
        return _META_FIXTURE

    monkeypatch.setattr(ws_mod, "_fetch_ddg", fake_fetch)

    sink = RoEAuditSink(path=tmp_path / "audit.jsonl")
    out = await run_web_search(
        "anything",
        workspace_path=str(tmp_path),  # no plan/roe.json -> empty scope
        sink=sink,
    )

    hosts = {r["url"] for r in out["results"]}
    assert "http://169.254.169.254/latest/meta-data/" not in hosts
    assert out["filtered_count"] == 1

    filtered = [
        e
        for e in _audit_lines(tmp_path / "audit.jsonl")
        if e.get("event") == "web_search.result_filtered"
    ]
    assert len(filtered) == 1
    assert filtered[0]["host"] == "169.254.169.254"
    assert filtered[0]["reason_code"] == "FORBIDDEN_DESTINATION"


_BAD_HOST_FIXTURE = """
<html><body>
<div class="result"><h2>
  <a class="result__a" href="https://example.com/ok">OK</a>
</h2><a class="result__snippet" href="https://example.com/ok">ok</a></div>

<div class="result"><h2>
  <a class="result__a" href="http://[::1/x">Bad</a>
</h2><a class="result__snippet" href="http://[::1/x">bad</a></div>
</body></html>
"""


@_asyncio
async def test_web_search_drops_unparseable_host_and_never_raises(
    monkeypatch, tmp_path: Path
) -> None:
    # A malformed result URL whose host cannot be parsed must be dropped
    # (default-deny) rather than crash the tool or leak through.
    async def fake_fetch(query: str, *, timeout_s: float) -> str:
        return _BAD_HOST_FIXTURE

    monkeypatch.setattr(ws_mod, "_fetch_ddg", fake_fetch)

    sink = RoEAuditSink(path=tmp_path / "audit.jsonl")
    out = await run_web_search("anything", workspace_path=str(tmp_path), sink=sink)

    assert "error" not in out
    assert [r["url"] for r in out["results"]] == ["https://example.com/ok"]
    assert out["filtered_count"] == 1

    filtered = [
        e
        for e in _audit_lines(tmp_path / "audit.jsonl")
        if e.get("event") == "web_search.result_filtered"
    ]
    assert len(filtered) == 1
    assert filtered[0]["reason_code"] == "UNPARSEABLE_HOST"
