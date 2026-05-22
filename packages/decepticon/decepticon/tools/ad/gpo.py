"""Active Directory GPO abuse path analysis.

Analyzes BloodHound data for GPO-based attack paths:
- GPOs with low-priv write access (GenericAll, GenericWrite, WriteDacl,
  WriteOwner)
- GPO links to sensitive OUs (Domain Controllers, domain root)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph


@dataclass
class GPOFinding:
    gpo_name: str
    linked_to: str
    acl_abuse: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpo_name": self.gpo_name,
            "linked_to": self.linked_to,
            "acl_abuse": self.acl_abuse,
            "severity": self.severity,
            "detail": self.detail,
        }


_ACL_ABUSE_RIGHTS = {"GenericAll", "GenericWrite", "WriteDacl", "WriteOwner"}

_DC_OU_MARKERS = {"domain controllers"}


def _is_sensitive_ou(label: str) -> bool:
    """Check if an OU label suggests Domain Controllers or domain root."""
    lower = label.lower()
    return any(marker in lower for marker in _DC_OU_MARKERS)


def analyze_gpo_abuse(graph: KnowledgeGraph) -> list[GPOFinding]:
    """Identify GPO-based attack paths from the knowledge graph.

    Finds GPO nodes with ACL edges from low-privilege principals, then
    checks GPLink edges to determine which OUs they affect.
    """
    findings: list[GPOFinding] = []

    # Identify GPO nodes
    gpo_nodes: dict[str, str] = {}  # node_id -> label
    for node in graph.nodes.values():
        if node.props.get("bh_type") == "GPO":
            gpo_nodes[node.id] = node.label

    if not gpo_nodes:
        return findings

    # Build GPO -> linked OUs via GPLink/CONTAINS edges
    gpo_links: dict[str, list[str]] = {}  # gpo_id -> [ou_label, ...]
    for edge in graph.edges.values():
        right = edge.props.get("bh_right", "")
        if right == "GPLink" or edge.kind == EdgeKind.CONTAINS:
            if edge.src in gpo_nodes:
                dst_node = graph.nodes.get(edge.dst)
                if dst_node is not None:
                    gpo_links.setdefault(edge.src, []).append(dst_node.label)

    # Find ACL abuse edges targeting GPO nodes
    gpo_abusers: dict[str, list[tuple[str, str]]] = {}  # gpo_id -> [(attacker_label, right)]
    for edge in graph.edges.values():
        right = edge.props.get("bh_right", "")
        if right not in _ACL_ABUSE_RIGHTS:
            continue
        if edge.dst not in gpo_nodes:
            continue
        src_node = graph.nodes.get(edge.src)
        if src_node is None:
            continue
        gpo_abusers.setdefault(edge.dst, []).append((src_node.label, right))

    # Produce findings
    for gpo_id, abusers in gpo_abusers.items():
        gpo_label = gpo_nodes[gpo_id]
        linked_ous = gpo_links.get(gpo_id, [])
        linked_display = ", ".join(linked_ous) if linked_ous else "(no linked OUs found)"

        has_dc_link = any(_is_sensitive_ou(ou) for ou in linked_ous)
        severity = "critical" if has_dc_link else "high"

        for attacker_label, right in abusers:
            if has_dc_link:
                detail = (
                    f"'{attacker_label}' has {right} on GPO '{gpo_label}' which is "
                    f"linked to a Domain Controllers OU. Modifying this GPO enables "
                    f"immediate code execution on all domain controllers."
                )
            else:
                detail = (
                    f"'{attacker_label}' has {right} on GPO '{gpo_label}' "
                    f"(linked to: {linked_display}). GPO modification enables "
                    f"lateral movement and persistence in linked OUs."
                )

            findings.append(
                GPOFinding(
                    gpo_name=gpo_label,
                    linked_to=linked_display,
                    acl_abuse=right,
                    severity=severity,
                    detail=detail,
                )
            )

    return findings
