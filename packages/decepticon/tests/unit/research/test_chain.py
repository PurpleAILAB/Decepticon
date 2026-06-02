"""Unit tests for attack-chain construction — chain.py.

All Neo4j / store calls are mocked via monkeypatch. No external services needed.
"""

from __future__ import annotations

from typing import Any

import pytest

from decepticon.tools.research.chain import (
    _ATTACK_REL_TYPES,
    Chain,
    ChainStep,
    compute_edge_cost,
    credential_reachability,
    critical_path_score,
    impact_analysis,
    plan_chains,
    promote_chain,
    unexplored_surface,
)
from decepticon_core.types.kg import SEVERITY_COST_MULTIPLIER, EdgeKind, NodeKind, Severity

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_step(
    node_id: str = "n1",
    node_label: str = "NodeA",
    node_kind: str = "Vulnerability",
    edge_kind: str = "EXPLOITS",
    hop_cost: float = 1.0,
) -> ChainStep:
    return ChainStep(
        node_id=node_id,
        node_label=node_label,
        node_kind=node_kind,
        edge_kind=edge_kind,
        hop_cost=hop_cost,
    )


def _make_chain(
    entrypoint_id: str = "ep1",
    entrypoint_label: str = "WebApp",
    crown_jewel_id: str = "cj1",
    crown_jewel_label: str = "Database",
    steps: list[ChainStep] | None = None,
    total_cost: float = 2.5,
) -> Chain:
    return Chain(
        entrypoint_id=entrypoint_id,
        entrypoint_label=entrypoint_label,
        crown_jewel_id=crown_jewel_id,
        crown_jewel_label=crown_jewel_label,
        steps=steps or [],
        total_cost=total_cost,
    )


