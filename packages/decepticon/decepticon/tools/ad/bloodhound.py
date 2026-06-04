"""BloodHound 5.x JSON → KGStore observations (engagement-scoped).

SharpHound / AzureHound / BloodHound.py emit one JSON file per object
type (``users.json``, ``computers.json``, ``groups.json``,
``domains.json``, ``gpos.json``, ``ous.json``, ``containers.json``).
This module parses those, builds observation dicts conforming to
:meth:`KGStore.record_observations`, and writes them in a single
atomic batch.

Compared to the legacy ``KnowledgeGraph`` -based ingest this replaces,
the rewrite addresses five of the load-bearing traps catalogued in
``docs/design/2026-06-04-bloodhound-kgstore-mapping.md`` §2.7:

  1. **PrimaryGroupSID synthesis** — BloodHound emits the primary group
     as a property on User / Computer, NOT as a relationship. The
     legacy ingest dropped this; we now synthesise an explicit
     ``MEMBER_OF`` edge so primary-group membership is visible to the
     chain planner.
  2. **Sessions direction** — ``Sessions.Results[]`` carries
     ``HasSession`` from computer → user; we preserve that direction
     (the legacy code already did, but only for the top-level
     ``Sessions`` block; we now also handle ``PrivilegedSessions`` and
     ``RegistrySessions``).
  3. **ContainedBy flip** — the JSON field is the child carrying a
     pointer to its parent. We flip into canonical ``parent CONTAINS
     child`` edges on ingest.
  4. **Trust 4-way split** — BHCE 5.x replaced single ``TrustedBy``
     with four distinct edges (``SameForestTrust`` /
     ``CrossForestTrust`` / ``AbuseTGTDelegation`` /
     ``SpoofSIDHistory``) based on ``TrustType`` + ``IsTransitive``.
     The legacy ingest collapsed everything to ``EdgeKind.ENABLES``.
  5. **meta.methods provenance** — the SharpHound collection-method
     bitmask is preserved as a node prop on objects from each file so
     "partial collection" debugging works.

Every BloodHound-emitted kind lands under its **dedicated
``AD_*`` NodeKind** value (``ADUser`` / ``ADComputer`` / ``ADGroup``
/ ``ADDomain`` / ``ADGPO`` / ``ADOU`` / ``ADContainer`` plus the
ADCS family). The RFC Option-A endgame for §4.6. AD analysis tools
(``delegation`` / ``gpo`` / ``dcsync`` / ``shadow_creds`` /
``adcs``) filter on the ``bh_type`` prop instead of ``NodeKind``, so
the label change is transparent to them. The consumer that gains
from real BHCE-faithful labels is the chain planner + any prompt-
written Cypher that filters by node label.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decepticon.middleware.kg_internal.store import KGStore
from decepticon_core.types.kg import EdgeKind, NodeKind


@dataclass
class ImportStats:
    users: int = 0
    computers: int = 0
    groups: int = 0
    domains: int = 0
    gpos: int = 0
    ous: int = 0
    containers: int = 0
    # ADCS kinds — SharpHound emits each as its own top-level file
    # (``certtemplates_*.json`` / ``enterprisecas_*.json`` / etc.).
    certtemplates: int = 0
    enterprisecas: int = 0
    rootcas: int = 0
    aiacas: int = 0
    ntauthstores: int = 0
    issuancepolicies: int = 0
    edges: int = 0

    def to_dict(self) -> dict[str, int]:
        return self.__dict__


# ── BloodHound → KGStore mapping ─────────────────────────────────────
#
# BloodHound's per-file ``type`` plural → singular form. Used to derive
# ``bh_type`` and pick the legacy NodeKind family for each object.

_BH_TYPE_SINGULAR: dict[str, str] = {
    "users": "User",
    "computers": "Computer",
    "groups": "Group",
    "domains": "Domain",
    "gpos": "GPO",
    "ous": "OU",
    "containers": "Container",
    # ADCS kinds are emitted by SharpHound as separate top-level files
    # (``certtemplates_*.json`` / ``enterprisecas_*.json`` / etc.) —
    # NOT as embedded blocks under ``domains[]``. The cert-template
    # `ObjectIdentifier` is the GUID; CA-class kinds use the SID.
    "certtemplates": "CertTemplate",
    "enterprisecas": "EnterpriseCA",
    "rootcas": "RootCA",
    "aiacas": "AIACA",
    "ntauthstores": "NTAuthStore",
    "issuancepolicies": "IssuancePolicy",
}


# ACE / direct edge kind mapping: BHCE edge name → (KGStore edge kind,
# weight). Weight: lower = easier-to-abuse. Edge kinds new in V003
# (``ALLOWED_TO_DELEGATE`` / ``ALLOWED_TO_ACT`` / ``HAS_SID_HISTORY`` /
# ACE right-name kinds) are used where the BHCE name is distinct; the
# generic ``ENABLES`` / ``LEAKS`` / ``OWNS`` fall back where it is not.

_BH_EDGE_MAP: dict[str, tuple[EdgeKind, float]] = {
    # Membership / session
    "MemberOf": (EdgeKind.MEMBER_OF, 0.8),
    "HasSession": (EdgeKind.HAS_SESSION, 0.5),
    "AdminTo": (EdgeKind.ADMIN_TO, 0.3),
    "CanRDP": (EdgeKind.CAN_ACCESS, 0.6),
    "CanPSRemote": (EdgeKind.CAN_ACCESS, 0.5),
    "ExecuteDCOM": (EdgeKind.CAN_ACCESS, 0.6),
    "SQLAdmin": (EdgeKind.ADMIN_TO, 0.5),
    # Delegation
    "AllowedToDelegate": (EdgeKind.ALLOWED_TO_DELEGATE, 0.4),
    "AllowedToAct": (EdgeKind.ALLOWED_TO_ACT, 0.4),
    # ACL — raw ACE right names (V003 introduced these so they survive
    # the round-trip even when no BHCE server post-processes them).
    "GenericAll": (EdgeKind.GENERIC_ALL, 0.3),
    "GenericWrite": (EdgeKind.GENERIC_WRITE, 0.4),
    "WriteOwner": (EdgeKind.WRITE_OWNER, 0.4),
    "WriteDacl": (EdgeKind.WRITE_DACL, 0.3),
    "Owns": (EdgeKind.OWNS, 0.3),
    "OwnsLimitedRights": (EdgeKind.OWNS_LIMITED_RIGHTS, 0.4),
    "WriteOwnerLimitedRights": (EdgeKind.WRITE_OWNER_LIMITED_RIGHTS, 0.5),
    "ForceChangePassword": (EdgeKind.FORCE_CHANGE_PASSWORD, 0.3),
    "AddMember": (EdgeKind.ADD_MEMBER, 0.4),
    "AddSelf": (EdgeKind.ADD_SELF, 0.4),
    "WriteSPN": (EdgeKind.WRITE_SPN, 0.4),
    "WriteGPLink": (EdgeKind.WRITE_GP_LINK, 0.3),
    "WriteAccountRestrictions": (EdgeKind.WRITE_ACCOUNT_RESTRICTIONS, 0.4),
    "AllExtendedRights": (EdgeKind.ALL_EXTENDED_RIGHTS, 0.3),
    "AddKeyCredentialLink": (EdgeKind.ADD_KEY_CREDENTIAL_LINK, 0.3),
    "ManageCA": (EdgeKind.MANAGE_CA, 0.3),
    "ManageCertificates": (EdgeKind.MANAGE_CERTIFICATES, 0.3),
    # Credential access
    "ReadLAPSPassword": (EdgeKind.READ_LAPS_PASSWORD, 0.3),
    "ReadGMSAPassword": (EdgeKind.READ_GMSA_PASSWORD, 0.3),
    "GetChanges": (EdgeKind.GET_CHANGES, 0.2),
    "GetChangesAll": (EdgeKind.GET_CHANGES_ALL, 0.2),
    "DCSync": (EdgeKind.DCSYNC, 0.1),
    "SIDHistory": (EdgeKind.HAS_SID_HISTORY, 0.3),
    # Structural
    "Contains": (EdgeKind.CONTAINS, 1.0),
    "GPLink": (EdgeKind.GP_LINK, 0.8),
}


def _node_kind_for_bh(type_name: str) -> NodeKind:
    """Map BloodHound object type to the right NodeKind.

    Every BloodHound-emitted kind now lands under its dedicated
    AD-prefixed NodeKind value (the RFC §4.6 Option-A endgame). The
    AD analysis tools (``delegation`` / ``gpo`` / ``dcsync`` /
    ``shadow_creds`` / ``adcs``) filter on the ``bh_type`` prop
    rather than on ``NodeKind``, so the label change is transparent
    to them. Cross-domain chain analysis (``chain.py`` / Cypher
    queries written in agent prompts) is the consumer that now
    sees real BHCE-faithful labels (``:ADUser`` / ``:ADComputer``
    / ``:ADGroup`` / ``:ADDomain`` / ``:ADGPO`` / ``:ADOU`` /
    ``:ADContainer``).
    """
    return {
        "User": NodeKind.AD_USER,
        "Computer": NodeKind.AD_COMPUTER,
        "Group": NodeKind.AD_GROUP,
        "Domain": NodeKind.AD_DOMAIN,
        "GPO": NodeKind.AD_GPO,
        "OU": NodeKind.AD_OU,
        "Container": NodeKind.AD_CONTAINER,
        # ADCS kinds use the dedicated V003 NodeKind values.
        "CertTemplate": NodeKind.AD_CERT_TEMPLATE,
        "EnterpriseCA": NodeKind.AD_ENTERPRISE_CA,
        "RootCA": NodeKind.AD_ROOT_CA,
        "AIACA": NodeKind.AD_AIA_CA,
        "NTAuthStore": NodeKind.AD_NT_AUTH_STORE,
        "IssuancePolicy": NodeKind.AD_ISSUANCE_POLICY,
    }.get(type_name, NodeKind.AD_COMPUTER)


def _key_for_object(type_name: str, object_id: str) -> str:
    """Deterministic ``(key, engagement)``-friendly dedup key."""
    return f"bh::{type_name}::{object_id}"


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


# ── Trust kind picker (function 5 in the trap catalogue) ─────────────


def _trust_edge_kind(trust_type: Any, is_transitive: Any) -> EdgeKind:
    """Map the BHCE 5.x ``TrustType`` + ``IsTransitive`` combination
    into the correct edge kind.

    BHCE main 2026-06 splits the single legacy ``TrustedBy`` into four:
      - ``ParentChild`` (always transitive)        → SameForestTrust
      - ``CrossLink``                              → CrossForestTrust
      - ``Forest`` + transitive                    → CrossForestTrust
      - ``External`` (typically non-transitive)    → CrossForestTrust
      - Any trust with ``TGTDelegationEnabled``    → AbuseTGTDelegation
      - Trust with SID filtering disabled          → SpoofSIDHistory

    The TGT delegation / SID-history flavours are computed from the
    raw trust object's ``TGTDelegationEnabled`` / ``SidFilteringEnabled``
    fields; this helper only handles the basic TrustType branching.
    The full post-process lives in ``adcs_post.py`` (PR-D2-3).
    """
    tt = _safe_str(trust_type)
    if tt == "ParentChild":
        return EdgeKind.SAME_FOREST_TRUST
    if tt in ("CrossLink", "Forest", "External"):
        return EdgeKind.CROSS_FOREST_TRUST
    return EdgeKind.CROSS_FOREST_TRUST if is_transitive else EdgeKind.SAME_FOREST_TRUST


# ── Observation builder ─────────────────────────────────────────────


@dataclass
class _IngestState:
    """Accumulator that holds the in-progress observation list plus
    the running stats counter. Mutated in place by the per-file
    helpers."""

    obs_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    stats: ImportStats = field(default_factory=ImportStats)
    collection_methods: int = 0

    def upsert_observation(
        self,
        *,
        kind: NodeKind,
        key: str,
        label: str,
        bh_type: str,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert or merge an observation by ``key``. Returns the
        observation dict so callers can extend its ``edges_out``."""
        existing = self.obs_by_key.get(key)
        merged_props: dict[str, Any] = {
            "bh_type": bh_type,
            "bh_id": _bh_id_from_key(key),
        }
        if props:
            for prop_key, prop_value in props.items():
                if prop_value is None:
                    continue
                merged_props[prop_key] = prop_value
        if self.collection_methods:
            merged_props.setdefault("bh_methods", self.collection_methods)
        if existing is None:
            obs: dict[str, Any] = {
                "kind": kind.value,
                "key": key,
                "label": label,
                "props": merged_props,
                "edges_out": [],
            }
            self.obs_by_key[key] = obs
            return obs
        existing.setdefault("props", {}).update(merged_props)
        if label and not existing.get("label"):
            existing["label"] = label
        return existing

    def add_edge(
        self,
        *,
        src_key: str,
        dst_key: str,
        kind: EdgeKind,
        weight: float,
        props: dict[str, Any] | None = None,
    ) -> None:
        src_obs = self.obs_by_key.get(src_key)
        if src_obs is None:
            return
        edge: dict[str, Any] = {
            "to_key": dst_key,
            "kind": kind.value,
            "weight": weight,
            "props": props or {},
        }
        src_obs.setdefault("edges_out", []).append(edge)
        self.stats.edges += 1


