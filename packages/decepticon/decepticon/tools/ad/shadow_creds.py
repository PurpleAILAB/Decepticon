"""Shadow Credentials (msDS-KeyCredentialLink) attack path analysis.

Detects principals that can write msDS-KeyCredentialLink on target
accounts, enabling certificate-based authentication takeover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decepticon.tools.research.graph import KnowledgeGraph

_SHADOW_CRED_RIGHTS = {"AddKeyCredentialLink", "GenericAll", "GenericWrite"}

_TARGET_BH_TYPES = {"User", "Computer"}


@dataclass
class ShadowCredsFinding:
    attacker: str
    target: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attacker": self.attacker,
            "target": self.target,
            "severity": self.severity,
            "detail": self.detail,
        }


def analyze_shadow_credentials(graph: KnowledgeGraph) -> list[ShadowCredsFinding]:
    """Identify Shadow Credentials attack paths from the knowledge graph.

    Walks edges with ``bh_right`` in {AddKeyCredentialLink, GenericAll,
    GenericWrite} where the target is a user or computer account.
    """
    findings: list[ShadowCredsFinding] = []

    for edge in graph.edges.values():
        right = edge.props.get("bh_right", "")
        if right not in _SHADOW_CRED_RIGHTS:
            continue

        dst_node = graph.nodes.get(edge.dst)
        if dst_node is None:
            continue
        dst_type = dst_node.props.get("bh_type", "")
        if dst_type not in _TARGET_BH_TYPES:
            continue

        src_node = graph.nodes.get(edge.src)
        if src_node is None:
            continue

        # High-priv attackers (admincount=True) are less interesting —
        # flag low-priv as HIGH, high-priv as medium
        is_low_priv = not src_node.props.get("admincount", False)
        severity = "high" if is_low_priv else "medium"

        if right == "AddKeyCredentialLink":
            detail = (
                f"'{src_node.label}' can write msDS-KeyCredentialLink on "
                f"'{dst_node.label}'. This enables Shadow Credentials attack: "
                f"add a Key Credential, request a certificate via PKINIT, and "
                f"obtain the target's NTLM hash."
            )
        else:
            detail = (
                f"'{src_node.label}' has {right} on '{dst_node.label}' "
                f"({dst_type}), which includes write access to "
                f"msDS-KeyCredentialLink. Shadow Credentials attack possible "
                f"via Whisker/pyWhisker."
            )

        findings.append(
            ShadowCredsFinding(
                attacker=src_node.label,
                target=dst_node.label,
                severity=severity,
                detail=detail,
            )
        )

    return findings
