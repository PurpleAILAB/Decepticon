"""Regression tests for the Offensive Vaccine tools.

Covers the AttributeError: 'Node' object has no attribute 'key' crash
hit on the Meridian retest (2026-08-04): the finding-node matcher in
vaccine_generate_brief / vaccine_verify accessed ``n.key`` on the KG
``Node`` model, which has no such attribute — the dedup key lives in
``Node.props["key"]``. Because the match is behind a short-circuit
``or``, the crash only fires when a FINDING node's label does NOT
contain the finding_id.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from decepticon.tools.defense import vaccine
from decepticon_core.types.kg import KnowledgeGraph, Node, NodeKind


def _graph_with_unrelated_finding() -> KnowledgeGraph:
    """A KG whose only FINDING node's label does not mention FIND-001."""
    graph = KnowledgeGraph()
    graph.upsert_node(
        Node.make(NodeKind.FINDING, "SQL injection in maintenance list", key="FIND-013")
    )
    return graph


@contextmanager
def _tx(graph):
    yield graph


@pytest.fixture
def patched_graph(monkeypatch):
    graph = _graph_with_unrelated_finding()
    monkeypatch.setattr(vaccine, "graph_transaction", lambda: _tx(graph))
    return graph


def test_vaccine_verify_with_unrelated_finding_node(patched_graph, tmp_path):
    """Must not raise AttributeError when a FINDING node's label lacks the id."""
    out = vaccine.vaccine_verify.func(
        finding_id="FIND-001",
        reattack_result="still exploitable",
        blocked=False,
        evidence="http 200",
        workspace=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["finding_id"] == "FIND-001"
    assert payload["status"] == "defense_failed"


def test_vaccine_verify_links_matching_finding_by_props_key(patched_graph, tmp_path):
    """The props['key'] path still matches findings whose label lacks the id."""
    vaccine.vaccine_verify.func(
        finding_id="FIND-013",
        reattack_result="fix confirmed",
        blocked=True,
        workspace=str(tmp_path),
    )
    assert patched_graph.by_kind(NodeKind.VERIFICATION), "expected a verification node"
    assert len(patched_graph.edges) >= 1, "expected VERIFIES edge to the FIND-013 node"


def test_vaccine_generate_brief_with_unrelated_finding_node(patched_graph, tmp_path):
    """Same crash class in the brief generator's defense-action linker."""
    out = vaccine.vaccine_generate_brief.func(
        finding_id="FIND-001",
        title="Exposed API key",
        severity="medium",
        attack_vector="grep bundle for AIza keys",
        evidence="key in index.js",
        workspace=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["finding_id"] == "FIND-001"
