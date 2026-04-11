"""DCSync capability indicator from a BloodHound graph.

Once a BloodHound export has been ingested, the agent can ask this
module which principals already have the three rights required for
DCSync: ``GetChanges``, ``GetChangesAll``, and (optionally)
``GetChangesInFilteredSet``. Any principal with both of the first two
can replicate directory data including krbtgt hash → golden ticket.
"""

from __future__ import annotations

from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph


def dcsync_candidates(graph: KnowledgeGraph) -> list[tuple[str, str]]:
    """Return ``(principal_id, principal_label)`` pairs with DCSync rights.

    Walks every ``leaks`` edge with ``bh_right ∈ {GetChanges, GetChangesAll,
    DCSync}`` and groups by source. A principal is a candidate when it
    holds at least ``GetChanges`` and ``GetChangesAll`` (or ``DCSync``
    directly).
    """
    rights_by_src: dict[str, set[str]] = {}
    for edge in graph.edges.values():
        if edge.kind != EdgeKind.LEAKS:
            continue
        right = edge.props.get("bh_right", "")
        if right in ("GetChanges", "GetChangesAll", "DCSync"):
            rights_by_src.setdefault(edge.src, set()).add(right)

    out: list[tuple[str, str]] = []
    for src, rights in rights_by_src.items():
        if "DCSync" in rights or ("GetChanges" in rights and "GetChangesAll" in rights):
            node = graph.nodes.get(src)
            if node is not None:
                out.append((src, node.label))
    return out
