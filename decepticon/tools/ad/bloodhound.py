"""BloodHound JSON → KnowledgeGraph importer.

BloodHound's collector (SharpHound / AzureHound / BloodHound.py) emits
one JSON file per object type: ``users.json``, ``computers.json``,
``groups.json``, ``domains.json``, ``gpos.json``, ``ous.json``. Each
contains ``data`` and ``meta`` arrays.

We merge these into the existing attack graph so the chain planner can
reason about AD paths *together with* web/cloud/binary findings — enabling
cross-domain attack chains like SSRF → IMDS → AWS → AD pivot → DA.

Every AD object becomes a node with its correct KG label; every ACE /
membership / session edge uses the semantically correct relationship type.
"""

from __future__ import annotations

import json
import logging
import re
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

log = logging.getLogger("decepticon.tools.ad.bloodhound")



@dataclass
class ImportStats:
    users: int = 0
    computers: int = 0
    groups: int = 0
    domains: int = 0
    gpos: int = 0
    ous: int = 0
    edges: int = 0
    skipped_aces: int = 0


    def to_dict(self) -> dict[str, int]:
        return self.__dict__


# ── BloodHound → KG mapping ──────────────────────────────────────────
#
# BloodHound edge types mapped to our EdgeKind with semantically correct
# relationship types. Lower weight = easier-to-abuse relationship.

_BH_EDGE_MAP: dict[str, tuple[EdgeKind, float]] = {
    # Group membership
    "MemberOf": (EdgeKind.MEMBER_OF, 0.8),
    # Session / access
    "HasSession": (EdgeKind.HAS_SESSION, 0.5),
    "AdminTo": (EdgeKind.ADMIN_TO, 0.3),
    "CanRDP": (EdgeKind.CAN_ACCESS, 0.6),
    "CanPSRemote": (EdgeKind.CAN_ACCESS, 0.5),
    "ExecuteDCOM": (EdgeKind.CAN_ACCESS, 0.6),
    "SQLAdmin": (EdgeKind.ADMIN_TO, 0.5),
    # Delegation
    "AllowedToDelegate": (EdgeKind.ENABLES, 0.4),
    "AllowedToAct": (EdgeKind.ENABLES, 0.4),
    # ACL abuse
    "GenericAll": (EdgeKind.ENABLES, 0.3),
    "GenericWrite": (EdgeKind.ENABLES, 0.4),
    "WriteOwner": (EdgeKind.ENABLES, 0.4),
    "WriteDacl": (EdgeKind.ENABLES, 0.3),
    "Owns": (EdgeKind.OWNS, 0.3),
    "ForceChangePassword": (EdgeKind.ENABLES, 0.3),
    "AddMember": (EdgeKind.ENABLES, 0.4),
    "AddSelf": (EdgeKind.ENABLES, 0.4),
    # Credential access
    "ReadLAPSPassword": (EdgeKind.LEAKS, 0.3),
    "ReadGMSAPassword": (EdgeKind.LEAKS, 0.3),
    "GetChanges": (EdgeKind.LEAKS, 0.2),
    "GetChangesAll": (EdgeKind.LEAKS, 0.2),
    "DCSync": (EdgeKind.LEAKS, 0.1),
    # Structural
    "Contains": (EdgeKind.CONTAINS, 1.0),
    "GPLink": (EdgeKind.CONTAINS, 0.8),
    "TrustedBy": (EdgeKind.ENABLES, 0.6),
}


def _node_kind_for_bh(type_name: str) -> NodeKind:
    """Map BloodHound object type to the correct KG NodeKind."""
    m = {
        "User": NodeKind.USER,
        "Computer": NodeKind.HOST,
        "Group": NodeKind.GROUP,
        "Domain": NodeKind.DOMAIN,
        "GPO": NodeKind.GROUP,  # GPOs act as policy containers
        "OU": NodeKind.GROUP,  # OUs act as organizational containers
    }
    return m.get(type_name, NodeKind.HOST)


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
    result: dict[str, Node] = {}
    for n in graph.nodes.values():
        bh_id = n.props.get("bh_id")
        if bh_id is not None:
            result[str(bh_id)] = n
    return result


