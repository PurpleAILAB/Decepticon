"""In-memory skill knowledge graph — infra-free, built from frontmatter.

Wraps an in-memory :class:`KnowledgeGraph` carrying three layers:

* the **skill** layer — one ``Skill`` node per SKILL.md,
* the **ATT&CK** layer — ``Technique`` / ``Tactic`` nodes from the bundled
  offline dataset, joined to skills by ``TEACHES`` edges,
* the **skill-to-skill** layer — ``REQUIRES`` / ``CHAINS_TO`` / ``REFINES``.

Unlike the engagement attack graph this never touches Neo4j: skill routing
must work in any context, including network-isolated sandboxes with no
database. The graph is built once per process and cached.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from decepticon.tools.research.attack.catalog import AttackCatalog, load_attack_catalog
from decepticon.tools.research.attack.seed import technique_graph_elements
from decepticon.tools.research.attack.skill_index import (
    SkillRecord,
    load_skill_index,
    skill_graph_elements,
    skill_node_id,
    skill_skill_edges,
)
from decepticon.tools.research.attack.validate import (
    SkillGraphDiagnostics,
    validate_skill_graph,
)
from decepticon.tools.research.graph import KnowledgeGraph

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillGraph:
    """The skill knowledge graph plus its build-time validation result."""

    graph: KnowledgeGraph
    by_path: dict[str, str]
    catalog: AttackCatalog
    diagnostics: SkillGraphDiagnostics


def build_skill_graph(
    records: list[SkillRecord] | None = None,
    catalog: AttackCatalog | None = None,
) -> SkillGraph:
    """Build a :class:`SkillGraph` from skill records and the ATT&CK catalog.

    Both default to the bundled datasets. Pure and infra-free — no Neo4j,
    no network access.
    """
    records = load_skill_index() if records is None else records
    catalog = catalog or load_attack_catalog()
    diagnostics = validate_skill_graph(records, catalog)

    graph = KnowledgeGraph()
    tech_nodes, tech_edges = technique_graph_elements(catalog)
    skill_nodes, teaches_edges = skill_graph_elements(records)
    graph.bulk_upsert_nodes(tech_nodes)
    graph.bulk_upsert_nodes(skill_nodes)
    graph.bulk_upsert_edges(tech_edges)
    graph.bulk_upsert_edges(teaches_edges)
    graph.bulk_upsert_edges(skill_skill_edges(records))

    by_path = {rec.path: skill_node_id(rec.path) for rec in records}
    return SkillGraph(graph=graph, by_path=by_path, catalog=catalog, diagnostics=diagnostics)


@lru_cache(maxsize=1)
def get_skill_graph() -> SkillGraph:
    """Return the process-global skill graph, building it on first call.

    Cached for the process lifetime — skills are static within a run. Call
    ``get_skill_graph.cache_clear()`` to force a rebuild (used by the
    ``DECEPTICON_SKILLS_DIR`` development workflow).
    """
    skill_graph = build_skill_graph()
    diag = skill_graph.diagnostics
    if diag.errors:
        log.warning(
            "skill graph built with %d error(s): %s",
            len(diag.errors),
            "; ".join(diag.errors[:5]),
        )
    elif diag.warnings:
        log.info("skill graph built with %d warning(s)", len(diag.warnings))
    return skill_graph


__all__ = ["SkillGraph", "build_skill_graph", "get_skill_graph"]
