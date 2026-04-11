"""BloodHound JSON → KnowledgeGraph importer.

BloodHound's collector (SharpHound / AzureHound / BloodHound.py) emits
one JSON file per object type: ``users.json``, ``computers.json``,
``groups.json``, ``domains.json``, ``gpos.json``, ``ous.json``. Each
contains ``data`` and ``meta`` arrays.

We merge these into the existing ``KnowledgeGraph`` so the chain
planner can reason about AD paths *together with* web/cloud findings.
Every AD object becomes a node with kind-specific metadata; every
ACE / membership / SessionCount edge becomes a graph edge.

This module is intentionally resilient: BloodHound schema varies across
versions, so we accept minor differences and skip unknown shapes.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)


@dataclass
class ImportStats:
    users: int = 0
    computers: int = 0
    groups: int = 0
    domains: int = 0
    gpos: int = 0
    ous: int = 0
    edges: int = 0

    def to_dict(self) -> dict[str, int]:
        return self.__dict__


# ── High-value BloodHound edge types ────────────────────────────────────

# Mapping of common BloodHound edge names → our internal edge kind +
# weight. Lower weight = easier-to-abuse relationship.
_BH_EDGE_MAP: dict[str, tuple[EdgeKind, float]] = {
    "MemberOf": (EdgeKind.AUTH_AS, 0.8),
    "HasSession": (EdgeKind.AUTH_AS, 0.5),
    "AdminTo": (EdgeKind.GRANTS, 0.3),
    "CanRDP": (EdgeKind.GRANTS, 0.6),
    "CanPSRemote": (EdgeKind.GRANTS, 0.5),
    "ExecuteDCOM": (EdgeKind.GRANTS, 0.6),
    "SQLAdmin": (EdgeKind.GRANTS, 0.5),
    "AllowedToDelegate": (EdgeKind.ENABLES, 0.4),
    "AllowedToAct": (EdgeKind.ENABLES, 0.4),
    "GenericAll": (EdgeKind.ENABLES, 0.3),
    "GenericWrite": (EdgeKind.ENABLES, 0.4),
    "WriteOwner": (EdgeKind.ENABLES, 0.4),
    "WriteDacl": (EdgeKind.ENABLES, 0.3),
    "Owns": (EdgeKind.ENABLES, 0.3),
    "ForceChangePassword": (EdgeKind.ENABLES, 0.3),
    "AddMember": (EdgeKind.ENABLES, 0.4),
    "AddSelf": (EdgeKind.ENABLES, 0.4),
    "ReadLAPSPassword": (EdgeKind.LEAKS, 0.3),
    "ReadGMSAPassword": (EdgeKind.LEAKS, 0.3),
    "GetChanges": (EdgeKind.LEAKS, 0.2),
    "GetChangesAll": (EdgeKind.LEAKS, 0.2),
    "DCSync": (EdgeKind.LEAKS, 0.1),
    "Contains": (EdgeKind.CONTAINS, 1.0),
    "GPLink": (EdgeKind.AFFECTED_BY, 0.8),
    "TrustedBy": (EdgeKind.AUTH_AS, 0.6),
}


def _node_kind_for_bh(type_name: str) -> NodeKind:
    m = {
        "User": NodeKind.USER,
        "Computer": NodeKind.HOST,
        "Group": NodeKind.USER,  # represent groups as users for the chain planner
        "Domain": NodeKind.HOST,
        "GPO": NodeKind.SERVICE,
        "OU": NodeKind.SERVICE,
    }
    return m.get(type_name, NodeKind.SERVICE)


def _upsert_bh_object(graph: KnowledgeGraph, obj: dict[str, Any], type_name: str) -> Node:
    props = obj.get("Properties") or {}
    object_id = obj.get("ObjectIdentifier") or props.get("objectid") or ""
    label = props.get("name") or obj.get("Name") or object_id or "unknown"
    node_kind = _node_kind_for_bh(type_name)
    node = Node.make(
        node_kind,
        str(label),
        key=f"bh::{type_name}::{object_id}",
        bh_type=type_name,
        bh_id=object_id,
        domain=props.get("domain"),
        enabled=props.get("enabled"),
        admincount=props.get("admincount"),
        haslaps=props.get("haslaps"),
        hasspn=props.get("hasspn"),
        dontreqpreauth=props.get("dontreqpreauth"),
    )
    graph.upsert_node(node)
    return node


def _build_bh_index(graph: KnowledgeGraph) -> dict[str, Node]:
    """Build a bh_id → Node lookup for O(1) principal resolution."""
    return {n.props.get("bh_id"): n for n in graph.nodes.values() if n.props.get("bh_id")}


def _ingest_aces(
    graph: KnowledgeGraph,
    src: Node,
    obj: dict[str, Any],
    stats: ImportStats,
    bh_index: dict[str, Node],
) -> None:
    for ace in obj.get("Aces") or []:
        right = ace.get("RightName") or ace.get("rightname")
        principal_sid = ace.get("PrincipalSID") or ace.get("principalid")
        if not right or not principal_sid:
            continue
        # O(1) lookup via bh_index
        principal_node = bh_index.get(principal_sid)
        if principal_node is None:
            principal_node = Node.make(
                NodeKind.USER,
                principal_sid,
                key=f"bh::Unknown::{principal_sid}",
                bh_id=principal_sid,
                bh_type="Unknown",
            )
            graph.upsert_node(principal_node)
            bh_index[principal_sid] = principal_node

        mapping = _BH_EDGE_MAP.get(right)
        if mapping:
            edge_kind, weight = mapping
        else:
            edge_kind, weight = (EdgeKind.ENABLES, 1.0)
        graph.upsert_edge(
            Edge.make(
                principal_node.id,
                src.id,
                edge_kind,
                weight=weight,
                key=f"bh-ace::{right}",
                bh_right=right,
            )
        )
        stats.edges += 1


def _ingest_memberships(
    graph: KnowledgeGraph, node: Node, obj: dict[str, Any], stats: ImportStats,
    bh_index: dict[str, Node],
) -> None:
    for mem in obj.get("MemberOf") or []:
        sid = mem.get("ObjectIdentifier") or mem
        if not isinstance(sid, str):
            continue
        parent = bh_index.get(sid)
        if parent is None:
            parent = Node.make(
                NodeKind.USER,
                sid,
                key=f"bh::Group::{sid}",
                bh_id=sid,
                bh_type="Group",
            )
            graph.upsert_node(parent)
            bh_index[sid] = parent
        graph.upsert_edge(
            Edge.make(node.id, parent.id, EdgeKind.AUTH_AS, weight=0.8, bh_right="MemberOf")
        )
        stats.edges += 1


def merge_bloodhound_json(
    data: dict[str, Any] | str,
    graph: KnowledgeGraph,
    *,
    type_hint: str | None = None,
) -> ImportStats:
    """Merge a single BloodHound JSON object into ``graph``.

    ``type_hint`` overrides BloodHound's ``meta.type`` field for the
    rare collector outputs without a meta block. Recognised types:
    Users, Computers, Groups, Domains, GPOs, OUs.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bloodhound: invalid JSON payload: {exc}") from exc
    # BloodHound's schema is always a top-level object — a top-level
    # array or scalar would crash the .get() calls below. Reject cleanly.
    if not isinstance(data, dict):
        raise ValueError(
            "bloodhound: expected a JSON object at the top level, got "
            f"{type(data).__name__}"
        )
    stats = ImportStats()

    meta_raw = data.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    object_type = type_hint or meta.get("type") or "Users"
    type_singular = object_type.rstrip("s")

    items_raw = data.get("data") if "data" in data else data.get("items")
    if items_raw is None:
        items: list[Any] = []
    elif isinstance(items_raw, list):
        items = items_raw
    else:
        raise ValueError(
            "bloodhound: 'data'/'items' must be an array, got "
            f"{type(items_raw).__name__}"
        )
    counter_attr = object_type.lower()

    bh_index = _build_bh_index(graph)

    for obj in items:
        if not isinstance(obj, dict):
            continue
        node = _upsert_bh_object(graph, obj, type_singular)
        bh_index[node.props.get("bh_id", "")] = node
        _ingest_aces(graph, node, obj, stats, bh_index)
        _ingest_memberships(graph, node, obj, stats, bh_index)
        if hasattr(stats, counter_attr):
            setattr(stats, counter_attr, getattr(stats, counter_attr) + 1)
    return stats


def ingest_bloodhound_zip(path: str | Path, graph: KnowledgeGraph) -> ImportStats:
    """Walk a BloodHound collector zip and merge every JSON file inside."""
    total = ImportStats()
    p = Path(path)
    _MAX_ENTRY_SIZE = 100_000_000  # 100 MB cap per entry (zip bomb defense)

    with zipfile.ZipFile(p) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            info = zf.getinfo(name)
            if info.file_size > _MAX_ENTRY_SIZE:
                continue
            try:
                raw = zf.read(name)
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            # Guess type from filename if meta is missing
            type_hint = None
            base = Path(name).stem.lower()
            for hint in ("users", "computers", "groups", "domains", "gpos", "ous"):
                if hint in base:
                    type_hint = hint.capitalize()
                    break
            inc = merge_bloodhound_json(data, graph, type_hint=type_hint)
            for attr in ("users", "computers", "groups", "domains", "gpos", "ous", "edges"):
                setattr(total, attr, getattr(total, attr) + getattr(inc, attr))
    return total