def _ingest_aces(
    graph: KnowledgeGraph,
    src: Node,
    obj: dict[str, Any],
    stats: ImportStats,
    bh_index: dict[str, Node],
    *,
    source_label: str = "",
) -> None:
    skipped = 0
    for ace in obj.get("Aces") or []:
        right = ace.get("RightName") or ace.get("rightname")
        principal_sid = ace.get("PrincipalSID") or ace.get("principalid")
        if not right or not principal_sid:
            skipped += 1
            continue
        principal_node = bh_index.get(principal_sid)
        if principal_node is None:
            # Infer node kind from SID structure
            node_kind = NodeKind.GROUP  # conservative default
            bh_type = "Unknown"
            rid_match = re.search(r"-(\d+)$", principal_sid)
            if rid_match:
                rid = int(rid_match.group(1))
                if 500 <= rid <= 999:
                    node_kind = NodeKind.SERVICE
                    bh_type = "WellKnown"
            principal_node = Node.make(
                node_kind,
                principal_sid,
                key=f"bh::Unknown::{principal_sid}",
                bh_id=principal_sid,
                bh_type=bh_type,
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
    if skipped:
        stats.skipped_aces += skipped
        log.warning(
            "%d ACEs skipped (missing principal_sid or right) in %s",
            skipped,
            source_label or src.label,
        )



def _ingest_memberships(
    graph: KnowledgeGraph,
    node: Node,
    obj: dict[str, Any],
    stats: ImportStats,
    bh_index: dict[str, Node],
) -> None:
    for mem in obj.get("MemberOf") or []:
        sid = mem.get("ObjectIdentifier") or mem
        if not isinstance(sid, str):
            continue
        parent = bh_index.get(sid)
        if parent is None:
            parent = Node.make(
                NodeKind.GROUP,
                sid,
                key=f"bh::Group::{sid}",
                bh_id=sid,
                bh_type="Group",
            )
            graph.upsert_node(parent)
            bh_index[sid] = parent
        graph.upsert_edge(
            Edge.make(node.id, parent.id, EdgeKind.MEMBER_OF, weight=0.8, bh_right="MemberOf")
        )
        stats.edges += 1


def merge_bloodhound_json(
    data: dict[str, Any] | str,
    graph: KnowledgeGraph,
    *,
    type_hint: str | None = None,
    bh_index: dict[str, Node] | None = None,
) -> ImportStats:
    """Merge a single BloodHound JSON object into ``graph``.

    ``type_hint`` overrides BloodHound's ``meta.type`` field for the
    rare collector outputs without a meta block. Recognised types:
    Users, Computers, Groups, Domains, GPOs, OUs.

    ``bh_index``, when provided, avoids rebuilding the O(n) index on
    every call — callers processing multiple files (e.g.
    ``ingest_bloodhound_zip``) should build it once and pass it in.

    Supports both classic SharpHound/BloodHound.py format (``meta`` +
    ``data``) and BloodHound CE format (``kind`` field, lowercase
    property names).
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bloodhound: invalid JSON payload: {exc}") from exc

    # Handle BH CE JSONL-style list format: each item has its own 'kind'
    if isinstance(data, list):
        stats = ImportStats()
        if bh_index is None:
            bh_index = _build_bh_index(graph)
        for item in data:
            if not isinstance(item, dict):
                continue
            item_kind = item.get("kind")
            if item_kind:
                # Wrap single CE item into the standard structure
                wrapped = {"data": [item], "meta": {"type": item_kind + "s"}}
                inc = merge_bloodhound_json(
                    wrapped, graph, type_hint=item_kind + "s", bh_index=bh_index
                )
                _STAT_ATTRS = (
                    "users", "computers", "groups", "domains",
                    "gpos", "ous", "edges", "skipped_aces",
                )
                for attr in _STAT_ATTRS:
                    setattr(stats, attr, getattr(stats, attr) + getattr(inc, attr))
        return stats

    if not isinstance(data, dict):
        raise ValueError(
            f"bloodhound: expected a JSON object at the top level, got {type(data).__name__}"
        )
    stats = ImportStats()

    # Detect BH CE format: top-level 'kind' field
    ce_kind = data.get("kind")

    meta_raw = data.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    object_type = type_hint or (ce_kind + "s" if ce_kind else None) or meta.get("type") or "Users"
    type_singular = object_type.rstrip("s")

    items_raw = data.get("data") if "data" in data else data.get("items")
    if items_raw is None:
        # CE single-object format: the data dict itself is the object
        if ce_kind and "properties" in data:
            items = [data]
        else:
            items: list[Any] = []
    elif isinstance(items_raw, list):
        items = items_raw
    else:
        raise ValueError(
            f"bloodhound: 'data'/'items' must be an array, got {type(items_raw).__name__}"
        )
    counter_attr = object_type.lower()

    if bh_index is None:
        bh_index = _build_bh_index(graph)

    for obj in items:
        if not isinstance(obj, dict):
            continue
        # Normalize CE format: 'kind' → type, 'properties' are lowercase
        obj_type = type_singular
        if "kind" in obj:
            obj_type = obj["kind"]
        # CE uses lowercase 'properties' with lowercase keys; normalize
        # to PascalCase 'Properties' for _upsert_bh_object compatibility
        if "properties" in obj and "Properties" not in obj:
            obj["Properties"] = obj["properties"]
        if "objectid" in obj and "ObjectIdentifier" not in obj:
            obj["ObjectIdentifier"] = obj["objectid"]

        node = _upsert_bh_object(graph, obj, obj_type)
        bh_index[node.props.get("bh_id", "")] = node
        _ingest_aces(graph, node, obj, stats, bh_index, source_label=node.label)
        _ingest_memberships(graph, node, obj, stats, bh_index)
        if hasattr(stats, counter_attr):
            setattr(stats, counter_attr, getattr(stats, counter_attr) + 1)
    return stats



def ingest_bloodhound_zip(path: str | Path, graph: KnowledgeGraph) -> ImportStats:
    """Walk a BloodHound collector zip and merge every JSON file inside."""
    total = ImportStats()
    p = Path(path)
    _MAX_ENTRY_SIZE = 100_000_000  # 100 MB cap per entry (zip bomb defense)
    _MAX_TOTAL_SIZE = 500_000_000  # 500 MB total decompressed size cap

    # Build the index once before the loop to avoid O(files * nodes) rebuild
    bh_index = _build_bh_index(graph)
    total_decompressed = 0

    try:
        zf = zipfile.ZipFile(p)
    except zipfile.BadZipFile as exc:
        log.error("Invalid or corrupt ZIP file %s: %s", p, exc)
        return total

    with zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            info = zf.getinfo(name)
            if info.file_size > _MAX_ENTRY_SIZE:
                log.warning("Skipping %s: entry size %d exceeds cap", name, info.file_size)
                continue
            total_decompressed += info.file_size
            if total_decompressed > _MAX_TOTAL_SIZE:
                raise ValueError(
                    f"ZIP total decompressed size exceeds {_MAX_TOTAL_SIZE} bytes"
                )
            try:
                raw = zf.read(name)
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            type_hint = None
            base = Path(name).stem.lower()
            for hint in ("users", "computers", "groups", "domains", "gpos", "ous"):
                if hint in base:
                    type_hint = hint.capitalize()
                    break
            inc = merge_bloodhound_json(data, graph, type_hint=type_hint, bh_index=bh_index)
            _STAT_ATTRS = (
                "users", "computers", "groups", "domains",
                "gpos", "ous", "edges", "skipped_aces",
            )
            for attr in _STAT_ATTRS:
                setattr(total, attr, getattr(total, attr) + getattr(inc, attr))
    return total
