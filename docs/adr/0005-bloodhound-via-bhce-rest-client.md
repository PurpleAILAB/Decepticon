# 0005. Integrate BloodHound via the official BHCE REST API, not via in-house reimplementation

- **Status:** Accepted
- **Date:** 2026-06-05
- **Deciders:** @PurpleCHOIms
- **Related:** PR #560, #562, #563, #565, #567, #569, #570, #571, #572, #573, #574, #575, #576, #577, #578 (KGStore-direct ingest + ADCS post-process — to be deprecated); BloodHound CE v9.2.2 (2026-06-01)

## Context

`tools/ad/` currently does two things in-house:

1. Reads SharpHound ZIP/JSON dumps and writes them into our own Neo4j
   ("KGStore") via `merge_bloodhound_json` / `ingest_bloodhound_zip`.
2. Re-implements BloodHound Community Edition's `PostProcessedRelationships`
   logic in Python/Cypher: ADCS ESC1/3/4/6/9/13, GoldenCert, DCSync,
   TrustedForNTAuth, plus per-edge ingest for SPNTargets, DumpSMSAPassword,
   HasSIDHistory, RootCA→Domain, etc.

This is a maintenance treadmill against a fast-moving upstream (BHCE shipped
v9.2.2 on 2026-06-01; new ESC kinds, edge renames, and Properties keys land
every release). Every in-house edge needed an RFC pass, a regex check, a
dogfood pass, and a PR — and the result still trails BHCE's analysis. The
community has a sanctioned answer: BloodHound CE exposes an official REST
API with HMAC-signed requests, and SpecterOps publishes a community MCP
wrapper (`mwnickerson/bloodhound_mcp`) that proves the surface is enough
for agentic use.

Direction from project owner (2026-06-05): the AD tool surface must call
**real BloodHound**, not a hand-written reimplementation. The community
MCP is reference material at most; primary sources are BHCE's own source
code and OpenAPI spec.

## Decision

We replace the in-house BloodHound layer with a thin Python client that
talks to a sidecar BHCE deployment over its official REST API. Three
concrete sub-decisions:

1. **(Y) Run BHCE against a dedicated Neo4j container, reuse our Postgres.**
   Neo4j Community Edition only allows one user database, and our KGStore
   already occupies it; we add a `decepticon-bhce-neo4j` container
   (Neo4j 4.4.42 or 5.x — whichever the BHCE `dawgs` driver currently
   supports as primary) plus a `decepticon-bhce-api` container running
   `ghcr.io/specterops/bloodhound:v9.2.2`. The BHCE API points at
   our existing Postgres (`bloodhound` database, `pg_trgm` extension
   pre-created) via `bhe_database_connection` and at the new Neo4j via
   `bhe_neo4j_connection`. BHCE migrations (`goose`) self-bootstrap on
   first boot.

2. **(Q) Stage the cutover.** A new `tools/ad/bh_*` surface backed by the
   REST client lands alongside the existing tools. The existing
   `bh_ingest_zip`, `bh_ingest_json`, `dcsync_check`, `delegation_audit`,
   `gpo_audit`, `adcs_audit`, plus the entire `adcs_post.py` post-process
   pipeline carry `DeprecationWarning` for one minor cycle, then move to
   `decepticon.compat` for one further cycle, then are removed (this is
   pre-1.0; the `compat/` shim policy in CLAUDE.md applies).

3. **(M2) Implement a hand-written Python client against the official BHCE
   REST surface; do NOT vendor or subprocess the community MCP.** The
   client targets the v9.2.2 OpenAPI 3.0.3 spec shipped at
   `packages/go/openapi/src/openapi.yaml` in the BHCE repo (also reachable
   at runtime via `GET /api/v2/spec` as `text/x-yaml`, no auth). Every
   endpoint, header, and signature step traces to BHCE source code, not
   to the community MCP. The community MCP's *interface shape* (13
   composite tools, 10 markdown resources) is allowed inspiration for the
   `@tool` grouping in `tools/ad/bh_*`, but no factual claim is taken from
   it. Resources we want for agent context (`cypher/offensive-queries`,
   `guides/adcs-methodology`, etc.) are vendored from SpecterOps' official
   docs site (`bloodhound.specterops.io`) rather than from the community
   repo.

### Authoritative facts the client must encode (source-cited)

These come from BHCE v9.2.2 (`/tmp/bhce-clone/`) and must be enshrined in
the client's tests:

- **HMAC chain** (`cmd/api/src/api/signature.go:97-145`): three-stage
  HMAC-SHA-256. `OperationKey = HMAC(token_secret, METHOD || URI)`;
  `DateKey = HMAC(OperationKey, RFC3339_truncated_to_hour)`;
  `BodyKey = HMAC(DateKey, body_bytes)`; signature = `base64(BodyKey)`.
  Empty body still runs the third HMAC.
- **Required headers** (`signature.go:169-171`): `Authorization: bhesignature <TOKEN_ID>`,
  `RequestDate: <RFC3339 full datetime>`, `Signature: <base64 BodyKey>`.
  Note: the date string fed to the signature is hour-truncated; the
  header itself is full RFC3339.
