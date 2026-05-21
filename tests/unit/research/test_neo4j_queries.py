"""Unit tests for Neo4j upsert Cypher construction.

Targets the first-class-property fix: the ``technique_id`` / ``skill_id``
uniqueness constraints only enforce if the upsert actually writes those
top-level properties.
"""

from __future__ import annotations

from decepticon.tools.research.graph import NodeKind
from decepticon.tools.research.neo4j_store import (
    _first_class_set,
    _node_batch_cypher,
    _node_upsert_cypher,
)


class TestFirstClassSet:
    def test_technique_writes_technique_id(self) -> None:
        assert "n.technique_id = $key" in _first_class_set(NodeKind.TECHNIQUE, "$key")

    def test_skill_writes_skill_id_with_row_ref(self) -> None:
        assert "n.skill_id = row.key" in _first_class_set(NodeKind.SKILL, "row.key")

    def test_plain_node_kinds_get_no_extra_clause(self) -> None:
        assert _first_class_set(NodeKind.HOST, "$key") == ""
        assert _first_class_set(NodeKind.FINDING, "$key") == ""


class TestNodeUpsertCypher:
    def test_technique_single_upsert_sets_technique_id(self) -> None:
        cypher = _node_upsert_cypher("Technique", NodeKind.TECHNIQUE)
        assert "MERGE (n:Technique {id: $id})" in cypher
        assert "n.technique_id = $key" in cypher

    def test_skill_single_upsert_sets_skill_id(self) -> None:
        cypher = _node_upsert_cypher("Skill", NodeKind.SKILL)
        assert "n.skill_id = $key" in cypher

    def test_host_single_upsert_has_no_first_class_prop(self) -> None:
        cypher = _node_upsert_cypher("Host", NodeKind.HOST)
        assert "technique_id" not in cypher
        assert "skill_id" not in cypher
        # base properties still present
        assert "n.props = $props" in cypher
        assert "n.key = $key" in cypher


class TestNodeBatchCypher:
    def test_technique_batch_uses_row_ref(self) -> None:
        cypher = _node_batch_cypher("Technique", NodeKind.TECHNIQUE)
        assert "UNWIND $batch AS row" in cypher
        assert "n.technique_id = row.key" in cypher

    def test_host_batch_has_no_first_class_prop(self) -> None:
        cypher = _node_batch_cypher("Host", NodeKind.HOST)
        assert "technique_id" not in cypher
        assert "n.props = row.props" in cypher
