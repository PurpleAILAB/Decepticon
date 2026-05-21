"""Unit tests for the debate_finding tool and the validate_finding gate."""

from __future__ import annotations

import json

import pytest

from decepticon.core.schemas import DebateVerdict
from decepticon.llm.debate import AdvocateRebuttal, SkepticOpinion
from decepticon.llm.ensemble import EnsembleAssignment
from decepticon.llm.factory import LLMFactory
from decepticon.llm.router import ModelRouter
from decepticon.tools.research.graph import (
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)
from decepticon.tools.research.poc import PoCResult
from decepticon.tools.research.tools import debate_finding, validate_finding


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


def _configure_kg(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr("decepticon.tools.research._state._store", fake)
    return fake


def _seed_vuln(store: _FakeStore, **props) -> str:
    vuln = Node.make(
        NodeKind.VULNERABILITY,
        "SQLi in product search",
        key="app.py:search:sqli",
        severity=Severity.CRITICAL.value,
        **props,
    )
    store.graph.upsert_node(vuln)
    return vuln.id


class _FakeStructured:
    def __init__(self, obj):
        self._obj = obj

    async def ainvoke(self, prompt):
        return self._obj


class _FakeModel:
    """Stands in for a chat model — yields a canned structured object."""

    def __init__(self, obj):
        self._obj = obj

    def with_structured_output(self, schema):
        return _FakeStructured(self._obj)


def _patch_debate_models(monkeypatch, skeptic: SkepticOpinion, advocate: AdvocateRebuttal):
    monkeypatch.setattr(
        LLMFactory, "get_model_by_id", lambda self, mid, **k: _FakeModel(skeptic)
    )
    monkeypatch.setattr(LLMFactory, "get_model", lambda self, role, **k: _FakeModel(advocate))


@pytest.mark.asyncio
class TestDebateFinding:
    async def test_upheld_persists_record_and_token(self, monkeypatch):
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(fake)
        _patch_debate_models(
            monkeypatch,
            SkepticOpinion(reachable=True, exploitable=True, confidence=0.9),
            AdvocateRebuttal(objection_holds=False),
        )

        raw = await debate_finding.ainvoke(
            {
                "vuln_id": vuln_id,
                "finding_summary": "SQLi in /search?q=",
                "poc_evidence": "sqlite_master leaked",
            }
        )
        result = json.loads(raw)
        assert result["verdict"] == DebateVerdict.UPHELD.value
        assert result["debate_token"]
        assert result["cross_family"] is True

        graph = fake.load_graph()
        vuln = graph.nodes[vuln_id]
        assert vuln.props["debate_token"] == result["debate_token"]
        assert vuln.props["debate_verdict"] == DebateVerdict.UPHELD.value

        hyps = [n for n in graph.nodes.values() if n.kind == NodeKind.HYPOTHESIS]
        assert len(hyps) == 1
        edges = [e for e in graph.edges.values() if e.kind == EdgeKind.DEBATED_BY]
        assert len(edges) == 1 and edges[0].dst == vuln_id

    async def test_single_family_skips_debate_but_issues_token(self, monkeypatch):
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(fake)
        # Force a single-family install: no cross-family debater.
        monkeypatch.setattr(
            ModelRouter,
            "resolve_ensemble",
            lambda self, role, **k: EnsembleAssignment(
                role=role,
                primary="anthropic/claude-sonnet-4-6",
                primary_family="anthropic",
                counterpoint=None,
                counterpoint_family="unknown",
                debater=None,
                debater_family="unknown",
                fallbacks=[],
                cross_family_available=False,
            ),
        )
        raw = await debate_finding.ainvoke(
            {"vuln_id": vuln_id, "finding_summary": "x", "poc_evidence": "y"}
        )
        result = json.loads(raw)
        assert result["verdict"] == DebateVerdict.SKIPPED.value
        assert result["debate_token"]  # token still issued so promotion proceeds

    async def test_unknown_vuln_returns_error(self, monkeypatch):
        _configure_kg(monkeypatch)
        raw = await debate_finding.ainvoke(
            {"vuln_id": "nope", "finding_summary": "x", "poc_evidence": "y"}
        )
        assert "error" in json.loads(raw)


def _fake_poc_result(vuln_id: str, *, validated: bool, severity: str) -> PoCResult:
    return PoCResult(
        validated=validated,
        vuln_id=vuln_id,
        summary="1 success signal",
        stdout_excerpt="sqlite_master",
        exit_code=0,
        cvss_score=9.5 if severity == "critical" else 5.0,
        severity=severity,
        output_hash="abc123",
    )


def _patch_validate_poc(monkeypatch, result: PoCResult):
    import importlib

    poc_mod = importlib.import_module("decepticon.tools.research.poc")
    bash_mod = importlib.import_module("decepticon.tools.bash.bash")

    async def _fake(**kwargs):
        return result

    monkeypatch.setattr(poc_mod, "validate_poc", _fake)
    monkeypatch.setattr(bash_mod, "get_sandbox", lambda: object())


@pytest.mark.asyncio
class TestValidateFindingGate:
    async def test_critical_without_debate_token_is_blocked(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_MODEL_PROFILE", "eco")
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(fake)
        _patch_validate_poc(
            monkeypatch, _fake_poc_result(vuln_id, validated=True, severity="critical")
        )

        raw = await validate_finding.ainvoke(
            {"vuln_id": vuln_id, "poc_command": "curl x", "success_patterns": "sqlite_master"}
        )
        result = json.loads(raw)
        assert result["promotion"] == "blocked"
        # No FINDING node was created.
        graph = fake.load_graph()
        assert not [n for n in graph.nodes.values() if n.kind == NodeKind.FINDING]

    async def test_refuted_token_is_blocked(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_MODEL_PROFILE", "eco")
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(
            fake, debate_token="tok123", debate_verdict="refuted", debate_credibility=0.1
        )
        _patch_validate_poc(
            monkeypatch, _fake_poc_result(vuln_id, validated=True, severity="critical")
        )

        raw = await validate_finding.ainvoke(
            {"vuln_id": vuln_id, "poc_command": "curl x", "success_patterns": "sqlite_master"}
        )
        result = json.loads(raw)
        assert result["promotion"] == "blocked"
        assert result["debate_verdict"] == "refuted"

    async def test_upheld_token_promotes_finding(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_MODEL_PROFILE", "eco")
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(
            fake, debate_token="tok456", debate_verdict="upheld", debate_credibility=0.95
        )
        _patch_validate_poc(
            monkeypatch, _fake_poc_result(vuln_id, validated=True, severity="critical")
        )

        raw = await validate_finding.ainvoke(
            {"vuln_id": vuln_id, "poc_command": "curl x", "success_patterns": "sqlite_master"}
        )
        result = json.loads(raw)
        assert result["promotion"] == "promoted"
        assert result["credibility"] == 0.95

        graph = fake.load_graph()
        findings = [n for n in graph.nodes.values() if n.kind == NodeKind.FINDING]
        assert len(findings) == 1
        assert findings[0].props["credibility"] == 0.95
        assert findings[0].props["debate_verdict"] == "upheld"

    async def test_test_profile_bypasses_gate(self, monkeypatch):
        # Under the test profile debate is disabled — promotion must not block.
        monkeypatch.setenv("DECEPTICON_MODEL_PROFILE", "test")
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(fake)
        _patch_validate_poc(
            monkeypatch, _fake_poc_result(vuln_id, validated=True, severity="critical")
        )

        raw = await validate_finding.ainvoke(
            {"vuln_id": vuln_id, "poc_command": "curl x", "success_patterns": "sqlite_master"}
        )
        result = json.loads(raw)
        assert result["promotion"] == "promoted"

    async def test_low_severity_skips_gate(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_MODEL_PROFILE", "eco")
        monkeypatch.delenv("DECEPTICON_DEBATE", raising=False)
        fake = _configure_kg(monkeypatch)
        vuln_id = _seed_vuln(fake)
        _patch_validate_poc(
            monkeypatch, _fake_poc_result(vuln_id, validated=True, severity="medium")
        )

        raw = await validate_finding.ainvoke(
            {"vuln_id": vuln_id, "poc_command": "curl x", "success_patterns": "x"}
        )
        result = json.loads(raw)
        assert result["promotion"] == "promoted"
