"""Unit tests for the in-memory skill knowledge graph."""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import (
    AttackCatalog,
    AttackTactic,
    AttackTechnique,
)
from decepticon.tools.research.attack.skill_graph import build_skill_graph, get_skill_graph
from decepticon.tools.research.attack.skill_index import SkillRecord, skill_node_id
from decepticon.tools.research.graph import EdgeKind, NodeKind

_CATALOG = AttackCatalog(
    version="test",
    tactics=[AttackTactic(id="TA0001", name="Initial Access", shortname="initial-access")],
    techniques=[
        AttackTechnique(
            id="T1190",
            name="Exploit Public-Facing Application",
            tactics=["initial-access"],
        ),
    ],
)

_RECS = [
    SkillRecord(
        name="web",
        path="/skills/web/SKILL.md",
        mitre=["T1190"],
        requires=["/skills/recon/SKILL.md"],
        chains_to=["/skills/post/SKILL.md"],
    ),
    SkillRecord(name="recon", path="/skills/recon/SKILL.md"),
    SkillRecord(name="post", path="/skills/post/SKILL.md"),
]


class TestBuildSkillGraph:
    def test_creates_one_node_per_skill(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        skills = sg.graph.by_kind(NodeKind.SKILL)
        assert {n.props["key"] for n in skills} == {
            "/skills/web/SKILL.md",
            "/skills/recon/SKILL.md",
            "/skills/post/SKILL.md",
        }

    def test_teaches_edge_connects_skill_to_technique(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        web = sg.by_path["/skills/web/SKILL.md"]
        teaches = sg.graph.neighbors(web, EdgeKind.TEACHES, direction="out")
        assert [nbr.kind for _edge, nbr in teaches] == [NodeKind.TECHNIQUE]

    def test_requires_and_chains_edges_present(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        web = sg.by_path["/skills/web/SKILL.md"]
        req = sg.graph.neighbors(web, EdgeKind.REQUIRES, direction="out")
        chains = sg.graph.neighbors(web, EdgeKind.CHAINS_TO, direction="out")
        assert [nbr.props["key"] for _e, nbr in req] == ["/skills/recon/SKILL.md"]
        assert [nbr.props["key"] for _e, nbr in chains] == ["/skills/post/SKILL.md"]

    def test_technique_and_tactic_layers_seeded(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        assert len(sg.graph.by_kind(NodeKind.TECHNIQUE)) == 1
        assert len(sg.graph.by_kind(NodeKind.TACTIC)) == 1

    def test_by_path_maps_canonical_path_to_node_id(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        assert sg.by_path["/skills/web/SKILL.md"] == skill_node_id("/skills/web/SKILL.md")

    def test_clean_records_validate_ok(self) -> None:
        sg = build_skill_graph(_RECS, _CATALOG)
        assert sg.diagnostics.ok


class TestGetSkillGraph:
    def test_is_cached_across_calls(self) -> None:
        get_skill_graph.cache_clear()
        assert get_skill_graph() is get_skill_graph()

    def test_builds_from_bundled_data_without_neo4j(self) -> None:
        get_skill_graph.cache_clear()
        sg = get_skill_graph()
        assert len(sg.graph.by_kind(NodeKind.SKILL)) > 0
        # Technique layer comes from the bundled offline ATT&CK dataset.
        assert len(sg.graph.by_kind(NodeKind.TECHNIQUE)) > 100
