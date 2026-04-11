"""Unit tests for the attack-chain planner."""

from __future__ import annotations

from decepticon.tools.research.chain import (
    critical_path_score,
    plan_chains,
    promote_chain,
)
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)


def _build_ssrf_chain_graph() -> tuple[KnowledgeGraph, str, str]:
    g = KnowledgeGraph()
    entry = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "public-api"))
    ssrf = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "SSRF", severity="high"))
    meta = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "IMDS leak", severity="critical"))
    cred = g.upsert_node(Node.make(NodeKind.CREDENTIAL, "iam-role"))
    jewel = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "prod-s3"))

    g.upsert_edge(Edge.make(entry.id, ssrf.id, EdgeKind.ENABLES, weight=0.5))
    g.upsert_edge(Edge.make(ssrf.id, meta.id, EdgeKind.ENABLES, weight=0.8))
    g.upsert_edge(Edge.make(meta.id, cred.id, EdgeKind.LEAKS, weight=0.3))
    g.upsert_edge(Edge.make(cred.id, jewel.id, EdgeKind.GRANTS, weight=0.4))
    return g, entry.id, jewel.id


class TestPlanChains:
    def test_finds_complete_chain(self) -> None:
        g, _, _ = _build_ssrf_chain_graph()
        chains = plan_chains(g)
        assert len(chains) == 1
        c = chains[0]
        labels = c.path_labels
        assert labels[0] == "public-api"
        assert labels[-1] == "prod-s3"
        assert c.length == 4

    def test_returns_empty_without_entrypoints(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "target"))
        assert plan_chains(g) == []

    def test_returns_empty_without_crown_jewels(self) -> None:
        g = KnowledgeGraph()
        g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "entry"))
        assert plan_chains(g) == []

    def test_non_traversable_edges_blocked(self) -> None:
        g = KnowledgeGraph()
        a = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "a"))
        b = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "b", severity="high"))
        c = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "c"))
        # Only edge is DEFINED_IN which the planner skips
        g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.DEFINED_IN))
        g.upsert_edge(Edge.make(b.id, c.id, EdgeKind.DEFINED_IN))
        assert plan_chains(g) == []

    def test_cheapest_path_wins(self) -> None:
        g = KnowledgeGraph()
        entry = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "e"))
        cheap_mid = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "cheap", severity="critical"))
        exp_mid = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "exp", severity="low"))
        goal = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "g"))
        g.upsert_edge(Edge.make(entry.id, cheap_mid.id, EdgeKind.ENABLES, weight=0.3))
        g.upsert_edge(Edge.make(cheap_mid.id, goal.id, EdgeKind.GRANTS, weight=0.3))
        g.upsert_edge(Edge.make(entry.id, exp_mid.id, EdgeKind.ENABLES, weight=2.0))
        g.upsert_edge(Edge.make(exp_mid.id, goal.id, EdgeKind.GRANTS, weight=2.0))
        chains = plan_chains(g, top_k=1)
        assert len(chains) == 1
        assert "cheap" in chains[0].path_labels

    def test_max_depth_limits(self) -> None:
        g = KnowledgeGraph()
        entry = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "e"))
        mids = [
            g.upsert_node(Node.make(NodeKind.VULNERABILITY, f"m{i}", severity="medium"))
            for i in range(5)
        ]
        goal = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "g"))
        chain_nodes = [entry, *mids, goal]
        for a, b in zip(chain_nodes[:-1], chain_nodes[1:]):
            g.upsert_edge(Edge.make(a.id, b.id, EdgeKind.ENABLES, weight=0.2))
        # max_depth 3 means path length ≤ 3 edges, not enough for 6-hop chain
        assert plan_chains(g, max_depth=3) == []
        assert len(plan_chains(g, max_depth=10)) == 1

    def test_validated_vulns_are_cheaper(self) -> None:
        g1 = KnowledgeGraph()
        g2 = KnowledgeGraph()
        for g, validated in [(g1, False), (g2, True)]:
            entry = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "e"))
            mid = g.upsert_node(
                Node.make(
                    NodeKind.VULNERABILITY,
                    "v",
                    severity="high",
                    validated=validated,
                )
            )
            goal = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "g"))
            g.upsert_edge(Edge.make(entry.id, mid.id, EdgeKind.ENABLES, weight=1.0))
            g.upsert_edge(Edge.make(mid.id, goal.id, EdgeKind.GRANTS, weight=1.0))
        c1 = plan_chains(g1)[0]
        c2 = plan_chains(g2)[0]
        assert c2.total_cost < c1.total_cost


class TestPromoteChain:
    def test_promotes_chain_into_graph(self) -> None:
        g, _, _ = _build_ssrf_chain_graph()
        chains = plan_chains(g)
        node = promote_chain(g, chains[0])
        assert node.kind == NodeKind.ATTACK_PATH
        assert node.props["length"] == 4
        # STARTS_AT / REACHES / CONTAINS edges exist
        out_edges = [e for e in g.edges.values() if e.src == node.id]
        kinds = {e.kind for e in out_edges}
        assert EdgeKind.STARTS_AT in kinds
        assert EdgeKind.REACHES in kinds
        assert EdgeKind.CONTAINS in kinds


class TestCriticalPathScore:
    def test_worst_severity_boosts_score(self) -> None:
        g = KnowledgeGraph()
        entry = g.upsert_node(Node.make(NodeKind.ENTRYPOINT, "e"))
        low = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "l", severity="low"))
        crit = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "c", severity="critical"))
        g_low = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "g1"))
        g_crit = g.upsert_node(Node.make(NodeKind.CROWN_JEWEL, "g2"))
        g.upsert_edge(Edge.make(entry.id, low.id, EdgeKind.ENABLES, weight=0.5))
        g.upsert_edge(Edge.make(low.id, g_low.id, EdgeKind.GRANTS, weight=0.5))
        g.upsert_edge(Edge.make(entry.id, crit.id, EdgeKind.ENABLES, weight=0.5))
        g.upsert_edge(Edge.make(crit.id, g_crit.id, EdgeKind.GRANTS, weight=0.5))
        chains = plan_chains(g, top_k=5)
        scores = {c.crown_jewel.label: critical_path_score(c) for c in chains}
        assert scores["g2"] > scores["g1"]