def _bh_id_from_key(key: str) -> str:
    """Recover ``ObjectIdentifier`` from a key built by ``_key_for_object``."""
    parts = key.split("::", 2)
    return parts[2] if len(parts) == 3 else key


def _ensure_placeholder(state: _IngestState, *, sid: str, default_type: str) -> str:
    """Ensure a node exists for ``sid``. Used when an ACE / edge
    references a principal that has not appeared in any object file
    yet (cross-file references are common in collector output)."""
    type_name = default_type
    key = _key_for_object(type_name, sid)
    if key not in state.obs_by_key:
        kind = _node_kind_for_bh(type_name)
        state.upsert_observation(
            kind=kind,
            key=key,
            label=sid,
            bh_type=type_name,
        )
    return key


# ── Per-file ingest helpers ─────────────────────────────────────────


def _ingest_object(state: _IngestState, obj: dict[str, Any], type_name: str) -> None:
    """Ingest one object (user/computer/group/etc.) from an items list."""
    properties_raw = obj.get("Properties")
    properties: dict[str, Any] = properties_raw if isinstance(properties_raw, dict) else {}
    object_id = obj.get("ObjectIdentifier") or properties.get("objectid") or ""
    if not object_id:
        return
    key = _key_for_object(type_name, object_id)
    label = properties.get("name") or obj.get("Name") or object_id
    kind = _node_kind_for_bh(type_name)

    # Preserve every BloodHound ``Properties`` field verbatim so the
    # ADCS template predicates (``authenticationenabled`` /
    # ``enrolleesuppliessubject`` / ``requiresmanagerapproval`` /
    # ``nosecurityextension`` / ``ekus`` / etc.) and any future
    # BHCE-emitted fields are available to downstream consumers
    # without per-key extraction maintenance. The legacy explicit
    # allow-list (User / Computer-centric: ``admincount`` /
    # ``dontreqpreauth`` / ``haslaps`` / etc.) silently dropped
    # everything else; ESC1 / ESC4 / ESC9 traversal needs the full
    # set, and the analysis tools that filter by name still find
    # what they look for.
    bh_props: dict[str, Any] = dict(properties)
    if obj.get("IsDeleted"):
        bh_props["isdeleted"] = True
    if obj.get("IsACLProtected"):
        bh_props["isaclprotected"] = True
    state.upsert_observation(
        kind=kind,
        key=key,
        label=str(label),
        bh_type=type_name,
        props={k: v for k, v in bh_props.items() if v is not None},
    )

    # ── Trap 1: PrimaryGroupSID synthesis ─────────────────────────
    primary_group_sid = properties.get("primarygroupsid") or obj.get("PrimaryGroupSID")
    if primary_group_sid and isinstance(primary_group_sid, str):
        dst_key = _ensure_placeholder(state, sid=primary_group_sid, default_type="Group")
        state.add_edge(
            src_key=key,
            dst_key=dst_key,
            kind=EdgeKind.MEMBER_OF,
            weight=0.8,
            props={"bh_right": "PrimaryGroup"},
        )

    _ingest_aces(state, key, obj)
    _ingest_memberships(state, key, obj)
    _ingest_delegation_edges(state, key, obj)
    _ingest_sessions(state, key, obj)
    _ingest_contained_by(state, key, obj)


