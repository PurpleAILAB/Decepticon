"""Unit tests for :mod:`kg_internal.summary` — driver-free.

Covers section rendering, section omission when empty, severity
ordering, and the public ``build_summary`` integration against a stub
store. Live-Neo4j coverage is in
``tests/integration/kg/test_kg_summary_live.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from decepticon.middleware.kg_internal.store import KGStore, KGStoreConfig
from decepticon.middleware.kg_internal.summary import (
    MAX_CROWN_JEWELS,
    MAX_ENTRYPOINTS,
    MAX_VULNS,
    _render_crown_jewels,
    _render_entrypoints,
    _render_stats,
    _render_vulns,
    _severity_order,
    build_summary,
)

# ── Severity ordering ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("critical", 0),
        ("high", 1),
        ("medium", 2),
        ("low", 3),
        ("info", 4),
        ("HIGH", 1),
        ("Critical", 0),
        ("unknown", 99),
        ("", 99),
        (None, 99),
    ],
)
def test_severity_order(severity: Any, expected: int) -> None:
    assert _severity_order(severity) == expected


# ── Section renderers ──────────────────────────────────────────────────


def test_render_stats_includes_engagement_revision_counts() -> None:
    out = _render_stats("acme-q2", "rev-acme-q2-1234", {"nodes": 12, "edges": 8})
    assert "engagement=acme-q2" in out
    assert "rev-acme-q2-1234" in out
    assert "Nodes**: 12" in out
    assert "Edges**: 8" in out


def test_render_vulns_lists_each_in_brackets() -> None:
    out = _render_vulns(
        [
            {"key": "k1", "label": "SSTI in /search", "severity": "critical"},
            {"key": "k2", "label": "SQLi in /login", "severity": "high"},
        ]
    )
    assert "Top vulnerabilities" in out
    assert "[CRITICAL]" in out
    assert "SSTI in /search" in out
    assert "[HIGH]" in out
    assert "SQLi in /login" in out


def test_render_entrypoints_lists_each_with_key() -> None:
    out = _render_entrypoints(
        [
            {"key": "ep::1", "label": "https://app/"},
            {"key": "ep::2", "label": "https://api/"},
        ]
    )
    assert "Unexplored entrypoints" in out
    assert "https://app/" in out
    assert "ep::1" in out


def test_render_crown_jewels_includes_path_counts() -> None:
    out = _render_crown_jewels(
        [
            {"key": "cj::admin", "label": "domain_admin", "paths": 1},
            {"key": "cj::db", "label": "payments_db", "paths": 0},
        ]
    )
    assert "Crown jewels" in out
    assert "domain_admin (1 viable path)" in out
    assert "payments_db (0 viable paths)" in out


def test_render_vulns_falls_back_to_key_when_label_missing() -> None:
    out = _render_vulns([{"key": "k1", "severity": "high"}])
    assert "k1" in out
    assert "[HIGH]" in out


# ── KGStore stub plumbing ──────────────────────────────────────────────


def _fake_driver() -> MagicMock:
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = None
    return driver


def _make_store() -> KGStore:
    cfg = KGStoreConfig(uri="bolt://x", user="u", password="p", database="neo4j")
    return KGStore(cfg, driver=_fake_driver())


class _StubStore:
    """Minimal stub matching the public KGStore surface the summary uses."""

    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self._responses = responses

    def revision(self, *, engagement: str) -> str:
        return f"rev-{engagement}-stub"

    def execute_read(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        engagement: str,
    ) -> list[dict[str, Any]]:
        # Coarse routing via signature substrings in the Cypher.
        if "count(n) AS nodes" in cypher:
            return self._responses.get("stats", [{"nodes": 0, "edges": 0}])
        if "(v:Vulnerability)" in cypher:
            return self._responses.get("vulns", [])
        # Match the relationship type only: the scope predicate inside the
        # pattern is an implementation detail this stub should not pin.
        if "(e:Entrypoint)" in cypher and "NOT (e)-[:HAS_VULN" in cypher:
            return self._responses.get("entrypoints", [])
        if "(c:CrownJewel)" in cypher:
            return self._responses.get("crown_jewels", [])
        return []


# ── build_summary integration with stubbed store ───────────────────────


def test_build_summary_minimal_engagement() -> None:
    """Empty engagement: only the header + stats section."""
    store = _StubStore({"stats": [{"nodes": 0, "edges": 0}]})
    out = build_summary(store, engagement="acme")  # type: ignore[arg-type]
    assert "KG STATE (engagement=acme)" in out
    assert "Nodes**: 0" in out
    # Empty sections are dropped.
    assert "Top vulnerabilities" not in out
    assert "Unexplored entrypoints" not in out
    assert "Crown jewels" not in out


def test_build_summary_full_engagement() -> None:
    store = _StubStore(
        {
            "stats": [{"nodes": 12, "edges": 8}],
            "vulns": [
                {"key": "v1", "label": "SSTI in /search", "severity": "critical"},
                {"key": "v2", "label": "SQLi in /login", "severity": "high"},
            ],
            "entrypoints": [{"key": "e1", "label": "https://app/"}],
            "crown_jewels": [{"key": "c1", "label": "domain_admin", "paths": 1}],
        }
    )
    out = build_summary(store, engagement="acme")  # type: ignore[arg-type]
    assert "engagement=acme" in out
    assert "Top vulnerabilities" in out
    assert "SSTI in /search" in out
    assert "Unexplored entrypoints" in out
    assert "https://app/" in out
    assert "Crown jewels" in out
    assert "domain_admin (1 viable path)" in out


def test_build_summary_drops_empty_sections() -> None:
    """Engagement with only stats and vulns: entrypoints/crown jewels absent."""
    store = _StubStore(
        {
            "stats": [{"nodes": 3, "edges": 1}],
            "vulns": [{"key": "v1", "label": "x", "severity": "low"}],
        }
    )
    out = build_summary(store, engagement="acme")  # type: ignore[arg-type]
    assert "Top vulnerabilities" in out
    assert "Unexplored entrypoints" not in out
    assert "Crown jewels" not in out


def test_build_summary_severity_orders_vulns_correctly() -> None:
    """Top-N is sorted by severity rank — critical / high above low / info."""
    store = _StubStore(
        {
            "stats": [{"nodes": 0, "edges": 0}],
            # Stub returns the rows the Cypher 'cap' window would —
            # build_summary re-sorts locally before truncating.
            "vulns": [
                {"key": "low_one", "label": "low_one", "severity": "low"},
                {"key": "crit_one", "label": "crit_one", "severity": "critical"},
                {"key": "info_one", "label": "info_one", "severity": "info"},
                {"key": "high_one", "label": "high_one", "severity": "high"},
            ],
        }
    )
    out = build_summary(store, engagement="acme")  # type: ignore[arg-type]
    crit_pos = out.find("crit_one")
    high_pos = out.find("high_one")
    low_pos = out.find("low_one")
    info_pos = out.find("info_one")
    # critical comes before high comes before low comes before info.
    assert 0 < crit_pos < high_pos < low_pos < info_pos


def test_build_summary_truncates_to_max_vulns() -> None:
    """No more than MAX_VULNS vuln lines in the block."""
    vulns = [{"key": f"v{i}", "label": f"v{i}", "severity": "medium"} for i in range(MAX_VULNS * 3)]
    store = _StubStore(
        {
            "stats": [{"nodes": 0, "edges": 0}],
            "vulns": vulns,
        }
    )
    out = build_summary(store, engagement="acme")  # type: ignore[arg-type]
    # Each vuln is one list item starting with "- `["
    bullet_count = out.count("- `[")
    assert bullet_count == MAX_VULNS


def test_max_constants_are_small() -> None:
    """Sanity guard: budgets stay tight (memory-systems anti-pattern guard)."""
    assert MAX_VULNS <= 10
    assert MAX_ENTRYPOINTS <= 10
    assert MAX_CROWN_JEWELS <= 25
