"""Unit tests for EvoGraph cross-session memory layer.

Most behavior requires Neo4j — we test the pure-Python edges:
- ``EngagementMemory`` dataclass shape + to_dict()
- ``format_bootstrap_for_prompt()`` rendering w/ varied inputs
- Graceful-degradation paths (Neo4j unavailable → empty results)

Live Neo4j tests would go in tests/integration/ with a docker-compose
fixture; out of scope here.
"""

from __future__ import annotations

from decepticon.tools.research.cross_session import (
    EngagementMemory,
    bootstrap_from_prior,
    commit_engagement_memory,
    find_similar_findings,
    format_bootstrap_for_prompt,
    register_engagement,
)


def test_engagement_memory_to_dict_roundtrip() -> None:
    m = EngagementMemory(
        slug="acme-q1",
        target="api.example.com",
        started_at="2026-05-01T00:00:00Z",
        ended_at="2026-05-02T00:00:00Z",
        total_findings=7,
        validated_findings=4,
        shipped_findings=2,
        top_bug_classes=[("sqli", 3), ("ssrf", 2)],
        top_techniques=["T1190", "T1078"],
        crown_jewels_reached=["prod-db"],
        notable_attack_paths=["ssrf->metadata->keys->db"],
        note="strict CSP blocked XSS",
    )
    d = m.to_dict()
    assert d["slug"] == "acme-q1"
    assert d["top_bug_classes"] == [("sqli", 3), ("ssrf", 2)]
    assert d["crown_jewels_reached"] == ["prod-db"]
    assert d["note"] == "strict CSP blocked XSS"


def test_format_bootstrap_for_prompt_empty() -> None:
    assert format_bootstrap_for_prompt([]) == ""


def test_format_bootstrap_for_prompt_renders_xml_block() -> None:
    memories = [
        EngagementMemory(
            slug="acme-q1",
            target="api.example.com",
            started_at="2026-05-01T00:00:00Z",
            ended_at="2026-05-02T00:00:00Z",
            total_findings=5,
            validated_findings=3,
            shipped_findings=1,
            top_bug_classes=[("sqli", 3), ("ssrf", 2)],
            top_techniques=["T1190"],
            crown_jewels_reached=["prod-db"],
            note="watch for double-escaped payloads",
        ),
    ]
    block = format_bootstrap_for_prompt(memories)
    assert block.startswith("<EVOGRAPH_PRIOR_ENGAGEMENTS>")
    assert block.endswith("</EVOGRAPH_PRIOR_ENGAGEMENTS>")
    assert "slug='acme-q1'" in block
    assert "target='api.example.com'" in block
    assert "sqli(3)" in block
    assert "ssrf(2)" in block
    assert "T1190" in block
    assert "prod-db" in block
    assert "double-escaped" in block


def test_format_bootstrap_for_prompt_omits_empty_optional_fields() -> None:
    memories = [
        EngagementMemory(
            slug="solo",
            target="x.test",
            started_at="t1",
            ended_at="t2",
        ),
    ]
    block = format_bootstrap_for_prompt(memories)
    assert "crown_jewels_reached" not in block
    assert "note: " not in block
    assert "(none)" in block  # empty bug_classes / techniques rendered as (none)


def test_neo4j_unavailable_graceful_degradation(monkeypatch) -> None:
    """All public functions must return empty/falsy without crashing
    when ``get_store()`` raises Neo4jUnavailableError.
    """
    from decepticon.tools.research import cross_session
    from decepticon.tools.research.neo4j_store import Neo4jUnavailableError

    def _raise(*_a, **_k):
        raise Neo4jUnavailableError("test: no neo4j")

    monkeypatch.setattr(cross_session, "get_store", _raise)

    assert cross_session.ensure_evograph_schema() is False
    assert register_engagement("slug-x", "tgt") is False
    assert (
        cross_session.tag_node_to_engagement(node_key="x", kind="Finding", engagement_slug="slug-x")
        is False
    )
    assert commit_engagement_memory("slug-x") is None
    assert bootstrap_from_prior(target_hint="x") == []
    assert find_similar_findings(bug_class="sqli") == []


def test_graph_kinds_extended() -> None:
    from decepticon.tools.research.graph import EdgeKind, NodeKind

    assert NodeKind.ENGAGEMENT.value == "Engagement"
    assert NodeKind.ENGAGEMENT_MEMORY.value == "EngagementMemory"
    assert EdgeKind.IN_ENGAGEMENT.value == "IN_ENGAGEMENT"
    assert EdgeKind.SUMMARIZES.value == "SUMMARIZES"
