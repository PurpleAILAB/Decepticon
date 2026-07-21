"""MITRE ATT&CK Enterprise STIX importer.

Phase 1a only loads Enterprise v19.1. The importer accepts a local
STIX 2.1 bundle (e.g. the pinned
``enterprise-attack-19.1.json`` from
github.com/mitre-attack/attack-stix-data) and emits ``:Tactic``,
``:Technique``, and ``:ThreatActor`` nodes plus MITRE edges
(``HAS_TECHNIQUE`` from each Tactic to its Techniques and
``HAS_SUBTECHNIQUE`` from a Technique to its Sub-Techniques, plus
``USES_TECHNIQUE`` from ThreatActors to Techniques).

Hazards handled
---------------
- **v19 Defense Evasion split.** ``TA0005`` was renamed from
  "Defense Evasion" → "Stealth" and a new ``TA0112`` "Defense Impairment"
  was introduced. The importer takes the names from the STIX bundle as
  authoritative, so feeding the v19.1 bundle gets the new names with no
  extra rename map.
- **Revoked / deprecated.** ``revoked=true`` or ``x_mitre_deprecated=true``
  entries are filtered out so they cannot become live Technique nodes.
- **Sub-technique linkage.** STIX models the relationship as a separate
  SRO of ``relationship_type="subtechnique-of"`` rather than a property
  on the sub-technique. The importer resolves source/target STIX UUIDs
  back to ATT&CK IDs to emit HAS_SUBTECHNIQUE edges.

The CLI passes the bundle path; the importer never fetches over the
network so CI builds stay deterministic and offline-capable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decepticon.skillogy.builder.model import Edge, Node

_ATTCK_VERSION = "19.1"


def _attck_id(obj: dict[str, Any]) -> str | None:
    """Return the ATT&CK external ID (TA0xxx / T1xxx[.xxx] / Gxxxx) for an SDO."""
    for ref in obj.get("external_references") or []:
        if ref.get("source_name") == "mitre-attack":
            ext_id = ref.get("external_id")
            if isinstance(ext_id, str) and ext_id:
                return ext_id
    return None


def _is_alive(obj: dict[str, Any]) -> bool:
    return not (obj.get("revoked") or obj.get("x_mitre_deprecated"))


def _group_status(obj: dict[str, Any]) -> str:
    if obj.get("revoked"):
        return "revoked"
    if obj.get("x_mitre_deprecated"):
        return "deprecated"
    return "active"


def _index_groups_and_uses(
    objects: list[Any], uuid_to_attck: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    group_by_id: dict[str, dict[str, Any]] = {}
    uses_relationships: list[dict[str, Any]] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "intrusion-set":
            attck_id = _attck_id(obj)
            if not attck_id:
                continue
            group_by_id[attck_id] = obj
            uuid_to_attck[str(obj.get("id") or "")] = attck_id
        elif (
            obj.get("type") == "relationship"
            and obj.get("relationship_type") == "uses"
            and _is_alive(obj)
        ):
            uses_relationships.append(obj)
    return group_by_id, uses_relationships


def _uses_edges(
    relationships: list[dict[str, Any]],
    uuid_to_attck: dict[str, str],
    group_by_id: dict[str, dict[str, Any]],
    technique_by_id: dict[str, dict[str, Any]],
) -> list[Edge]:
    edges: list[Edge] = []
    for rel in relationships:
        source_ref = rel.get("source_ref")
        target_ref = rel.get("target_ref")
        if not isinstance(source_ref, str) or not source_ref:
            continue
        if not isinstance(target_ref, str) or not target_ref:
            continue
        group_id = uuid_to_attck.get(source_ref)
        technique_id = uuid_to_attck.get(target_ref)
        if group_id not in group_by_id or technique_id not in technique_by_id:
            continue
        edges.append(
            Edge(
                edge_type="USES_TECHNIQUE",
                from_label="ThreatActor",
                from_key_field="id",
                from_key=group_id,
                to_label="Technique",
                to_key_field="id",
                to_key=technique_id,
            )
        )
    return edges


def _threat_actor_nodes(group_by_id: dict[str, dict[str, Any]]) -> list[Node]:
    nodes: list[Node] = []
    for attck_id, group in sorted(group_by_id.items()):
        aliases = sorted(
            {alias for alias in group.get("aliases") or [] if isinstance(alias, str) and alias}
        )
        nodes.append(
            Node(
                label="ThreatActor",
                key_field="id",
                properties={
                    "id": attck_id,
                    "stix_id": str(group.get("id") or ""),
                    "name": str(group.get("name") or ""),
                    "description": str(group.get("description") or ""),
                    "mitre_aliases": aliases,
                    "status": _group_status(group),
                    "created": str(group.get("created") or ""),
                    "modified": str(group.get("modified") or ""),
                    "matrix": "enterprise",
                    "framework": "attack",
                    "attck_version": _ATTCK_VERSION,
                    "deprecated": bool(group.get("x_mitre_deprecated", False)),
                    "revoked": bool(group.get("revoked", False)),
                },
            )
        )
    return nodes


def emit_mitre_records(bundle_path: Path) -> tuple[list[Node], list[Edge]]:
    """Load + parse an Enterprise STIX bundle, return (nodes, edges)."""
    if not bundle_path.exists():
        raise FileNotFoundError(f"STIX bundle not found: {bundle_path}")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError(f"{bundle_path}: 'objects' must be a list")

    # uuid → ATT&CK external id, used when resolving subtechnique-of relationships.
    uuid_to_attck: dict[str, str] = {}
    # ATT&CK id → STIX object, used to look up name/description.
    technique_by_id: dict[str, dict[str, Any]] = {}
    tactic_by_shortname: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        otype = obj.get("type")
        if otype == "x-mitre-tactic":
            attck_id = _attck_id(obj)
            shortname = obj.get("x_mitre_shortname")
            if not attck_id or not shortname or not _is_alive(obj):
                continue
            tactic_by_shortname[shortname] = {**obj, "_attck_id": attck_id}
            uuid_to_attck[obj.get("id", "")] = attck_id
        elif otype == "attack-pattern":
            attck_id = _attck_id(obj)
            if not attck_id or not _is_alive(obj):
                continue
            technique_by_id[attck_id] = obj
            uuid_to_attck[obj.get("id", "")] = attck_id
        elif otype == "relationship":
            if obj.get("relationship_type") == "subtechnique-of":
                relationships.append(obj)

    group_by_id, uses_relationships = _index_groups_and_uses(objects, uuid_to_attck)

    nodes: list[Node] = []
    edges: list[Edge] = []

    # === :Tactic nodes ===
    for shortname, tac in sorted(tactic_by_shortname.items()):
        nodes.append(
            Node(
                label="Tactic",
                key_field="id",
                properties={
                    "id": tac["_attck_id"],
                    "name": str(tac.get("name") or ""),
                    "description": str(tac.get("description") or ""),
                    "shortname": shortname,
                    "matrix": "enterprise",
                    "framework": "attack",
                    "attck_version": _ATTCK_VERSION,
                    "deprecated": bool(tac.get("x_mitre_deprecated", False)),
                    "revoked": bool(tac.get("revoked", False)),
                },
            )
        )

    # === :Technique nodes + HAS_TECHNIQUE / HAS_SUBTECHNIQUE edges ===
    for attck_id, tech in sorted(technique_by_id.items()):
        is_sub = bool(tech.get("x_mitre_is_subtechnique", False))
        parent_id = ""
        if is_sub and "." in attck_id:
            parent_id = attck_id.split(".", 1)[0]
        platforms = list(tech.get("x_mitre_platforms") or [])
        nodes.append(
            Node(
                label="Technique",
                key_field="id",
                properties={
                    "id": attck_id,
                    "name": str(tech.get("name") or ""),
                    "description": str(tech.get("description") or ""),
                    "matrix": "enterprise",
                    "framework": "attack",
                    "is_subtechnique": is_sub,
                    "parent_id": parent_id,
                    "platforms": sorted(platforms),
                    "attck_version": _ATTCK_VERSION,
                    "deprecated": bool(tech.get("x_mitre_deprecated", False)),
                    "revoked": bool(tech.get("revoked", False)),
                },
            )
        )
        # HAS_TECHNIQUE from each tactic this technique belongs to.
        for phase in tech.get("kill_chain_phases") or []:
            if phase.get("kill_chain_name") != "mitre-attack":
                continue
            shortname = phase.get("phase_name")
            tac = tactic_by_shortname.get(shortname)
            if not tac:
                continue
            edges.append(
                Edge(
                    edge_type="HAS_TECHNIQUE",
                    from_label="Tactic",
                    from_key_field="id",
                    from_key=tac["_attck_id"],
                    to_label="Technique",
                    to_key_field="id",
                    to_key=attck_id,
                )
            )

    # HAS_SUBTECHNIQUE from parent technique to each of its sub-techniques.
    for rel in relationships:
        src_uuid = rel.get("source_ref", "")  # sub-technique UUID
        tgt_uuid = rel.get("target_ref", "")  # parent technique UUID
        sub_id = uuid_to_attck.get(src_uuid)
        parent_id = uuid_to_attck.get(tgt_uuid)
        if not sub_id or not parent_id:
            continue
        edges.append(
            Edge(
                edge_type="HAS_SUBTECHNIQUE",
                from_label="Technique",
                from_key_field="id",
                from_key=parent_id,
                to_label="Technique",
                to_key_field="id",
                to_key=sub_id,
            )
        )

    edges.extend(_uses_edges(uses_relationships, uuid_to_attck, group_by_id, technique_by_id))
    nodes.extend(_threat_actor_nodes(group_by_id))

    # MatrixVersion idempotency-key meta node.
    nodes.append(
        Node(
            label="MatrixVersion",
            key_field="matrix",
            properties={
                "matrix": "enterprise",
                "version": _ATTCK_VERSION,
                "framework": "attack",
            },
        )
    )

    return nodes, edges
