"""ADCS post-process — BHCE-server-equivalent edge synthesis.

BloodHound CE's server walks the ingested raw graph and synthesises
the high-signal attack edges (``DCSync``, ``GoldenCert``,
``ADCS_ESC1`` … ``ESC13``, etc.) that chain planners actually
reason about. The Decepticon ingest in ``bloodhound.py`` only writes
the raw collector data; this module is where the synthesis runs.

Scope of this first cut (intentionally narrow — see the BloodHound
RFC §4.3 for the full plan):

  - **``DCSync``**: A principal that holds both ``GET_CHANGES`` and
    ``GET_CHANGES_ALL`` on a Domain has effective DCSync rights.
    BHCE collapses the pair into a single ``DCSync`` edge per
    (principal, domain) pair.
  - **``GoldenCert``**: A principal that holds ``OWNS`` /
    ``WRITE_OWNER`` / ``MANAGE_CA`` on an EnterpriseCA can issue
    arbitrary certificates as that CA — a forged-trust-anchor
    primitive. We mint one ``GoldenCert`` edge per principal +
    EnterpriseCA pair.

ESC1/3/4/6a/6b/9a/9b/10a/10b/13 require Enroll edges (raw ACE
right-name) that the current ingest does not yet emit — they land
in a dedicated follow-up PR alongside Enroll ingest.

The synthesis is **idempotent**: each ``MERGE`` keys on the
(principal, target) pair so re-running the post-process produces no
extra edges. Each new edge carries ``post_process_source`` props so
analysts can distinguish synthesised edges from raw ACE data.
"""

from __future__ import annotations

from dataclasses import dataclass

from decepticon.middleware.kg_internal.store import KGStore


@dataclass
class PostProcessStats:
    """Counts of edges created per algorithm. Re-runs return zero for
    every value because each ``MERGE`` is idempotent."""

    dcsync: int = 0
    golden_cert: int = 0
    adcs_esc1: int = 0
    adcs_esc3: int = 0
    adcs_esc4: int = 0
    adcs_esc6a: int = 0
    adcs_esc6b: int = 0
    adcs_esc9a: int = 0
    adcs_esc9b: int = 0
    adcs_esc13: int = 0
    trusted_for_ntauth: int = 0

    def to_dict(self) -> dict[str, int]:
        return self.__dict__


# Cypher templates — kept short + auditable so the algorithm is
# obvious to reviewers without hunting through string concatenation.

# ``r._jc`` is a transient marker the MERGE writes on the create path
# and clears on the match path; counting it gives the true new-edge
# count. ``count(r)`` instead returns the total ``MATCH``ed count
# (always ≥ 1 after the first run) and breaks idempotency reporting.
# Same trick the node-write path in ``record_observations`` uses.

_DCSYNC_QUERY = (
    "MATCH (p {engagement: $engagement})-[gc:GET_CHANGES {engagement: $engagement}]->(d:Domain {engagement: $engagement}) "
    "MATCH (p {engagement: $engagement})-[gca:GET_CHANGES_ALL {engagement: $engagement}]->(d) "
    "MERGE (p)-[r:DCSYNC {engagement: $engagement}]->(d) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'GetChanges+GetChangesAll', "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)

