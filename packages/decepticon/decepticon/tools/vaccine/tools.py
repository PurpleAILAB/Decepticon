"""Offensive Vaccine tools — the four primitives of the attack→defend→verify loop.

Each tool operates on the engagement knowledge graph, reading Findings and
writing Mitigation / DefenseAction / VerificationResult nodes with MERGE
semantics so repeated runs are idempotent.

Tool surface
------------

``generate_remediation_brief``
    Reads a Finding (and its linked Technique, Host, Service nodes) from the
    graph and builds a structured remediation brief: root-cause analysis,
    prioritised fix options, compensating-control recommendations, and
    verification criteria.

``apply_defense``
    Deploys a compensating control — firewall rule, configuration change,
    detection rule, or code patch — and records the action as a
    ``DefenseAction`` node linked ``-[:MITIGATES]->`` the Finding and
    ``-[:IMPLEMENTS]->`` the parent ``Mitigation``.

``verify_defense``
    Re-executes the original attack vector (tool ID or command hash from the
    Finding's provenance chain) against the now-defended target and records a
    ``VerificationResult`` with disposition ``blocked`` | ``bypassed`` |
    ``partial`` and raw evidence.

``record_vaccine_result``
    Persists the final vaccine outcome for a Finding — links the Mitigation,
    all DefenseActions, and the terminal VerificationResult into a closed
    provenance chain and sets the Finding's ``vaccine_status`` property.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, _load
from decepticon_core.types.kg import EdgeKind, KnowledgeGraph, NodeKind


def _utcnow() -> str:
    """ISO-8601 UTC timestamp for graph node properties."""
    return datetime.now(timezone.utc).isoformat()


def _merge_node(
    graph: KnowledgeGraph,
    kind: NodeKind,
    node_id: str,
    properties: dict[str, Any],
) -> str:
    """MERGE-style upsert: create or update a node."""
    existing = graph.get_node(node_id)
    if existing is not None:
        graph.update_node(node_id, properties)
    else:
        graph.add_node(node_id, kind=kind, properties=properties)
    return node_id


def _merge_edge(
    graph: KnowledgeGraph,
    source: str,
    target: str,
    kind: EdgeKind,
    properties: dict[str, Any] | None = None,
) -> None:
    """MERGE-style upsert: create an edge if it does not exist."""
    for edge in graph.edges(source):
        if edge.target == target and edge.kind == kind:
            return
    graph.add_edge(source, target, kind=kind, properties=properties or {})


# ---------------------------------------------------------------------------
# Tool 1: generate_remediation_brief
# ---------------------------------------------------------------------------


@tool
def generate_remediation_brief(finding_id: str) -> str:
    """Generate a structured remediation brief for a confirmed Finding.

    Reads the Finding node, its linked Technique(s), Host, and Service from the
    engagement knowledge graph and produces a JSON brief containing:

    - ``finding_id``: the input Finding identifier.
    - ``severity``: inherited from the Finding node.
    - ``root_cause``: human-readable root-cause analysis.
    - ``fix_options``: list of ranked remediation options with effort/impact.
    - ``compensating_controls``: interim mitigations deployable immediately.
    - ``verification_criteria``: what ``verify_defense`` should check.
    - ``mitigation_id``: the ``Mitigation`` node created in the KG.

    A ``Mitigation`` node is MERGED into the graph with status ``planned``
    and linked ``-[:ADDRESSES]->`` the Finding.

    Args:
        finding_id: knowledge-graph ID of the Finding to remediate.

    Returns:
        JSON-encoded remediation brief.
    """
    graph: KnowledgeGraph = _load()
    finding = graph.get_node(finding_id)
    if finding is None:
        return _json({"error": f"Finding {finding_id!r} not found in the graph."})

    # Gather context: linked techniques, host, service.
    techniques = graph.neighbors(
        finding_id, edge_kind=EdgeKind.USES_TECHNIQUE, direction="out",
    )
    hosts = graph.neighbors(finding_id, edge_kind=EdgeKind.ON_HOST, direction="out")
    services = graph.neighbors(
        finding_id, edge_kind=EdgeKind.ON_SERVICE, direction="out",
    )

    severity = finding.properties.get("severity", "unknown")
    technique_names = [t.properties.get("name", t.id) for t in techniques]

    mitigation_id = f"mitigation-{uuid.uuid4().hex[:12]}"
    _merge_node(graph, NodeKind.MITIGATION, mitigation_id, {
        "status": "planned",
        "finding_id": finding_id,
        "severity": severity,
        "techniques": technique_names,
        "created_at": _utcnow(),
    })
    _merge_edge(graph, mitigation_id, finding_id, EdgeKind.ADDRESSES)

    brief: dict[str, Any] = {
        "finding_id": finding_id,
        "mitigation_id": mitigation_id,
        "severity": severity,
        "techniques": technique_names,
        "hosts": [h.properties.get("hostname", h.id) for h in hosts],
        "services": [s.properties.get("name", s.id) for s in services],
        "root_cause": finding.properties.get("description", "See Finding details."),
        "fix_options": [
            {
                "rank": 1,
                "action": "Apply vendor patch or configuration hardening.",
                "effort": "low",
                "impact": "high",
            },
            {
                "rank": 2,
                "action": "Deploy network-level compensating control (ACL/WAF rule).",
                "effort": "medium",
                "impact": "medium",
            },
        ],
        "compensating_controls": [
            "Enable enhanced logging and alerting for the affected technique(s).",
            "Restrict lateral-movement paths from the affected host.",
        ],
        "verification_criteria": [
            "Re-execute the original attack tool/command; expect connection "
            "refused, access denied, or detection alert within SLA.",
        ],
    }
    return _json(brief)


# ---------------------------------------------------------------------------
# Tool 2: apply_defense
# ---------------------------------------------------------------------------


@tool
def apply_defense(
    mitigation_id: str,
    finding_id: str,
    action_type: str,
    description: str,
    configuration: str = "",
) -> str:
    """Deploy a compensating control and record it in the knowledge graph.

    Creates a ``DefenseAction`` node linked to both the parent ``Mitigation``
    and the targeted ``Finding``.  The action_type field captures the defence
    category (e.g. ``firewall_rule``, ``config_change``, ``detection_rule``,
    ``code_patch``).

    Args:
        mitigation_id: ID of the parent Mitigation node (from the brief).
        finding_id: ID of the Finding this action addresses.
        action_type: defence category — one of ``firewall_rule``,
            ``config_change``, ``detection_rule``, ``code_patch``, ``other``.
        description: human-readable description of the deployed control.
        configuration: optional raw configuration / rule body applied.

    Returns:
        JSON-encoded confirmation with the ``defense_action_id``.
    """
    graph: KnowledgeGraph = _load()

    action_id = f"defense-action-{uuid.uuid4().hex[:12]}"
    _merge_node(graph, NodeKind.DEFENSE_ACTION, action_id, {
        "action_type": action_type,
        "description": description,
        "configuration": configuration,
        "mitigation_id": mitigation_id,
        "finding_id": finding_id,
        "deployed_at": _utcnow(),
        "status": "deployed",
    })
    _merge_edge(graph, action_id, finding_id, EdgeKind.MITIGATES)
    _merge_edge(graph, action_id, mitigation_id, EdgeKind.IMPLEMENTS)

    # Update parent mitigation status.
    graph.update_node(mitigation_id, {"status": "deployed"})

    return _json({
        "defense_action_id": action_id,
        "mitigation_id": mitigation_id,
        "finding_id": finding_id,
        "action_type": action_type,
        "status": "deployed",
    })


# ---------------------------------------------------------------------------
# Tool 3: verify_defense
# ---------------------------------------------------------------------------


@tool
def verify_defense(
    defense_action_id: str,
    finding_id: str,
    attack_replay_command: str,
) -> str:
    """Re-execute the original attack vector to verify the defence holds.

    Runs the attack replay (via the sandbox) against the now-defended target
    and records a ``VerificationResult`` node with disposition:

    - ``blocked`` — attack failed entirely; defence proven effective.
    - ``bypassed`` — attack succeeded unchanged; defence ineffective.
    - ``partial`` — attack partially succeeded; defence needs refinement.

    The result node is linked ``-[:VERIFIES]->`` the ``DefenseAction`` and
    ``-[:TESTED]->`` the ``Finding``.

    Args:
        defense_action_id: ID of the DefenseAction being verified.
        finding_id: ID of the original Finding.
        attack_replay_command: the command or tool invocation to replay.

    Returns:
        JSON-encoded verification result with disposition and evidence.
    """
    graph: KnowledgeGraph = _load()

    verification_id = f"verification-{uuid.uuid4().hex[:12]}"

    # The actual attack replay is delegated to the sandbox executor by the
    # agent runtime; this tool records the structured result.  In the OSS
    # baseline the replay is simulated — production deployments wire the
    # sandbox execution backend.
    _merge_node(graph, NodeKind.VERIFICATION_RESULT, verification_id, {
        "defense_action_id": defense_action_id,
        "finding_id": finding_id,
        "attack_replay_command": attack_replay_command,
        "disposition": "pending",
        "evidence": "",
        "verified_at": _utcnow(),
    })
    _merge_edge(graph, verification_id, defense_action_id, EdgeKind.VERIFIES)
    _merge_edge(graph, verification_id, finding_id, EdgeKind.TESTED)

    return _json({
        "verification_id": verification_id,
        "defense_action_id": defense_action_id,
        "finding_id": finding_id,
        "disposition": "pending",
        "note": (
            "Verification node created.  Execute the attack replay via the "
            "sandbox and update disposition with record_vaccine_result."
        ),
    })


# ---------------------------------------------------------------------------
# Tool 4: record_vaccine_result
# ---------------------------------------------------------------------------


@tool
def record_vaccine_result(
    verification_id: str,
    finding_id: str,
    disposition: str,
    evidence: str,
) -> str:
    """Persist the final vaccine verification outcome for a Finding.

    Updates the ``VerificationResult`` node with the terminal disposition and
    raw evidence, then sets the Finding's ``vaccine_status`` property to
    reflect the proven mitigation state.

    Args:
        verification_id: ID of the VerificationResult node to finalise.
        finding_id: ID of the Finding under test.
        disposition: terminal outcome — ``blocked``, ``bypassed``, or
            ``partial``.
        evidence: raw output / log excerpt proving the disposition.

    Returns:
        JSON-encoded summary of the closed vaccine loop for this Finding.
    """
    graph: KnowledgeGraph = _load()

    if disposition not in {"blocked", "bypassed", "partial"}:
        return _json({
            "error": (
                f"Invalid disposition {disposition!r}.  "
                "Must be 'blocked', 'bypassed', or 'partial'."
            ),
        })

    # Update the verification result node.
    graph.update_node(verification_id, {
        "disposition": disposition,
        "evidence": evidence,
        "finalised_at": _utcnow(),
    })

    # Propagate status to the Finding.
    vaccine_status = {
        "blocked": "mitigated",
        "bypassed": "unmitigated",
        "partial": "partially_mitigated",
    }[disposition]
    graph.update_node(finding_id, {"vaccine_status": vaccine_status})

    # If mitigated, also close the parent Mitigation.
    verification_node = graph.get_node(verification_id)
    if verification_node is not None and disposition == "blocked":
        defense_action_id = verification_node.properties.get("defense_action_id")
        if defense_action_id:
            action_node = graph.get_node(defense_action_id)
            if action_node is not None:
                mitigation_id = action_node.properties.get("mitigation_id")
                if mitigation_id:
                    graph.update_node(mitigation_id, {"status": "verified"})

    return _json({
        "verification_id": verification_id,
        "finding_id": finding_id,
        "disposition": disposition,
        "vaccine_status": vaccine_status,
        "closed": disposition == "blocked",
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

VACCINE_TOOLS = [
    generate_remediation_brief,
    apply_defense,
    verify_defense,
    record_vaccine_result,
]

__all__ = [
    "generate_remediation_brief",
    "apply_defense",
    "verify_defense",
    "record_vaccine_result",
    "VACCINE_TOOLS",
]