class _FakeStore:
    """Minimal fake store used to drive plan_chains / promote_chain etc."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def query_custom(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((cypher, params))
        return self._rows


# ── _ATTACK_REL_TYPES ────────────────────────────────────────────────────


class TestAttackRelTypes:
    def test_contains_exploits(self) -> None:
        assert EdgeKind.EXPLOITS.value in _ATTACK_REL_TYPES

    def test_contains_enables(self) -> None:
        assert EdgeKind.ENABLES.value in _ATTACK_REL_TYPES

    def test_contains_escalates_to(self) -> None:
        assert EdgeKind.ESCALATES_TO.value in _ATTACK_REL_TYPES

    def test_is_pipe_separated_string(self) -> None:
        parts = _ATTACK_REL_TYPES.split("|")
        assert len(parts) >= 5

    def test_no_leading_or_trailing_pipe(self) -> None:
        assert not _ATTACK_REL_TYPES.startswith("|")
        assert not _ATTACK_REL_TYPES.endswith("|")


class TestSeverityMultiplier:
    def test_critical_cheapest(self) -> None:
        assert SEVERITY_COST_MULTIPLIER[Severity.CRITICAL] < SEVERITY_COST_MULTIPLIER[Severity.HIGH]

    def test_info_most_expensive(self) -> None:
        assert SEVERITY_COST_MULTIPLIER[Severity.INFO] > SEVERITY_COST_MULTIPLIER[Severity.LOW]

    def test_medium_is_neutral(self) -> None:
        assert SEVERITY_COST_MULTIPLIER[Severity.MEDIUM] == 1.0

    def test_all_severities_covered(self) -> None:
        for sev in Severity:
            assert sev in SEVERITY_COST_MULTIPLIER


# ── compute_edge_cost ────────────────────────────────────────────────────


class TestComputeEdgeCost:
    def test_critical_unvalidated(self) -> None:
        cost = compute_edge_cost("critical", False, 1.0)
        assert cost == pytest.approx(0.4)

    def test_critical_validated_halved(self) -> None:
        cost = compute_edge_cost("critical", True, 1.0)
        assert cost == pytest.approx(0.2)

    def test_medium_unvalidated_neutral(self) -> None:
        cost = compute_edge_cost("medium", False, 1.0)
        assert cost == pytest.approx(1.0)

    def test_info_raises_cost(self) -> None:
        cost = compute_edge_cost("info", False, 1.0)
        assert cost == pytest.approx(2.5)

    def test_unknown_severity_falls_back_to_1(self) -> None:
        cost = compute_edge_cost("not-a-severity", False, 1.0)
        assert cost == pytest.approx(1.0)

    def test_empty_severity_falls_back_to_1(self) -> None:
        cost = compute_edge_cost("", False, 1.0)
        assert cost == pytest.approx(1.0)

    def test_minimum_base_weight_clamped_at_0_05(self) -> None:
        # base_weight=0.0 → clamp to 0.05 → × critical multiplier 0.4
        cost = compute_edge_cost("critical", False, 0.0)
        assert cost == pytest.approx(0.05 * 0.4)

    def test_high_base_weight_scales(self) -> None:
        cost = compute_edge_cost("medium", False, 3.0)
        assert cost == pytest.approx(3.0)

    def test_validated_high_severity(self) -> None:
        cost = compute_edge_cost("high", True, 1.0)
        # 0.6 * 0.5 = 0.3
        assert cost == pytest.approx(0.3)


# ── ChainStep ────────────────────────────────────────────────────────────


class TestChainStep:
    def test_frozen(self) -> None:
        step = _make_step()
        with pytest.raises((AttributeError, TypeError)):
            step.hop_cost = 99.0  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        step = _make_step(
            node_id="x",
            node_label="Host",
            node_kind="Host",
            edge_kind="LEADS_TO",
            hop_cost=0.8,
        )
        assert step.node_id == "x"
        assert step.node_label == "Host"
        assert step.node_kind == "Host"
        assert step.edge_kind == "LEADS_TO"
        assert step.hop_cost == 0.8


# ── Chain ────────────────────────────────────────────────────────────────


class TestChainLength:
    def test_empty_chain_length_zero(self) -> None:
        chain = _make_chain(steps=[])
        assert chain.length == 0

    def test_single_step_length_one(self) -> None:
        chain = _make_chain(steps=[_make_step()])
        assert chain.length == 1

    def test_multiple_steps(self) -> None:
        steps = [_make_step(node_id=f"n{i}") for i in range(5)]
        chain = _make_chain(steps=steps)
        assert chain.length == 5


class TestChainPathLabels:
    def test_empty_steps_only_entrypoint(self) -> None:
        chain = _make_chain(entrypoint_label="EP", steps=[])
        assert chain.path_labels == ["EP"]

    def test_steps_appended(self) -> None:
        steps = [
            _make_step(node_id="n1", node_label="Middle"),
            _make_step(node_id="n2", node_label="Crown"),
        ]
        chain = _make_chain(entrypoint_label="Entry", steps=steps)
        assert chain.path_labels == ["Entry", "Middle", "Crown"]


class TestChainSummary:
    def test_format_includes_cost_and_length(self) -> None:
        chain = _make_chain(total_cost=3.14, steps=[_make_step()])
        summary = chain.summary()
        assert "cost=3.14" in summary
        assert "len=1" in summary

    def test_format_contains_entrypoint(self) -> None:
        chain = _make_chain(entrypoint_label="WebApp", steps=[])
        assert "WebApp" in chain.summary()

    def test_format_arrow_separator(self) -> None:
        steps = [_make_step(node_label="DB")]
        chain = _make_chain(entrypoint_label="App", steps=steps)
        assert "App → DB" in chain.summary()


class TestChainToDict:
    def test_top_level_keys(self) -> None:
        chain = _make_chain()
        d = chain.to_dict()
        assert "entrypoint" in d
        assert "crown_jewel" in d
        assert "total_cost" in d
        assert "length" in d
        assert "steps" in d

    def test_total_cost_rounded(self) -> None:
        chain = _make_chain(total_cost=1.23456789)
        d = chain.to_dict()
        assert d["total_cost"] == round(1.23456789, 3)

    def test_steps_list_structure(self) -> None:
        steps = [
            _make_step(node_id="n1", node_label="Host", node_kind="Host", edge_kind="EXPLOITS")
        ]
        chain = _make_chain(steps=steps)
        d = chain.to_dict()
        assert len(d["steps"]) == 1
        s = d["steps"][0]
        assert s["node_id"] == "n1"
        assert s["node_label"] == "Host"
        assert s["edge_kind"] == "EXPLOITS"
        assert "hop_cost" in s

    def test_empty_steps_list(self) -> None:
        chain = _make_chain(steps=[])
        d = chain.to_dict()
        assert d["steps"] == []
        assert d["length"] == 0


# ── plan_chains ──────────────────────────────────────────────────────────


class TestPlanChains:
    def _row(
        self,
        entry_id: str = "e1",
        entry_label: str = "EP",
        crown_id: str = "c1",
        crown_label: str = "DB",
        total_cost: float = 2.0,
        path_nodes: list[dict[str, Any]] | None = None,
        path_edges: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Use explicit None-check so callers can pass [] to mean "empty"
        if path_nodes is None:
            path_nodes = [
                {"id": entry_id, "label": entry_label, "kind": "Entrypoint"},
                {"id": crown_id, "label": crown_label, "kind": "CrownJewel"},
            ]
        if path_edges is None:
            path_edges = [{"kind": "EXPLOITS", "cost": 2.0}]
        return {
            "entry_id": entry_id,
            "entry_label": entry_label,
            "crown_id": crown_id,
            "crown_label": crown_label,
            "total_cost": total_cost,
            "path_nodes": path_nodes,
            "path_edges": path_edges,
        }

    def test_happy_path_apoc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [self._row()]
        fake = _FakeStore(rows=rows)
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chains = plan_chains()
        assert len(chains) == 1
        c = chains[0]
        assert c.entrypoint_id == "e1"
        assert c.crown_jewel_id == "c1"
        assert c.total_cost == pytest.approx(2.0)

    def test_apoc_failure_falls_back_to_shortestpath(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """First query_custom raises → second call (fallback) returns rows."""
        rows = [self._row()]
        call_count = 0

        class _FailFirstStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("APOC not available")
                return rows

        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", _FailFirstStore())
        chains = plan_chains()
        assert call_count == 2
        assert len(chains) == 1

    def test_both_queries_fail_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _AlwaysFailStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
                raise RuntimeError("Neo4j down")

        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", _AlwaysFailStore())
        chains = plan_chains()
        assert chains == []

    def test_multi_hop_steps_built_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = self._row(
            path_nodes=[
                {"id": "e1", "label": "EP", "kind": "Entrypoint"},
                {"id": "m1", "label": "Middle", "kind": "Host"},
                {"id": "c1", "label": "DB", "kind": "CrownJewel"},
            ],
            path_edges=[
                {"kind": "EXPLOITS", "cost": 1.0},
                {"kind": "LEADS_TO", "cost": 1.5},
            ],
        )
        fake = _FakeStore(rows=[row])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chains = plan_chains()
        assert len(chains) == 1
        assert chains[0].length == 2
        assert chains[0].steps[0].node_label == "Middle"
        assert chains[0].steps[1].node_label == "DB"
        assert chains[0].steps[0].hop_cost == 1.0
        assert chains[0].steps[1].hop_cost == 1.5

    def test_entrypoint_ids_filter_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        plan_chains(entrypoint_ids=["ep1", "ep2"])
        assert any("entry_ids" in str(p) for _, p in fake.calls)

    def test_crown_jewel_ids_filter_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        plan_chains(crown_jewel_ids=["cj1"])
        assert any("crown_ids" in str(p) for _, p in fake.calls)

    def test_empty_path_nodes_produces_empty_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = self._row(path_nodes=[], path_edges=[])
        fake = _FakeStore(rows=[row])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chains = plan_chains()
        assert chains[0].length == 0

    def test_missing_edge_data_defaults_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = self._row(
            path_nodes=[
                {"id": "e1", "label": "EP", "kind": "Entrypoint"},
                {"id": "c1", "label": "DB", "kind": "CrownJewel"},
            ],
            path_edges=[],  # no edges — should default
        )
        fake = _FakeStore(rows=[row])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chains = plan_chains()
        assert chains[0].steps[0].hop_cost == 1.0  # default
        assert chains[0].steps[0].edge_kind == ""  # default


# ── promote_chain ────────────────────────────────────────────────────────


class TestPromoteChain:
    def test_returns_string_node_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain = _make_chain(steps=[])
        result = promote_chain(chain)
        assert isinstance(result, str)
        assert len(result) == 16  # sha1[:16]

    def test_deterministic_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain = _make_chain(entrypoint_id="ep-A", crown_jewel_id="cj-B", steps=[])
        id1 = promote_chain(chain)
        id2 = promote_chain(chain)
        assert id1 == id2

    def test_different_chains_different_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain_a = _make_chain(entrypoint_id="ep1", crown_jewel_id="cj1")
        chain_b = _make_chain(entrypoint_id="ep2", crown_jewel_id="cj2")
        assert promote_chain(chain_a) != promote_chain(chain_b)

    def test_step_queries_issued_per_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        steps = [_make_step(node_id=f"s{i}") for i in range(3)]
        chain = _make_chain(steps=steps)
        promote_chain(chain)
        # 1 main MERGE query + 3 STEP queries = 4 total
        assert len(fake.calls) == 4

    def test_no_step_queries_for_empty_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain = _make_chain(steps=[])
        promote_chain(chain)
        # Only the main MERGE query
        assert len(fake.calls) == 1


# ── critical_path_score ──────────────────────────────────────────────────


class TestCriticalPathScore:
    def test_no_vuln_steps_uses_only_inv_cost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Chain with no Vulnerability nodes — worst_sev stays 0.0."""
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain = _make_chain(total_cost=10.0, steps=[_make_step(node_kind="Host")])
        score = critical_path_score(chain)
        expected = round(0.6 * (1.0 / 10.0) * 10 + 0.4 * 0.0, 2)
        assert score == pytest.approx(expected)

    def test_critical_vuln_boosts_score(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import _state as state

        fake = _FakeStore(rows=[{"severity": "critical"}])
        monkeypatch.setattr(state, "_store", fake)
        step = _make_step(node_id="v1", node_kind=NodeKind.VULNERABILITY.value)
        chain = _make_chain(total_cost=5.0, steps=[step])
        score = critical_path_score(chain)
        # worst_sev = 9.5 (SEVERITY_SCORE[critical])
        expected = round(0.6 * (1.0 / 5.0) * 10 + 0.4 * 9.5, 2)
        assert score == pytest.approx(expected)

    def test_query_failure_returns_score_without_sev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Store failure is swallowed; score based on inv cost alone."""
        from decepticon.tools.research import _state as state

        class _FailStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[Any]:
                raise RuntimeError("Neo4j down")

        monkeypatch.setattr(state, "_store", _FailStore())
        step = _make_step(node_id="v1", node_kind=NodeKind.VULNERABILITY.value)
        chain = _make_chain(total_cost=2.0, steps=[step])
        score = critical_path_score(chain)
        assert score >= 0.0  # should not raise

    def test_unknown_severity_string_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import _state as state

        fake = _FakeStore(rows=[{"severity": "bogus-sev"}])
        monkeypatch.setattr(state, "_store", fake)
        step = _make_step(node_id="v1", node_kind=NodeKind.VULNERABILITY.value)
        chain = _make_chain(total_cost=1.0, steps=[step])
        # Should not raise even with unknown severity
        score = critical_path_score(chain)
        assert score >= 0.0

    def test_very_small_total_cost_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """total_cost=0 → max(total_cost, 0.1) prevents ZeroDivisionError."""
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        chain = _make_chain(total_cost=0.0, steps=[])
        score = critical_path_score(chain)
        assert score == pytest.approx(round(0.6 * (1.0 / 0.1) * 10, 2))


# ── impact_analysis ──────────────────────────────────────────────────────


class TestImpactAnalysis:
    def test_returns_rows_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [
            {"id": "h1", "type": "Host", "label": "10.0.0.1", "depth": 1},
            {"id": "s1", "type": "Service", "label": "svc", "depth": 2},
        ]
        fake = _FakeStore(rows=rows)
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        result = impact_analysis("start-node")
        assert len(result) == 2
        assert result[0]["id"] == "h1"

    def test_returns_empty_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import _state as state

        class _FailStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[Any]:
                raise RuntimeError("APOC unavailable")

        monkeypatch.setattr(state, "_store", _FailStore())
        result = impact_analysis("any-node")
        assert result == []

    def test_node_id_passed_in_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        impact_analysis("target-node-99")
        assert fake.calls[0][1]["node_id"] == "target-node-99"


# ── unexplored_surface ───────────────────────────────────────────────────


class TestUnexploredSurface:
    def test_returns_rows_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [{"host_id": "h1", "ip": "10.0.0.2", "hostname": "api", "services": ["80/"]}]
        fake = _FakeStore(rows=rows)
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        result = unexplored_surface()
        assert len(result) == 1
        assert result[0]["ip"] == "10.0.0.2"

    def test_returns_empty_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import _state as state

        class _FailStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[Any]:
                raise RuntimeError("Neo4j down")

        monkeypatch.setattr(state, "_store", _FailStore())
        result = unexplored_surface()
        assert result == []


# ── credential_reachability ───────────────────────────────────────────────


class TestCredentialReachability:
    def test_returns_rows_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [
            {
                "cred_id": "cred1",
                "identity": "admin",
                "accessible_targets": [{"type": "Host", "name": "10.0.0.1"}],
                "active_sessions": ["10.0.0.5"],
            }
        ]
        fake = _FakeStore(rows=rows)
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        result = credential_reachability("cred1")
        assert len(result) == 1
        assert result[0]["identity"] == "admin"

    def test_returns_empty_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from decepticon.tools.research import _state as state

        class _FailStore:
            def query_custom(self, cypher: str, params: dict[str, Any]) -> list[Any]:
                raise RuntimeError("Neo4j down")

        monkeypatch.setattr(state, "_store", _FailStore())
        result = credential_reachability("cred99")
        assert result == []

    def test_cred_id_passed_in_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeStore(rows=[])
        from decepticon.tools.research import _state as state

        monkeypatch.setattr(state, "_store", fake)
        credential_reachability("credential-xyz")
        assert fake.calls[0][1]["cred_id"] == "credential-xyz"
