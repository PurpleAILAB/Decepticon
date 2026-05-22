"""Active Directory delegation attack path analysis.

Analyzes BloodHound data in the knowledge graph for:
- Unconstrained delegation (TrustedForDelegation flag)
- Constrained delegation (AllowedToDelegate edges + msDS-AllowedToDelegateTo)
- Resource-Based Constrained Delegation (AllowedToAct edges /
  msDS-AllowedToActOnBehalfOfOtherIdentity)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decepticon.tools.research.graph import KnowledgeGraph


@dataclass
class DelegationFinding:
    target: str
    delegation_type: str
    severity: str
    detail: str
    attack_path: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "delegation_type": self.delegation_type,
            "severity": self.severity,
            "detail": self.detail,
            "attack_path": self.attack_path,
        }


_SENSITIVE_SPNS = {"ldap", "cifs", "http", "host", "mssql", "krbtgt"}


def _is_dc(node_props: dict[str, Any]) -> bool:
    """Heuristic: a node is a domain controller if its label contains 'DC' or admincount is set."""
    label = str(node_props.get("label", "")).upper()
    bh_type = node_props.get("bh_type", "")
    # DCs are typically in the Domain Controllers OU or have specific markers
    return bh_type == "Computer" and (
        node_props.get("is_dc", False) or "DOMAIN CONTROLLER" in label
    )


def _spn_targets_dc(detail: str) -> bool:
    """Check if a constrained delegation SPN targets a DC-class service."""
    lower = detail.lower()
    return any(f"{spn}/" in lower for spn in _SENSITIVE_SPNS)


def analyze_delegation(graph: KnowledgeGraph) -> list[DelegationFinding]:
    """Identify delegation-based attack paths from the knowledge graph.

    Walks edges with ``bh_right`` in {AllowedToDelegate, AllowedToAct} and
    checks node properties for unconstrained delegation flags.
    """
    findings: list[DelegationFinding] = []
    seen_unconstrained: set[str] = set()

    # Pass 1: unconstrained delegation via node properties
    for node in graph.nodes.values():
        bh_type = node.props.get("bh_type", "")
        if bh_type != "Computer":
            continue
        trusted = node.props.get("trustedfordelegation", False)
        unconstr = node.props.get("unconstraineddelegation", False)
        if not (trusted or unconstr):
            continue
        if _is_dc({"label": node.label, "bh_type": bh_type, **node.props}):
            # DCs with unconstrained delegation are expected — skip
            continue
        seen_unconstrained.add(node.id)
        findings.append(
            DelegationFinding(
                target=node.label,
                delegation_type="unconstrained",
                severity="high",
                detail=(
                    f"Computer '{node.label}' has unconstrained delegation enabled. "
                    "Any user authenticating to this host has their TGT cached, "
                    "enabling credential theft via print spooler or other coercion."
                ),
                attack_path=[node.label],
            )
        )

    # Pass 2: constrained and RBCD via edges
    for edge in graph.edges.values():
        right = edge.props.get("bh_right", "")
        if right not in ("AllowedToDelegate", "AllowedToAct"):
            continue
        src_node = graph.nodes.get(edge.src)
        dst_node = graph.nodes.get(edge.dst)
        if src_node is None or dst_node is None:
            continue

        if right == "AllowedToDelegate":
            # Constrained delegation — check if target is a sensitive service
            spn = edge.props.get("spn", dst_node.label)
            severity = "high" if _spn_targets_dc(str(spn)) else "medium"
            findings.append(
                DelegationFinding(
                    target=dst_node.label,
                    delegation_type="constrained",
                    severity=severity,
                    detail=(
                        f"'{src_node.label}' has constrained delegation to "
                        f"'{dst_node.label}'. S4U2Proxy can be used to impersonate "
                        f"any user to the target service."
                    ),
                    attack_path=[src_node.label, dst_node.label],
                )
            )
        elif right == "AllowedToAct":
            # RBCD — attacker can write msDS-AllowedToActOnBehalfOfOtherIdentity
            findings.append(
                DelegationFinding(
                    target=dst_node.label,
                    delegation_type="rbcd",
                    severity="medium",
                    detail=(
                        f"'{src_node.label}' can configure resource-based constrained "
                        f"delegation on '{dst_node.label}'. With a machine account, "
                        f"S4U2Self + S4U2Proxy yields impersonation on the target."
                    ),
                    attack_path=[src_node.label, dst_node.label],
                )
            )

    return findings