- **Clock skew window**: ±1 hour (`cmd/api/src/api/auth.go:276-296`,
  `maxClockSkew = time.Hour`). The docs page paraphrases this as "2 hours";
  the code wins.
- **Cypher**: `POST /api/v2/graphs/cypher` with
  `{query: string, include_properties: bool}` — NOT `/api/v2/cypher`.
  Mount: `cmd/api/src/api/registration/v2.go:217`.
- **File upload (SharpHound ingest)** is a three-step flow + polling:
  `POST /api/v2/file-upload/start` → `POST /api/v2/file-upload/{job_id}`
  (Content-Type ∈ {`application/json`, `application/zip`,
  `application/zip-compressed`, `application/x-zip-compressed`}) →
  `POST /api/v2/file-upload/{job_id}/end`. Status via
  `GET /api/v2/file-upload/{job_id}`. No webhook/SSE.
- **Token CRUD**: create `POST /api/v2/tokens`, list `GET /api/v2/tokens`,
  revoke `DELETE /api/v2/tokens/{token_id}` (`registration/v2.go:108-110`).
- **OpenAPI**: 3.0.3, 223 path entries under `/api/v2/*`, served at
  `GET /api/v2/spec`. We pin against a vendored copy of the v9.2.2 spec to
  detect upstream drift in CI.

## Consequences

- **Easier**
  - One source of truth for ADCS/ESC analysis: BHCE itself, maintained by
    SpecterOps. Our codebase stops carrying ESC1/3/4/6/9/13 Cypher.
  - Cross-team trust: red-team users already know BloodHound's output
    shape; reusing it gives recognizable findings instead of our
    artisanal equivalents.
  - SharpHound ingest semantics (per-kind JSON files, Trust 4-way split,
    PrimaryGroupSID trap, etc.) become BHCE's problem, not ours.
  - Cypher passthrough lets agents prototype attack-path queries against
    a familiar schema.

- **Harder**
  - Deployment complexity: one more API container and one more Neo4j
    container. Smoke/dogfood paths need updates to wait on BHCE health
    (`GET /api/version`) and seed a HMAC token on first boot.
  - Cross-graph joins (AD ↔ web ↔ cloud ↔ smart-contract) no longer
    happen in one Cypher session — the BHCE graph and the KGStore graph
    are physically separate. Chain-planner workflows that previously
    joined `:HasVuln` (web) with `:AdminTo` (AD) must either move to
    KGStore-side mirroring of BHCE findings or accept a two-step plan.
  - HMAC token rotation, secret storage, and BHCE admin password
    bootstrap join the secret-management surface area.

- **Given up**
  - Authoring novel ADCS / SIDHistory / GMSA-related Cypher in-tree.
  - Treating the KGStore as the single AD source-of-truth.
  - The `decepticon-net` "Neo4j is the one intentional shared service"
    invariant relaxes to "two Neo4j instances, both inside `decepticon-net`,
    different roles" — CLAUDE.md needs a follow-up edit.

- **Migration timeline**
  - Sprint 1: PR #2 compose stack (BHCE API + Neo4j + Postgres bootstrap),
    PR #3 `bhce_client.py` + HMAC test vector, PR #4 `tools/ad/bh_*`
    LangChain `@tool` surface, PR #5 vendored docs/resources from
    `bloodhound.specterops.io`.
  - Sprint 2: PR #6 `DeprecationWarning` on legacy `tools/ad/*` (one
    minor cycle of overlap), update CLAUDE.md and `docs/architecture.md`.
  - Sprint 3 (next minor after Sprint 2): move legacy tools to
    `decepticon.compat`. The minor after that: hard-remove.

## Alternatives considered

- **(X) Run BHCE against our existing single Neo4j by upgrading to Neo4j
  Enterprise.** Rejected: licensing cost on OSS users (curl|bash install
  philosophy in CLAUDE.md), no benefit beyond avoiding one container.
- **(Z) Adopt BHCE's Neo4j as the only Neo4j and rehome KGStore web/cloud
  state into the same database.** Rejected: BHCE's `dawgs` driver owns
  the schema; KGStore's `(key, engagement)` composite uniqueness and
  cross-domain labels would either collide with BHCE's `:User`/`:Computer`
  constraints or fight BHCE's migration ownership on every release.
- **(P) Hard-delete the in-house AD layer in one PR.** Rejected: rolls back
  ~5 days of merged work without giving downstream agents time to switch
  call sites. The `compat/` shim policy exists for exactly this case.
- **(R) Run both surfaces side-by-side indefinitely.** Rejected: the
  in-house ESC* output and BHCE's will diverge subtly (different edge
  weight, missing edges, different `via_*` provenance), and agents will
  have no principled rule for which to trust. Maintenance cost is
  multiplicative.
- **(M1) Embed `mwnickerson/bloodhound_mcp` as a stdio MCP subprocess and
  let `langchain-mcp-adapters` expose its 13 composite tools.** Rejected:
  adds an external dependency on a non-SpecterOps-owned community wrapper
  (GPL-3.0 vs Decepticon's Apache-2.0 OSS — licensing review needed),
  stdio glue is harder to debug, and we still need a Python REST client
  for `file-upload` workflows the MCP doesn't expose cleanly. The MCP's
  composite-tool shape is allowed inspiration, not load-bearing dependency.
