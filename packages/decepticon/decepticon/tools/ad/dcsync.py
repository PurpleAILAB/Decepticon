"""DCSync capability indicator from a BloodHound graph.

Once a BloodHound export has been ingested, the agent can ask this
module which principals already have the three rights required for
DCSync: ``GetChanges``, ``GetChangesAll``, and (optionally)
``GetChangesInFilteredSet``. Any principal with both of the first two
can replicate directory data including krbtgt hash → golden ticket.
"""

from __future__ import annotations

from decepticon_core.types.kg import EdgeKind, KnowledgeGraph


def dcsync_candidates(graph: KnowledgeGraph) -> list[tuple[str, str, str]]:
    """Return ``(principal_id, principal_label, target_domain)`` tuples with DCSync rights.

    Walks every ``leaks`` edge with ``bh_right ∈ {GetChanges, GetChangesAll,
    GetChangesInFilteredSet, DCSync}`` and groups by (source, target domain).
    A principal is a candidate when it holds at least ``GetChanges`` and
    ``GetChangesAll`` (or ``DCSync`` directly) on the same domain object.
    ``GetChangesInFilteredSet`` is tracked as a soft indicator but is not
    sufficient on its own.
    """
    _DCSYNC_RIGHTS = frozenset(
        {
            "GetChanges",
            "GetChangesAll",
            "GetChangesInFilteredSet",
            "DCSync",
        }
    )
    # (src, dst_domain) → set of rights
    rights_by_src_dst: dict[tuple[str, str], set[str]] = {}
    for edge in graph.edges.values():
        if edge.kind != EdgeKind.LEAKS:
            continue
        right = edge.props.get("bh_right", "")
        if right in _DCSYNC_RIGHTS:
            # Resolve the target domain from the edge destination
            dst_node = graph.nodes.get(edge.dst)
            target_domain = ""
            if dst_node is not None:
                target_domain = dst_node.props.get("domain") or dst_node.label
            key = (edge.src, target_domain)
            rights_by_src_dst.setdefault(key, set()).add(right)

    out: list[tuple[str, str, str]] = []
    for (src, target_domain), rights in rights_by_src_dst.items():
        if "DCSync" in rights or ("GetChanges" in rights and "GetChangesAll" in rights):
            node = graph.nodes.get(src)
            if node is not None:
                out.append((src, node.label, target_domain))
    return out
