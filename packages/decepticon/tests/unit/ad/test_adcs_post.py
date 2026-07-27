"""KGStore-mock-based tests for ``tools.ad.adcs_post``.

The synthesis runs as raw Cypher inside ``KGStore.execute_write``, so
the unit tests verify the **shape of the calls** (engagement scoping,
provenance threading, query content) — full algorithmic correctness
is covered by the live dogfood against compose Neo4j (the
post-process is fundamentally a graph traversal, not pure Python).
"""

from __future__ import annotations

from typing import Any

from decepticon.tools.ad.adcs_post import (
    PostProcessStats,
    synthesise_adcs_post,
)


class _FakeKGStore:
    """Captures every ``execute_write`` call so tests can inspect the
    queries and parameter shape."""

    def __init__(
        self,
        *,
        dcsync_created: int = 1,
        golden_created: int = 1,
        esc1_created: int = 1,
        esc3_created: int = 1,
        esc4_created: int = 1,
        esc6a_created: int = 1,
        esc6b_created: int = 1,
        esc9a_created: int = 1,
        esc9b_created: int = 1,
        esc13_created: int = 1,
        trusted_for_ntauth_created: int = 1,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []
        self._dcsync_created = dcsync_created
        self._golden_created = golden_created
        self._esc1_created = esc1_created
        self._esc3_created = esc3_created
        self._esc4_created = esc4_created
        self._esc6a_created = esc6a_created
        self._esc6b_created = esc6b_created
        self._esc9a_created = esc9a_created
        self._esc9b_created = esc9b_created
        self._esc13_created = esc13_created
        self._trusted_for_ntauth_created = trusted_for_ntauth_created
        self.closed = False

    def execute_write(
        self, query: str, params: dict[str, Any], *, engagement: str
    ) -> list[dict[str, Any]]:
        self.calls.append((query, dict(params), engagement))
        # Each algorithm is identifiable by a distinctive substring in
        # its MATCH pattern. Check the more-specific ESC* markers
        # before falling back to the broader GoldenCert one so the
        # ``OWNS_LIMITED_RIGHTS`` substring used in ESC4 doesn't trip
        # the wrong return value.
        if "TRUSTED_FOR_NTAUTH" in query:
            return [{"created": self._trusted_for_ntauth_created}]
        if "ADCS_ESC13" in query:
            return [{"created": self._esc13_created}]
        if "ADCS_ESC6A" in query:
            return [{"created": self._esc6a_created}]
        if "ADCS_ESC6B" in query:
            return [{"created": self._esc6b_created}]
        if "ADCS_ESC9A" in query:
            return [{"created": self._esc9a_created}]
        if "ADCS_ESC9B" in query:
            return [{"created": self._esc9b_created}]
        if "ADCS_ESC3" in query:
            return [{"created": self._esc3_created}]
        if "ADCS_ESC4" in query:
            return [{"created": self._esc4_created}]
        if "ADCS_ESC1" in query:
            return [{"created": self._esc1_created}]
        if "GET_CHANGES" in query:
            return [{"created": self._dcsync_created}]
        if "OWNS|WRITE_OWNER|MANAGE_CA" in query:
            return [{"created": self._golden_created}]
        return []

    def close(self) -> None:
        self.closed = True


# ── Public signature contracts ─────────────────────────────────────


class TestPublicSignatures:
    def test_returns_post_process_stats(self) -> None:
        store = _FakeKGStore()
        result = synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        assert isinstance(result, PostProcessStats)

    def test_stats_carry_counts_from_each_query(self) -> None:
        store = _FakeKGStore(
            dcsync_created=3,
            golden_created=2,
            esc1_created=4,
            esc3_created=11,
            esc4_created=5,
            esc6a_created=8,
            esc6b_created=9,
            esc9a_created=6,
            esc9b_created=7,
            esc13_created=10,
            trusted_for_ntauth_created=12,
        )
        stats = synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        assert stats.dcsync == 3
        assert stats.golden_cert == 2
        assert stats.adcs_esc1 == 4
        assert stats.adcs_esc3 == 11
        assert stats.adcs_esc4 == 5
        assert stats.adcs_esc6a == 8
        assert stats.adcs_esc6b == 9
        assert stats.adcs_esc9a == 6
        assert stats.adcs_esc9b == 7
        assert stats.adcs_esc13 == 10
        assert stats.trusted_for_ntauth == 12

    def test_provenance_threaded_into_every_call(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t-eng",
            store=store,  # type: ignore[arg-type]
            source_episode_id="ep-x",
            created_by="adcs_post_test",
        )
        assert len(store.calls) == 11
        for _query, params, engagement in store.calls:
            assert engagement == "t-eng"
            assert params["engagement"] == "t-eng"
            assert params["created_by"] == "adcs_post_test"
            assert params["source_episode_id"] == "ep-x"

    def test_caller_supplied_store_not_closed(self) -> None:
        """When a caller passes ``store=``, the post-process must NOT
        close it on return — caller owns the lifetime."""
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        assert store.closed is False


# ── DCSync algorithm ───────────────────────────────────────────────


class TestDcsyncQuery:
    def _dcsync_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "DCSYNC" in q:
                return q
        raise AssertionError("DCSync query not issued")

    def test_dcsync_query_requires_both_get_changes_edges(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._dcsync_query(store)
        # Both rights must MATCH on the same (principal, domain) pair.
        assert ":GET_CHANGES" in q
        assert ":GET_CHANGES_ALL" in q

    def test_dcsync_query_scopes_match_to_engagement(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._dcsync_query(store)
        assert q.count("engagement: $engagement") >= 3  # 2 raw + 1 merged

    def test_dcsync_query_uses_jc_marker_for_idempotent_count(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._dcsync_query(store)
        # The ``_jc`` marker pattern is what makes the run-2 stats
        # truthfully zero. ``count(r)`` would always return ≥ 1 after
        # the first run.
        assert "_jc" in q
        assert "ON CREATE SET" in q and "ON MATCH SET" in q


# ── GoldenCert algorithm ───────────────────────────────────────────


class TestGoldenCertQuery:
    def _golden_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "GOLDEN_CERT" in q:
                return q
        raise AssertionError("GoldenCert query not issued")

    def test_golden_cert_requires_owns_writeowner_or_manageca_on_enterprise_ca(
        self,
    ) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._golden_query(store)
        # The alternation covers the three rights BHCE promotes to
        # GoldenCert.
        assert ":OWNS|WRITE_OWNER|MANAGE_CA" in q
        # Target must be an EnterpriseCA, not an arbitrary node.
        assert ":ADEnterpriseCA" in q

    def test_golden_cert_query_deduplicates_via_distinct(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._golden_query(store)
        # Without ``WITH DISTINCT``, a principal with multiple rights
        # on the same CA would mint extra GoldenCert edges.
        assert "WITH DISTINCT" in q

    def test_golden_cert_query_uses_jc_marker_for_idempotent_count(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._golden_query(store)
        assert "_jc" in q
        assert "ON CREATE SET" in q and "ON MATCH SET" in q


# ── ADCS ESC1 algorithm ─────────────────────────────────────────────


class TestAdcsEsc1Query:
    def _esc1_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC1" in q:
                return q
        raise AssertionError("ADCS_ESC1 query not issued")

    def test_template_conditions_required(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc1_query(store)
        # The core ESC1 template predicates.
        assert "ct.authenticationenabled = true" in q
        assert "ct.enrolleesuppliessubject = true" in q
        assert "ct.requiresmanagerapproval" in q  # checked via coalesce

    def test_enroll_edge_required_via_bh_right(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc1_query(store)
        # Enroll matches on the ``bh_right`` ACE prop rather than a
        # dedicated edge type — the ingest writes the ACE under the
        # generic ENABLES fallback so we match on the prop.
        assert "bh_right = 'Enroll'" in q

    def test_published_to_required(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc1_query(store)
        # EnterpriseCA must publish the vulnerable template.
        assert ":PUBLISHED_TO" in q
        assert ":ADEnterpriseCA" in q

    def test_query_uses_jc_marker_for_idempotent_count(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc1_query(store)
        assert "_jc" in q
        assert "ON CREATE SET" in q and "ON MATCH SET" in q

    def test_via_template_provenance_attached(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc1_query(store)
        # The vulnerable template's key is preserved on the ESC1 edge
        # so an analyst can trace the path back without re-running the
        # algorithm.
        assert "via_template" in q


# ── ADCS ESC3 algorithm ─────────────────────────────────────────────


class TestAdcsEsc3Query:
    def _esc3_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC3" in q:
                return q
        raise AssertionError("ESC3 query not issued")

    def test_agent_template_filter_on_certificate_request_agent_oid(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc3_query(store)
        # ESC3 requires the agent template's applicationpolicies to
        # include the Certificate Request Agent EKU OID.
        assert "1.3.6.1.4.1.311.20.2.1" in q
        assert "agent.applicationpolicies" in q

    def test_auth_template_filter(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc3_query(store)
        # The chained authentication target template must be auth-
        # enabled and manager-approval-free.
        assert "auth.authenticationenabled = true" in q
        assert "auth.requiresmanagerapproval" in q

    def test_both_templates_published_by_same_ca(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc3_query(store)
        # Both PUBLISHED_TO matches must land — the same CA publishes
        # both the agent and auth templates.
        assert q.count(":PUBLISHED_TO") == 2

    def test_enroll_required_on_agent_template(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc3_query(store)
        # Enroll right is required on the **agent** template — that's
        # the one the principal uses to mint enrolment-agent certs.
        # The principal node carries the scope too, so assert the shape
        # rather than one exact rendering of it.
        assert "-[en {engagement: $engagement}]->(agent)" in q
        assert "(p {engagement: $engagement})" in q
        assert "bh_right = 'Enroll'" in q

    def test_via_template_provenance_attached(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc3_query(store)
        # Both template keys land on the synthesised edge so analysts
        # can re-trace either side of the chain.
        assert "via_agent_template" in q
        assert "via_auth_template" in q


# ── ADCS ESC4 algorithm ─────────────────────────────────────────────


class TestAdcsEsc4Query:
    def _esc4_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC4" in q:
                return q
        raise AssertionError("ADCS_ESC4 query not issued")

    def test_writable_ace_alternation(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc4_query(store)
        # All five "writable on the template" rights must be in the
        # alternation, plus the OwnsLimitedRights / WriteOwnerLimitedRights
        # raw forms that BHCE post-process otherwise promotes.
        for kind in (
            "GENERIC_ALL",
            "GENERIC_WRITE",
            "WRITE_DACL",
            "WRITE_OWNER",
            "OWNS",
            "OWNS_LIMITED_RIGHTS",
            "WRITE_OWNER_LIMITED_RIGHTS",
        ):
            assert kind in q

    def test_published_to_required(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc4_query(store)
        assert ":PUBLISHED_TO" in q
        assert ":ADEnterpriseCA" in q
        assert ":ADCertTemplate" in q

    def test_via_template_provenance(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc4_query(store)
        assert "via_template" in q


# ── ADCS ESC6a / ESC6b algorithms ──────────────────────────────────


class TestAdcsEsc6Queries:
    def _esc6_queries(self, store: _FakeKGStore) -> tuple[str, str]:
        esc6a, esc6b = None, None
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC6A" in q:
                esc6a = q
            elif "ADCS_ESC6B" in q:
                esc6b = q
        if esc6a is None or esc6b is None:
            raise AssertionError("ESC6a or ESC6b query missing")
        return esc6a, esc6b

    def test_both_variants_require_is_user_specifies_san_enabled(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc6a, esc6b = self._esc6_queries(store)
        # ``EDITF_ATTRIBUTESUBJECTALTNAME2`` surfaces as this CA prop.
        assert "eca.isuserspecifiessanenabled = true" in esc6a
        assert "eca.isuserspecifiessanenabled = true" in esc6b

    def test_esc6b_requires_no_security_extension(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        _, esc6b = self._esc6_queries(store)
        # ESC6b is strictly broader: no security-extension fallback.
        assert "ct.nosecurityextension = true" in esc6b

    def test_esc6a_does_not_filter_on_no_security_extension(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc6a, _ = self._esc6_queries(store)
        # ESC6a matches authentication-enabled templates with or
        # without the security extension.
        assert "ct.nosecurityextension" not in esc6a

    def test_both_variants_require_enroll_via_bh_right(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc6a, esc6b = self._esc6_queries(store)
        assert "bh_right = 'Enroll'" in esc6a
        assert "bh_right = 'Enroll'" in esc6b


# ── TrustedForNTAuth algorithm ─────────────────────────────────────


class TestTrustedForNTAuthQuery:
    def _query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "TRUSTED_FOR_NTAUTH" in q:
                return q
        raise AssertionError("TRUSTED_FOR_NTAUTH query not issued")

    def test_matches_enterprise_ca_and_nt_auth_store(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._query(store)
        assert ":ADEnterpriseCA" in q
        assert ":ADNTAuthStore" in q

    def test_thumbprint_membership_check(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._query(store)
        # The CA's single thumbprint must be IN the store's list.
        assert "eca.certthumbprint IN nta.certthumbprints" in q
        # Both sides null-checked so a partial-ingest doesn't pair
        # unrelated nodes via NULL = NULL.
        assert "eca.certthumbprint IS NOT NULL" in q
        assert "nta.certthumbprints IS NOT NULL" in q

    def test_thumbprint_carried_as_provenance(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._query(store)
        # The matching thumbprint lands on the edge so analysts can
        # confirm which key actually closed the trust path.
        assert "via_thumbprint" in q
        assert "eca.certthumbprint" in q

    def test_query_uses_jc_marker_for_idempotent_count(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._query(store)
        assert "_jc" in q
        assert "ON CREATE SET" in q and "ON MATCH SET" in q


# ── ADCS ESC13 algorithm ───────────────────────────────────────────


class TestAdcsEsc13Query:
    def _esc13_query(self, store: _FakeKGStore) -> str:
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC13" in q:
                return q
        raise AssertionError("ESC13 query not issued")

    def test_template_must_have_issuancepolicies(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc13_query(store)
        # The OID-list field must be present (a null check) and the
        # IssuancePolicy's OID must be contained in it.
        assert "ct.issuancepolicies IS NOT NULL" in q
        assert "pol.certtemplateoid IN ct.issuancepolicies" in q

    def test_requires_oid_group_link_to_target_group(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc13_query(store)
        # The IssuancePolicy must publish an ``OID_GROUP_LINK`` edge
        # to the group whose membership is implicit on enrol.
        assert ":OID_GROUP_LINK" in q
        assert ":ADIssuancePolicy" in q

    def test_requires_enroll_via_bh_right(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc13_query(store)
        assert "bh_right = 'Enroll'" in q

    def test_via_template_and_via_policy_provenance(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        q = self._esc13_query(store)
        # ESC13 carries both the vulnerable template and the abused
        # policy on the edge so analysts can trace either side.
        assert "via_template" in q
        assert "via_policy" in q


# ── ADCS ESC9a / ESC9b algorithms ──────────────────────────────────


class TestAdcsEsc9Queries:
    def _esc9_queries(self, store: _FakeKGStore) -> tuple[str, str]:
        esc9a, esc9b = None, None
        for q, _params, _engagement in store.calls:
            if "ADCS_ESC9A" in q:
                esc9a = q
            elif "ADCS_ESC9B" in q:
                esc9b = q
        if esc9a is None or esc9b is None:
            raise AssertionError("ESC9a or ESC9b query missing")
        return esc9a, esc9b

    def test_both_variants_require_no_security_extension(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc9a, esc9b = self._esc9_queries(store)
        assert "ct.nosecurityextension = true" in esc9a
        assert "ct.nosecurityextension = true" in esc9b

    def test_esc9a_branches_on_subjectaltrequireupn(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc9a, _ = self._esc9_queries(store)
        assert "ct.subjectaltrequireupn = true" in esc9a
        # ESC9a must NOT trigger on DNS-only templates.
        assert "subjectaltrequiredns" not in esc9a

    def test_esc9b_branches_on_subjectaltrequiredns(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        _, esc9b = self._esc9_queries(store)
        assert "ct.subjectaltrequiredns = true" in esc9b
        assert "subjectaltrequireupn" not in esc9b

    def test_both_variants_require_enroll_via_bh_right(self) -> None:
        store = _FakeKGStore()
        synthesise_adcs_post(
            engagement="t",
            store=store,  # type: ignore[arg-type]
        )
        esc9a, esc9b = self._esc9_queries(store)
        assert "bh_right = 'Enroll'" in esc9a
        assert "bh_right = 'Enroll'" in esc9b


# ── Default-store path ─────────────────────────────────────────────


class TestDefaultStorePath:
    def test_omitting_store_constructs_from_env(self, monkeypatch) -> None:
        """When the caller omits ``store=``, the helper builds a
        ``KGStore`` via ``from_env`` and closes it before return."""
        constructed: list[_FakeKGStore] = []

        def _fake_from_env() -> _FakeKGStore:  # type: ignore[override]
            s = _FakeKGStore()
            constructed.append(s)
            return s

        monkeypatch.setattr(
            "decepticon.tools.ad.adcs_post.KGStore.from_env",
            staticmethod(_fake_from_env),
        )

        synthesise_adcs_post(engagement="t")
        assert len(constructed) == 1
        assert constructed[0].closed is True
