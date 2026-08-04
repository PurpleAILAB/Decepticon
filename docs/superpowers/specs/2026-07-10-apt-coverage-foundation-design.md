# APT Coverage Foundation Design

**Status:** Approved for specification PR

**Date:** 2026-07-10

**Scope:** `PurpleAILAB/Decepticon`, with later consumer PRs in `decepticon-saas`, documentation, and `decepticon-landing`

**Development policy:** Ponytail Full; one concern per PR; no direct pushes to `main`

## Summary

Decepticon will provide measurable catalog and profile coverage for every active MITRE ATT&CK Enterprise group while keeping executable adversary-emulation playbooks curated, reviewed, and evidence-gated.

The implementation extends the existing Skillogy MITRE STIX builder instead of creating a second threat-intelligence subsystem. A pinned MITRE bundle supplies canonical group and technique facts. Small curated overlays add source-scoped vendor aliases, priority, review metadata, and links to deeper Decepticon artifacts. Deterministic generated artifacts feed Skillogy, Soundwave, coverage reports, ATT&CK Navigator, and public documentation.

"100% APT coverage" means 100% coverage of the defined MITRE denominator at the catalog and retrievable-profile levels. It does not claim that every actor has a fully executable or evaluated emulation playbook.

## Current State

The repository currently contains:

- 310 `SKILL.md` files;
- 22 operational actor profiles under `skills/shared/adversary-emulation`;
- 7 Soundwave planning playbooks under `skills/standard/soundwave/threat-profile/emulation`;
- a Skillogy builder that imports MITRE ATT&CK Enterprise v19.1 tactics and techniques from a local STIX 2.1 bundle;
- separate hand-maintained actor indexes whose breadth and terminology can drift;
- benchmark infrastructure for XBOW and other providers, but no actor-registry coverage or playbook-routing evaluation lane.

The design preserves the existing skill and builder architecture. It removes the need to create hundreds of repetitive actor Markdown files merely to claim breadth.

## Goals

1. Define an objective, versioned denominator for MITRE group coverage.
2. Represent every active Enterprise group as a normalized, source-backed actor record.
3. Make every active group retrievable through Skillogy by canonical name, MITRE alias, and curated vendor alias.
4. Distinguish cataloged, profiled, playbook-ready, and evaluated maturity.
5. Generate coverage artifacts and documentation from the same registry.
6. Add full Soundwave playbooks in small, source-reviewed waves.
7. Fail closed on ambiguous identities, invalid references, drift, and unsupported execution claims.
8. Expose a stable, versioned contract for later SaaS and landing consumers.

## Non-goals

- Claiming complete coverage of every vendor's private or short-lived actor taxonomy.
- Generating executable procedures for every group from MITRE descriptions.
- Running live CTI fetches in Decepticon runtime paths.
- Shipping real actor malware or bypassing existing Rules of Engagement.
- Replacing operational skills, the knowledge graph, or the existing Skillogy retrieval API.
- Mixing registry, runtime, UI, landing, and long-form documentation changes into one PR.

## Coverage Contract

### Denominator

The denominator is the set of Enterprise ATT&CK `intrusion-set` objects in the pinned STIX bundle after excluding objects where `revoked` or `x_mitre_deprecated` is true.

Historical revoked or deprecated groups remain available as lifecycle records when useful for alias resolution, but they do not count toward active-group coverage.

The generated coverage report must publish:

- ATT&CK matrix and snapshot version;
- source bundle checksum;
- active-group denominator;
- covered counts and percentages at each maturity level;
- unmapped curated vendor clusters as a separate count;
- generation timestamp and registry schema version.

### Maturity Levels

| Level | Name | Required evidence |
|---|---|---|
| L1 | Cataloged | Canonical MITRE identity, lifecycle state, MITRE aliases, ATT&CK relationships, and source provenance validate. |
| L2 | Profiled | Skillogy can retrieve a planning-safe profile by canonical name and known aliases, including source provenance and freshness metadata. |
| L3 | Playbook-ready | A reviewed Soundwave playbook provides a threat-profile seed, ordered kill chain, operational skill links, signature-fidelity notes, RoE gates, abort conditions, deconfliction, and cited sources. |
| L4 | Evaluated | Schema, retrieval, routing, safety, and a representative lab scenario all pass with retained evidence. |

The initial foundation is complete when all active MITRE groups reach L1 and L2. L3 and L4 expand in reviewed waves and are never included in the 100% claim unless their respective numerators equal the published denominator.

## Architecture

### Sources

1. **Pinned MITRE Enterprise STIX bundle:** authoritative for group IDs, MITRE names and aliases, lifecycle state, technique relationships, and upstream modification dates.
2. **Curated overlay records:** authoritative only for Decepticon judgments and explicitly sourced vendor mappings.
3. **Existing Decepticon actor profiles and playbooks:** linked deeper artifacts, never silently treated as canonical identity data.

Runtime components never fetch threat intelligence from the network. Updating upstream data is a maintainer operation that produces a semantic diff in a dedicated PR.

### Build Flow

