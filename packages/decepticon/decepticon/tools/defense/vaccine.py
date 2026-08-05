"""Offensive Vaccine — attack-defend-verify feedback loop.

Implements the Offensive Vaccine cycle documented in
``docs/offensive-vaccine.md``:

1. ATTACK: Agent discovers vulnerability (existing flow)
2. BRIEF: Generate remediation brief from finding
3. DEFEND: Record defense action (mitigation applied)
4. VERIFY: Re-attack verification, record result
5. RECORD: Update finding status in KG

Storage: ``{workspace}/vaccine/`` directory with per-finding JSON
records tracking the full loop lifecycle. KG nodes link findings to
defense actions and verification results.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, graph_transaction
from decepticon_core.types.kg import Edge, EdgeKind, Node, NodeKind
from decepticon_core.utils.logging import get_logger

log = get_logger("defense.vaccine")


def _vaccine_dir(workspace: str = "/workspace") -> Path:
    d = Path(workspace) / "vaccine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vaccine_path(finding_id: str, workspace: str = "/workspace") -> Path:
    return _vaccine_dir(workspace) / f"{finding_id}.json"


def _load_vaccine_record(finding_id: str, workspace: str = "/workspace") -> dict[str, Any]:
    path = _vaccine_path(finding_id, workspace)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "finding_id": finding_id,
        "status": "discovered",
        "brief": None,
        "defense_actions": [],
        "verifications": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _save_vaccine_record(record: dict[str, Any], workspace: str = "/workspace") -> None:
    path = _vaccine_path(record["finding_id"], workspace)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


@tool
def vaccine_generate_brief(
    finding_id: str,
    title: str,
    severity: str,
    attack_vector: str,
    evidence: str,
    workspace: str = "/workspace",
) -> str:
    """Generate a remediation brief from a confirmed finding.

    Creates a structured remediation brief documenting what was exploited,
    recommended mitigations (immediate/short-term/long-term), and the
    specific re-attack vector for verification.

    This is step 2 of the Offensive Vaccine loop. Call after a finding
    is confirmed (FIND-NNN.md written).

    Args:
        finding_id: The finding ID (e.g. "FIND-001").
        title: One-line finding summary.
        severity: critical/high/medium/low.
        attack_vector: The specific exploit vector used (e.g.
            "BOLA via GET /api/users/{id} with horizontal ID enumeration").
        evidence: Evidence summary (request/response, PoC command).
        workspace: Engagement workspace path.

    Returns:
        JSON with the generated brief and vaccine record status.
    """
    record = _load_vaccine_record(finding_id, workspace)

    brief = {
        "finding_id": finding_id,
        "title": title,
        "severity": severity,
        "attack_vector": attack_vector,
        "evidence_summary": evidence,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "recommended_mitigations": {
            "immediate": f"Block/disable the vulnerable endpoint or add input validation for: {attack_vector}",
            "short_term": "Apply authorization checks, rate limiting, and logging for the affected resource",
            "long_term": "Implement defense-in-depth: WAF rules, RBAC enforcement, continuous monitoring",
        },
        "verification_vector": attack_vector,
    }

    record["brief"] = brief
    record["status"] = "briefed"

    brief_path = _vaccine_dir(workspace) / f"{finding_id}-brief.md"
    brief_md = (
        f"# Remediation Brief: {title}\n\n"
        f"**Finding:** {finding_id}\n"
        f"**Severity:** {severity}\n"
        f"**Attack Vector:** {attack_vector}\n\n"
        f"## Evidence\n{evidence}\n\n"
        f"## Recommended Mitigations\n\n"
        f"### Immediate\n{brief['recommended_mitigations']['immediate']}\n\n"
        f"### Short-term\n{brief['recommended_mitigations']['short_term']}\n\n"
        f"### Long-term\n{brief['recommended_mitigations']['long_term']}\n\n"
        f"## Verification\nRe-run the attack vector after mitigations are applied:\n"
        f"```\n{attack_vector}\n```\n"
    )
    brief_path.write_text(brief_md, encoding="utf-8")

    _save_vaccine_record(record, workspace)
    return _json(
        {
            "finding_id": finding_id,
            "status": "briefed",
            "brief_path": str(brief_path),
            "verification_vector": attack_vector,
        }
    )


@tool
def vaccine_record_defense(
    finding_id: str,
    action_type: str,
    description: str,
    applied_by: str = "operator",
    workspace: str = "/workspace",
) -> str:
    """Record a defense action applied to address a finding.

    This is step 3 of the Offensive Vaccine loop. Call after a
    mitigation has been applied (firewall rule, patch, config change).

    Args:
        finding_id: The finding ID (e.g. "FIND-001").
        action_type: Type of defense action: firewall_rule, patch,
            config_change, waf_rule, access_control, rate_limit.
        description: What was done (e.g. "Added RBAC check to
            /api/users/{id} endpoint requiring session user_id match").
        applied_by: Who applied it (operator/automated).
        workspace: Engagement workspace path.
    """
    record = _load_vaccine_record(finding_id, workspace)

    action = {
        "type": action_type,
        "description": description,
        "applied_by": applied_by,
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    record["defense_actions"].append(action)
    record["status"] = "defended"

    with graph_transaction() as graph:
        defense_key = f"defense::{finding_id}::{len(record['defense_actions'])}"
        defense_node = graph.upsert_node(
            Node.make(
                NodeKind.DEFENSE_ACTION,
                f"[{action_type}] {description[:80]}",
                key=defense_key,
                action_type=action_type,
                applied_by=applied_by,
            )
        )

        finding_nodes = [
            n
            for n in graph.by_kind(NodeKind.FINDING)
            if finding_id.lower() in (n.label or "").lower()
            or finding_id.lower() in str(n.props.get("key") or "").lower()
        ]
        for fn in finding_nodes:
            graph.upsert_edge(Edge.make(defense_node.id, fn.id, EdgeKind.MITIGATES, weight=0.8))

    _save_vaccine_record(record, workspace)
    return _json(
        {
            "finding_id": finding_id,
            "status": "defended",
            "defense_action_count": len(record["defense_actions"]),
            "action": action,
        }
    )


@tool
def vaccine_verify(
    finding_id: str,
    reattack_result: str,
    blocked: bool,
    evidence: str = "",
    workspace: str = "/workspace",
) -> str:
    """Record the result of a verification re-attack.

    This is step 4 of the Offensive Vaccine loop. After a defense
    action is applied, the same exploit vector is re-run. Call this
    with the result.

    Args:
        finding_id: The finding ID (e.g. "FIND-001").
        reattack_result: Brief description of what happened on re-attack.
        blocked: True if the defense held (exploit failed), False if
            the exploit still succeeded (defense failed).
        evidence: Evidence from the re-attack (response code, error msg).
        workspace: Engagement workspace path.
    """
    record = _load_vaccine_record(finding_id, workspace)

    verification = {
        "result": "blocked" if blocked else "bypassed",
        "description": reattack_result,
        "evidence": evidence,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    record["verifications"].append(verification)

    if blocked:
        record["status"] = "mitigated"
    else:
        record["status"] = "defense_failed"

    with graph_transaction() as graph:
        verify_key = f"verification::{finding_id}::{len(record['verifications'])}"
        verify_node = graph.upsert_node(
            Node.make(
                NodeKind.VERIFICATION,
                f"[{'BLOCKED' if blocked else 'BYPASSED'}] {reattack_result[:80]}",
                key=verify_key,
                result="blocked" if blocked else "bypassed",
            )
        )

        finding_nodes = [
            n
            for n in graph.by_kind(NodeKind.FINDING)
            if finding_id.lower() in (n.label or "").lower()
            or finding_id.lower() in str(n.props.get("key") or "").lower()
        ]
        for fn in finding_nodes:
            graph.upsert_edge(Edge.make(verify_node.id, fn.id, EdgeKind.VERIFIES, weight=0.9))

    _save_vaccine_record(record, workspace)
    return _json(
        {
            "finding_id": finding_id,
            "status": record["status"],
            "blocked": blocked,
            "verification": verification,
            "total_verifications": len(record["verifications"]),
        }
    )


@tool
def vaccine_status(workspace: str = "/workspace") -> str:
    """Get the status of all vaccine loop records in the engagement.

    Returns a summary of all findings that have entered the vaccine
    loop, their current status, and whether verification passed.
    """
    vaccine_dir = _vaccine_dir(workspace)
    records: list[dict[str, Any]] = []

    for path in sorted(vaccine_dir.glob("FIND-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            records.append(
                {
                    "finding_id": record.get("finding_id", path.stem),
                    "status": record.get("status", "unknown"),
                    "defense_actions": len(record.get("defense_actions", [])),
                    "verifications": len(record.get("verifications", [])),
                    "last_verification": (
                        record.get("verifications", [{}])[-1].get("result", "none")
                        if record.get("verifications")
                        else "none"
                    ),
                }
            )
        except json.JSONDecodeError:
            continue

    return _json(
        {
            "total_findings_in_loop": len(records),
            "statuses": {
                "discovered": sum(1 for r in records if r["status"] == "discovered"),
                "briefed": sum(1 for r in records if r["status"] == "briefed"),
                "defended": sum(1 for r in records if r["status"] == "defended"),
                "mitigated": sum(1 for r in records if r["status"] == "mitigated"),
                "defense_failed": sum(1 for r in records if r["status"] == "defense_failed"),
            },
            "records": records,
        }
    )


VACCINE_TOOLS = [
    vaccine_generate_brief,
    vaccine_record_defense,
    vaccine_verify,
    vaccine_status,
]
