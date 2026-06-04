---
name: bloodhound-bhce
description: Operate BloodHound Community Edition v9.2.2 via Decepticon's bhce_* tools — health check, Cypher passthrough, SharpHound ZIP ingest. Replaces the in-house ingest + ESC* post-process pipeline per ADR-0005.
metadata:
  subdomain: active-directory
  when_to_use: "bloodhound bhce attack path adcs esc dcsync sharphound ingest cypher ad enumeration domain compromise"
  mitre_attack:
    - T1078.002
    - T1558.003
    - T1649
    - T1003.006
  upstream_url: https://bloodhound.specterops.io/
---

# BloodHound CE via Decepticon's `bhce_*` Tools

Decepticon ships a sidecar BloodHound Community Edition v9.2.2 stack
(see `docs/adr/0005-bloodhound-via-bhce-rest-client.md`).  Three
`@tool` wrappers expose it to the agent:

| tool | what it does |
|---|---|
| `bhce_status` | Confirm BHCE is healthy and our HMAC token authenticates.  Always call this first when an AD task starts. |
| `bhce_cypher` | Run any Cypher query against BHCE's graph.  Mutations are off by default. |
| `bhce_ingest_zip` | Push a SharpHound `.zip` into BHCE — 3-step `file-upload` flow + polling until BHCE finishes parse + ESC* analysis. |

Use these instead of the legacy `bh_ingest_zip` / `dcsync_check` /
`delegation_audit` / `gpo_audit` / `adcs_audit` family — those are
the in-house port and are being retired per ADR-0005.

## Why we use BHCE rather than our own ingest

BHCE's `PostProcessedRelationships` Go pipeline emits every edge a
red-team operator expects: `ADCSESC1-13`, `GoldenCert`, `DCSync`,
`TrustedForNTAuth`, `IssuedSignedBy`, `CoerceAndRelayNTLMTo*`,
`HasSIDHistory`, `HasTrustKeys`, `SyncLAPSPassword`, …  The list is in
`graphschema/ad/ad.go::PostProcessedRelationships()` in the BHCE
source.  We deliberately do **not** re-implement these in our
codebase; the agent leans on BHCE's analyzer instead.

The Decepticon KGStore still owns web, cloud, and smart-contract
findings, and stays canonical for cross-domain chain planning.
BHCE is the AD layer.

## End-to-end loop the agent should follow

1. **Health check** — `bhce_status()`.  Verify `version.data.server_version` matches the deployed v9.2.2 and `self.data.principal_name` is non-empty.  If the diagnostic mentions `BHCE_URL` / `BHCE_TOKEN_*`, the sidecar is offline or the token has been revoked — stop and report.

2. **Ingest** — for every SharpHound collection drop:
   ```
   bhce_ingest_zip(path="/abs/path/to/20260605_lab.zip")
   ```
   Expected result envelope: `{job_id, terminal_status, last_payload, elapsed_seconds}`.  `terminal_status` must be one of
   `Complete`, `PartiallyComplete`, `Failed`, `Cancelled`.  Anything else
   (an `error` field, missing terminal_status) means BHCE never closed
   the job — surface the error to the operator rather than continuing
   with stale data.

3. **Walk the graph** with `bhce_cypher`.  Some battle-tested starting
   queries (BHCE node labels — `User`, `Computer`, `Group`, `Domain`,
   `GPO`, `OU`, `CertTemplate`, `EnterpriseCA`, `RootCA`, `AIACA`,
   `NTAuthStore`, `IssuancePolicy`):

   - **All Domain Admins** (sanity check that ingest landed):
     ```cypher
     MATCH (g:Group)
     WHERE g.objectid ENDS WITH '-512'
     MATCH (n)-[:MemberOf*1..]->(g)
     RETURN n.name, labels(n)
     ```

   - **Shortest path from a foothold to a Tier-Zero asset**:
     ```cypher
     MATCH p = shortestPath(
       (n {objectid: $foothold_sid})-[*1..15]->(t {system_tags: 'admin_tier_0'})
     )
     RETURN p
     ```

   - **ADCS escalation paths** (BHCE post-processes ESC* edges, so the
     agent never has to derive them):
     ```cypher
     MATCH p = (u {objectid: $foothold_sid})
                 -[:MemberOf|ADCSESC1|ADCSESC3|ADCSESC4|ADCSESC6a|ADCSESC6b|
                   ADCSESC9a|ADCSESC9b|ADCSESC10a|ADCSESC10b|ADCSESC13|
                   Enroll|AutoEnroll|GenericAll*1..10]->
               (t:Domain)
     RETURN p LIMIT 10
     ```

   - **GoldenCert opportunities** (CA + NTAuthStore + Domain triangle):
     ```cypher
     MATCH (ca:EnterpriseCA)-[:TrustedForNTAuth]->(:NTAuthStore)
     MATCH (ca)-[:GoldenCert]->(d:Domain)
     RETURN ca.name, d.name
     ```

   - **DCSync candidates**:
     ```cypher
     MATCH (n)-[:DCSync]->(d:Domain)
     RETURN n.name, labels(n), d.name
     ```

4. **Cross-domain plays** — when an AD path terminates and the chain
   needs to cross into the Decepticon KGStore (web exploitation, cloud
   pivots, smart-contract findings), hand the BHCE finding off to the
   chain planner.  Do not try to write web/cloud nodes into BHCE; BHCE
   is AD-only.

## Common failure modes

- **`bhce_status` returns a `BHCE_URL` diagnostic** — the sidecar
  isn't running (`docker compose up -d bhce-neo4j bhce`) or the
  agent's environment is missing `BHCE_TOKEN_ID` / `BHCE_TOKEN_KEY`.
- **`bhce_cypher` returns 401 `signature digest mismatch`** — clock
  skew.  BHCE enforces ±1 hour (`cmd/api/src/api/auth.go:276-296`).
  Check the container time before opening a wider investigation.
- **`bhce_ingest_zip` reports `terminal_status: Failed`** — the ZIP
  is corrupt or BHCE rejected an unknown JSON schema version
  (`meta.version`).  Look in `last_payload` for the BHCE-side reason.
- **An expected ADCS edge is missing after ingest** — BHCE only
  derives ESC* / GoldenCert / DCSync at analysis time, which runs
  after ingest closes.  Wait for `terminal_status` (the tool already
  polls until terminal) rather than re-running cypher in a busy loop.

## Where authoritative information lives

- **BHCE source code**: `github.com/SpecterOps/BloodHound` (current
  release v9.2.2, 2026-06-01).  This is the single source of truth
  for every edge, post-process algorithm, and Cypher passthrough
  guard.  When the upstream changes the schema, the agent's queries
  here have to follow.
- **Official BHCE REST API spec**: shipped at
  `packages/go/openapi/src/openapi.yaml` in the BHCE repo, also
  reachable at runtime via `GET /api/v2/spec` on the sidecar.
- **SpecterOps documentation site**:
  https://bloodhound.specterops.io — official methodology, AD / Azure
  / ADCS guides, and the canonical attack-path query library.
  Consult it directly for novel attack patterns; we deliberately
  avoid vendoring it here so the agent always reads the latest.
- **ADR**: `docs/adr/0005-bloodhound-via-bhce-rest-client.md` — why
  the agent talks to a sidecar BHCE instead of using the in-house
  port that PRs #560..#578 built.