```text
pinned MITRE STIX + curated overlays
                 |
                 v
       actor registry builder
       normalize / merge / validate
                 |
       +---------+----------+----------------+
       |                    |                |
       v                    v                v
 canonical registry   coverage report   Navigator layer
       |                    |                |
       +---------+----------+----------------+
                 |
       +---------+-----------+
       |                     |
       v                     v
 Skillogy ingestion   generated documentation
       |
       v
 Soundwave actor resolution and playbook routing
```

### Ownership

- **Decepticon Core:** source schema, builder, overlays, generated artifacts, Skillogy ingestion, Soundwave routing, playbooks, validation, and evaluation.
- **Decepticon SaaS:** consumes a versioned Core artifact or API; owns customer-visible actor selection, maturity, freshness, and evidence UX.
- **Documentation:** publishes methodology, denominator, snapshot, maturity definitions, coverage tables, authoring rules, and limitations.
- **Landing:** consumes approved coverage claims and links to methodology. It never maintains an independent actor count.

## Actor Data Model

The canonical generated actor record contains:

| Field | Meaning |
|---|---|
| `schema_version` | Version of the Decepticon actor contract. |
| `group_id` | MITRE external ID such as `G0016`; absent only for explicitly unmapped overlay clusters. |
| `stix_id` | Stable upstream STIX object ID. |
| `name` | Canonical MITRE group name. |
| `mitre_aliases` | Aliases from the pinned MITRE object. |
| `vendor_aliases` | Alias sets namespaced by source, never flattened without provenance. |
| `status` | `active`, `revoked`, `deprecated`, or `unmapped`. |
| `created` / `modified` | Upstream lifecycle timestamps. |
| `techniques` | Valid ATT&CK technique IDs connected by live STIX relationships. |
| `priority` | Curated playbook priority used for wave planning, not identity resolution. |
| `confidence` | Confidence in curated mappings or summaries. |
| `last_reviewed` | Date a maintainer reviewed the overlay. |
| `sources` | Public URLs and source identifiers supporting overlay claims. |
| `profile_ref` | Optional existing operational profile path. |
| `playbook_ref` | Optional Soundwave playbook path. |
| `coverage` | Derived L1-L4 evidence and status. |

Overlay records contain only fields not owned by MITRE. They may map a vendor cluster to one MITRE group, record a qualified relationship, or remain explicitly unmapped. An unmapped record is reported separately and cannot inflate MITRE coverage.

Descriptions from third-party sources are summarized rather than copied. Alias mappings retain source URLs and review dates.

## Identity Resolution

Skillogy resolves actor intent in this order:

1. exact MITRE group ID;
2. exact canonical name;
3. exact source-scoped alias;
4. normalized alias match;
5. ranked candidate search.

Normalization handles case, whitespace, and punctuation only. It does not infer attribution.

If one normalized term maps to multiple groups or clusters, the resolver returns ranked candidates with canonical IDs and sources. Soundwave asks the operator to choose. It never silently selects an actor from an ambiguous alias.

MITRE-only records expose the pinned snapshot and upstream modification date as provenance and freshness. Curated confidence applies only to overlay claims; its absence never implies a confidence judgment about MITRE attribution.

If a resolved actor has no L3 playbook, Soundwave may construct a generic RoE-bounded plan from verified ATT&CK techniques and existing operational skills. The output must state that actor-specific procedure and sequencing fidelity is reduced. It must not invent malware, campaigns, or procedures.

## Playbook Contract

L3 playbooks remain reviewed Markdown skills because they encode behavior and safety judgments. Every playbook contains:

- a valid `ThreatProfile` seed;
- an ordered phase, technique, action, agent, and operational-skill map;
- actor-defining signature fidelity;
- citations and a review date;
- explicit deviations from real actor tooling;
- RoE prerequisites and named abort conditions;
- deconfliction and cleanup identifiers;
- safe lab or canary substitutions for destructive actions.

The first playbook waves reuse existing operational profiles. Actor priority is based on customer relevance, distinct tradecraft, source freshness, coverage gaps, and lab feasibility. Popularity alone does not determine order.

## Generated Artifacts

The builder emits deterministic, sorted artifacts:

- canonical actor registry JSON;
- coverage summary JSON;
- MITRE ATT&CK Navigator layer;
- generated actor catalog and coverage tables for documentation;
- a routing index consumed by Skillogy and Soundwave.

Generated artifacts include the schema version, ATT&CK snapshot, and source checksum. Re-running the builder on unchanged inputs produces a byte-identical result.

The exact paths and packaging boundary are resolved in the implementation plan after checking current distribution and wheel-inclusion conventions. The contract, not a speculative file layout, is fixed by this design.

## Validation and Error Handling

The validator rejects:

- a missing or duplicate active MITRE group;
- duplicate source-scoped aliases for different actors without an explicit collision record;
- an overlay referring to a nonexistent group;
- a technique ID absent from the pinned bundle;
- an L3 claim whose playbook path does not exist;
- a playbook whose referenced operational skill does not exist;
- an L4 claim without every required evidence result;
- stale generated artifacts;
- nondeterministic output ordering;
- coverage documentation whose denominator or snapshot differs from the registry.

