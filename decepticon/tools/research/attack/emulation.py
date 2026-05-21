"""Adversary emulation — turn a threat actor's TTPs into OPPLAN objectives.

Given a threat actor's MITRE ATT&CK technique IDs, build kill-chain-ordered
draft objectives. The orchestrator calls ``add_objective`` for each draft —
this module never mutates OPPLAN, mirroring ``suggest_objectives_from_chains``.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from decepticon.core.schemas import ObjectivePhase
from decepticon.tools.research.attack.catalog import (
    AttackCatalog,
    is_technique_id,
    load_attack_catalog,
    parse_ids,
)

# Tactic ID → ObjectivePhase. Mirrors the mapping documented in the
# ObjectivePhase docstring (decepticon/core/schemas.py).
_TACTIC_PHASE: dict[str, ObjectivePhase] = {
    "TA0043": ObjectivePhase.RECON,  # Reconnaissance
    "TA0042": ObjectivePhase.RECON,  # Resource Development
    "TA0001": ObjectivePhase.INITIAL_ACCESS,  # Initial Access
    "TA0002": ObjectivePhase.INITIAL_ACCESS,  # Execution
    "TA0003": ObjectivePhase.POST_EXPLOIT,  # Persistence
    "TA0004": ObjectivePhase.POST_EXPLOIT,  # Privilege Escalation
    "TA0005": ObjectivePhase.POST_EXPLOIT,  # Defense Evasion
    "TA0006": ObjectivePhase.POST_EXPLOIT,  # Credential Access
    "TA0007": ObjectivePhase.POST_EXPLOIT,  # Discovery
    "TA0008": ObjectivePhase.POST_EXPLOIT,  # Lateral Movement
    "TA0009": ObjectivePhase.POST_EXPLOIT,  # Collection
    "TA0011": ObjectivePhase.C2,  # Command and Control
    "TA0010": ObjectivePhase.EXFILTRATION,  # Exfiltration
    "TA0040": ObjectivePhase.EXFILTRATION,  # Impact
}

_PHASE_ORDER: dict[ObjectivePhase, int] = {
    ObjectivePhase.RECON: 0,
    ObjectivePhase.INITIAL_ACCESS: 1,
    ObjectivePhase.POST_EXPLOIT: 2,
    ObjectivePhase.C2: 3,
    ObjectivePhase.EXFILTRATION: 4,
}


def _phase_for_technique(catalog: AttackCatalog, technique_id: str) -> ObjectivePhase:
    """Resolve a technique to the earliest kill-chain phase of its tactics."""
    phases = [
        _TACTIC_PHASE[tac_id]
        for tac_id in catalog.tactic_ids_for(technique_id)
        if tac_id in _TACTIC_PHASE
    ]
    if not phases:
        return ObjectivePhase.INITIAL_ACCESS
    return min(phases, key=lambda p: _PHASE_ORDER[p])


def plan_objectives_from_ttps(
    ttps: object,
    actor_name: str = "",
    catalog: AttackCatalog | None = None,
) -> list[dict]:
    """Build kill-chain-ordered draft objectives from ATT&CK technique IDs.

    ``ttps`` is a list or comma string of technique IDs. Unknown techniques
    are skipped. Returns draft dicts ready for the orchestrator's
    ``add_objective`` tool — this never mutates OPPLAN.
    """
    catalog = catalog or load_attack_catalog()
    items: list[tuple[int, ObjectivePhase, str, str]] = []
    seen: set[str] = set()
    for tid in parse_ids(ttps):
        if not is_technique_id(tid) or tid in seen:
            continue
        seen.add(tid)
        tech = catalog.technique(tid)
        if tech is None:
            continue
        phase = _phase_for_technique(catalog, tid)
        items.append((_PHASE_ORDER[phase], phase, tid, tech.name))

    items.sort(key=lambda x: (x[0], x[2]))
    actor_suffix = f" of {actor_name}" if actor_name else ""
    drafts: list[dict] = []
    for priority, (_order, phase, tid, name) in enumerate(items, start=1):
        drafts.append(
            {
                "priority": priority,
                "phase": phase.value,
                "title": f"Emulate {name} ({tid})",
                "description": (
                    f"Adversary emulation{actor_suffix}: exercise ATT&CK technique {tid} — {name}."
                ),
                "acceptance_criteria": [
                    f"Technique {tid} attempted against an in-scope target.",
                    "Outcome (success or failure) recorded with evidence.",
                    "Blue-team detection result noted for the technique.",
                ],
                "mitre": [tid],
                "opsec": "standard",
            }
        )
    return drafts


def plan_objectives_from_actor(
    profile: object,
    catalog: AttackCatalog | None = None,
) -> list[dict]:
    """Build draft objectives from a ``ThreatProfile`` or ``ThreatActor``.

    Duck-typed: reads ``key_ttps``/``ttps`` and ``initial_access`` for the
    technique list, and ``actor_name``/``name`` for the actor label.
    """
    ttps: list[str] = []
    ttps += list(getattr(profile, "key_ttps", None) or getattr(profile, "ttps", None) or [])
    ttps += list(getattr(profile, "initial_access", None) or [])
    name = getattr(profile, "actor_name", None) or getattr(profile, "name", "") or ""
    return plan_objectives_from_ttps(ttps, actor_name=str(name), catalog=catalog)


@tool
def suggest_objectives_from_actor(actor_name: str, key_ttps: str) -> str:
    """Draft OPPLAN objectives from a threat actor's MITRE ATT&CK TTPs.

    Adversary emulation: turns the TTP list from ``plan/threat-profile.json``
    into kill-chain-ordered objective drafts. Does NOT mutate OPPLAN — call
    ``add_objective`` for each returned draft.

    Args:
        actor_name: The emulated actor, e.g. ``"APT29"``.
        key_ttps: Comma-separated ATT&CK technique IDs from the threat
            profile, e.g. ``"T1566.001, T1059.001, T1078"``.

    Returns:
        JSON with draft objectives (priority, phase, title, description,
        acceptance_criteria, mitre) ready for ``add_objective``.
    """
    drafts = plan_objectives_from_ttps(key_ttps, actor_name=actor_name)
    return json.dumps({"count": len(drafts), "objectives": drafts}, indent=2, ensure_ascii=False)


__all__ = [
    "plan_objectives_from_actor",
    "plan_objectives_from_ttps",
    "suggest_objectives_from_actor",
]
