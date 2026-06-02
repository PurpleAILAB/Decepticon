"""Cypher node + edge model used by the builder.

Each node and edge becomes one or more ``MERGE`` statements in the
deterministic ``skills.cypher`` dump. The builder works in two phases:

1. Each module (seeds, skills, mitre_stix) produces a list of ``Node``
   and ``Edge`` records via dataclass instances.
2. ``emit.py`` sorts the records and renders them as Cypher.

Keeping the model in plain dataclasses (no Neo4j driver imports) means
the builder can run in a pure-Python CI environment without a running
database. The runtime ``skillogy.server`` is the only component that
talks to Neo4j; the builder writes a text file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _canonical_props(props: dict[str, Any]) -> dict[str, Any]:
    """Return a sorted dict so the emitter produces deterministic output."""
    return dict(sorted(props.items()))


@dataclass(frozen=True, slots=True)
class Node:
    """A single graph node.

    ``label`` is the Neo4j node label (e.g. ``Skill``, ``Phase``,
    ``Technique``). ``key_field`` is the name of the property used as
    the natural key for MERGE (usually ``name`` or ``id``). The value
    of ``key_field`` MUST appear in ``properties`` — the emitter asserts
    this.
    """

    label: str
    key_field: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.key_field not in self.properties:
            raise ValueError(
                f"Node label={self.label!r} key_field={self.key_field!r} "
                f"missing from properties {sorted(self.properties)!r}"
            )

    @property
    def key(self) -> Any:
        return self.properties[self.key_field]

    def sort_key(self) -> tuple[str, str]:
        return (self.label, str(self.key))


@dataclass(frozen=True, slots=True)
class Edge:
    """A typed graph edge from one node to another.

    Both endpoints are identified by (label, key_field, key_value)
    because the builder doesn't carry node IDs — it emits `MERGE`
    statements that look the endpoints up by their natural key. The
    emitter inserts the right MATCH clauses for each endpoint.
    """

    edge_type: str
    from_label: str
    from_key_field: str
    from_key: Any
    to_label: str
    to_key_field: str
    to_key: Any
    properties: dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.from_label,
            str(self.from_key),
            self.edge_type,
            self.to_label,
            str(self.to_key),
        )


def canonicalize_node(node: Node) -> Node:
    """Return a copy of ``node`` with properties sorted."""
    return Node(
        label=node.label,
        key_field=node.key_field,
        properties=_canonical_props(node.properties),
    )


def canonicalize_edge(edge: Edge) -> Edge:
    """Return a copy of ``edge`` with properties sorted."""
    return Edge(
        edge_type=edge.edge_type,
        from_label=edge.from_label,
        from_key_field=edge.from_key_field,
        from_key=edge.from_key,
        to_label=edge.to_label,
        to_key_field=edge.to_key_field,
        to_key=edge.to_key,
        properties=_canonical_props(edge.properties),
    )
