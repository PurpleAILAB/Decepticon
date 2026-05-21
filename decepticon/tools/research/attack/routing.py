"""Technique-aware skill routing.

Given an objective's MITRE ATT&CK technique IDs, find and rank the skills
that teach them by traversing ``TEACHES`` edges in the knowledge graph.
A sub-technique objective falls back to skills teaching the parent
technique when nothing teaches the sub-technique directly.
"""

from __future__ import annotations

from collections import defaultdict

from decepticon.tools.research.attack.catalog import is_technique_id, parse_ids
from decepticon.tools.research.attack.seed import technique_node_id
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


__all__ = ["skills_for_objective"]