_GOLDEN_CERT_QUERY = (
    "MATCH (p {engagement: $engagement})-[r:OWNS|WRITE_OWNER|MANAGE_CA {engagement: $engagement}]->"
    "(ca:ADEnterpriseCA {engagement: $engagement}) "
    "WITH DISTINCT p, ca "
    "MERGE (p)-[gc:GOLDEN_CERT {engagement: $engagement}]->(ca) "
    "ON CREATE SET gc.firstseen = $now, "
    "              gc.created_by = $created_by, "
    "              gc.source_episode_id = $source_episode_id, "
    "              gc.post_process_source = 'Owns|WriteOwner|ManageCA on EnterpriseCA', "
    "              gc._jc = true "
    "ON MATCH SET gc._jc = false "
    "SET gc.lastupdated = $now "
    "WITH gc, gc._jc AS just_created "
    "REMOVE gc._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


# ADCS ESC1 — minimum-viable variant.
#
# BHCE's full ESC1 algorithm also requires the EnterpriseCA to chain
# to an NTAuthStore via ``TRUSTED_FOR_NTAUTH``, but we don't emit
# that edge yet (NTAuthStore.certthumbprints + EnterpriseCA cert chain
# matching is a follow-up). For now we accept any EnterpriseCA that
# publishes the vulnerable template — false-positives are unlikely
# in a real engagement because raw collector output won't include
# an unrelated CA in the same domain.
#
# Template conditions (per
# https://bloodhound.specterops.io/resources/edges/adcs-esc1):
#   - authenticationenabled = true
#   - enrolleesuppliessubject = true   (the core ESC1 primitive)
#   - requiresmanagerapproval = false  (default false when missing)
#
# Edge requirements:
#   - principal -[bh_right='Enroll']-> CertTemplate (raw ACE)
#   - EnterpriseCA -[:PUBLISHED_TO]-> CertTemplate
#
# Result: principal --ADCS_ESC1--> EnterpriseCA, dedup'd via DISTINCT
# so a principal with multiple matching templates on the same CA
# doesn't mint extra edges.

_ADCS_ESC1_QUERY = (
    "MATCH (ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND ct.enrolleesuppliessubject = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(ct) "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[r:ADCS_ESC1 {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC1: vulnerable template + Enroll + PublishedTo', "
    "              r.via_template = ct.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


# ADCS ESC3 — Certificate Request Agent / Enroll Agent abuse.
#
# A principal who can enrol an *agent template* (one whose
# ``applicationpolicies`` includes the Certificate Request Agent OID
# ``1.3.6.1.4.1.311.20.2.1``) can use the issued cert to enrol for
# any *auth template* (one with ``authenticationenabled = true``)
# **on behalf of** any AD principal. That gives them an
# impersonation primitive against the CA's authentication surface.
#
# Pre-requisites in the raw graph:
#   - Agent template (``agent``): the Certificate Request Agent OID
#     is in its ``applicationpolicies`` list.
#   - Auth template (``auth``): authentication-enabled + manager
#     approval off.
#   - The same EnterpriseCA publishes both templates.
#   - Principal holds ``Enroll`` on the agent template.
#
# Edge: principal --ADCS_ESC3--> EnterpriseCA. Provenance attaches
# both template keys.
#
# Simplification vs BHCE: the upstream algorithm additionally checks
# ``hasenrollmentagentrestrictions = false`` on the EnterpriseCA
# (without restrictions, any enrolment-agent cert holder can act as
# anyone). We don't ingest that flag yet, so the check is implicit
# — the false-positive risk is low because enrolment-agent
# restrictions are typically set for high-value CAs only and any
# such restrictions land as a CA-level filter we can add when
# ``CARegistryData`` ingest support arrives.

_ADCS_ESC3_QUERY = (
    "MATCH (auth:ADCertTemplate {engagement: $engagement}) "
    "WHERE auth.authenticationenabled = true "
    "  AND coalesce(auth.requiresmanagerapproval, false) = false "
    "MATCH (agent:ADCertTemplate {engagement: $engagement}) "
    "WHERE '1.3.6.1.4.1.311.20.2.1' IN agent.applicationpolicies "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(auth) "
    "MATCH (eca)-[:PUBLISHED_TO {engagement: $engagement}]->(agent) "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(agent) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, auth, agent "
    "MERGE (p)-[r:ADCS_ESC3 {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC3: Enrollment Agent template + auth template + Enroll', "
    "              r.via_agent_template = agent.key, "
    "              r.via_auth_template = auth.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


# ADCS ESC4 — vulnerable ACL on a published CertTemplate.
#
# A principal that holds ``OWNS`` / ``WRITE_OWNER`` / ``WRITE_DACL``
# / ``GENERIC_ALL`` / ``GENERIC_WRITE`` (or their limited-rights raw
# counterparts) on a CertTemplate that is published by an
# EnterpriseCA can rewrite the template's flags (enrolleesuppliessubject,
# authenticationenabled, ...) and then enrol — effectively a write-
# then-ESC1 primitive.
#
# We dedup via DISTINCT so a principal with multiple writable rights
# on the same template doesn't mint extras. The template's key lands
# on the edge as ``via_template`` provenance.

_ADCS_ESC4_QUERY = (
    "MATCH (p {engagement: $engagement})-[r:GENERIC_ALL|GENERIC_WRITE|WRITE_DACL|WRITE_OWNER|OWNS"
    "|OWNS_LIMITED_RIGHTS|WRITE_OWNER_LIMITED_RIGHTS {engagement: $engagement}]->"
    "(ct:ADCertTemplate {engagement: $engagement}) "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(ct) "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[e:ADCS_ESC4 {engagement: $engagement}]->(eca) "
    "ON CREATE SET e.firstseen = $now, "
    "              e.created_by = $created_by, "
    "              e.source_episode_id = $source_episode_id, "
    "              e.post_process_source = 'ESC4: writable ACL on PublishedTo CertTemplate', "
    "              e.via_template = ct.key, "
    "              e._jc = true "
    "ON MATCH SET e._jc = false "
    "SET e.lastupdated = $now "
    "WITH e, e._jc AS just_created "
    "REMOVE e._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


# ADCS ESC9a / ESC9b — no security extension + subjectAlt user-controlled.
#
# When the CertTemplate has ``nosecurityextension = true`` and
# ``authenticationenabled = true``, the issued certificate's strong
# mapping to the AD account relies on a Subject Alternative Name.
# If the SAN is user-controllable (``subjectaltrequireupn = true``
# for ESC9a; ``subjectaltrequiredns = true`` for ESC9b) the enroller
# can impersonate any AD principal whose UPN / DNS they put on the
# SAN.
#
# Both variants also need raw Enroll rights + the template to be
# published by an EnterpriseCA.

# ADCS ESC6a / ESC6b — EDITF_ATTRIBUTESUBJECTALTNAME2 abuse.
#
# When an EnterpriseCA has the registry flag
# ``EDITF_ATTRIBUTESUBJECTALTNAME2`` set, callers can request any
# SAN they like in the CSR — which means an enroller who can issue
# any authentication-enabled template can impersonate any principal
# (UPN / DNS) via the SAN.
#
# BHCE exposes this as the ``isuserspecifiessanenabled`` property
# on the CA node. ESC6a and ESC6b only differ in whether the
# template also has the strong-mapping security extension stripped:
#
#   ESC6a: any authentication-enabled template, manager approval off
#   ESC6b: same but with ``nosecurityextension = true``
#
# ESC6b is rarer but strictly broader in impact (no cert-mapping
# fallback), so we synthesise both edges so chain planners can
# prioritise.

_ADCS_ESC6A_QUERY = (
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement}) "
    "WHERE eca.isuserspecifiessanenabled = true "
    "MATCH (eca)-[:PUBLISHED_TO {engagement: $engagement}]->(ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[r:ADCS_ESC6A {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC6a: SAN-enabled CA + AuthEnabled template + Enroll', "
    "              r.via_template = ct.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)

_ADCS_ESC6B_QUERY = (
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement}) "
    "WHERE eca.isuserspecifiessanenabled = true "
    "MATCH (eca)-[:PUBLISHED_TO {engagement: $engagement}]->(ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND ct.nosecurityextension = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[r:ADCS_ESC6B {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC6b: SAN-enabled CA + AuthEnabled + NoSecExt template + Enroll', "
    "              r.via_template = ct.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


_ADCS_ESC9A_QUERY = (
    "MATCH (ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND ct.nosecurityextension = true "
    "  AND ct.subjectaltrequireupn = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(ct) "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[r:ADCS_ESC9A {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC9a: no SecExt + UPN SAN + Enroll', "
    "              r.via_template = ct.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)

# ADCS ESC13 — OID-group-link abuse.
#
# When a CertTemplate's ``issuancepolicies`` field references the OID
# of an ``IssuancePolicy`` whose ``GroupLink`` points to a group,
# enrolling for that template implicitly grants membership in the
# target group for the duration of the issued cert. A principal who
# can enrol thus gains group membership without ever being added to
# the group itself.
#
# Edge: principal --ADCS_ESC13--> target group.
#
# Pre-requisites in the raw graph:
#   - CertTemplate is authentication-enabled, no manager approval.
#   - ``ct.issuancepolicies`` (list of OID strings) contains the
#     ``IssuancePolicy.certtemplateoid`` of some IssuancePolicy node.
#   - That IssuancePolicy has an ``OID_GROUP_LINK`` edge to the
#     target group.
#   - EnterpriseCA publishes the template.
#   - Principal has Enroll right on the template.

_ADCS_ESC13_QUERY = (
    "MATCH (ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "  AND ct.issuancepolicies IS NOT NULL "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(ct) "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "MATCH (pol:ADIssuancePolicy {engagement: $engagement}) "
    "WHERE pol.certtemplateoid IN ct.issuancepolicies "
    "MATCH (pol)-[:OID_GROUP_LINK {engagement: $engagement}]->"
    "(g {engagement: $engagement}) "
    "WITH DISTINCT p, g, ct, pol "
    "MERGE (p)-[r:ADCS_ESC13 {engagement: $engagement}]->(g) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC13: IssuancePolicy.GroupLink + Enroll on PublishedTo template', "
    "              r.via_template = ct.key, "
    "              r.via_policy = pol.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


_ADCS_ESC9B_QUERY = (
    "MATCH (ct:ADCertTemplate {engagement: $engagement}) "
    "WHERE ct.authenticationenabled = true "
    "  AND ct.nosecurityextension = true "
    "  AND ct.subjectaltrequiredns = true "
    "  AND coalesce(ct.requiresmanagerapproval, false) = false "
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement})-[:PUBLISHED_TO {engagement: $engagement}]->(ct) "
    "MATCH (p {engagement: $engagement})-[en {engagement: $engagement}]->(ct) "
    "WHERE en.bh_right = 'Enroll' "
    "WITH DISTINCT p, eca, ct "
    "MERGE (p)-[r:ADCS_ESC9B {engagement: $engagement}]->(eca) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'ESC9b: no SecExt + DNS SAN + Enroll', "
    "              r.via_template = ct.key, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


# ``TRUSTED_FOR_NTAUTH`` — pair every EnterpriseCA whose certificate
# thumbprint is listed in an NTAuthStore's ``certthumbprints`` with
# the matching store. BHCE uses this edge as the trust-anchor leg
# of every ESC* path; we synthesise it lazily here so future ESC
# refinements can stack a ``MATCH (eca)-[:TRUSTED_FOR_NTAUTH]->(:ADNTAuthStore)``
# precondition on top of the existing predicate without changing
# the ingest layer.
#
# BHCE simplification: the upstream algorithm also handles
# ``ADRootCA``/``ADAIACA`` chain validation via
# ``ROOT_CA_FOR`` / ``ISSUED_SIGNED_BY``. We only model the leaf
# ``ADEnterpriseCA`` cert here; intermediate-CA chain validation
# is the natural follow-up.

_TRUSTED_FOR_NTAUTH_QUERY = (
    "MATCH (eca:ADEnterpriseCA {engagement: $engagement}) "
    "WHERE eca.certthumbprint IS NOT NULL "
    "MATCH (nta:ADNTAuthStore {engagement: $engagement}) "
    "WHERE nta.certthumbprints IS NOT NULL "
    "  AND eca.certthumbprint IN nta.certthumbprints "
    "MERGE (eca)-[r:TRUSTED_FOR_NTAUTH {engagement: $engagement}]->(nta) "
    "ON CREATE SET r.firstseen = $now, "
    "              r.created_by = $created_by, "
    "              r.source_episode_id = $source_episode_id, "
    "              r.post_process_source = 'TrustedForNTAuth: thumbprint match', "
    "              r.via_thumbprint = eca.certthumbprint, "
    "              r._jc = true "
    "ON MATCH SET r._jc = false "
    "SET r.lastupdated = $now "
    "WITH r, r._jc AS just_created "
    "REMOVE r._jc "
    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created"
)


def synthesise_adcs_post(
    *,
    engagement: str,
    store: KGStore | None = None,
    source_episode_id: str = "adcs_post",
    created_by: str = "adcs_post",
) -> PostProcessStats:
    """Run every post-process synthesis algorithm in this module
    against ``engagement``.

    Args:
        engagement: Engagement label whose raw graph to walk.
        store: Optional pre-constructed ``KGStore`` for tests; defaults
            to ``KGStore.from_env()`` and is closed before return.
        source_episode_id: Provenance tag attached to every synthesised
            edge so analysts can distinguish post-process output from
            raw ACE data.
        created_by: ``created_by`` provenance prop (defaults to
            ``adcs_post`` so it sorts visibly next to ``bh_ingest``).

    Returns:
        :class:`PostProcessStats` with per-algorithm counts of edges
        the synthesis created **this run** (excluding ones that were
        already present and only re-touched).
    """
    import time

    now = int(time.time())
    owned_store = store is None
    target_store = store if store is not None else KGStore.from_env()

    stats = PostProcessStats()
    try:
        # DCSync
        rows = target_store.execute_write(
            _DCSYNC_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.dcsync = int(rows[0].get("created") or 0)

        # GoldenCert
        rows = target_store.execute_write(
            _GOLDEN_CERT_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.golden_cert = int(rows[0].get("created") or 0)

        # ADCS ESC1
        rows = target_store.execute_write(
            _ADCS_ESC1_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc1 = int(rows[0].get("created") or 0)

        # ADCS ESC3
        rows = target_store.execute_write(
            _ADCS_ESC3_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc3 = int(rows[0].get("created") or 0)

        # ADCS ESC4
        rows = target_store.execute_write(
            _ADCS_ESC4_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc4 = int(rows[0].get("created") or 0)

        # ADCS ESC6a
        rows = target_store.execute_write(
            _ADCS_ESC6A_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc6a = int(rows[0].get("created") or 0)

        # ADCS ESC6b
        rows = target_store.execute_write(
            _ADCS_ESC6B_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc6b = int(rows[0].get("created") or 0)

        # ADCS ESC9a
        rows = target_store.execute_write(
            _ADCS_ESC9A_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc9a = int(rows[0].get("created") or 0)

        # ADCS ESC9b
        rows = target_store.execute_write(
            _ADCS_ESC9B_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc9b = int(rows[0].get("created") or 0)

        # ADCS ESC13
        rows = target_store.execute_write(
            _ADCS_ESC13_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.adcs_esc13 = int(rows[0].get("created") or 0)

        # TrustedForNTAuth — runs last so analysts inspecting the
        # post-process trace see ESC* edges then the trust-anchor
        # pairing, matching the BHCE server's processing order.
        rows = target_store.execute_write(
            _TRUSTED_FOR_NTAUTH_QUERY,
            {
                "engagement": engagement,
                "now": now,
                "created_by": created_by,
                "source_episode_id": source_episode_id,
            },
            engagement=engagement,
        )
        if rows:
            stats.trusted_for_ntauth = int(rows[0].get("created") or 0)
    finally:
        if owned_store:
            target_store.close()

    return stats