def _ingest_aces(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """Translate ``Aces[]`` into edges. Direction is principal → target."""
    aces = obj.get("Aces") or []
    if not isinstance(aces, list):
        return
    for ace in aces:
        if not isinstance(ace, dict):
            continue
        right = ace.get("RightName") or ace.get("rightname")
        principal_sid = ace.get("PrincipalSID") or ace.get("principalid")
        if not right or not principal_sid:
            continue
        principal_type = ace.get("PrincipalType") or ace.get("principaltype") or "Unknown"
        principal_key = _ensure_placeholder(
            state,
            sid=principal_sid,
            default_type=principal_type
            if principal_type in _BH_TYPE_SINGULAR.values()
            else "Unknown",
        )
        edge_kind, weight = _BH_EDGE_MAP.get(right, (EdgeKind.ENABLES, 1.0))
        ace_props: dict[str, Any] = {"bh_right": right}
        if ace.get("IsInherited") is not None:
            ace_props["is_inherited"] = bool(ace["IsInherited"])
        if ace.get("InheritanceHash"):
            ace_props["inheritance_hash"] = ace["InheritanceHash"]
        state.add_edge(
            src_key=principal_key,
            dst_key=src_key,
            kind=edge_kind,
            weight=weight,
            props=ace_props,
        )


def _ingest_memberships(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """``MemberOf[]`` (per-object) → MEMBER_OF edges. Also processes
    ``Members[]`` on groups (which carry the reverse: members → group)."""
    member_of = obj.get("MemberOf") or []
    if isinstance(member_of, list):
        for mem in member_of:
            sid = mem.get("ObjectIdentifier") if isinstance(mem, dict) else mem
            if not isinstance(sid, str):
                continue
            dst_key = _ensure_placeholder(state, sid=sid, default_type="Group")
            state.add_edge(
                src_key=src_key,
                dst_key=dst_key,
                kind=EdgeKind.MEMBER_OF,
                weight=0.8,
                props={"bh_right": "MemberOf"},
            )

    members = obj.get("Members") or []
    if isinstance(members, list):
        for mem in members:
            sid = mem.get("ObjectIdentifier") if isinstance(mem, dict) else mem
            if not isinstance(sid, str):
                continue
            mem_type = (mem.get("ObjectType") if isinstance(mem, dict) else None) or "User"
            mem_type = mem_type if mem_type in _BH_TYPE_SINGULAR.values() else "User"
            mem_key = _ensure_placeholder(state, sid=sid, default_type=mem_type)
            state.add_edge(
                src_key=mem_key,
                dst_key=src_key,
                kind=EdgeKind.MEMBER_OF,
                weight=0.8,
                props={"bh_right": "MemberOf"},
            )


def _ingest_delegation_edges(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """``AllowedToDelegate[]`` + ``AllowedToActOnBehalfOfOtherIdentity``."""
    for entry in obj.get("AllowedToDelegate") or []:
        sid = entry.get("ObjectIdentifier") if isinstance(entry, dict) else str(entry)
        if not sid:
            continue
        dst_key = _ensure_placeholder(state, sid=sid, default_type="Computer")
        spn = entry.get("Value", "") if isinstance(entry, dict) else ""
        state.add_edge(
            src_key=src_key,
            dst_key=dst_key,
            kind=EdgeKind.ALLOWED_TO_DELEGATE,
            weight=0.4,
            props={"bh_right": "AllowedToDelegate", "spn": spn},
        )

    for entry in obj.get("AllowedToActOnBehalfOfOtherIdentity") or []:
        sid = entry.get("ObjectIdentifier") if isinstance(entry, dict) else str(entry)
        if not sid:
            continue
        actor_key = _ensure_placeholder(state, sid=sid, default_type="Computer")
        state.add_edge(
            src_key=actor_key,
            dst_key=src_key,
            kind=EdgeKind.ALLOWED_TO_ACT,
            weight=0.4,
            props={"bh_right": "AllowedToAct"},
        )


def _ingest_sessions(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """Trap 2: Sessions / PrivilegedSessions / RegistrySessions all
    carry ``HasSession`` from computer → user. We preserve that
    direction and add ``privileged`` / ``source`` props so consumers
    can filter."""
    for field_name, extra_props in (
        ("Sessions", {}),
        ("PrivilegedSessions", {"privileged": True}),
        ("RegistrySessions", {"source": "registry"}),
    ):
        block = obj.get(field_name)
        results = block.get("Results") if isinstance(block, dict) else None
        if not isinstance(results, list):
            continue
        for entry in results:
            if not isinstance(entry, dict):
                continue
            computer_sid = entry.get("ComputerSID")
            user_sid = entry.get("UserSID")
            if not computer_sid or not user_sid:
                continue
            comp_key = _ensure_placeholder(state, sid=computer_sid, default_type="Computer")
            user_key = _ensure_placeholder(state, sid=user_sid, default_type="User")
            edge_props: dict[str, Any] = {"bh_right": "HasSession"}
            if entry.get("LogonType") is not None:
                edge_props["logon_type"] = entry["LogonType"]
            edge_props.update(extra_props)
            state.add_edge(
                src_key=comp_key,
                dst_key=user_key,
                kind=EdgeKind.HAS_SESSION,
                weight=0.5,
                props=edge_props,
            )


def _ingest_contained_by(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """Trap 3: ``ContainedBy`` is the child carrying a pointer to its
    parent. Flip into canonical ``parent CONTAINS child`` edges."""
    contained_by = obj.get("ContainedBy")
    if not isinstance(contained_by, dict):
        return
    parent_sid = contained_by.get("ObjectIdentifier")
    if not isinstance(parent_sid, str) or not parent_sid:
        return
    parent_type = contained_by.get("ObjectType") or "Container"
    parent_type = parent_type if parent_type in _BH_TYPE_SINGULAR.values() else "Container"
    parent_key = _ensure_placeholder(state, sid=parent_sid, default_type=parent_type)
    state.add_edge(
        src_key=parent_key,
        dst_key=src_key,
        kind=EdgeKind.CONTAINS,
        weight=1.0,
        props={"bh_right": "Contains"},
    )


def _ingest_child_objects(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """``ChildObjects[]`` on Domain / OU / Container — forward
    ``parent CONTAINS child`` edges (no flip needed)."""
    children = obj.get("ChildObjects") or []
    if not isinstance(children, list):
        return
    for child in children:
        if not isinstance(child, dict):
            continue
        child_sid = child.get("ObjectIdentifier")
        if not isinstance(child_sid, str) or not child_sid:
            continue
        child_type = child.get("ObjectType") or "Container"
        child_type = child_type if child_type in _BH_TYPE_SINGULAR.values() else "Container"
        child_key = _ensure_placeholder(state, sid=child_sid, default_type=child_type)
        state.add_edge(
            src_key=src_key,
            dst_key=child_key,
            kind=EdgeKind.CONTAINS,
            weight=1.0,
            props={"bh_right": "Contains"},
        )


def _ingest_gp_links(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """Domain / OU ``Links[]`` → GP_LINK edges from GPO to the container."""
    links = obj.get("Links") or []
    if not isinstance(links, list):
        return
    for link in links:
        if not isinstance(link, dict):
            continue
        gpo_guid = link.get("Guid") or link.get("GUID")
        if not isinstance(gpo_guid, str) or not gpo_guid:
            continue
        gpo_key = _ensure_placeholder(state, sid=gpo_guid, default_type="GPO")
        state.add_edge(
            src_key=gpo_key,
            dst_key=src_key,
            kind=EdgeKind.GP_LINK,
            weight=0.8,
            props={
                "bh_right": "GPLink",
                "enforced": bool(link.get("IsEnforced")),
            },
        )


def _ingest_spn_targets(state: _IngestState, user_key: str, obj: dict[str, Any]) -> None:
    """User ``SPNTargets[]`` → ``WRITE_SPN`` edges per target computer.

    Each entry is ``{ComputerSID, Port, Service}`` and marks a SPN
    the user could write (Targeted Kerberoasting primitive). BHCE
    emits these as raw ACE data; we flip into ``user --WRITE_SPN-->
    computer`` with the SPN metadata preserved on the edge so chain
    analysis can score by service / port.
    """
    targets = obj.get("SPNTargets") or []
    if not isinstance(targets, list):
        return
    for entry in targets:
        if not isinstance(entry, dict):
            continue
        comp_sid = entry.get("ComputerSID")
        if not isinstance(comp_sid, str) or not comp_sid:
            continue
        comp_key = _ensure_placeholder(state, sid=comp_sid, default_type="Computer")
        state.add_edge(
            src_key=user_key,
            dst_key=comp_key,
            kind=EdgeKind.WRITE_SPN,
            weight=0.4,
            props={
                "bh_right": "SPNTarget",
                "port": entry.get("Port"),
                "service": entry.get("Service"),
            },
        )


def _ingest_dump_smsa_password(state: _IngestState, computer_key: str, obj: dict[str, Any]) -> None:
    """Computer ``DumpSMSAPassword[]`` → ``DUMP_SMSA_PASSWORD`` edges.

    Each entry is a ``TypedPrincipal`` pointing at the sMSA / gMSA
    whose password the computer can extract. We emit
    ``computer --DUMP_SMSA_PASSWORD--> principal`` so chain analysis
    sees the credential primitive.
    """
    entries = obj.get("DumpSMSAPassword") or []
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("ObjectIdentifier")
        if not isinstance(sid, str) or not sid:
            continue
        target_type = entry.get("ObjectType") or "User"
        target_type = target_type if target_type in _BH_TYPE_SINGULAR.values() else "User"
        target_key = _ensure_placeholder(state, sid=sid, default_type=target_type)
        state.add_edge(
            src_key=computer_key,
            dst_key=target_key,
            kind=EdgeKind.DUMP_SMSA_PASSWORD,
            weight=0.3,
            props={"bh_right": "DumpSMSAPassword"},
        )


def _ingest_has_sid_history(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """User/Group ``HasSIDHistory[]`` → ``HAS_SID_HISTORY`` edges.

    Each entry is a ``TypedPrincipal`` whose SID appears in the
    principal's SID history; the principal inherits that SID's access
    cross-domain (the SIDHistory primitive — see Trimarc / SpecterOps).
    We emit ``principal --HAS_SID_HISTORY--> historic-principal`` so
    chain analysis can lift SIDHistory escalations.
    """
    entries = obj.get("HasSIDHistory") or []
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("ObjectIdentifier")
        if not isinstance(sid, str) or not sid:
            continue
        target_type = entry.get("ObjectType") or "User"
        target_type = target_type if target_type in _BH_TYPE_SINGULAR.values() else "User"
        target_key = _ensure_placeholder(state, sid=sid, default_type=target_type)
        state.add_edge(
            src_key=src_key,
            dst_key=target_key,
            kind=EdgeKind.HAS_SID_HISTORY,
            weight=0.3,
            props={"bh_right": "HasSIDHistory"},
        )


_LOCAL_GROUP_RID_TO_EDGE: dict[str, tuple[EdgeKind, float]] = {
    "500": (EdgeKind.ADMIN_TO, 0.3),
    "555": (EdgeKind.CAN_ACCESS, 0.6),  # CanRDP
    "562": (EdgeKind.CAN_ACCESS, 0.6),  # ExecuteDCOM
    "580": (EdgeKind.CAN_ACCESS, 0.5),  # CanPSRemote
}


def _rid_from_local_group_id(object_id: str) -> str | None:
    """Extract the trailing numeric RID from a SharpHound LocalGroup id.

    BHCE-emitted ids take two shapes:
      - ``<computerSID>-<RID>`` (numeric trailing — built-in groups)
      - ``<computerSID>__<groupname>`` (string suffix — non-built-in)

    Returns the RID string when the trailing fragment is purely
    numeric so the caller can look it up in
    ``_LOCAL_GROUP_RID_TO_EDGE``.
    """
    tail = object_id.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else None


def _ingest_local_groups(state: _IngestState, computer_key: str, obj: dict[str, Any]) -> None:
    """Computer ``LocalGroups[]`` → ``ADLocalGroup`` nodes + direct
    access edges per RID.

    Per local group: emits one ``ADLocalGroup`` node,
    ``computer --CONTAINS--> ADLocalGroup``, and for each member
    ``principal --MEMBER_OF_LOCAL_GROUP--> ADLocalGroup``. When the
    group's trailing RID matches a known lateral-movement primitive
    (-500 / -555 / -562 / -580), an extra direct
    ``principal --<edge>--> computer`` edge lands so the chain
    planner sees the path without re-deriving it from
    ``MEMBER_OF_LOCAL_GROUP`` traversal.
    """
    local_groups = obj.get("LocalGroups") or []
    if not isinstance(local_groups, list):
        return
    for lg in local_groups:
        if not isinstance(lg, dict):
            continue
        lg_id = lg.get("ObjectIdentifier")
        if not isinstance(lg_id, str) or not lg_id:
            continue
        lg_name = lg.get("Name") or lg_id
        lg_key = _key_for_object("LocalGroup", lg_id)
        state.upsert_observation(
            kind=NodeKind.AD_LOCAL_GROUP,
            key=lg_key,
            label=str(lg_name),
            bh_type="LocalGroup",
            props={
                "ComputerObjectIdentifier": _bh_id_from_key(computer_key),
                "name": lg_name,
            },
        )
        state.add_edge(
            src_key=computer_key,
            dst_key=lg_key,
            kind=EdgeKind.CONTAINS,
            weight=1.0,
            props={"bh_right": "ContainsLocalGroup"},
        )

        rid = _rid_from_local_group_id(lg_id)
        direct_edge = _LOCAL_GROUP_RID_TO_EDGE.get(rid) if rid else None

        results = lg.get("Results") or []
        if not isinstance(results, list):
            continue
        for member in results:
            if not isinstance(member, dict):
                continue
            principal_sid = member.get("ObjectIdentifier")
            if not isinstance(principal_sid, str) or not principal_sid:
                continue
            principal_type = member.get("ObjectType") or "User"
            principal_type = (
                principal_type if principal_type in _BH_TYPE_SINGULAR.values() else "User"
            )
            principal_key = _ensure_placeholder(
                state, sid=principal_sid, default_type=principal_type
            )
            state.add_edge(
                src_key=principal_key,
                dst_key=lg_key,
                kind=EdgeKind.MEMBER_OF_LOCAL_GROUP,
                weight=0.6,
                props={"bh_right": "MemberOfLocalGroup"},
            )
            if direct_edge is not None:
                edge_kind, weight = direct_edge
                state.add_edge(
                    src_key=principal_key,
                    dst_key=computer_key,
                    kind=edge_kind,
                    weight=weight,
                    props={
                        "bh_right": "LocalGroupRid",
                        "rid": rid,
                        "via_local_group": lg_id,
                    },
                )


# Computer ``GPOChanges`` block — GptTmpl.inf-derived effective group
# membership changes applied to the host by GPOs linked to its OU.
#
# Each list under GPOChanges enumerates the **principals** that the
# GPO push grants the corresponding local primitive on **this**
# computer. BHCE's server walks them and synthesises one direct
# access edge per (principal, computer) pair:
#
#   LocalAdmins         → AdminTo
#   RemoteDesktopUsers  → CAN_ACCESS  (CanRDP equivalent)
#   DcomUsers           → CAN_ACCESS  (ExecuteDCOM equivalent)
#   PSRemoteUsers       → CAN_ACCESS  (CanPSRemote equivalent)
#
# The provenance prop ``via_gpo_changes`` records which bucket the
# edge came from so analysts can re-derive the chain to the GPO
# without a separate query.

_GPO_CHANGES_BUCKET_TO_EDGE: dict[str, tuple[EdgeKind, float]] = {
    "LocalAdmins": (EdgeKind.ADMIN_TO, 0.3),
    "RemoteDesktopUsers": (EdgeKind.CAN_ACCESS, 0.6),
    "DcomUsers": (EdgeKind.CAN_ACCESS, 0.6),
    "PSRemoteUsers": (EdgeKind.CAN_ACCESS, 0.5),
}


def _ingest_gpo_changes(state: _IngestState, computer_key: str, obj: dict[str, Any]) -> None:
    """Computer ``GPOChanges`` → direct AdminTo / CAN_ACCESS edges per
    principal granted that primitive on this host by linked GPOs."""
    gpo_changes = obj.get("GPOChanges")
    if not isinstance(gpo_changes, dict):
        return
    for bucket, (edge_kind, weight) in _GPO_CHANGES_BUCKET_TO_EDGE.items():
        principals = gpo_changes.get(bucket) or []
        if not isinstance(principals, list):
            continue
        for principal in principals:
            if not isinstance(principal, dict):
                continue
            principal_sid = principal.get("ObjectIdentifier")
            if not isinstance(principal_sid, str) or not principal_sid:
                continue
            principal_type = principal.get("ObjectType") or "User"
            principal_type = (
                principal_type if principal_type in _BH_TYPE_SINGULAR.values() else "User"
            )
            principal_key = _ensure_placeholder(
                state, sid=principal_sid, default_type=principal_type
            )
            state.add_edge(
                src_key=principal_key,
                dst_key=computer_key,
                kind=edge_kind,
                weight=weight,
                props={
                    "bh_right": "GPOChange",
                    "via_gpo_changes": bucket,
                },
            )


# Computer ``UserRights`` block — the host's effective User Rights
# Assignments (a different policy surface from GPOChanges). BHCE
# maps a small whitelist of privileges to direct access edges:
#
#   SeRemoteInteractiveLogonRight → CAN_ACCESS (CanRDP via UR)
#   SeInteractiveLogonRight       → CAN_ACCESS (local logon proxy)
#   SeServiceLogonRight           → CAN_ACCESS (service-only)
#   SeBatchLogonRight             → CAN_ACCESS (scheduled tasks)
#
# Privileges outside this whitelist are ignored — they don't carry
# the lateral-movement primitive we care about on the chain graph.

_USER_RIGHTS_PRIVILEGE_TO_EDGE: dict[str, tuple[EdgeKind, float]] = {
    "SeRemoteInteractiveLogonRight": (EdgeKind.CAN_ACCESS, 0.6),
    "SeInteractiveLogonRight": (EdgeKind.CAN_ACCESS, 0.7),
    "SeServiceLogonRight": (EdgeKind.CAN_ACCESS, 0.7),
    "SeBatchLogonRight": (EdgeKind.CAN_ACCESS, 0.7),
}


def _ingest_user_rights(state: _IngestState, computer_key: str, obj: dict[str, Any]) -> None:
    """Computer ``UserRights[]`` → direct CAN_ACCESS edges per
    principal that holds a known lateral-movement privilege."""
    user_rights = obj.get("UserRights")
    if not isinstance(user_rights, list):
        return
    for ur in user_rights:
        if not isinstance(ur, dict):
            continue
        privilege = ur.get("Privilege")
        if not isinstance(privilege, str):
            continue
        mapping = _USER_RIGHTS_PRIVILEGE_TO_EDGE.get(privilege)
        if mapping is None:
            continue
        edge_kind, weight = mapping
        results = ur.get("Results") or []
        if not isinstance(results, list):
            continue
        for principal in results:
            if not isinstance(principal, dict):
                continue
            principal_sid = principal.get("ObjectIdentifier")
            if not isinstance(principal_sid, str) or not principal_sid:
                continue
            principal_type = principal.get("ObjectType") or "User"
            principal_type = (
                principal_type if principal_type in _BH_TYPE_SINGULAR.values() else "User"
            )
            principal_key = _ensure_placeholder(
                state, sid=principal_sid, default_type=principal_type
            )
            state.add_edge(
                src_key=principal_key,
                dst_key=computer_key,
                kind=edge_kind,
                weight=weight,
                props={
                    "bh_right": "UserRight",
                    "via_privilege": privilege,
                },
            )


def _ingest_enterprise_ca_edges(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """``EnterpriseCA`` extras: ``EnabledCertTemplates[]`` and
    ``HostingComputer``.

    ``EnabledCertTemplates`` is a list of ``TypedPrincipal`` pointing
    at the CertTemplate GUID; flips into ``EnterpriseCA --PUBLISHED_TO-->
    CertTemplate``. ``HostingComputer`` is the SID of the Windows host
    running the CA service; flips into ``Computer --HOSTS_CA_SERVICE-->
    EnterpriseCA`` so a host-compromise chain naturally reaches the CA."""
    for entry in obj.get("EnabledCertTemplates") or []:
        if not isinstance(entry, dict):
            continue
        template_id = entry.get("ObjectIdentifier")
        if not isinstance(template_id, str) or not template_id:
            continue
        template_key = _ensure_placeholder(state, sid=template_id, default_type="CertTemplate")
        state.add_edge(
            src_key=src_key,
            dst_key=template_key,
            kind=EdgeKind.PUBLISHED_TO,
            weight=0.4,
            props={"bh_right": "PublishedTo"},
        )

    hosting_computer = obj.get("HostingComputer")
    if isinstance(hosting_computer, str) and hosting_computer:
        host_key = _ensure_placeholder(state, sid=hosting_computer, default_type="Computer")
        state.add_edge(
            src_key=host_key,
            dst_key=src_key,
            kind=EdgeKind.HOSTS_CA_SERVICE,
            weight=0.4,
            props={"bh_right": "HostsCAService"},
        )


def _ingest_issuance_policy_link(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """``IssuancePolicy.GroupLink`` (``TypedPrincipal`` pointing at a
    Group SID) is the core of ESC13 — it grants membership in the
    target group to whoever obtains a cert tagged with this policy.
    Flipped into ``IssuancePolicy --OID_GROUP_LINK--> Group``."""
    link = obj.get("GroupLink")
    if not isinstance(link, dict):
        return
    group_sid = link.get("ObjectIdentifier")
    if not isinstance(group_sid, str) or not group_sid:
        return
    group_key = _ensure_placeholder(state, sid=group_sid, default_type="Group")
    state.add_edge(
        src_key=src_key,
        dst_key=group_key,
        kind=EdgeKind.OID_GROUP_LINK,
        weight=0.3,
        props={"bh_right": "OIDGroupLink"},
    )


def _ingest_trusts(state: _IngestState, src_key: str, obj: dict[str, Any]) -> None:
    """Trap 4: Trust 4-way split. Replaces the legacy single
    ``TrustedBy`` edge."""
    trusts = obj.get("Trusts") or []
    if not isinstance(trusts, list):
        return
    for trust in trusts:
        if not isinstance(trust, dict):
            continue
        target_sid = trust.get("TargetDomainSid")
        if not isinstance(target_sid, str) or not target_sid:
            continue
        dst_key = _ensure_placeholder(state, sid=target_sid, default_type="Domain")
        edge_kind = _trust_edge_kind(trust.get("TrustType"), trust.get("IsTransitive"))
        trust_props: dict[str, Any] = {
            "trust_type": trust.get("TrustType"),
            "is_transitive": bool(trust.get("IsTransitive")),
            "trust_direction": trust.get("TrustDirection"),
            "sid_filtering_enabled": trust.get("SidFilteringEnabled"),
            "tgt_delegation_enabled": trust.get("TGTDelegationEnabled"),
        }
        trust_props = {k: v for k, v in trust_props.items() if v is not None}
        state.add_edge(
            src_key=src_key,
            dst_key=dst_key,
            kind=edge_kind,
            weight=0.4,
            props=trust_props,
        )


# ── Top-level merge ─────────────────────────────────────────────────


def _merge_one_payload(state: _IngestState, data: dict[str, Any], *, type_hint: str | None) -> None:
    """Merge one BloodHound JSON payload (one file's worth of objects)
    into the accumulator. Updates per-kind counters in ``state.stats``."""
    meta_raw = data.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    object_type = type_hint or meta.get("type") or "Users"
    type_singular = _BH_TYPE_SINGULAR.get(object_type.lower(), object_type.rstrip("s"))

    # Trap 5: capture meta.methods so every ingested object carries
    # the collection-method bitmask as provenance.
    methods = meta.get("methods")
    if isinstance(methods, int) and methods:
        state.collection_methods = methods

    items_raw = data.get("data") if "data" in data else data.get("items")
    if items_raw is None:
        items: list[Any] = []
    elif isinstance(items_raw, list):
        items = items_raw
    else:
        raise ValueError(
            f"bloodhound: 'data'/'items' must be an array, got {type(items_raw).__name__}"
        )

    counter_attr = object_type.lower()
    for obj in items:
        if not isinstance(obj, dict):
            continue
        _ingest_object(state, obj, type_singular)
        src_key = _key_for_object(type_singular, obj.get("ObjectIdentifier", ""))
        if type_singular in ("Domain", "OU", "Container"):
            _ingest_child_objects(state, src_key, obj)
            _ingest_gp_links(state, src_key, obj)
        if type_singular == "Domain":
            _ingest_trusts(state, src_key, obj)
        if type_singular == "EnterpriseCA":
            _ingest_enterprise_ca_edges(state, src_key, obj)
        if type_singular == "IssuancePolicy":
            _ingest_issuance_policy_link(state, src_key, obj)
        if type_singular == "User":
            _ingest_spn_targets(state, src_key, obj)
            _ingest_has_sid_history(state, src_key, obj)
        if type_singular == "Group":
            _ingest_has_sid_history(state, src_key, obj)
        if type_singular == "Computer":
            _ingest_local_groups(state, src_key, obj)
            _ingest_gpo_changes(state, src_key, obj)
            _ingest_user_rights(state, src_key, obj)
            _ingest_dump_smsa_password(state, src_key, obj)
        if hasattr(state.stats, counter_attr):
            setattr(state.stats, counter_attr, getattr(state.stats, counter_attr) + 1)

    # Clear the collection-method context once this payload is done.
    state.collection_methods = 0


def _merge_payload(state: _IngestState, data: Any, *, type_hint: str | None) -> None:
    """Recursively merge a payload (object, list, or string-encoded)."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bloodhound: invalid JSON payload: {exc}") from exc
    if isinstance(data, list):
        for item in data:
            _merge_payload(state, item, type_hint=type_hint)
        return
    if not isinstance(data, dict):
        raise ValueError(
            f"bloodhound: expected a JSON object at the top level, got {type(data).__name__}"
        )
    _merge_one_payload(state, data, type_hint=type_hint)


# ── Public API ──────────────────────────────────────────────────────


_MAX_ENTRY_SIZE = 100_000_000  # per-entry decompressed-byte cap (zip-bomb defense)


def merge_bloodhound_json(
    data: dict[str, Any] | list[Any] | str,
    *,
    engagement: str,
    type_hint: str | None = None,
    store: KGStore | None = None,
    source_episode_id: str = "bh_ingest_json",
) -> ImportStats:
    """Merge one BloodHound JSON payload into the engagement KG.

    Returns an :class:`ImportStats` capturing how many objects of each
    kind were merged. The KGStore write happens in a single atomic
    batch — partial failure rolls back.

    Args:
        data: JSON object, list, or string-encoded payload.
        engagement: Engagement label (mandatory). KGStore writes are
            scoped to this engagement.
        type_hint: Override BloodHound's ``meta.type`` (rare collector
            outputs omit the meta block).
        store: Optional pre-constructed ``KGStore`` for tests; defaults
            to ``KGStore.from_env()`` and is closed before return.
        source_episode_id: Provenance tag for every observation.
    """
    state = _IngestState()
    _merge_payload(state, data, type_hint=type_hint)
    _flush(state, engagement=engagement, store=store, source_episode_id=source_episode_id)
    return state.stats


def ingest_bloodhound_zip(
    path: str | Path,
    *,
    engagement: str,
    store: KGStore | None = None,
    source_episode_id: str = "bh_ingest_zip",
) -> ImportStats:
    """Walk a BloodHound collector ZIP and merge every JSON file inside.

    Returns an :class:`ImportStats` summarising the merge. All files
    land in a single :meth:`KGStore.record_observations` call so the
    whole ZIP either applies atomically or rolls back.
    """
    state = _IngestState()
    p = Path(path)

    with zipfile.ZipFile(p) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            try:
                buf = io.BytesIO()
                with zf.open(name) as entry:
                    accumulated = 0
                    for chunk in iter(lambda: entry.read(65536), b""):
                        accumulated += len(chunk)
                        if accumulated > _MAX_ENTRY_SIZE:
                            break
                        buf.write(chunk)
                if accumulated > _MAX_ENTRY_SIZE:
                    continue
                raw = buf.getvalue()
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            type_hint = None
            base = Path(name).stem.lower()
            # Order matters: ``certtemplates`` must be checked before
            # ``containers`` (substring overlap on ``t``) — but the
            # two don't share a prefix so it's only a concern if we
            # add ``certtemplate`` (singular) later. ADCS hints are
            # also checked first so the more-specific match wins.
            for hint in (
                "certtemplates",
                "enterprisecas",
                "rootcas",
                "aiacas",
                "ntauthstores",
                "issuancepolicies",
                "users",
                "computers",
                "groups",
                "domains",
                "gpos",
                "ous",
                "containers",
            ):
                if hint in base:
                    # Plural file name keeps the ``meta.type`` form;
                    # ``_BH_TYPE_SINGULAR`` does the singular conversion
                    # inside the payload merge. Pass the plural string
                    # directly so ``_merge_one_payload`` picks the
                    # right entry.
                    type_hint = hint
                    break
            _merge_payload(state, data, type_hint=type_hint)

    _flush(state, engagement=engagement, store=store, source_episode_id=source_episode_id)
    return state.stats


def _flush(
    state: _IngestState,
    *,
    engagement: str,
    store: KGStore | None,
    source_episode_id: str,
) -> None:
    """Single atomic write of the accumulated observations."""
    observations = list(state.obs_by_key.values())
    if not observations:
        return
    owned_store = store is None
    target_store = store if store is not None else KGStore.from_env()
    try:
        target_store.record_observations(
            observations,
            engagement=engagement,
            created_by="bh_ingest",
            source_episode_id=source_episode_id,
        )
    finally:
        if owned_store:
            target_store.close()
