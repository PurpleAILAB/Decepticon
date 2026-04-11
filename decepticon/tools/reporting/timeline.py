"""Graph-to-timeline extractor.

Walks the KnowledgeGraph ``created_at`` / ``updated_at`` fields and
produces a chronological list of events the agent can render in the
final report or an interactive dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decepticon.tools.research.graph import KnowledgeGraph


@dataclass
class TimelineEvent:
    ts: float
    kind: str  # "node" | "edge"
    type_name: str
    label: str
    severity: str | None
    validated: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "kind": self.kind,
            "type_name": self.type_name,
            "label": self.label,
            "severity": self.severity,
            "validated": self.validated,
        }


def extract_timeline(graph: KnowledgeGraph) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for node in graph.nodes.values():
        events.append(
            TimelineEvent(
                ts=node.created_at,
                kind="node",
                type_name=node.kind.value,
                label=node.label,
                severity=node.props.get("severity"),
                validated=bool(node.props.get("validated")) if "validated" in node.props else None,
            )
        )
        if node.updated_at and node.updated_at - node.created_at > 0.5:
            events.append(
                TimelineEvent(
                    ts=node.updated_at,
                    kind="node",
                    type_name=f"{node.kind.value}:update",
                    label=node.label,
                    severity=node.props.get("severity"),
                    validated=bool(node.props.get("validated"))
                    if "validated" in node.props
                    else None,
                )
            )
    for edge in graph.edges.values():
        events.append(
            TimelineEvent(
                ts=edge.created_at,
                kind="edge",
                type_name=edge.kind.value,
                label=f"{edge.src[:8]}→{edge.dst[:8]}",
                severity=None,
                validated=None,
            )
        )
    events.sort(key=lambda e: e.ts)
    return events