Invalid generated state fails the build or CI lane. Runtime excludes invalid playbooks instead of guessing. Source or freshness warnings remain visible in retrieved profiles and documentation.

## Evaluation Strategy

### Schema and Determinism

- Parse valid and invalid STIX fixtures.
- Verify revoked and deprecated denominator behavior.
- Verify overlay merge, namespace, collision, and unmapped-cluster behavior.
- Run the builder twice and compare bytes.

### Completeness

- Assert every active Enterprise intrusion set appears exactly once.
- Assert the generated L1 and L2 numerator equals the active denominator.
- Assert generated documentation and registry metadata agree.

### Retrieval and Routing

- Golden tests cover group IDs, canonical names, MITRE aliases, vendor aliases, punctuation variants, ambiguous aliases, and unknown actors.
- Soundwave routes L3 actors to the reviewed playbook.
- L1/L2 actors take the explicitly labeled reduced-fidelity path.

### Playbook Safety

- Validate required sections and fields.
- Validate every technique and operational skill reference.
- Require RoE, abort, deconfliction, and safe-impact language.
- Preserve existing OPSEC and command safety controls.

### Scenario Evaluation

L4 requires a representative lab scenario that exercises actor resolution, plan generation, operational routing, and evidence capture. Destructive, phishing, identity-takeover, and ICS actions use authorized lab or canary substitutions unless the test environment and RoE explicitly permit more.

## Documentation Design

Documentation is generated from the same contract where exact mappings or counts are shown. Separate documentation PRs provide:

- the definition and limits of "100% coverage";
- current ATT&CK snapshot, checksum, denominator, and maturity counts;
- the actor and alias catalog;
- a coverage matrix and downloadable Navigator layer;
- the refresh and semantic-review workflow;
- overlay sourcing, confidence, and freshness rules;
- playbook authoring and review requirements;
- reduced-fidelity behavior and safety limitations;
- examples for finding an actor through Skillogy and using a reviewed playbook.

Landing and SaaS claims must use the maturity labels. "100% MITRE ATT&CK Enterprise group catalog and profile coverage" is permitted when the generated gate passes. "100% executable APT emulation" is not permitted unless L3 reaches the same measured denominator.

## Ponytail Full Policy

Every PR follows this ladder:

1. remove work that does not need to exist;
2. reuse the current builder, schemas, validation helpers, and test patterns;
3. use the Python standard library where sufficient;
4. reuse installed dependencies before proposing a new one;
5. implement the smallest diff satisfying the PR's success criteria.

Each PR records a Ponytail Full review covering reused code, rejected abstractions, dependency changes, and remaining unavoidable complexity. The existing Decepticon quality bar remains authoritative when it is stricter.

## PR Delivery Sequence

All changes use isolated branches and PRs. Runtime PRs stay within the repository's default limit of 400 changed runtime lines, 10 files, and one logical concern unless an owner explicitly approves otherwise.

| PR | Repository | Single concern | Depends on |
|---|---|---|---|
| C0 | Core | This approved design and measurable contract | None |
| C1 | Core | Extend the existing STIX builder with group records and the actor schema | C0 |
| C2 | Core | Curated overlay merge, validation, and deterministic coverage artifacts | C1 |
| C3 | Core | Skillogy actor ingestion and ambiguity-safe alias resolution | C2 |
| C4 | Core | Soundwave routing and labeled reduced-fidelity fallback | C3 |
| C5 | Core | Coverage, routing, safety, and scenario evaluation lane | C4 |
| C6+ | Core | Small waves of reviewed L3 playbooks using existing profiles | C5 where practical |
| C-docs | Core/docs | Methodology, generated coverage, authoring guide, and limitations | C2-C5 as relevant |
| S0-S3 | SaaS | Version pin, coverage model/API, actor UX, and E2E evidence in separate PRs | Stable Core contract |
| L0-L2 | Landing | Claim model, coverage presentation, then accessibility/performance/conversion | Repository access and stable Core contract |

Dependent PRs are opened only when their base contract is reviewable. No implementation PR bundles unrelated cleanup.

## Acceptance Criteria

The foundation milestone is accepted when:

1. the pinned MITRE snapshot and checksum are published;
2. every active Enterprise group has one valid L1 record;
3. every active group is retrievable as an L2 profile by ID and canonical name;
4. known aliases resolve correctly or return explicit ambiguity;
5. generated coverage reports show 100% L1 and L2 against the published denominator;
6. generated docs and Navigator data match the registry byte-for-byte inputs;
7. invalid overlays, paths, technique IDs, maturity claims, and drift fail validation;
8. actors without L3 artifacts are labeled reduced fidelity and do not receive invented procedures;
9. focused tests, the relevant full quality lane, Ponytail Full review, and end-to-end verification are recorded in each PR;
10. no change is pushed directly to `main`.

## Known Delivery Constraint

The connected GitHub app currently has access to `PurpleAILAB/Decepticon` and `PurpleAILAB/decepticon-saas` but returns 404 for `PurpleAILAB/decepticon-landing`. Landing PRs remain blocked until the repository name is corrected or that repository is added to the GitHub app installation. This does not block Core or SaaS work.
