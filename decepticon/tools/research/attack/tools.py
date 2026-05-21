"""LangChain ``@tool`` wrappers for the ATT&CK spine.

These surface the offline ATT&CK catalog and the skill↔technique↔finding
joins to agents. Exported as ``ATTACK_TOOLS`` and appended to
``RESEARCH_TOOLS`` so every research-equipped agent gets them.
"""

from __future__ import annotations

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, _load, _save
from decepticon.tools.research.attack.catalog import load_attack_catalog, normalize
from decepticon.tools.research.attack.link import backfill_mitre, link_mitre
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.graph import EdgeKind, NodeKind


@tool
def mitre_lookup(technique_id: str) -> str:
    """Look up a MITRE ATT&CK technique by ID — offline, no graph needed.

    WHEN TO USE: To resolve a technique ID (e.g. ``T1190``) into its name,
    tactics, and description before tagging a finding or planning an
    objective.

    Args:
        technique_id: ATT&CK technique ID, e.g. ``T1190`` or ``T1558.003``.

    Returns:
        JSON with the technique's name, tactics, tactic IDs, sub-technique
        info, description, and URL — or an ``error`` field.
    """
    norm = normalize(technique_id)
    if norm is None:
        return _json({"error": f"not a valid ATT&CK ID: {technique_id!r}"})
    catalog = load_attack_catalog()
    tech = catalog.technique(norm)
    if tech is None:
        return _json({"error": f"unknown technique: {norm}"})
    return _json(
        {
            "id": tech.id,
            "name": tech.name,
            "tactics": tech.tactics,
            "tactic_ids": catalog.tactic_ids_for(tech.id),
            "is_subtechnique": tech.is_subtechnique,
            "parent": tech.parent,
            "description": tech.description,
            "url": tech.url,
        }
    )


@tool
def mitre_skills_for_technique(technique_id: str) -> str:
    """List the Decepticon skills that teach a given ATT&CK technique.

    WHEN TO USE: When an objective is tagged with a technique and you want
    the specific skill that covers it before acting.

    Args:
        technique_id: ATT&CK technique ID, e.g. ``T1190``.

    Returns:
        JSON with the matching skills (name + ``load_skill`` path).
    """
    norm = normalize(technique_id)
    if norm is None:
        return _json({"error": f"not a valid ATT&CK ID: {technique_id!r}"})
    graph, _path = _load()
    tech_node = technique_node_id(norm)
    skills = [
        {"name": nbr.label, "path": nbr.props.get("key", "")}
        for _edge, nbr in graph.neighbors(tech_node, EdgeKind.TEACHES, direction="in")
        if nbr.kind == NodeKind.SKILL
    ]
    skills.sort(key=lambda s: s["name"])
    return _json({"technique": norm, "skills": skills, "count": len(skills)})


@tool
def kg_backfill_mitre() -> str:
    """Backfill ATT&CK ``MAPS_TO`` edges for existing graph nodes.

    WHEN TO USE: Once after importing findings/vulnerabilities that carry
    ``mitre`` props but predate the ATT&CK spine — connects them to the
    Technique layer. Idempotent; safe to re-run.

    Returns:
        JSON with the count of nodes scanned and edges linked.
    """
    graph, path = _load()
    result = backfill_mitre(graph)
    _save(graph, path)
    return _json(result)


@tool
def kg_link_finding_technique(finding_id: str, technique_id: str) -> str:
    """Link a graph node to an ATT&CK technique via a ``MAPS_TO`` edge.

    WHEN TO USE: To attach a technique to a finding/vulnerability after the
    fact (e.g. an analyst correction).

    Args:
        finding_id: Node id (from a ``kg_add_node`` return value).
        technique_id: ATT&CK technique ID, e.g. ``T1190``.

    Returns:
        JSON confirming the link, or an ``error`` field.
    """
    graph, path = _load()
    node = graph.nodes.get(finding_id)
    if node is None:
        return _json({"error": f"node not found: {finding_id}"})
    count = link_mitre(graph, node, [technique_id])
    if count == 0:
        return _json({"error": f"not a valid technique ID: {technique_id!r}"})
    _save(graph, path)
    return _json({"linked": count, "src": finding_id, "technique": normalize(technique_id)})


ATTACK_TOOLS = [
    mitre_lookup,
    mitre_skills_for_technique,
    kg_backfill_mitre,
    kg_link_finding_technique,
]

__all__ = [
    "ATTACK_TOOLS",
    "kg_backfill_mitre",
    "kg_link_finding_technique",
    "mitre_lookup",
    "mitre_skills_for_technique",
]
