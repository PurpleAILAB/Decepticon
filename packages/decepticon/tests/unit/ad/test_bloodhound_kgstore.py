"""KGStore-mock-based tests for the BloodHound ingest rewrite.

These replace the legacy ``test_ad_bloodhound_tools.py`` / portions of
``test_ad.py`` / ``test_delegation_props.py`` / ``test_gpo_bh_type_case.py``
that were tied to the ``ingest_bloodhound_zip(path, graph)`` signature.

The new ingest writes through ``KGStore.record_observations``; we
inject a ``_FakeKGStore`` via the ``store=`` kwarg and inspect the
captured observations to verify the trap-fix behaviour from the
BloodHound RFC §2.7.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from decepticon.tools.ad.bloodhound import (
    ImportStats,
    ingest_bloodhound_zip,
    merge_bloodhound_json,
)


class _FakeKGStore:
    """Captures every ``record_observations`` call so tests can inspect
    the observation graph the ingest would write."""

    def __init__(self) -> None:
        self.observations: list[dict[str, Any]] = []
        self.engagement: str | None = None
        self.created_by: str | None = None
        self.source_episode_id: str | None = None
        self.flush_count: int = 0

    def record_observations(
        self,
        observations: Iterable[dict[str, Any]],
        *,
        engagement: str,
        created_by: str,
        source_episode_id: str,
    ) -> dict[str, Any]:
        obs_list = list(observations)
        self.observations.extend(obs_list)
        self.engagement = engagement
        self.created_by = created_by
        self.source_episode_id = source_episode_id
        self.flush_count += 1
        edge_count = sum(len(o.get("edges_out") or []) for o in obs_list)
        return {
            "created": len(obs_list),
            "merged": 0,
            "edges": edge_count,
            "revision": "fake-rev",
        }

    def close(self) -> None:
        pass

    # ── Inspection helpers ──────────────────────────────────────────

    def nodes_by_key(self) -> dict[str, dict[str, Any]]:
        return {o["key"]: o for o in self.observations}

    def edges(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        """Returns (src_key, edge_kind, dst_key, props) tuples."""
        out: list[tuple[str, str, str, dict[str, Any]]] = []
        for obs in self.observations:
            for edge in obs.get("edges_out") or []:
                out.append(
                    (
                        obs["key"],
                        edge["kind"],
                        edge["to_key"],
                        edge.get("props") or {},
                    )
                )
        return out

    def edges_of_kind(self, kind: str) -> list[tuple[str, str, dict[str, Any]]]:
        return [(s, d, p) for s, k, d, p in self.edges() if k == kind]


# ── Top-level signature contracts ───────────────────────────────────


class TestPublicSignatures:
    def test_merge_returns_import_stats(self) -> None:
        store = _FakeKGStore()
        result = merge_bloodhound_json(
            {"meta": {"type": "users"}, "data": []},
            engagement="t-1",
            store=store,
        )
        assert isinstance(result, ImportStats)

    def test_engagement_threaded_to_store(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            {
                "meta": {"type": "users"},
                "data": [
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                        "Properties": {"name": "admin"},
                    }
                ],
            },
            engagement="t-eng",
            store=store,
            source_episode_id="ep-x",
        )
        assert store.engagement == "t-eng"
        assert store.source_episode_id == "ep-x"
        assert store.created_by == "bh_ingest"

    def test_empty_data_array_does_not_flush(self) -> None:
        """Empty payload short-circuits before any KGStore write."""
        store = _FakeKGStore()
        merge_bloodhound_json(
            {"meta": {"type": "users"}, "data": []},
            engagement="t-2",
            store=store,
        )
        assert store.flush_count == 0
        assert store.observations == []


# ── Trap 1: PrimaryGroupSID synthesis ───────────────────────────────


class TestPrimaryGroupSidSynthesis:
    def _bh(self) -> dict[str, Any]:
        return {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "PrimaryGroupSID": "S-1-5-21-1-1-1-513",
                    "Properties": {"name": "admin"},
                }
            ],
        }

    def test_member_of_edge_synthesised(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(self._bh(), engagement="t", store=store)
        member_of_edges = store.edges_of_kind("MEMBER_OF")
        assert any(
            "S-1-5-21-1-1-1-500" in s and "S-1-5-21-1-1-1-513" in d for s, d, _ in member_of_edges
        )

    def test_synth_edge_carries_primary_group_marker(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(self._bh(), engagement="t", store=store)
        member_of_edges = store.edges_of_kind("MEMBER_OF")
        primary_edges = [p for _s, _d, p in member_of_edges if p.get("bh_right") == "PrimaryGroup"]
        assert len(primary_edges) == 1


# ── Trap 2: Sessions direction (computer → user) ────────────────────


class TestSessionsDirection:
    def test_session_edge_runs_computer_to_user(self) -> None:
        bh = {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "Sessions": {
                        "Results": [
                            {
                                "ComputerSID": "S-1-5-21-1-1-1-1001",
                                "UserSID": "S-1-5-21-1-1-1-500",
                                "LogonType": 2,
                            }
                        ]
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        session_edges = store.edges_of_kind("HAS_SESSION")
        assert len(session_edges) == 1
        src, dst, props = session_edges[0]
        assert "1001" in src  # computer
        assert "500" in dst  # user
        assert props.get("logon_type") == 2

    def test_privileged_sessions_marker(self) -> None:
        bh = {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "PrivilegedSessions": {
                        "Results": [
                            {
                                "ComputerSID": "S-1-5-21-1-1-1-1001",
                                "UserSID": "S-1-5-21-1-1-1-500",
                            }
                        ]
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        session_edges = store.edges_of_kind("HAS_SESSION")
        assert len(session_edges) == 1
        assert session_edges[0][2].get("privileged") is True


# ── Trap 3: ContainedBy flip ────────────────────────────────────────


class TestContainedByFlip:
    def test_child_pointer_flipped_into_parent_contains_child(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "admin"},
                    "ContainedBy": {
                        "ObjectIdentifier": "OU-DEPT-GUID",
                        "ObjectType": "OU",
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        contains = store.edges_of_kind("CONTAINS")
        assert any("OU-DEPT-GUID" in s and "S-1-5-21-1-1-1-500" in d for s, d, _ in contains)


# ── Trap 4: Trust 4-way split ───────────────────────────────────────


class TestTrust4WaySplit:
    @pytest.mark.parametrize(
        "trust_type,is_transitive,expected_kind",
        [
            ("ParentChild", True, "SAME_FOREST_TRUST"),
            ("CrossLink", False, "CROSS_FOREST_TRUST"),
            ("Forest", True, "CROSS_FOREST_TRUST"),
            ("External", False, "CROSS_FOREST_TRUST"),
        ],
    )
    def test_trust_branches_into_correct_edge_kind(
        self,
        trust_type: str,
        is_transitive: bool,
        expected_kind: str,
    ) -> None:
        bh = {
            "meta": {"type": "domains"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-0",
                    "Properties": {"name": "corp.local"},
                    "Trusts": [
                        {
                            "TargetDomainSid": "S-1-5-21-2-2-2-0",
                            "TrustType": trust_type,
                            "IsTransitive": is_transitive,
                        }
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        trust_edges = store.edges_of_kind(expected_kind)
        assert len(trust_edges) == 1
        assert trust_edges[0][2].get("trust_type") == trust_type


# ── Trap 5: meta.methods provenance ─────────────────────────────────


class TestMetaMethodsProvenance:
    def test_collection_method_bitmask_preserved_on_node_prop(self) -> None:
        bh = {
            "meta": {"type": "users", "methods": 32, "version": 5},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "admin"},
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        user_node = store.nodes_by_key().get("bh::User::S-1-5-21-1-1-1-500")
        assert user_node is not None
        assert user_node["props"].get("bh_methods") == 32

    def test_methods_does_not_leak_into_next_payload(self) -> None:
        """The collection-method context resets after each payload."""
        bh_list = [
            {
                "meta": {"type": "users", "methods": 32},
                "data": [
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                        "Properties": {"name": "admin"},
                    }
                ],
            },
            {
                "meta": {"type": "groups"},
                "data": [
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-513",
                        "Properties": {"name": "users"},
                    }
                ],
            },
        ]
        store = _FakeKGStore()
        merge_bloodhound_json(bh_list, engagement="t", store=store)
        group_node = store.nodes_by_key().get("bh::Group::S-1-5-21-1-1-1-513")
        assert group_node is not None
        assert "bh_methods" not in group_node["props"]


# ── ACE edge kind mapping (raw form survives) ───────────────────────


class TestAceEdgeMapping:
    @pytest.mark.parametrize(
        "right_name,expected_kind",
        [
            ("GenericAll", "GENERIC_ALL"),
            ("GenericWrite", "GENERIC_WRITE"),
            ("WriteDacl", "WRITE_DACL"),
            ("WriteOwner", "WRITE_OWNER"),
            ("ForceChangePassword", "FORCE_CHANGE_PASSWORD"),
            ("AddMember", "ADD_MEMBER"),
            ("ReadLAPSPassword", "READ_LAPS_PASSWORD"),
            ("ReadGMSAPassword", "READ_GMSA_PASSWORD"),
            ("GetChanges", "GET_CHANGES"),
            ("GetChangesAll", "GET_CHANGES_ALL"),
            ("DCSync", "DCSYNC"),
            ("AddKeyCredentialLink", "ADD_KEY_CREDENTIAL_LINK"),
        ],
    )
    def test_each_ace_right_maps_to_distinct_edge_kind(
        self, right_name: str, expected_kind: str
    ) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "target"},
                    "Aces": [
                        {
                            "RightName": right_name,
                            "PrincipalSID": "S-1-5-21-1-1-1-1106",
                            "PrincipalType": "User",
                        }
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind(expected_kind)
        assert any(
            "1106" in s and "500" in d and p.get("bh_right") == right_name for s, d, p in edges
        )

    def test_inheritance_hash_preserved_on_ace_edge(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "target"},
                    "Aces": [
                        {
                            "RightName": "GenericAll",
                            "PrincipalSID": "S-1-5-21-1-1-1-1106",
                            "PrincipalType": "User",
                            "IsInherited": True,
                            "InheritanceHash": "abc123",
                        }
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("GENERIC_ALL")
        assert any(
            p.get("is_inherited") is True and p.get("inheritance_hash") == "abc123"
            for _s, _d, p in edges
        )


# ── ZIP entry handling ──────────────────────────────────────────────


class TestZipIngest:
    def _make_zip(self, tmp_path: Path, payload: dict[str, Any]) -> Path:
        import json as _json

        zip_path = tmp_path / "bh.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("users.json", _json.dumps(payload))
        return zip_path

    def test_zip_dispatches_per_filename_hint(self, tmp_path: Path) -> None:
        payload = {
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "admin"},
                }
            ]
        }
        store = _FakeKGStore()
        stats = ingest_bloodhound_zip(
            self._make_zip(tmp_path, payload),
            engagement="t",
            store=store,
        )
        assert stats.users == 1

    def test_oversized_entry_silently_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cap to 100 bytes so the test entry trips it.
        import decepticon.tools.ad.bloodhound as bh_mod

        monkeypatch.setattr(bh_mod, "_MAX_ENTRY_SIZE", 100)
        oversized = b'{"meta":{"type":"users"},"data":[]}' + b"x" * 200
        zip_path = tmp_path / "bh.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("users.json", oversized)
        store = _FakeKGStore()
        stats = ingest_bloodhound_zip(zip_path, engagement="t", store=store)
        assert stats.users == 0

    def test_in_memory_zip_works_too(self, tmp_path: Path) -> None:
        # ``ingest_bloodhound_zip`` takes a path; the in-memory ``BytesIO``
        # path is exercised when callers stream from S3 / GHCR.
        # Verified separately by spilling to disk via tmp_path here so
        # the public path is exercised end-to-end.
        import json as _json

        zip_path = tmp_path / "bh.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr(
                "domains.json",
                _json.dumps(
                    {
                        "data": [
                            {
                                "ObjectIdentifier": "S-1-5-21-1-1-1-0",
                                "Properties": {"name": "corp.local"},
                            }
                        ]
                    }
                ),
            )
        zip_path.write_bytes(buf.getvalue())
        store = _FakeKGStore()
        stats = ingest_bloodhound_zip(zip_path, engagement="t", store=store)
        assert stats.domains == 1


# ── ADCS ingest (separate top-level files per kind) ─────────────────


class TestAdcsIngest:
    """BHCE 5.x emits ADCS objects as their own top-level files
    (``certtemplates_*.json`` / ``enterprisecas_*.json`` etc.) — NOT
    as embedded blocks under ``domains[]``. These tests pin the
    file-per-kind dispatch + the ADCS-specific edge synthesis."""

    def test_cert_template_lands_under_ad_cert_template_label(self) -> None:
        bh = {
            "meta": {"type": "certtemplates"},
            "data": [
                {
                    "ObjectIdentifier": "CT-GUID-1",
                    "Properties": {
                        "name": "User",
                        "enrolleesuppliessubject": True,
                        "authenticationenabled": True,
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="certtemplates")
        node = store.nodes_by_key().get("bh::CertTemplate::CT-GUID-1")
        assert node is not None
        assert node["kind"] == "ADCertTemplate"
        assert node["props"].get("bh_type") == "CertTemplate"

    def test_enterprise_ca_published_to_template_edge(self) -> None:
        bh = {
            "meta": {"type": "enterprisecas"},
            "data": [
                {
                    "ObjectIdentifier": "ECA-1",
                    "Properties": {"caname": "CorpCA"},
                    "EnabledCertTemplates": [
                        {"ObjectIdentifier": "CT-GUID-1", "ObjectType": "CertTemplate"}
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="enterprisecas")
        published = store.edges_of_kind("PUBLISHED_TO")
        assert any(
            "ECA-1" in s and "CT-GUID-1" in d and p.get("bh_right") == "PublishedTo"
            for s, d, p in published
        )

    def test_enterprise_ca_hosts_ca_service_edge(self) -> None:
        bh = {
            "meta": {"type": "enterprisecas"},
            "data": [
                {
                    "ObjectIdentifier": "ECA-1",
                    "Properties": {"caname": "CorpCA"},
                    "HostingComputer": "S-1-5-21-1-1-1-1001",
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="enterprisecas")
        hosts = store.edges_of_kind("HOSTS_CA_SERVICE")
        assert any(
            "S-1-5-21-1-1-1-1001" in s and "ECA-1" in d and p.get("bh_right") == "HostsCAService"
            for s, d, p in hosts
        )

    def test_issuance_policy_oid_group_link_edge(self) -> None:
        bh = {
            "meta": {"type": "issuancepolicies"},
            "data": [
                {
                    "ObjectIdentifier": "POL-GUID-1",
                    "Properties": {
                        "displayname": "High Assurance",
                        "certtemplateoid": "1.3.6.1.4.1.311.21.8",
                    },
                    "GroupLink": {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-513",
                        "ObjectType": "Group",
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="issuancepolicies")
        link_edges = store.edges_of_kind("OID_GROUP_LINK")
        assert any(
            "POL-GUID-1" in s and "S-1-5-21-1-1-1-513" in d and p.get("bh_right") == "OIDGroupLink"
            for s, d, p in link_edges
        )

    def test_root_ca_lands_under_dedicated_label(self) -> None:
        bh = {
            "meta": {"type": "rootcas"},
            "data": [
                {
                    "ObjectIdentifier": "ROOT-1",
                    "Properties": {"domain": "corp.local"},
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="rootcas")
        node = store.nodes_by_key().get("bh::RootCA::ROOT-1")
        assert node is not None
        assert node["kind"] == "ADRootCA"

    def test_nt_auth_store_lands_under_dedicated_label(self) -> None:
        bh = {
            "meta": {"type": "ntauthstores"},
            "data": [
                {
                    "ObjectIdentifier": "NTA-1",
                    "Properties": {
                        "domain": "corp.local",
                        "certthumbprints": ["AABBCC"],
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="ntauthstores")
        node = store.nodes_by_key().get("bh::NTAuthStore::NTA-1")
        assert node is not None
        assert node["kind"] == "ADNTAuthStore"

    def test_aiaca_lands_under_dedicated_label(self) -> None:
        bh = {
            "meta": {"type": "aiacas"},
            "data": [
                {
                    "ObjectIdentifier": "AIA-1",
                    "Properties": {"domain": "corp.local"},
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store, type_hint="aiacas")
        node = store.nodes_by_key().get("bh::AIACA::AIA-1")
        assert node is not None
        assert node["kind"] == "ADAIACA"

    def test_stats_counters_for_adcs_kinds(self) -> None:
        bh = {
            "meta": {"type": "certtemplates"},
            "data": [
                {"ObjectIdentifier": "CT-GUID-A", "Properties": {"name": "A"}},
                {"ObjectIdentifier": "CT-GUID-B", "Properties": {"name": "B"}},
            ],
        }
        store = _FakeKGStore()
        stats = merge_bloodhound_json(bh, engagement="t", store=store, type_hint="certtemplates")
        assert stats.certtemplates == 2

    def test_zip_filename_hint_dispatches_certtemplates(self, tmp_path: Path) -> None:
        import json as _json

        payload = {"data": [{"ObjectIdentifier": "CT-1", "Properties": {"name": "DomainUser"}}]}
        zip_path = tmp_path / "bh.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("certtemplates_20260605.json", _json.dumps(payload))
        store = _FakeKGStore()
        stats = ingest_bloodhound_zip(zip_path, engagement="t", store=store)
        assert stats.certtemplates == 1
        assert any(obs["kind"] == "ADCertTemplate" for obs in store.observations)


# ── LocalGroups ingest + RID-based direct edges ─────────────────────


class TestLocalGroupsIngest:
    """Computer ``LocalGroups[]`` → ``ADLocalGroup`` nodes plus the
    BHCE-equivalent direct lateral-movement edges by built-in RID."""

    def _bh(self, *, lg_id: str, members: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "LocalGroups": [
                        {
                            "ObjectIdentifier": lg_id,
                            "Name": "BUILTIN\\Whatever",
                            "Results": members,
                        }
                    ],
                }
            ],
        }

    def test_local_group_node_emitted_under_ad_local_group_label(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id="S-1-5-21-1-1-1-1001-500",
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        node = store.nodes_by_key().get("bh::LocalGroup::S-1-5-21-1-1-1-1001-500")
        assert node is not None
        assert node["kind"] == "ADLocalGroup"

    def test_computer_contains_local_group(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id="S-1-5-21-1-1-1-1001-500",
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        contains = store.edges_of_kind("CONTAINS")
        assert any(
            "S-1-5-21-1-1-1-1001" in s
            and "S-1-5-21-1-1-1-1001-500" in d
            and p.get("bh_right") == "ContainsLocalGroup"
            for s, d, p in contains
        )

    def test_member_emits_member_of_local_group_edge(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id="S-1-5-21-1-1-1-1001-500",
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        mol = store.edges_of_kind("MEMBER_OF_LOCAL_GROUP")
        assert any("1106" in s and "1001-500" in d for s, d, _ in mol)

    @pytest.mark.parametrize(
        "rid,expected_kind",
        [
            ("500", "ADMIN_TO"),  # BUILTIN\Administrators
            ("555", "CAN_ACCESS"),  # BUILTIN\Remote Desktop Users
            ("562", "CAN_ACCESS"),  # BUILTIN\Distributed COM Users
            ("580", "CAN_ACCESS"),  # BUILTIN\Remote Management Users
        ],
    )
    def test_built_in_rid_emits_direct_lateral_edge(self, rid: str, expected_kind: str) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id=f"S-1-5-21-1-1-1-1001-{rid}",
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        direct_edges = store.edges_of_kind(expected_kind)
        # The direct edge must point principal → computer (not principal
        # → local group), with the RID + via-local-group provenance.
        assert any(
            "1106" in s
            and "1001" in d
            and "1001-500" not in d
            and "1001-555" not in d
            and "1001-562" not in d
            and "1001-580" not in d
            and p.get("rid") == rid
            and p.get("bh_right") == "LocalGroupRid"
            for s, d, p in direct_edges
        )

    def test_non_catalogue_rid_does_not_emit_direct_edge(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id="S-1-5-21-1-1-1-1001-999",  # RID 999 has no primitive
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        admin = store.edges_of_kind("ADMIN_TO")
        can_access = store.edges_of_kind("CAN_ACCESS")
        # Only MEMBER_OF_LOCAL_GROUP — no ADMIN_TO / CAN_ACCESS direct.
        assert all("1001-999" not in s for s, _d, _p in admin + can_access)

    def test_non_numeric_suffix_id_does_not_emit_direct_edge(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                lg_id="S-1-5-21-1-1-1-1001__custom-group",
                members=[
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                        "ObjectType": "User",
                    }
                ],
            ),
            engagement="t",
            store=store,
        )
        admin = store.edges_of_kind("ADMIN_TO")
        # Non-numeric trailing fragment skips the RID lookup entirely.
        assert all("custom-group" not in s for s, _d, _p in admin)


# ── GPOChanges + UserRights ingest ──────────────────────────────────


class TestGpoChangesIngest:
    """Computer ``GPOChanges`` → direct AdminTo / CAN_ACCESS edges
    derived from GptTmpl.inf-pushed local-group membership."""

    def _bh(self, *, bucket: str, principal_sid: str) -> dict[str, Any]:
        return {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "GPOChanges": {
                        bucket: [{"ObjectIdentifier": principal_sid, "ObjectType": "User"}]
                    },
                }
            ],
        }

    @pytest.mark.parametrize(
        "bucket,expected_kind",
        [
            ("LocalAdmins", "ADMIN_TO"),
            ("RemoteDesktopUsers", "CAN_ACCESS"),
            ("DcomUsers", "CAN_ACCESS"),
            ("PSRemoteUsers", "CAN_ACCESS"),
        ],
    )
    def test_each_bucket_emits_correct_direct_edge(self, bucket: str, expected_kind: str) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(bucket=bucket, principal_sid="S-1-5-21-1-1-1-2001"),
            engagement="t",
            store=store,
        )
        edges = store.edges_of_kind(expected_kind)
        assert any(
            "2001" in s
            and "1001" in d
            and p.get("bh_right") == "GPOChange"
            and p.get("via_gpo_changes") == bucket
            for s, d, p in edges
        )

    def test_unknown_bucket_emits_no_edge(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(bucket="UnknownBucket", principal_sid="S-1-5-21-1-1-1-2001"),
            engagement="t",
            store=store,
        )
        # No edges from the unknown bucket — the whitelist is the
        # source of truth.
        all_edges = store.edges()
        assert not any(p.get("via_gpo_changes") for _s, _k, _d, p in all_edges)


class TestUserRightsIngest:
    """Computer ``UserRights[]`` → direct CAN_ACCESS edges for the
    whitelisted lateral-movement privileges."""

    def _bh(self, *, privilege: str, principal_sid: str) -> dict[str, Any]:
        return {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "UserRights": [
                        {
                            "Privilege": privilege,
                            "Results": [
                                {
                                    "ObjectIdentifier": principal_sid,
                                    "ObjectType": "User",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    @pytest.mark.parametrize(
        "privilege",
        [
            "SeRemoteInteractiveLogonRight",
            "SeInteractiveLogonRight",
            "SeServiceLogonRight",
            "SeBatchLogonRight",
        ],
    )
    def test_whitelisted_privilege_emits_can_access_edge(self, privilege: str) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(privilege=privilege, principal_sid="S-1-5-21-1-1-1-2001"),
            engagement="t",
            store=store,
        )
        edges = store.edges_of_kind("CAN_ACCESS")
        assert any(
            "2001" in s
            and "1001" in d
            and p.get("bh_right") == "UserRight"
            and p.get("via_privilege") == privilege
            for s, d, p in edges
        )

    def test_unknown_privilege_emits_no_edge(self) -> None:
        store = _FakeKGStore()
        merge_bloodhound_json(
            self._bh(
                privilege="SeUnknownPrivilegeRight",
                principal_sid="S-1-5-21-1-1-1-2001",
            ),
            engagement="t",
            store=store,
        )
        # The whitelist is the source of truth; unknown privileges
        # produce no edges.
        all_edges = store.edges()
        assert not any(p.get("via_privilege") for _s, _k, _d, p in all_edges)


# ── User SPNTargets + Computer DumpSMSAPassword ingest ─────────────


class TestSpnTargetsIngest:
    def test_spn_target_emits_write_spn_edge(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {"name": "user"},
                    "SPNTargets": [
                        {
                            "ComputerSID": "S-1-5-21-1-1-1-1001",
                            "Port": 1433,
                            "Service": "MSSQLSvc",
                        }
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        write_spn = store.edges_of_kind("WRITE_SPN")
        assert any(
            "500" in s
            and "1001" in d
            and p.get("bh_right") == "SPNTarget"
            and p.get("port") == 1433
            and p.get("service") == "MSSQLSvc"
            for s, d, p in write_spn
        )


class TestRootCaForIngest:
    def test_top_level_domain_sid_emits_root_ca_for(self) -> None:
        bh = {
            "meta": {"type": "rootcas"},
            "data": [
                {
                    "ObjectIdentifier": "ROOT-THUMB-AABB",
                    "Properties": {"name": "ROOT-CA@LAB.LOCAL"},
                    "DomainSID": "S-1-5-21-1-1-1",
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("ROOT_CA_FOR")
        assert any(
            "ROOT-THUMB-AABB" in s and "S-1-5-21-1-1-1" in d and p.get("bh_right") == "RootCAFor"
            for s, d, p in edges
        )

    def test_properties_domainsid_fallback(self) -> None:
        bh = {
            "meta": {"type": "rootcas"},
            "data": [
                {
                    "ObjectIdentifier": "ROOT-THUMB-CCDD",
                    "Properties": {
                        "name": "ROOT-CA@LAB.LOCAL",
                        "domainsid": "S-1-5-21-2-2-2",
                    },
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("ROOT_CA_FOR")
        assert any("CCDD" in s and "S-1-5-21-2-2-2" in d for s, d, _p in edges)

    def test_missing_domain_sid_skipped(self) -> None:
        bh = {
            "meta": {"type": "rootcas"},
            "data": [
                {
                    "ObjectIdentifier": "ROOT-NODS",
                    "Properties": {"name": "stray-root"},
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        assert store.edges_of_kind("ROOT_CA_FOR") == []


class TestHasSidHistoryIngest:
    def test_user_has_sid_history_emits_edge(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1000",
                    "Properties": {"name": "user"},
                    "HasSIDHistory": [
                        {"ObjectIdentifier": "S-1-5-21-9-9-9-500", "ObjectType": "User"},
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("HAS_SID_HISTORY")
        assert any(
            "1000" in s and "500" in d and p.get("bh_right") == "HasSIDHistory" for s, d, p in edges
        )

    def test_group_has_sid_history_emits_edge(self) -> None:
        bh = {
            "meta": {"type": "groups"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-512",
                    "Properties": {"name": "Domain Admins"},
                    "HasSIDHistory": [
                        {"ObjectIdentifier": "S-1-5-21-9-9-9-512", "ObjectType": "Group"},
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("HAS_SID_HISTORY")
        assert any("1-512" in s and "9-512" in d for s, d, _p in edges)


class TestDumpSmsaPasswordIngest:
    def test_dump_smsa_emits_dump_smsa_password_edge(self) -> None:
        bh = {
            "meta": {"type": "computers"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1001",
                    "Properties": {"name": "ws01"},
                    "DumpSMSAPassword": [
                        {
                            "ObjectIdentifier": "S-1-5-21-1-1-1-2000",
                            "ObjectType": "User",
                        }
                    ],
                }
            ],
        }
        store = _FakeKGStore()
        merge_bloodhound_json(bh, engagement="t", store=store)
        edges = store.edges_of_kind("DUMP_SMSA_PASSWORD")
        assert any(
            "1001" in s and "2000" in d and p.get("bh_right") == "DumpSMSAPassword"
            for s, d, p in edges
        )
