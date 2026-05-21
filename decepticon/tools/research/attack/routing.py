"""Technique-aware skill routing.

Given an objective's MITRE ATT&CK technique IDs, find and rank the skills
that teach them by traversing the skill knowledge graph.

:func:`route_skills` is the primary entry point — it walks ``TEACHES``,
``REFINES``, ``REQUIRES`` and ``CHAINS_TO`` edges to return a
dependency-ordered skill path. :func:`skills_for_objective` is the original
flat lookup, kept for back-compatibility.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from decepticon.tools.research.attack.catalog import is_technique_id, parse_ids
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.attack.skill_graph import SkillGraph
from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph, Node, NodeKind


def _skills_teaching(graph: KnowledgeGraph, technique_id: str) -> list[Node]:
    """Skill nodes with a TEACHES edge into the given technique."""
    tnode = technique_node_id(technique_id)
    return [
        nbr
        for _edge, nbr in graph.neighbors(tnode, EdgeKind.TEACHES, direction="in")
        if nbr.kind == NodeKind.SKILL
    ]


def skills_for_objective(
    graph: KnowledgeGraph,
    mitre_value: object,
    max_results: int = 5,
) -> list[dict]:
    """Rank skills that teach an objective's ATT&CK techniques.

    ``mitre_value`` is the objective's ``mitre`` list (or comma string).
    Each sub-technique with no directly-teaching skill falls back to skills
    teaching its parent technique. Results are ranked by the number of the
    objective's techniques each skill covers.
    """
    techniques = [t for t in parse_ids(mitre_value) if is_technique_id(t)]
    if not techniques:
        return []

    coverage: dict[str, set[str]] = defaultdict(set)
    skill_nodes: dict[str, Node] = {}

    for tid in techniques:
        # Try the exact technique; only on a miss, fall back to the parent.
        candidates = [tid]
        if "." in tid:
            candidates.append(tid.rsplit(".", 1)[0])
        for cand in candidates:
            skills = _skills_teaching(graph, cand)
            if skills:
                for skill in skills:
                    coverage[skill.id].add(tid)
                    skill_nodes[skill.id] = skill
                break

    results = [
        {
            "name": skill_nodes[sid].label,
            "path": skill_nodes[sid].props.get("key", ""),
            "techniques": sorted(covered),
            "match_count": len(covered),
        }
        for sid, covered in coverage.items()
    ]
    results.sort(key=lambda r: (-r["match_count"], r["name"]))
    return results[:max_results]


# ── route_skills — dependency-ordered traversal ──────────────────────────────


@dataclass
class RoutedSkill:
    """One skill in a routed result — what to load, why, and in what order."""

    name: str
    path: str
    slug: str
    techniques: list[str]
    match_count: int
    order: int
    reason: str
    score: float


# Relevance weight per routing reason — higher means more directly relevant.
_REASON_WEIGHT: dict[str, float] = {
    "direct": 3.0,
    "prerequisite": 2.0,
    "chained": 1.0,
    "refines": 0.0,
}


def _slug_of(path: str) -> str:
    """Strip the ``/skills/`` prefix and ``/SKILL.md`` suffix from a path."""
    slug = path
    if slug.startswith("/skills/"):
        slug = slug[len("/skills/") :]
    if slug.endswith("/SKILL.md"):
        slug = slug[: -len("/SKILL.md")]
    return slug.strip("/")


def _candidate_ids(technique_id: str) -> list[str]:
    """A technique, plus its parent if it is a sub-technique (for fallback)."""
    candidates = [technique_id]
    if "." in technique_id:
        candidates.append(technique_id.rsplit(".", 1)[0])
    return candidates


def _topo_order(graph: KnowledgeGraph, members: set[str]) -> dict[str, int]:
    """Layered topological order over ``REQUIRES`` edges within ``members``.

    A skill's prerequisites always get a strictly lower order. Members left
    over by a ``REQUIRES`` cycle (caught by validation, tolerated here) are
    placed in a final layer rather than dropped.
    """
    prereqs: dict[str, set[str]] = {sid: set() for sid in members}
    dependents: dict[str, set[str]] = {sid: set() for sid in members}
    for sid in members:
        for _edge, dst in graph.neighbors(sid, EdgeKind.REQUIRES, direction="out"):
            if dst.id in members and dst.id != sid:
                prereqs[sid].add(dst.id)
                dependents[dst.id].add(sid)

    indegree = {sid: len(prereqs[sid]) for sid in members}
    order: dict[str, int] = {}
    layer = sorted(sid for sid in members if indegree[sid] == 0)
    current = 0
    while layer:
        for sid in layer:
            order[sid] = current
        nxt: set[str] = set()
        for sid in layer:
            for dep in dependents[sid]:
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    nxt.add(dep)
        layer = sorted(nxt)
        current += 1
    for sid in members:  # remainder of any REQUIRES cycle
        order.setdefault(sid, current)
    return order


def route_skills(
    skill_graph: SkillGraph,
    mitre_value: object,
    observed_findings: object = None,
    max_results: int = 8,
    expand_chains: bool = True,
) -> list[RoutedSkill]:
    """Route an objective's ATT&CK techniques to a dependency-ordered skill path.

    Traverses the skill knowledge graph: finds skills that teach the
    objective's techniques, collapses a general skill shadowed by a more
    specific one via ``REFINES``, pulls in transitive ``REQUIRES``
    prerequisites, optionally expands one hop of ``CHAINS_TO`` follow-ons,
    and returns the result in dependency order — every prerequisite before
    its dependents.

    ``observed_findings`` (technique IDs already seen this engagement) boost
    a skill's score. ``max_results`` bounds the relevance-selected set;
    mandatory prerequisites of selected skills are always kept even when that
    pushes the count past ``max_results``.
    """
    graph = skill_graph.graph
    techniques = [t for t in parse_ids(mitre_value) if is_technique_id(t)]
    if not techniques:
        return []
    observed = {t for t in parse_ids(observed_findings) if is_technique_id(t)}

    # Stage A — seed set: skills that directly teach the objective's techniques.
    coverage: dict[str, set[str]] = defaultdict(set)
    for tid in techniques:
        for cand in _candidate_ids(tid):
            skills = _skills_teaching(graph, cand)
            if skills:
                for skill in skills:
                    coverage[skill.id].add(tid)
                break
    if not coverage:
        return []

    reason: dict[str, str] = {sid: "direct" for sid in coverage}
    depth: dict[str, int] = {sid: 0 for sid in coverage}
    members: set[str] = set(coverage)

    # Stage B — refinement collapse: a more specific skill shadows the general one.
    for sid in list(coverage):
        for _edge, target in graph.neighbors(sid, EdgeKind.REFINES, direction="out"):
            if reason.get(target.id) == "direct":
                reason[target.id] = "refines"

    # Stage C — chain expansion: one hop of CHAINS_TO from each direct skill.
    if expand_chains:
        for sid in [s for s in list(members) if reason.get(s) == "direct"]:
            for _edge, nxt in graph.neighbors(sid, EdgeKind.CHAINS_TO, direction="out"):
                if nxt.id not in members:
                    members.add(nxt.id)
                    reason[nxt.id] = "chained"
                    depth[nxt.id] = 1

    # Stage D — prerequisite closure: transitively pull in REQUIRES targets.
    queue = list(members)
    while queue:
        sid = queue.pop()
        for _edge, prereq in graph.neighbors(sid, EdgeKind.REQUIRES, direction="out"):
            if prereq.id not in members:
                members.add(prereq.id)
                reason[prereq.id] = "prerequisite"
                depth[prereq.id] = depth.get(sid, 0) + 1
                queue.append(prereq.id)

    # Score every member: coverage dominates, then observed-finding overlap,
    # then how directly relevant the reason is, minus how deep it was pulled in.
    score: dict[str, float] = {}
    for sid in members:
        covered = coverage.get(sid, set())
        overlap = sum(1 for t in covered if t in observed)
        score[sid] = (
            10.0 * len(covered)
            + 5.0 * overlap
            + 2.0 * _REASON_WEIGHT.get(reason.get(sid, "chained"), 0.0)
            - 1.0 * depth.get(sid, 0)
        )

    # Relevance-select the top max_results, then restore mandatory prerequisites.
    selected = set(members)
    if max_results > 0 and len(members) > max_results:
        ranked = sorted(members, key=lambda s: (-score[s], graph.nodes[s].label))
        selected = set(ranked[:max_results])
        queue = list(selected)
        while queue:
            sid = queue.pop()
            for _edge, prereq in graph.neighbors(sid, EdgeKind.REQUIRES, direction="out"):
                if prereq.id in members and prereq.id not in selected:
                    selected.add(prereq.id)
                    queue.append(prereq.id)

    order = _topo_order(graph, selected)

    routed: list[RoutedSkill] = []
    for sid in selected:
        node = graph.nodes.get(sid)
        if node is None:
            continue
        path = str(node.props.get("key", ""))
        covered = sorted(coverage.get(sid, set()))
        routed.append(
            RoutedSkill(
                name=node.label,
                path=path,
                slug=_slug_of(path),
                techniques=covered,
                match_count=len(covered),
                order=order.get(sid, 0),
                reason=reason.get(sid, "chained"),
                score=round(score.get(sid, 0.0), 3),
            )
        )
    routed.sort(key=lambda rs: (rs.order, -rs.score, rs.name))
    return routed


__all__ = ["RoutedSkill", "route_skills", "skills_for_objective"]
