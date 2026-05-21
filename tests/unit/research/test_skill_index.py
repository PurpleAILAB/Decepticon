"""Unit tests for skill discovery and skill→technique graph seeding."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.attack.skill_index import (
    SkillRecord,
    discover_skills,
    load_skill_index,
    parse_skill_md,
    seed_skills,
    skill_graph_elements,
    skill_node_id,
)
from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph, NodeKind

_SKILL_MD = """\
---
name: passive-recon
description: "Passive intelligence gathering without touching the target."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "passive recon, WHOIS, DNS lookup"
  tags: passive, dns, subdomain-enum
  mitre_attack: T1590, T1591, t1592
---

# Passive Reconnaissance Knowledge Base

Body text here.
"""

_SKILL_MD_LIST_MITRE = """\
---
name: ad-exploit
description: "Active Directory exploitation."
metadata:
  subdomain: credential-access
  mitre_attack:
    - T1558.003
    - T1003.006
---
Body.
"""

_SKILL_MD_NO_NAME = """\
---
description: "no name field"
---
Body.
"""


class _GraphStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def batch_upsert_nodes(self, nodes: list) -> int:
        return self.graph.bulk_upsert_nodes(nodes)

    def batch_upsert_edges(self, edges: list) -> int:
        return self.graph.bulk_upsert_edges(edges)


class TestParseSkillMd:
    def test_parses_nested_metadata_and_comma_mitre(self) -> None:
        rec = parse_skill_md(_SKILL_MD, "/skills/standard/recon/passive-recon/SKILL.md")
        assert rec is not None
        assert rec.name == "passive-recon"
        assert rec.subdomain == "reconnaissance"
        # comma-separated, case-normalized
        assert rec.mitre == ["T1590", "T1591", "T1592"]

    def test_parses_yaml_list_mitre(self) -> None:
        rec = parse_skill_md(_SKILL_MD_LIST_MITRE, "/skills/standard/ad/SKILL.md")
        assert rec is not None
        assert rec.mitre == ["T1558.003", "T1003.006"]

    def test_returns_none_without_name(self) -> None:
        assert parse_skill_md(_SKILL_MD_NO_NAME, "/skills/x/SKILL.md") is None


class TestDiscoverSkills:
    def test_walks_tree_and_builds_canonical_paths(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "standard" / "recon" / "passive-recon"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")

        records = discover_skills(tmp_path / "skills")
        assert len(records) == 1
        assert records[0].path == "/skills/standard/recon/passive-recon/SKILL.md"
        assert records[0].name == "passive-recon"

    def test_empty_dir_yields_no_records(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        assert discover_skills(tmp_path / "skills") == []


class TestSkillGraphElements:
    def test_builds_skill_node_and_teaches_edges(self) -> None:
        rec = SkillRecord(
            name="passive-recon",
            path="/skills/standard/recon/passive-recon/SKILL.md",
            mitre=["T1590", "T1591"],
        )
        nodes, edges = skill_graph_elements([rec])
        assert len(nodes) == 1
        assert nodes[0].kind == NodeKind.SKILL
        teaches = [e for e in edges if e.kind == EdgeKind.TEACHES]
        assert len(teaches) == 2
        assert {e.dst for e in teaches} == {
            technique_node_id("T1590"),
            technique_node_id("T1591"),
        }
        assert all(e.src == skill_node_id(rec.path) for e in teaches)

    def test_skill_node_carries_path_as_key(self) -> None:
        rec = SkillRecord(name="x", path="/skills/x/SKILL.md", mitre=[])
        nodes, _edges = skill_graph_elements([rec])
        assert nodes[0].props["key"] == "/skills/x/SKILL.md"


class TestBundledSkillIndex:
    """Smoke tests for the build-time artifact ``data/skill_techniques.json``."""

    def test_bundled_skill_index_loads(self) -> None:
        records = load_skill_index()
        assert len(records) > 30
        assert all(r.path.startswith("/skills/") for r in records)

    def test_some_bundled_skills_carry_mitre_ids(self) -> None:
        records = load_skill_index()
        assert any(r.mitre for r in records), "expected mitre-tagged skills in the index"


class TestSeedSkills:
    def test_seeds_and_is_idempotent(self) -> None:
        recs = [
            SkillRecord(name="a", path="/skills/a/SKILL.md", mitre=["T1190"]),
            SkillRecord(name="b", path="/skills/b/SKILL.md", mitre=["T1059"]),
        ]
        store = _GraphStore()
        counts = seed_skills(store, records=recs)
        assert counts["skills"] == 2
        first = store.graph.stats()
        seed_skills(store, records=recs)
        assert store.graph.stats() == first
