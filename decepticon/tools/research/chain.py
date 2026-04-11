"""Attack-chain planner.

Given a KnowledgeGraph, compute multi-hop exploitation paths from
``Entrypoint`` nodes to ``CrownJewel`` nodes, ranked by composite
exploit cost. The cost model combines:

- edge weight (analyst-assigned difficulty, lower = easier)
- vulnerability severity (critical shrinks cost, info grows it)
- node-level validation state (validated PoCs halve the cost)

The planner does NOT mutate the graph — it returns ranked chains as
plain data structures that callers can serialize or promote into
``Chain`` nodes via :func:`promote_chain`.

Algorithm
---------
Dijkstra with pruning:
- Start: every entrypoint node.
- Goal: every crown-jewel node.
- Frontier is a min-heap keyed on cumulative cost.
- Paths exceeding ``max_depth`` or ``max_cost`` are abandoned early.

For small engagement graphs (<10k nodes) the O((E+N) log N) cost is
negligible. For larger graphs we iterate per-(entry, goal) pair so the
planner can be parallelised or early-exited by the caller.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

from decepticon.tools.research.graph import (
    SEVERITY_SCORE,
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)

# ── Cost model ──────────────────────────────────────────────────────────

# Edge kinds that should NEVER appear in an attack path (e.g. documentation
# edges, validation back-references). Anything not listed here is traversable.
_NON_TRAVERSABLE: set[EdgeKind] = {
    EdgeKind.DEFINED_IN,
    EdgeKind.LOCATED_AT,
    EdgeKind.VALIDATES,
}

# Severity → multiplier. High severity shrinks cost (faster to reach).
_SEVERITY_MULTIPLIER: dict[str, float] = {
    Severity.CRITICAL.value: 0.4,
    Severity.HIGH.value: 0.6,
    Severity.MEDIUM.value: 1.0,
    Severity.LOW.value: 1.6,
    Severity.INFO.value: 2.5,
}


@dataclass(frozen=True)
class ChainStep:
    """One hop in an attack chain."""

    edge: Edge
    node: Node
    hop_cost: float


@dataclass
class Chain:
    """A candidate attack chain from an entrypoint to a crown jewel."""

    entrypoint: Node
    crown_jewel: Node
    steps: list[ChainStep] = field(default_factory=list)
    total_cost: float = 0.0

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def path_labels(self) -> list[str]:
        return [self.entrypoint.label] + [s.node.label for s in self.steps]

    def summary(self) -> str:
        arrow = " → ".join(self.path_labels)
        return f"cost={self.total_cost:.2f} len={self.length} {arrow}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entrypoint": self.entrypoint.label,
            "crown_jewel": self.crown_jewel.label,
            "total_cost": round(self.total_cost, 3),
            "length": self.length,
            "steps": [
                {
                    "edge_kind": s.edge.kind.value,
                    "node_id": s.node.id,
                    "node_label": s.node.label,
                    "node_kind": s.node.kind.value,
                    "hop_cost": round(s.hop_cost, 3),
                }
                for s in self.steps
            ],
        }


def _node_cost(node: Node) -> float:
    """Return a per-node cost multiplier."""
    mult = 1.0
    if node.kind == NodeKind.VULNERABILITY:
        severity = node.props.get("severity", Severity.MEDIUM.value)
        mult *= _SEVERITY_MULTIPLIER.get(severity, 1.0)
    if node.props.get("validated") is True:
        mult *= 0.5  # validated PoCs are easier to chain
    return mult


def _edge_cost(edge: Edge, node: Node) -> float:
    """Compute the cost of traversing ``edge`` into ``node``."""
    base = max(edge.weight, 0.05)  # avoid zero-weight tricks
    return base * _node_cost(node)


# ── Dijkstra core ───────────────────────────────────────────────────────


def _dijkstra(
    graph: KnowledgeGraph,
    src: str,
    goal: str,
    *,
    max_depth: int,
    max_cost: float,
) -> Chain | None:
    """Return the cheapest chain from src to goal, or None if unreachable."""
    if src not in graph.nodes or goal not in graph.nodes:
        return None

    adj = graph.adjacency()

    # (cumulative_cost, monotonic counter, current_node_id, path[list[(Edge, Node, hop_cost)]])
    frontier: list[tuple[float, int, str, list[ChainStep]]] = []
    best: dict[str, float] = {src: 0.0}
    counter = 0
    heapq.heappush(frontier, (0.0, counter, src, []))

    while frontier:
        cost, _, current, steps = heapq.heappop(frontier)
        if cost > max_cost:
            continue
        if current == goal and steps:
            entry_node = graph.nodes[src]
            goal_node = graph.nodes[goal]
            return Chain(
                entrypoint=entry_node,
                crown_jewel=goal_node,
                steps=steps,
                total_cost=cost,
            )
        if len(steps) >= max_depth:
            continue

        for nxt_id, edge in adj.get(current, []):
            if edge.kind in _NON_TRAVERSABLE:
                continue
            if any(step.node.id == nxt_id for step in steps):
                continue  # simple path — no revisits
            nxt_node = graph.nodes[nxt_id]
            hop = _edge_cost(edge, nxt_node)
            new_cost = cost + hop
            if new_cost > max_cost:
                continue
            if new_cost >= best.get(nxt_id, float("inf")):
                continue  # dominated path
            best[nxt_id] = new_cost
            counter += 1
            heapq.heappush(
                frontier,
                (
                    new_cost,
                    counter,
                    nxt_id,
                    steps + [ChainStep(edge=edge, node=nxt_node, hop_cost=hop)],
                ),
            )

    return None


# ── Public API ──────────────────────────────────────────────────────────


def plan_chains(
    graph: KnowledgeGraph,
    *,
    max_depth: int = 8,
    max_cost: float = 20.0,
    top_k: int = 10,
    entrypoints: list[str] | None = None,
    crown_jewels: list[str] | None = None,
) -> list[Chain]:
    """Enumerate and rank attack chains.

    ``entrypoints`` and ``crown_jewels`` are optional node-id filters; when
    omitted, all nodes of kind ``ENTRYPOINT`` / ``CROWN_JEWEL`` are used.

    Returns up to ``top_k`` chains, lowest total cost first.
    """
    entry_nodes = (
        [graph.nodes[e] for e in entrypoints if e in graph.nodes]
        if entrypoints is not None
        else graph.by_kind(NodeKind.ENTRYPOINT)
    )
    goal_nodes = (
        [graph.nodes[g] for g in crown_jewels if g in graph.nodes]
        if crown_jewels is not None
        else graph.by_kind(NodeKind.CROWN_JEWEL)
    )

    if not entry_nodes or not goal_nodes:
        return []

    chains: list[Chain] = []
    for entry in entry_nodes:
        for goal in goal_nodes:
            chain = _dijkstra(
                graph,
                entry.id,
                goal.id,
                max_depth=max_depth,
                max_cost=max_cost,
            )
            if chain is not None:
                chains.append(chain)

    chains.sort(key=lambda c: (c.total_cost, c.length))
    return chains[:top_k]


def promote_chain(graph: KnowledgeGraph, chain: Chain) -> Node:
    """Materialize a computed chain as a ``CHAIN`` node in the graph.

    The chain gets edges ``STARTS_AT → entrypoint``, ``REACHES → crown_jewel``,
    and ``CONTAINS → each step node`` so future queries can find it.
    """
    label = f"{chain.entrypoint.label} → {chain.crown_jewel.label} (cost {chain.total_cost:.2f})"
    props: dict[str, Any] = {
        "key": f"chain::{chain.entrypoint.id}::{chain.crown_jewel.id}",
        "total_cost": round(chain.total_cost, 3),
        "length": chain.length,
        "path": [s.node.id for s in chain.steps],
    }
    node = Node.make(NodeKind.CHAIN, label, **props)
    graph.upsert_node(node)
    graph.upsert_edge(Edge.make(node.id, chain.entrypoint.id, EdgeKind.STARTS_AT))
    graph.upsert_edge(Edge.make(node.id, chain.crown_jewel.id, EdgeKind.REACHES))
    for step in chain.steps:
        graph.upsert_edge(Edge.make(node.id, step.node.id, EdgeKind.CONTAINS))
    return node


def critical_path_score(chain: Chain) -> float:
    """Single-number rating for a chain used by the orchestrator prioritiser.

    Combines inverse cost and severity-of-worst-hop so chains with one
    critical pivot aren't masked by a generally cheap path.
    """
    worst_sev = max(
        (
            SEVERITY_SCORE.get(
                Severity(step.node.props.get("severity", Severity.INFO.value)),
                0.0,
            )
            for step in chain.steps
            if step.node.kind == NodeKind.VULNERABILITY
        ),
        default=0.0,
    )
    inv_cost = 1.0 / max(chain.total_cost, 0.1)
    return round(0.6 * inv_cost * 10 + 0.4 * worst_sev, 2)
