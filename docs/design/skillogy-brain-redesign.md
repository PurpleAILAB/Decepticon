# Skillogy — Brain Redesign (v0.2 Design)

**Status**: design spec, awaiting implementation
**Date**: 2026-06-03
**Supersedes (in spirit)**: [docs/design/skillogy.md](../../design/skillogy.md) (2026-05-28 v0.1 draft)
**Replaces (at runtime)**: `decepticon.middleware.skills.SkillsMiddleware` (text-matching catalog)
**Rebuilds (in package)**: `decepticon.skillogy.*` REST + gRPC service — backend switched from in-memory dict to Neo4j; wire protocol preserved.
**Target version**: Skillogy v0.2 — "Brain"

---

## TL;DR

Skillogy v0.2 reframes the skill system as **the agent's brain**: a Neo4j knowledge graph in which each skill is a node carrying its full markdown body as a property, frontmatter relations are first-class edges, and discovery is performed by the agent itself through Cypher traversal (Phase 1a) and later semantic recall over vector embeddings (Phase 1b). **MITRE ATT&CK Enterprise (v19.1) is the only first-class matrix in Phase 1a**; ICS, Mobile, and ATLAS values are preserved as raw frontmatter and promoted to graph edges in later phases when their importers land.

Three changes vs. the v0.1 draft:

1. **Body lives in the graph node**, not on disk. The graph is the agent's working knowledge surface; SKILL.md remains the git-side source of truth that the CI build pipeline ingests.
2. **Agents get raw Cypher (read-only) access**, not only curated tools. The "brain" metaphor demands associative navigation, not a five-method interface.
3. **MITRE matrices are first-class but phased.** Phase 1a loads ATT&CK Enterprise v19.1 only — single STIX importer, single ID format to validate. The `matrix` property on `:Technique` is kept as an enum so ICS / Mobile / ATLAS can be added in Phase 1b or 2 without schema breakage.

Three changes vs. the **current REST skillogy implementation** (`packages/decepticon/decepticon/skillogy/`):

1. **The skillogy service stays standalone — the in-memory dict registry is replaced by a Neo4j backend.** The service container keeps speaking REST + gRPC; its server-side now owns the Neo4j driver, loads the CI-emitted `skills.cypher` on startup, and serves agents over the wire. This is a rebuild, not a deletion of the package.
2. **Agents do not connect to Neo4j directly.** `SkillogyMiddleware` is a thin REST (default) / gRPC client that calls the skillogy service container. This preserves the "skill-as-a-service" intent of the original package, enables multi-tenant SaaS and OSS distribution (each operator runs their own skillogy container with their own SKILL.md tree), and lets future non-Python runtimes (Go, Rust, TypeScript) consume the same skill catalog via the wire protocol.
3. **The langgraph (agent) container image drops the `skills/` directory at the end of Phase 1a.** The skillogy service container is the only image that carries the catalog; the agent image just carries the thin client. SKILL.md authoring continues in git; the build pipeline ships them into the skillogy image, not into langgraph.

A **Phase 0 corpus cleanup** precedes Phase 1a: 251 `SKILL.md` files are normalized against a canonical schema, MITRE mappings are filled in and validated, subdomain aliases are collapsed. This is a pre-condition for a clean graph — building a graph on dirty input data produces a dirty graph.

---

## Amendment v0.2.2 — Tool surface + prompt-assembly refinements

**Date**: 2026-06-03 (mid-Phase-1a, applied during PR #538)
**Supersedes**: §5.7.3 (`run_cypher_read`) and the second half of §5.10 (workflow.md auto-load + MoC summary mechanism).

Three refinements emerged from dogfooding the four-tool middleware against the live graph (commit 6ba761da on `feat/skillogy-phase1a-service`). All three preserve the brain metaphor while trimming runtime surface and improving where context lives.

1. **`run_cypher_read` is removed from the agent tool surface.** The original argument — "agents need raw Cypher for associative navigation" — is satisfied by `find_skill(query?, subdomain?, mitre_id?, tag?, tactic_id?)` AND-combining over the five edge types and `traverse(from_path, edge_types?, depth?)` doing variable-length BFS over the whitelist. The remaining queries `run_cypher_read` would have enabled are aggregate/statistical (`count(*) GROUP BY`, etc.) — not load-bearing for kill-chain execution. Removing the tool eliminates the largest attack surface in Phase 1a (Cypher injection, write-keyword bypass) and shrinks the agent prompt. `Neo4jBackend.run_cypher_read` + `assert_read_only` + the `_WRITE_KEYWORDS` denylist are **kept in the server backend** for internal diagnostics, Phase 1b's `recall()` implementation, and test fixtures. Phase 1a agent surface is now **3 tools**: `find_skill`, `load_skill`, `traverse`.

2. **`workflow.md` is inlined at agent prompt assembly, not loaded by the middleware.** Each specialist's phase loop / scope rules / OPSEC discipline / handoff format live in `packages/decepticon/decepticon/skills/standard/<role>/workflow.md` (8 roles have one). The original §5.10 plan kept the deepagents-era `before_agent` hook that read these files into `state.workflow_content` at every turn. That conflates two responsibilities — *agent identity* (static, factory-time) and *skill discovery* (dynamic, per-turn). The amendment splits them: `PromptBuilder` reads `workflow.md` at factory time and concatenates it into the cacheable static prefix, so the workflow body sits inside the prompt-cache boundary and the middleware owns no filesystem behavior. Roles without a `workflow.md` get no extra content (no fallback, no warning — the absence is the contract).

3. **The middleware now injects two prompt fragments, not one.** A **static graph schema cheat-sheet** (node labels, edge types, key properties, two example queries) explains what the `find_skill` filters and the `traverse` whitelist actually walk — making the three remaining tools self-documenting. A **dynamic per-phase MoC summary** (≈300 tokens) primes the agent on the concept areas available in its current phase, queried at request time via a new `Neo4jBackend.query_moc_summary(phase)` method. This requires `SkillogyMiddleware.__init__(*, agent_phase: str, ...)` and a `role → phase` mapping in `agents/build.py`; the original §5.10 sketch already specified `agent_phase` but did not wire it.

Net effect on the runtime: agent boot prompt = (PromptBuilder static prefix, including workflow.md if present) + (middleware-injected schema cheat-sheet, static) + (middleware-injected MoC summary for this phase, dynamic). The four-tool sketch in §5.10 is replaced by the three-tool surface above; `build_run_cypher_read_tool` is deleted from the middleware (not the backend).

---

## 1. Motivation

### 1.1 Where we are today

The current production path is `decepticon.middleware.skills.SkillsMiddleware`, a subclass of `deepagents.middleware.skills.SkillsMiddleware`. At each agent boot, it:

1. Reads every `SKILL.md` under the agent's configured `sources` list.
2. Injects a 2–4 KB system-prompt block listing every skill's `name`, `description`, `mitre_attack` tags, and `when_to_use` triggers grouped by `subdomain`.
3. Registers a single `load_skill(path)` tool that the agent calls when a trigger keyword matches its current task.

The catalog is **flat text**; the agent picks a skill by reading the catalog and matching keywords. Per-agent slicing (different specialists get different `sources`) cuts the catalog to ~20–40 skills per agent, but the routing decision remains opaque LLM keyword matching.

A parallel `decepticon.skillogy.*` package (added 2026-05-28 in `20d57603`) externalizes the catalog as a REST service backed by an in-memory dict. It is feature-flagged behind `DECEPTICON_USE_SKILLOGY=1` and currently sees no production traffic. The original gRPC half is unwired (`build_grpc_server` raises `RuntimeError`).

### 1.2 What hurts (user-confirmed, in priority order)

1. **Routing is actually wrong**. Agents pick irrelevant skills, miss applicable skills, and produce MITRE mappings that don't match the executed action — observable in benchmarks and dogfood.
2. **Token cost is high**. Each specialist agent's boot prompt carries 2–4 KB of skill catalog before any tool call. Sub-agents inherit this. Across 16 specialists × N turns, the cost is non-trivial.
3. **The skill system itself needs efficiency and feature improvements**. The current text-matching surface is at its limit; new functionality (cross-skill discovery, prerequisites, capability planning) has nowhere to live in a flat-text model.
4. **Agents should use skills as the primary expertise interface, not as a passive lookup table**. The user's framing: *"skillogy 시스템이 에이전트의 '뇌' 였으면해. 사람의 뇌처럼 뉴런들로 지식들이 연결되어있는거지."* The system should be **the agent's brain** — knowledge as interconnected neurons, not a passive lookup table. This is the load-bearing intent of the redesign.

### 1.3 Reality check on the corpus

Measured 2026-06-03 across `packages/decepticon/decepticon/skills/**/SKILL.md` (251 files):

| Field | Coverage |
|---|---|
| `name`, `description` | 251 / 251 (100%) |
| `metadata` block | 207 / 251 (82%) |
| `metadata.subdomain` | 197 / 251 (78%) |
| `metadata.when_to_use` | 195 / 251 (78%) |
| `metadata.mitre_attack` | 186 / 251 (74%) |
| `metadata.tags` | 145 / 251 (58%) |
| `allowed-tools` | 138 / 251 (55%) |
| `metadata.aatmf_tactic` | 15 (6%) |
| `metadata.kind` | 4 (2%) |
| `metadata.safety_critical` | 1 (<1%) |
| `metadata.gated_by_conops` | 1 (<1%) |

MITRE format issues found:
- `defense-evasion-validation` — free-text value polluting `mitre_attack`.
- `TA0001`–`TA0008`, `TA0043` — tactic IDs misused as technique IDs in at least one file.
- `T0800`–`T0859` — **ICS-ATT&CK** (separate matrix) is in use (12 ICS skills), but the v0.1 design assumed Enterprise-only.
- 65 skills (26%) have no MITRE mapping at all.

Subdomain inconsistency observed:
- `reverse-engineering` (4) vs `reverser` (3) — duplicate concept.
- `contracts` (3) vs `smart-contracts` (5) — duplicate concept.
- `cloud` (7) vs `cloud-native` (5) — overlap.

Top subdomains: `ai-security` (18), `planning` (17), `reconnaissance` (14), `iot` (12), `adversary-emulation` (11), `execution` (9), `wireless` (8), `ics-ot` (8), `active-directory` (8), `orchestration` (7), `cloud` (7).

This corpus is the input to the graph. Phase 0 cleans it.

### 1.4 Audit of which frontmatter fields are actually used

A code audit of `deepagents.middleware.skills.SkillsMiddleware` (base) + `decepticon.middleware.skills.SkillsMiddleware` (override) + `decepticon.tools.skills.build_load_skill_tool` was performed against the same 251-file corpus. Findings drive the slim `:Skill` schema in §5.2:

| Frontmatter field | Files | deepagents parses? | Decepticon middleware reads? | Reaches system prompt? | Verdict |
|---|---|---|---|---|---|
| `name` | 251 | ✅ | ✅ | ✅ | ACTIVE |
| `description` | 251 | ✅ | ✅ | ✅ | ACTIVE |
| `metadata.subdomain` | 197 | ✅ stored | ✅ groups catalog | ✅ as section header | ACTIVE |
| `metadata.when_to_use` | 195 | ✅ stored | ✅ as `triggers:` line | ✅ | ACTIVE |
| `metadata.mitre_attack` | 186 | ✅ stored | ✅ as inline tags | ✅ | ACTIVE |
| `metadata.tags` | 145 | ✅ stored | ❌ | ❌ | stored but unread (promoted to `:Tag` edges in v0.2) |
| `allowed-tools` | 138 | ✅ stored | ❌ — Decepticon override replaces base prompt entirely | ❌ | **VESTIGIAL — dropped** |
| `metadata.aatmf_tactic` | 15 | ❌ | ❌ | ❌ | raw preserve only |
| `metadata.upstream_ref` | 14 | ❌ | ❌ | ❌ | raw preserve only |
| `metadata.kind` | 4 | ❌ | ❌ | ❌ | **DEAD — dropped** (offensive vs reporting now inferred from path) |
| `metadata.safety_critical` | 1 | ❌ | only v0.1 REST skillogy | ❌ | **ASPIRATIONAL — dropped** |
| `metadata.gated_by_conops` | 1 | ❌ | only v0.1 REST skillogy | ❌ | **ASPIRATIONAL — dropped** |

Two findings change the design vs. the 2026-05-28 v0.1 draft:

1. **Decepticon's `SkillsMiddleware` overrides `_format_skills_list` and `SKILLS_SYSTEM_PROMPT` from the deepagents base**, so any frontmatter the base parses but the override doesn't re-read is invisible to the agent. `allowed-tools` falls into this trap.
2. **`SkillogyMiddleware` is built fresh on `langchain.agents.middleware.AgentMiddleware`**, not subclassed from `deepagents.middleware.skills.SkillsMiddleware`. We are not inheriting its frontmatter parsing decisions or its `SkillMetadata` shape — the graph is the canonical schema, with raw frontmatter preserved on the node for round-trip.

`workflow.md` auto-load (current Decepticon middleware reads `<source>/workflow.md` into `state.workflow_content`) is **preserved as agent-boot context** — orthogonal to the skill graph and load-bearing for agent loop behavior. Originally planned to remain in `SkillogyMiddleware` (see §5.10); the v0.2.2 amendment relocates it to `PromptBuilder` so the workflow body sits inside the static cache prefix and the middleware owns no filesystem behavior. See "Amendment v0.2.2" at the top of this document.

---

## 2. Concept

### 2.1 One-line definition

> Skillogy v0.2 is a **Neo4j knowledge graph that is the agent's brain**: each `:Skill` node carries its full markdown body, frontmatter relations (phase, MITRE, tags, asset type) are typed edges, and agents discover skills by Cypher traversal (Phase 1a) and semantic recall (Phase 1b). The graph is built deterministically at CI from `SKILL.md` files in git.

### 2.2 Six principles

| # | Principle | Why |
|---|---|---|
| 1 | **Graph as brain, not as index** | Brain ⇒ dense connectivity + associative recall + spreading activation. A pointer-only "discovery layer" (the v0.1 Index-Only stance) is just a catalog with extra steps. We want the working knowledge surface to *be* the graph. |
| 2 | **Body lives in the node** | An agent that traverses to a skill should get the body without a second round-trip to disk. Bodies as node properties enable single-hop knowledge consumption. |
| 3 | **SKILL.md is the git source of truth** | Authors keep writing markdown. CI ingests it. PR diffs show graph changes via the checked-in `skills.cypher` dump. We do not redesign authoring UX or lose git history. |
| 4 | **Agent gets read-only Cypher access** | Curated tools cover common patterns, but the brain metaphor demands ad-hoc associative navigation. A read-only Cypher escape hatch costs little and unlocks autonomy. |
| 5 | **MITRE matrices are first-class, but phased** | Enterprise is loaded in Phase 1a. ICS, Mobile, ATLAS use the same single-label / `matrix` property pattern (OSS-standard) so they slot in without schema breakage when their importers land in Phase 1b or 2. Routing by technique/tactic/platform becomes a Cypher query. |
| 6 | **Phase the build** | The brain isn't built in one PR. Phase 0 (corpus cleanup) → Phase 1a (anatomy: graph + MITRE + Cypher tools) → Phase 1b (associative memory: embeddings + semantic recall) → Phase 2+ (LLM-inferred edges, plasticity, capability plane). Each phase is schema-additive and independently shippable. |

### 2.3 Paradigm shift, side by side

| Axis | Current (`SkillsMiddleware`) | Current REST skillogy | Skillogy v0.2 (Brain) |
|---|---|---|---|
| Storage | filesystem | in-memory dict | Neo4j (persistent) |
| Catalog injection | 2–4 KB at every boot | ~200-byte policy + REST | ~300-token MoC summary per phase |
| Discovery mechanism | LLM keyword match on prompt-embedded catalog | LLM keyword match + REST `list_skills` | Cypher traversal + (1b) semantic recall + (2+) PPR |
| Skill body fetch | `read_file` via Backend | REST `load_skill` returns JSON envelope | Node `body` property; one Cypher hop |
| Cross-skill relations | not modeled | not modeled | typed edges (`IMPLEMENTS`, `IN_PHASE`, `RELATED_TO`, `TAGGED`, ...) |
| MITRE matrices supported | strings only | strings only | Phase 1a: Enterprise as graph; ICS/Mobile/ATLAS preserved as raw frontmatter, promoted in later phases |
| Agent autonomy on discovery | LLM picks from prompt | LLM calls `list_skills` then picks | LLM writes Cypher / calls `recall`, picks |
| Audit trail | none | per-load REST log | every Cypher query is loggable; routing reasoning is the Cypher result |
| Hot-swap | restart container | REST `ingest_skill` | re-run CI; or REST proxy (Phase 2+ if needed) |

### 2.4 What does **not** change

- `SKILL.md` format. Frontmatter and body remain author-facing.
- The 16 specialist agents and the orchestrator. Code is unmodified except for the middleware swap.
- Neo4j infrastructure. Decepticon already runs Neo4j (attack graph + KG). The skill graph adds new labels in the same database.
- Plugin SDK contract. `decepticon-sdk` plugin authors continue shipping skills as files; their files participate in the build like any others.

---

## 3. Architecture

### 3.1 System diagram

```
                  ┌──────────────────────────────────────────────────┐
                  │                  BUILD TIME (CI)                 │
SKILL.md (251) ───┤                                                  │
MITRE STIX (Ent.)─┤── skillogy.builder ──► skills.cypher             │
canonical seeds ──┤   (Python)             (checked into repo)       │
                  │                        ▲ reviewable diff         │
                  └────────────────────────│─────────────────────────┘
                                           │
                                           ▼ baked into skillogy image
                                           │ (langgraph image drops skills/ here)
                                           ▼
   ┌──────────────────────────────┐    over the wire    ┌──────────────────────────────┐
   │      langgraph container     │  ◄────── REST ─────► │     skillogy container       │
   │                              │      (gRPC opt.)     │                              │
   │ ┌──────────────────────────┐ │                      │ ┌──────────────────────────┐ │
   │ │ SkillogyMiddleware       │ │                      │ │ FastAPI / grpcio app     │ │
   │ │  (thin REST/gRPC client) │ │                      │ │  POST /v1/skills:load    │ │
   │ │  before_agent():         │ │                      │ │  POST /v1/skills:traverse│ │
   │ │   - check service health │ │                      │ │  POST /v1/skills:cypher  │ │
   │ │   - fetch MoC summary    │ │                      │ │  (read-only, parameterised)│
   │ │  get_tools():            │ │                      │ │                          │ │
   │ │   - load_skill           │ │                      │ │ Owns Neo4j driver:       │ │
   │ │   - traverse             │ │                      │ │  - idempotent load of    │ │
   │ │   - run_cypher_read      │ │                      │ │    skills.cypher at boot │ │
   │ │   - recall (Phase 1b)    │ │                      │ │  - validates queries     │ │
   │ └──────────────────────────┘ │                      │ │  - per-engagement ACL    │ │
   │                              │                      │ │    (Phase 2)             │ │
   │ workflow.md auto-load        │                      │ └──────────────────────────┘ │
   │ stays in-process             │                      │              │               │
   │                              │                      │              ▼               │
   │ NO local skills/ tree after  │                      │   ┌────────────────────────┐ │
   │ Phase 1a final cutover.      │                      │   │ Neo4j (shared instance)│ │
   └──────────────────────────────┘                      │   │  skill_graph labels:   │ │
                                                         │   │   :Skill (body, emb 1b)│ │
                                                         │   │   :Phase :AssetType    │ │
                                                         │   │   :Tag :MoC :Tactic    │ │
                                                         │   │   :Technique           │ │
                                                         │   │   :MatrixVersion       │ │
                                                         │   │  attack_graph labels   │ │
                                                         │   │   (unchanged):         │ │
                                                         │   │   :Host :Service       │ │
                                                         │   │   :Vulnerability …     │ │
                                                         │   │  bridges (runtime):    │ │
                                                         │   │   (:Service)-[:IS_OF]->│ │
                                                         │   │       (:AssetType)     │ │
                                                         │   └────────────────────────┘ │
                                                         └──────────────────────────────┘
```

Key shift vs. the original v0.2 diagram: **Neo4j is owned by the skillogy service, not by `SkillogyMiddleware`**. The agent process never opens a Bolt connection. This preserves the original `decepticon.skillogy.*` package's intent (skill-as-a-service over a wire protocol) and makes the langgraph image catalog-free at the end of Phase 1a.

### 3.2 Component decomposition

| Component | Location | Responsibility |
|---|---|---|
| `skillogy.builder` | `packages/decepticon/decepticon/skillogy/builder/` (NEW) | CI build pipeline: parse SKILL.md, import MITRE STIX, validate, emit `skills.cypher` |
| `skillogy.proto` | `packages/decepticon/decepticon/skillogy/proto/` (REWRITTEN) | Wire protocol definitions (gRPC `.proto` + matching Python types). Source of truth for both transports. |
| `skillogy.server` | `packages/decepticon/decepticon/skillogy/server/` (REWRITTEN) | FastAPI + grpcio app. Owns the Neo4j driver, loads `skills.cypher` at boot, serves `/v1/skills:{load,traverse,cypher_read,recall}` over REST + gRPC. Read-only query enforcement lives here. |
| `skillogy.client` | `packages/decepticon/decepticon/skillogy/client/` (REWRITTEN) | Async REST + gRPC client used by `SkillogyMiddleware`. No Neo4j dependency. |
| `skillogy.middleware` | `packages/decepticon/decepticon/middleware/skillogy.py` (REWRITTEN) | Runtime middleware: instantiates a `SkillogyClient`, fetches the MoC summary, registers tools. **Does NOT open a Bolt connection.** |
| `skillogy.tools` | `packages/decepticon/decepticon/tools/skillogy.py` (NEW) | The 3–4 agent-facing `@tool` functions — each just calls the client. |
| `skillogy.validation` | `packages/decepticon/decepticon/skillogy/validation.py` (NEW) | Cypher-rule validator run by CI (build-time, not runtime). |
| `skills.cypher` | `packages/decepticon/decepticon/skills/.graph/skills.cypher` (NEW, checked in) | Deterministic Cypher dump produced by `skillogy.builder`. **Baked into the skillogy container image at build time**; the langgraph image does not need it. |
| `containers/skillogy.Dockerfile` | (REWRITTEN) | Now builds an image that contains `skills.cypher` + the server, exposing REST (default 9100) and gRPC (default 50051). |
| `docker-compose.yml` skillogy service | (REWRITTEN) | Same compose entry, new image. Talks to Neo4j on the existing `decepticon-net`. |
| `langgraph` image | (TRIMMED at Phase 1a final cutover) | Drops `COPY packages/decepticon/decepticon/skills` once `SkillogyMiddleware` is the only path. See §5.11. |

### 3.3 Phase split

```
Phase 0   Skill Corpus Cleanup        ~4-6 weeks   gated by user PR review
Phase 1a  Brain Anatomy                ~6 weeks    graph + MITRE + Cypher
Phase 1b  Associative Memory          ~3-4 weeks   embeddings + recall + PPR
Phase 2   LLM-inferred edges          (later)     REQUIRES, APPLICABLE_TO
Phase 3   Plasticity + Capability     (later)     trace feedback, planning
```

Each phase is **schema-additive**. Phase 1b adds a property and a tool; Phase 2 adds edges with provenance; Phase 3 adds labels. No phase requires re-engineering its predecessor's output.

---

## 4. Phase 0 — Skill Corpus Cleanup

**Goal**: 251 `SKILL.md` files conform to a canonical schema. All MITRE mappings are valid for one of {Enterprise, Mobile, ICS, ATLAS}. Subdomain duplicates are collapsed. Validation script enforces the schema in CI.

### 4.1 Deliverables

1. **Canonical schema spec** — `docs/skill-schema.md`. Defines required vs optional frontmatter fields, MITRE ID format rules, YAML style.
2. **Canonical subdomain list** — ~20 phases. Aliases (`reverser`, `contracts`, `cloud-native`) renamed in source.
3. **`tools/validate_skills.py`** — frontmatter parser + schema checker + MITRE format validator. CI-blocking after cleanup completes.
4. **Cleanup PRs** — batched by subdomain. MITRE backfill for the 65 unmapped skills. Frontmatter completion for the 44 metadata-less files.
5. **Content audit notes** — `docs/skill-audit-2026-06.md`. Flags description-vs-body mismatches, stale techniques, broken references, domain misplacement (e.g., SQL injection found under `/skills/standard/recon/`). Each flagged issue becomes a separate follow-up issue; Phase 0 does not rewrite bodies.
6. **Authoring contract** — `CONTRIBUTING-skills.md` or section. New skill PRs must pass the validator.

### 4.2 Execution model — Co-design

For each subdomain batch:

1. **Sub-agent** reads all SKILL.md in the batch, proposes:
   - Canonical schema patch per file (frontmatter normalization)
   - MITRE mapping recommendation (with reasoning from body content)
   - Flag-suspicious issues (description-vs-body mismatch, stale, misplaced)
2. **User reviews** proposed PR — accepts, modifies, or rejects per file.
3. **Sub-agent commits** the approved patch as a PR. CI runs `validate_skills.py` (warn mode during Phase 0).
4. **Next batch.**

This produces a deterministic, reviewable cleanup. The validator is built and iterated alongside the first batches (D-1 user decision: Co-design over Tooling-first).

### 4.3 Sub-decisions (defaults; can be revised before Phase 0)

| ID | Decision | Default |
|---|---|---|
| D-2 | MITRE mapping for the 65 unmapped skills | Sub-agent recommends from body content; user reviews each batch PR |
| D-3 | Content audit scope | Frontmatter normalization + **flag-suspicious** body issues for separate follow-up. No body rewrites in Phase 0. |
| D-4 | Production compat during cleanup | Existing `SkillsMiddleware` (lenient parser) keeps working on cleaned-up files. CI validation is warn-mode during Phase 0, blocks after Phase 0 completes. |

### 4.4 Canonical frontmatter schema (target)

The schema is intentionally lean — only fields that the current production middleware uses (`subdomain`, `when_to_use`, `mitre_attack`, `tags`) or that have raw preservation value (`aatmf_tactic`, `upstream_ref`) survive. Dead fields are removed during Phase 0 cleanup, not migrated forward.

```yaml
name: <slug>                     # REQUIRED, unique across corpus
description: |                   # REQUIRED, one-line
  <one-line skill summary>

metadata:
  subdomain: <canonical>         # REQUIRED, must be in subdomains.yaml
  when_to_use: |                 # REQUIRED, comma-separated triggers
    <kw1>, <kw2>, ...
  mitre_attack:                  # REQUIRED unless under /skills/*/reporting/ or /skills/*/analyst/
    - T1190                      #   Enterprise / Mobile  T1xxx[.xxx]   ← graph edges in Phase 1a
    - T1595.001                  #   Enterprise / Mobile  T1xxx[.xxx]   ← graph edges in Phase 1a
    - T0800                      #   ICS                  T0xxx[.xxx]   ← raw only in Phase 1a, edges later
    - AML.T0043                  #   ATLAS                AML.Txxxx     ← raw only in Phase 1a, edges later
  tags:                          # OPTIONAL, free-form list
    - web-recon
    - http

  # Raw preservation. Not modeled as edges in Phase 1a.
  aatmf_tactic: [...]            # OPTIONAL, AATMF v3.x (15 files today)
  upstream_ref: <ref>            # OPTIONAL, external skill reference (14 files today)
```

**Fields removed by Phase 0 cleanup** (audit-confirmed dead in production — see §1.3):
- `allowed-tools` — never read by Decepticon middleware; tool dispatch is not skill-gated.
- `metadata.kind` — only 4 occurrences; offensive vs reporting is inferred from path.
- `metadata.safety_critical`, `metadata.gated_by_conops` — 1 occurrence each; SaaS-gating placeholders not in production.

The validator rejects:
- Missing `name`, `description`, `subdomain`, `when_to_use`.
- Skill outside `/skills/*/reporting/` and `/skills/*/analyst/` paths with empty `mitre_attack` AND empty `aatmf_tactic` AND empty `upstream_ref` (an attack skill with no provenance attribution at all).
- Any `mitre_attack` entry that doesn't match one of: Enterprise/Mobile `T\d{4}(\.\d{3})?`, ICS `T0\d{3}(\.\d{3})?`, ATLAS `AML\.T\d{4}(\.\d{3})?`.
- `subdomain` not in the canonical list.

> Note: Phase 1a only produces `IMPLEMENTS` graph edges for Enterprise-namespaced `T\d{4}` values that match a built `:Technique`. Mobile `T1xxx`, ICS `T0xxx`, and ATLAS `AML.T` values are syntactically valid but stay in `mitre_attack_raw` until their importers land (Phase 1b / 2).

### 4.5 Canonical subdomain list (initial proposal, to be locked during Phase 0)

`reconnaissance`, `initial-access`, `execution`, `persistence`, `privilege-escalation`, `defense-evasion`, `credential-access`, `discovery`, `lateral-movement`, `collection`, `command-and-control`, `exfiltration`, `impact`, `ad`, `cloud`, `web-exploitation`, `mobile`, `ics-ot`, `iot`, `wireless`, `ai-security`, `reverse-engineering`, `dfir`, `osint`, `phishing`, `smart-contracts`, `reporting`, `planning`, `orchestration`, `adversary-emulation`.

Aliases resolved at cleanup:
- `reverser` → `reverse-engineering`
- `contracts` → `smart-contracts`
- `cloud-native` → `cloud`
- `ad` → kept (commonly used) — `active-directory` becomes alias of `ad` OR vice-versa (lock during Phase 0)

---

## 5. Phase 1a — Brain Anatomy

**Scope**: Neo4j graph schema with MITRE matrices, CI build pipeline that compiles `SKILL.md` → `skills.cypher`, a skillogy service (REST + gRPC, Neo4j-backed) that loads the dump on boot and serves agents over the wire, and a thin-client `SkillogyMiddleware` that exposes three agent tools by delegating to the service.

### 5.1 Graph schema — node labels

| Label | Purpose | Key properties | Source |
|---|---|---|---|
| `:Skill` | One `SKILL.md` file | name (unique), path (unique), description, body, content_sha256, size_bytes, subdomain, when_to_use, mitre_attack_raw, tags_raw, aatmf_tactic_raw, upstream_ref_raw, commit_sha, built_at — see §5.2 for full contract and §1.4 for fields explicitly dropped | builder, from frontmatter |
| `:Phase` | Kill-chain / domain phase | name (unique), kill_chain_order, description | seed (canonical subdomain list) |
| `:AssetType` | Engagement asset taxonomy | name (unique), category | seed (Phase 1a starter ~35 nodes) |
| `:Tag` | Free-form tag (controlled vocab deferred) | name (unique) | from `metadata.tags` |
| `:MoC` | Map-of-Concepts navigation category | name (unique), description, parent_phase | seed + computed |
| `:Tactic` | MITRE tactic | id (unique, e.g. `TA0001`), name, description, matrix, framework, attck_version, deprecated, revoked | STIX importer (Phase 1a: Enterprise) |
| `:Technique` | MITRE technique or sub-technique | id (unique, e.g. `T1190` / `T1595.001`), name, description, **matrix**, **framework**, is_subtechnique, parent_id, platforms[], attck_version, deprecated, revoked | STIX importer (Phase 1a: Enterprise) |
| `:MatrixVersion` | Imported matrix bundle version (idempotency key) | matrix (unique), version, released_at, imported_at | STIX importer |

Notes:
- Single `:Technique` label is **kept** even though Phase 1a only loads Enterprise — `matrix ∈ {enterprise, mobile, ics, atlas}` and `framework ∈ {attack, atlas}` are reserved enum values so Phase 1b/2 can drop in ICS/Mobile/ATLAS importers without label refactoring. This follows the OSS-standard pattern (Ontolocy, pyattck, attackcti).
- Phase 1a populates only `matrix: "enterprise"`, `framework: "attack"`. ICS T0xxx and ATLAS AML.T values from frontmatter are preserved on `:Skill.mitre_attack_raw` but produce no `:Technique` nodes or `IMPLEMENTS` edges until those importers land.
- `:MatrixVersion` exists so re-imports are idempotent and traceable.

### 5.2 `:Skill` node — full property contract

The schema is slim by design. Every field listed is either (a) used by the current production SkillsMiddleware system prompt, (b) needed by the graph build itself, or (c) raw preservation of frontmatter that has author-side semantic value even if Phase 1a does not yet turn it into edges. **Fields that the production middleware never reads (`allowed-tools`, `metadata.kind`, `metadata.safety_critical`, `metadata.gated_by_conops`) are deliberately dropped** — see §1.3 audit findings.

```cypher
(:Skill {
  // === identity (UNIQUE, required) ===
  name: STRING,                  // slug
  path: STRING,                  // canonical /skills/.../SKILL.md
  description: STRING,

  // === content (required) ===
  body: STRING,                  // full markdown after frontmatter strip
  content_sha256: STRING,        // "sha256:" + hex(body)
  size_bytes: INT,

  // === active frontmatter (present in production system prompt today) ===
  subdomain: STRING,             // canonical, matches :Phase.name
  when_to_use: STRING,           // raw triggers (free text)

  // === raw preservation (debug, round-trip, future edge promotion) ===
  mitre_attack_raw: LIST<STRING>,    // ALL mitre values; Enterprise → IMPLEMENTS, others raw
  tags_raw: LIST<STRING>,            // also promoted to :Tag edges
  aatmf_tactic_raw: LIST<STRING>,    // AATMF v3.x — 15 files; raw only in Phase 1a
  upstream_ref_raw: STRING,          // external skill reference — 14 files

  // === build lineage ===
  commit_sha: STRING,            // git HEAD at build time
  built_at: DATETIME

  // Phase 1b will add:
  // , embedding: LIST<FLOAT>     // 1536-dim vector
})
```

**Explicitly NOT included** (vestigial in production):
- `allowed_tools` — `deepagents.middleware.skills.SkillsMiddleware` parses it, but the Decepticon override replaces the base system prompt entirely without using it, and no tool dispatch logic enforces it. 138 frontmatter occurrences but 0 production code paths consume them.
- `kind` — only 4 of 251 files declare it; no production code branches on it. Whether a skill is offensive vs reporting is inferred from path (`/skills/*/reporting/` and `/skills/*/analyst/` are non-offensive). The R3 validation rule (§5.9) uses path inference, not the `kind` field.
- `safety_critical`, `gated_by_conops` — 1 file each, aspirational SaaS-gating placeholders from the 2026-05-28 v0.1 spec. Re-introduce only when SaaS gating is a concrete shippable requirement.

### 5.3 `:Technique` node — matrix-aware

```cypher
(:Technique {
  id: STRING,                    // UNIQUE
  matrix: STRING,                // enterprise | mobile | ics | atlas
  framework: STRING,             // attack | atlas
  name: STRING,
  description: STRING,
  is_subtechnique: BOOL,
  parent_id: STRING,             // e.g. "T1595" for "T1595.001"; "" for top
  platforms: LIST<STRING>,       // ["Windows","Linux","Containers",...]
  attck_version: STRING,         // "19.1" / "5.4"
  deprecated: BOOL,
  revoked: BOOL
})
```

### 5.4 Edge inventory (Phase 1a)

| Edge | From → To | Source |
|---|---|---|
| `IN_PHASE` | `:Skill` → `:Phase` | `metadata.subdomain` |
| `IMPLEMENTS` | `:Skill` → `:Technique` | `metadata.mitre_attack` Enterprise entries (validated); non-Enterprise entries stay in `mitre_attack_raw` |
| `TAGGED` | `:Skill` → `:Tag` | `metadata.tags` |
| `BELONGS_TO` | `:Skill` → `:MoC` | computed (subdomain → MoC seed mapping) |
| `RELATED_TO` | `:Skill` → `:Skill` | optional frontmatter `related[]` (introduced in Phase 0) |
| `HAS_TECHNIQUE` | `:Tactic` → `:Technique` | STIX (Enterprise) |
| `HAS_SUBTECHNIQUE` | `:Technique` → `:Technique` | STIX (Enterprise) |

Reserved labels/edges (defined in schema, populated in later phases):
- `MAPS_TO` (`:Technique` → `:Technique`) — Cross-matrix mapping (ATLAS↔Enterprise from combined STIX bundle); lands when ATLAS importer lands.
- `:Capability`, `PRODUCES` / `CONSUMES` — Phase 3 (STRIPS-style planning).
- `:Tool`, `USES_TOOL` — Phase 2 (tools extracted from skill body content — e.g. `nmap`, `sqlmap` mentions — when traversal value is concrete; the `allowed-tools` frontmatter field is dropped per §1.4 audit, so the `:Tool` population path is body-side, not frontmatter-side).
- `:RoEConstraint`, `FORBIDDEN_BY` — Phase 3.
- `:Agent`, `CAN_USE` — Phase 2.
- `REQUIRES`, `APPLICABLE_TO` (LLM-inferred) — Phase 2.

### 5.5 MITRE STIX importer (Enterprise only in Phase 1a)

Implemented as `skillogy.builder.mitre`. Strategy:

- **One importer**, parameterized by `(matrix, framework, stix_url)`. The parameterization is kept generic so adding Mobile / ICS / ATLAS in later phases is a config addition, not a rewrite.
- **Phase 1a pinned URL**:
  - Enterprise: `mitre-attack/attack-stix-data/enterprise-attack/enterprise-attack-19.1.json` (verified latest as of 2026-06-03; next major v20 expected ~2026-10)
- **Phase 1a v19.1 hazards** (handled by importer):
  - `TA0005` renamed Defense Evasion → Stealth; new `TA0112` Defense Impairment. Importer applies a known-rename map so legacy frontmatter referencing the old name still resolves correctly.
- **Validation**: any frontmatter `mitre_attack` entry matching Enterprise format `T\d{4}(\.\d{3})?` that does not match a built `:Technique.id` is a build-time error (after Phase 0 cleanup). Non-Enterprise entries (`T0xxx`, `AML.T...`) are syntactically validated but not required to resolve to a node — they live in `mitre_attack_raw`.
- **Future matrices** (Phase 1b/2): same importer class, additional pinned URLs (`mobile-attack-19.1.json`, `ics-attack-19.1.json`, ATLAS combined bundle). When each lands, raw frontmatter values get promoted to `IMPLEMENTS` edges automatically on the next build (no SKILL.md edit required).

Version pinning is explicit. Bumping a matrix version is a manual PR (no silent picks-up-newer).

### 5.6 CI build pipeline (`skillogy.builder`)

```
packages/decepticon/decepticon/skillogy/builder/
├── __init__.py
├── __main__.py                   # `python -m decepticon.skillogy.builder`
├── frontmatter.py                # SKILL.md → :Skill + IN_PHASE/IMPLEMENTS/TAGGED/RELATED_TO
├── mitre.py                      # 4-matrix STIX importer
├── seeds/
│   ├── subdomains.yaml           # canonical phase list
│   ├── moc.yaml                  # Map-of-Concepts seed
│   └── asset_types.yaml          # Phase 1a starter ~35 nodes
├── seed.py                       # apply YAML seeds → :Phase / :MoC / :AssetType
├── validate.py                   # Cypher rules (see §5.9)
├── emit.py                       # → skills/.graph/skills.cypher (deterministic order)
└── manifest.py                   # → skills/.graph/manifest.json (counts, version pins)
```

CLI:

```bash
python -m decepticon.skillogy.builder            # full build
python -m decepticon.skillogy.builder --validate # rules only, no write
python -m decepticon.skillogy.builder --diff     # show diff vs checked-in dump
```

**Stages** (in order):

1. Clear `skill_graph` labels (`{Skill, Phase, AssetType, Tag, MoC, Tactic, Technique, MatrixVersion}`). Attack-graph labels untouched.
2. Apply constraints + indexes (§5.8).
3. Import MITRE STIX (Enterprise v19.1 only in Phase 1a). Emit `:Tactic`, `:Technique`, `HAS_TECHNIQUE`, `HAS_SUBTECHNIQUE`. `MAPS_TO` is reserved for when ATLAS imports later.
4. Seed `:Phase`, `:MoC`, `:AssetType` from YAML.
5. Parse `SKILL.md`. Emit `:Skill` (with body + raw frontmatter), `IN_PHASE`, `IMPLEMENTS`, `TAGGED`, `BELONGS_TO`, `RELATED_TO`.
6. Validate (§5.9). Build fails on any rule violation.
7. Emit `skills.cypher` (deterministic order — sorted by node name, then edge type, then target).
8. Emit `manifest.json` (counts per label, validation results, matrix version pins, build time).
9. CI step: `git diff skills.cypher manifest.json` ≠ ∅ → PR comment summarizing the change.

Determinism is enforced: the dump is checked into git; CI re-builds and asserts the dump matches what is checked in.

### 5.7 Agent tool surface (Phase 1a — 3 tools)

> **Amended (v0.2.2):** the three tools are now `find_skill`, `load_skill`, and `traverse`. §5.7.3 `run_cypher_read` is **removed from the agent surface** (the backend method is retained for internal use). See "Amendment v0.2.2" at the top of this document for rationale.

#### 5.7.1 `load_skill(name_or_path: str) -> str`

Fetch a single skill node and return its body + metadata as a structured envelope. Replaces the existing `load_skill` semantics; signature compatible with current SkillsMiddleware so agent prompts do not need re-training.

```cypher
MATCH (s:Skill {name: $arg}) RETURN s
// OR
MATCH (s:Skill {path: $arg}) RETURN s
```

Returns body, frontmatter metadata, and a list of `RELATED_TO` neighbors (names + descriptions) so the agent can decide whether to traverse further.

#### 5.7.2 `traverse(start: str, edges: list[str], depth: int = 2) -> list[dict]`

Generic typed BFS. Returns reachable nodes (skill + technique + phase + tag) with the path that connected them.

Whitelist of edges (Phase 1a): `IN_PHASE`, `IMPLEMENTS`, `TAGGED`, `BELONGS_TO`, `RELATED_TO`, `HAS_TECHNIQUE`, `HAS_SUBTECHNIQUE`, `MAPS_TO`. Empty list = all.

Example: `traverse("web-recon", ["RELATED_TO","IMPLEMENTS","HAS_TECHNIQUE"], depth=2)` returns the skill, related skills, the techniques it implements, and the tactics those techniques belong to.

#### 5.7.3 `run_cypher_read(query: str, params: dict | None = None) -> list[dict]`

Read-only Cypher escape hatch. Implementation:

- Neo4j session opened with `default_access_mode=READ` (driver-side enforcement).
- Parameterized; agent provides `params`.
- Result row count capped (e.g. 200) to prevent context blow-up.
- The Skillogy schema cheat-sheet (labels, edges, key properties) is injected into the agent system prompt so the LLM can construct queries without trial-and-error.

This is the "brain" capability that lets agents ask any question the curated tools don't anticipate.

#### Read-only enforcement

Three layers, in order of preference:

1. **Driver session**: Neo4j Python driver supports `default_access_mode="READ"`. The session refuses writes server-side — the canonical defense.
2. **Cypher syntactic check** (belt-and-suspenders): reject queries containing `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DETACH`, `CALL apoc.*write*`, etc. before sending.
3. **Neo4j role**: in production, the agent connects with a dedicated user that lacks write permissions on the skill_graph labels.

In Phase 1a we require (1) and (2). (3) is a Phase 1b operational hardening.

### 5.8 Constraints + indexes (Phase 1a)

```cypher
CREATE CONSTRAINT skill_name_unique IF NOT EXISTS
  FOR (s:Skill) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT skill_path_unique IF NOT EXISTS
  FOR (s:Skill) REQUIRE s.path IS UNIQUE;
CREATE CONSTRAINT tactic_id_unique IF NOT EXISTS
  FOR (t:Tactic) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT technique_id_unique IF NOT EXISTS
  FOR (t:Technique) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT phase_name_unique IF NOT EXISTS
  FOR (p:Phase) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT asset_type_name_unique IF NOT EXISTS
  FOR (a:AssetType) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT tag_name_unique IF NOT EXISTS
  FOR (t:Tag) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT moc_name_unique IF NOT EXISTS
  FOR (m:MoC) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT matrix_version_unique IF NOT EXISTS
  FOR (m:MatrixVersion) REQUIRE m.matrix IS UNIQUE;

CREATE INDEX skill_subdomain  IF NOT EXISTS FOR (s:Skill) ON (s.subdomain);
CREATE INDEX technique_matrix IF NOT EXISTS FOR (t:Technique) ON (t.matrix);
CREATE INDEX technique_revoked IF NOT EXISTS FOR (t:Technique) ON (t.revoked);
```

### 5.9 Validation rules (build-time, `validate.py`)

```cypher
-- R1: every skill is in a phase (no orphans)
MATCH (s:Skill)
WHERE NOT (s)-[:IN_PHASE]->(:Phase)
RETURN s.name AS violation_orphan_skill;

-- R2: no RELATED_TO self-loop
MATCH (s:Skill)-[:RELATED_TO]->(s)
RETURN s.name AS violation_related_self_loop;

-- R3: every offensive skill has either an IMPLEMENTS edge or a non-empty raw mapping.
--     "offensive" is inferred from path — anything outside /skills/*/reporting/
--     and /skills/*/analyst/ is treated as offensive.
MATCH (s:Skill)
WHERE NOT (s.path =~ '/skills/[^/]+/(reporting|analyst)/.*')
  AND NOT (s)-[:IMPLEMENTS]->(:Technique)
  AND size(coalesce(s.mitre_attack_raw, [])) = 0
  AND size(coalesce(s.aatmf_tactic_raw, [])) = 0
  AND coalesce(s.upstream_ref_raw, '') = ''
RETURN s.name AS violation_no_attribution;

-- R4: TA0xxx never appears as IMPLEMENTS target (tactic IDs are not techniques)
MATCH (s:Skill)-[:IMPLEMENTS]->(t:Tactic)
RETURN s.name, t.id AS violation_tactic_as_technique;

-- R5: no deprecated / revoked technique mappings
MATCH (s:Skill)-[:IMPLEMENTS]->(t:Technique)
WHERE t.deprecated = true OR t.revoked = true
RETURN s.name, t.id AS violation_deprecated_mapping;

-- R6: subdomain matches an IN_PHASE phase name
MATCH (s:Skill)
WHERE NOT EXISTS {
  MATCH (s)-[:IN_PHASE]->(p:Phase) WHERE p.name = s.subdomain
}
RETURN s.name, s.subdomain AS violation_subdomain_phase_mismatch;

-- W1 (warning, not failure): over-used technique (≥ 15 skills mapped to one technique)
MATCH (s:Skill)-[:IMPLEMENTS]->(t:Technique)
WITH t.id AS tech_id, count(s) AS n
WHERE n >= 15
RETURN tech_id, n AS warning_over_used_technique;
```

R1–R6 fail the build; W1 is informational on the PR diff comment.

> Note on R3: the rule treats "offensive" as a path attribute rather than a frontmatter field because `metadata.kind` is dead in production (4/251 occurrences, 0 readers). The path inference is concrete, derivable from existing data, and survives any future authoring rename without an extra frontmatter migration. The "non-empty raw mapping" leg of the rule lets ICS / ATLAS / AATMF-tagged skills pass even though Phase 1a only emits `IMPLEMENTS` edges for Enterprise.

### 5.10 Runtime middleware (`SkillogyMiddleware`)

> **Amended (v0.2.2):** `workflow.md` is **no longer loaded by the middleware** — it is concatenated into the cacheable static prefix by `PromptBuilder` at agent factory time. The middleware injects two fragments only: a static graph schema cheat-sheet and a dynamic per-phase MoC summary queried via `Neo4jBackend.query_moc_summary(phase)`. The four-tool `get_tools()` example below is reduced to three (`run_cypher_read` removed). See "Amendment v0.2.2" at the top of this document for rationale.

`SkillogyMiddleware` extends `langchain.agents.middleware.AgentMiddleware` directly — **not** a subclass of `deepagents.middleware.skills.SkillsMiddleware`. The graph is the canonical schema; we do not inherit deepagents' frontmatter parsing, `SkillMetadata` TypedDict, or three-stage progressive disclosure scheme.

Two responsibilities orthogonal to the graph are preserved from the current Decepticon `SkillsMiddleware`:

1. **`workflow.md` auto-load**: for each configured skill source (e.g. `/skills/standard/recon/`), read the sibling `workflow.md` body into `state.workflow_content` so the agent loop has its phase workflow, scope rules, and handoff format loaded before any tool call. Implementation lives next to (not inside) the graph machinery.
2. **MoC summary injection**: a ~300-token navigation map for the current agent's phase is appended to the system prompt — same pattern as today's catalog injection but radically smaller.

```python
class SkillogyMiddleware(AgentMiddleware):
    """Replaces both decepticon.middleware.skills.SkillsMiddleware and
    its deepagents base. Thin client of the skillogy service container;
    holds no Neo4j connection of its own."""

    def __init__(
        self,
        *,
        skillogy_url: str,           # e.g. "http://skillogy:9100" (REST) or "grpc://skillogy:50051"
        skill_sources: list[str],    # for workflow.md auto-load, e.g. ["/skills/standard/recon/"]
        agent_phase: str,            # injected by the agent factory
        backend: BackendProtocol,    # for workflow.md reads (filesystem backend)
        api_key: str | None = None,  # SKILLOGY_API_KEY, optional bearer-token auth
        transport: Literal["rest", "grpc"] = "rest",
    ) -> None:
        self._client = build_skillogy_client(
            url=skillogy_url, api_key=api_key, transport=transport
        )
        self._sources = skill_sources
        self._phase = agent_phase
        self._backend = backend

    async def abefore_agent(self, state, runtime, config):
        # 1. Health-check the service; fail fast on misconfig.
        await self._client.health()
        # 2. Preserve workflow.md auto-load (current Decepticon middleware behavior).
        #    workflow.md stays in-process — it's not part of the graph.
        workflow_blob = await load_workflow_blob(self._backend, self._sources)
        # 3. Pull a ~300-token MoC summary for the agent's current phase.
        moc_summary = await self._client.moc_summary(phase=self._phase)
        return {
            "workflow_content": workflow_blob,
            "skillogy_prompt": render_skillogy_guide(moc_summary, schema_cheatsheet()),
        }

    def get_tools(self) -> list:
        # Each tool is a thin wrapper that calls the client.
        return [
            build_load_skill_tool(self._client),
            build_traverse_tool(self._client),
            build_run_cypher_read_tool(self._client),
        ]
```

Notes:

- The middleware imports nothing from `neo4j`. The `langgraph` container does not need the Neo4j driver to be installed.
- `build_skillogy_client` returns either a REST or gRPC implementation behind a shared `SkillogyClient` Protocol. Default REST keeps OSS deployments simple; gRPC is opt-in for performance-sensitive operators.
- The `decepticon-skillogy-skillogy` compose service is the authoritative owner of the schema cheat-sheet — the middleware fetches it from `/v1/skills:schema` on first use and caches it per-process. This way schema drift cannot desync the agent prompt from the live graph.

The injected system prompt (~300 tokens) carries:
- The always-loaded workflow (`workflow.md` body — unchanged behavior, still in-process).
- The current phase's MoC summary fetched from the skillogy service ("you are in reconnaissance; concepts: passive-recon, active-recon, web-recon, ad-recon").
- The Skillogy schema cheat-sheet (labels, edges, key properties, two example queries) so the agent can write Cypher without trial-and-error.
- The 3-tool usage policy: "call `load_skill` to fetch a known skill; `traverse` to walk relations; `run_cypher_read` for anything else."

### 5.11 Migration (Phase 1a)

- New env flag: `DECEPTICON_SKILL_BACKEND ∈ {skills, skillogy_brain}` (default `skills`).
- New env vars for the client side: `DECEPTICON_SKILLOGY_URL` (default `http://skillogy:9100`), `DECEPTICON_SKILLOGY_API_KEY` (optional). These are read by `SkillogyMiddleware.from_env()`.
- Existing `SkillsMiddleware` is kept and continues to read SKILL.md files. After Phase 0 cleanup, both backends operate on the same canonical corpus.
- The current `decepticon.skillogy.*` REST/proto/client package is **rewritten in place**, not deleted. The wire surface (4 RPC methods + Bearer-token auth) is preserved; the storage backend swaps from in-memory dict to Neo4j; new RPCs (`Traverse`, `CypherRead`, `MocSummary`, `Schema`) are added. The `DECEPTICON_USE_SKILLOGY` flag is renamed `DECEPTICON_SKILL_BACKEND` for clarity but the legacy name accepts a compat shim for one minor cycle.
- Agent-by-agent rollout: specialists opt in to `skillogy_brain` one at a time. Benchmark per agent before moving the next.
- A 50-case routing benchmark + token-cost comparison gates the global default flip.
- After one release cycle on the new backend as default:
  1. `SkillsMiddleware` is removed.
  2. The `langgraph` container image stops copying `packages/decepticon/decepticon/skills/` into `/app/skills/`. SKILL.md continues to live in git, but only the skillogy image carries them at runtime. This shrinks the agent image and removes a stale-catalog footgun (langgraph and skillogy holding divergent SKILL.md copies).

### 5.12 Observability (Phase 1a)

- **Server-side**: every Cypher query executed by the skillogy service is OpenTelemetry-traced (existing exporter). Span attributes: `skillogy.rpc` (load_skill/traverse/cypher_read/moc_summary), `skillogy.tenant`, `skillogy.engagement`, query text hash, row count.
- **Client-side** (middleware in the langgraph image): each tool call is a LangSmith span with `skill.tool`, `skill.name`, `skill.matched_phase`, `skill.traversal_depth`, plus the wire latency. The middleware does not log Cypher; only the service does.
- **Trace correlation**: the middleware emits a `traceparent` header on every REST/gRPC call so the agent-side LangSmith span and the service-side OTel span share a trace.
- **Per-engagement metrics**: count of skill loads, hit rate of `run_cypher_read` vs `load_skill`, distribution of which MITRE matrices were touched. Aggregated at the service so SaaS dashboards do not depend on every agent runtime forwarding metrics.

### 5.13 Testing strategy (Phase 1a)

- **Builder unit tests**: frontmatter parser, MITRE importer (one fixture per matrix), seed loader, validator rules (one negative case per R1–R6).
- **Builder property tests**: re-build is bit-identical for the same input (determinism).
- **Server unit tests**: per-RPC handler against an in-memory or stub Neo4j driver. Asserts request shape, auth enforcement, parameter validation, error mapping.
- **Server integration tests**: ephemeral Neo4j via testcontainers + fixture `skills.cypher` load + each RPC invoked end-to-end.
- **Read-only enforcement tests** (server-side): assert `run_cypher_read` / `cypher_read` RPC rejects `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DETACH`, write-mode APOC calls, etc. via both Cypher-AST analysis and Neo4j session `default_access_mode=READ`.
- **Client unit tests**: mock httpx + grpcio transports; assert request serialisation, retry, auth header propagation, error mapping back to `SkillogyClientError`.
- **Middleware integration tests**: a fake `SkillogyClient` implementation; assert tool outputs match documented schema; workflow.md auto-load still fires.
- **End-to-end smoke**: `make dogfood` with `DECEPTICON_SKILL_BACKEND=skillogy_brain`. The dogfood stack now boots the skillogy container alongside langgraph; assert one agent boots, calls `load_skill` over REST, and executes one tool call.
- **Routing benchmark**: 50-case set against current `SkillsMiddleware` baseline. Metrics: routing accuracy (skill picked matches gold), missed-skill rate, token cost per engagement, p95 wire latency for `load_skill` / `traverse` / `cypher_read`.

---

## 6. Phase 1b — Associative Memory

### 6.1 Scope

Add semantic recall on top of the structural graph. Three changes:

1. `:Skill.embedding: LIST<FLOAT>` (1536-dim default; model-configurable).
2. Neo4j vector index on `:Skill.embedding` (cosine).
3. A fourth agent tool, `recall(query, asset_hint?, k=10)`, that blends semantic similarity (vector search) with structural activation (PPR) and returns ranked skills with reasoning paths.

This is what makes the system "brain-like" in the associative sense: a vague query retrieves the right skill even when no exact tag matches.

### 6.2 Embedding pipeline

- Embedding text per skill: `name + "\n" + description + "\n" + body`. Truncated at model max.
- Model: configurable via LiteLLM. Default `text-embedding-3-small` (1536). Local fallback `bge-small-en` (384) for offline / SaaS-isolated cases.
- Embeddings are produced at CI build time (deterministic with `temperature=0`, fixed model version pin) and embedded into `skills.cypher` as vector literals. The dump remains the single artifact; no separate embedding store.

### 6.3 `recall` tool semantics

```
recall(query, asset_hint=None, k=10) ->
  1. vector_seed = vector search top-K_v over :Skill.embedding by cosine(query_embedding, s.embedding)
  2. (optional) filter to skills in current phase / matching asset_hint
  3. structural_expand = PPR (APOC pageRank) seeded by vector_seed, walking
       REQUIRES, RELATED_TO, IMPLEMENTS, APPLICABLE_TO (Phase 2 edges where present)
  4. blended ranking: alpha * vector_score + (1-alpha) * structural_score
  5. return top-K with reasoning path (which edges contributed)
```

Personalized PageRank via APOC (`apoc.algo.pageRankWithSeed`) — GDS not required. If GDS is available (cluster-side install), use `gds.pageRank.stream`.

### 6.4 Performance budget

- Vector search on 251 nodes: sub-10 ms (Neo4j vector index is HNSW-backed).
- PPR over a ~500-edge skill subgraph: sub-50 ms.
- Total `recall` call budget: ≤ 100 ms p95.

### 6.5 Migration

Phase 1b is schema-additive. Set `:Skill.embedding` on existing nodes during the next CI build; vector index creation is idempotent. Old tools (`load_skill`, `traverse`, `run_cypher_read`) keep working.

---

## 7. Phase 2 — LLM-Inferred Edges + `:Tool` / `:Agent` / `:RoEConstraint`

Defer until Phase 1b benchmarks demonstrate the structural + semantic plane is insufficient.

- `(:Skill)-[:REQUIRES]->(:Skill)` — prerequisite inferred from body.
- `(:Skill)-[:APPLICABLE_TO]->(:AssetType)` — refined assetability inferred from body.
- Each inferred edge carries `confidence`, `provenance='body-llm'`, `justification`, `inferred_at`, `inferrer_model`.
- LLM inference runs at build time (deterministic seed, pinned model version), output checked into `skills.cypher` for PR review. No runtime LLM calls.

Promotes `:Tool` / `:Agent` / `:RoEConstraint` from reserved schema to populated.

---

## 8. Phase 3 — Plasticity + Capability Plane

- **Plasticity**: engagement-trace feedback strengthens `:CO_ACTIVATED` edge weights between skills used in success paths. Requires a stable trace pipeline.
- **Capability plane**: `:Capability` nodes + `PRODUCES` / `CONSUMES` edges + `get_skill_chain(target_capability)` tool — STRIPS-style backward planning.
- **RoE filtering**: `FORBIDDEN_BY` edges filter skills out of results based on the current engagement's RoE.

Out of scope for this design doc; tracked here only to confirm that the Phase 1a schema does not foreclose them.

---

## 9. Open Questions

| ID | Question | Likely resolution |
|---|---|---|
| OQ-1 | ATLAS releases at higher cadence than ATT&CK (~quarterly+). Bump policy in CI? | Pin to released version; auto-PR on new release; human reviews diff before merge. |
| OQ-2 | Controlled vocabulary for `tags` — when does it become required? | Defer to Phase 1b or later. Free-form until embedding-based semantic clustering shows value. |
| OQ-3 | Per-agent graph slicing (16 specialists each see only their region)? | **Revised 2026-06-06 — see [ADR-0008](../../adr/0008-skillogy-hard-acl-phase1a.md).** Phase 1a now enforces a *path-prefix ACL* on `find_skill`/`load_skill`/`traverse` (legacy `FilesystemBackend` contract: `/skills/standard/{role}/` + `/skills/shared/`). The single-graph Neo4j model is preserved; per-tenant graph slicing is still a Phase 2 hardening — but the deterministic per-role visibility boundary lands now, not later. |
| OQ-4 | Should `aatmf_tactic` get promoted to a `:Framework` node + edges in Phase 1b? | Re-evaluate after AATMF v3 schema stabilizes. Currently preserved as raw frontmatter. |
| OQ-5 | Hot-swap via runtime `ingest_skill` endpoint? | Not in Phase 1a (rebuild + redeploy). Reintroduce if SaaS shows real need. Phase 2 candidate. |
| OQ-6 | Existing attack-graph schema shares Neo4j — what label collisions are possible? | `:Tactic`/`:Technique` are unique to skill graph; `:Skill` is unique. `:Phase` is shared (already used by OPPLAN middleware?). Verify against [docs/design/attack-graph-schema.md](../../design/attack-graph-schema.md) during Phase 0. |
| OQ-7 | If SaaS gating becomes a concrete requirement (today: `safety_critical`/`gated_by_conops` are 1-file aspirational fields, dropped — see §1.4), where should the gating signal live: re-added frontmatter, runtime engagement state, or a separate `:Gating` node? | Defer until SaaS gating is a shippable feature. Prefer engagement-runtime over frontmatter when the time comes — gating that depends on the engagement's authorized scope is naturally runtime, not author-time. |

---

## 10. Migration Plan

### 10.1 Phase 0 → 1a

1. Phase 0 lands cleaned-up corpus + validator + canonical schema. **(DONE — PR #519 merged 2026-06-03.)**
2. PR introduces `skillogy.builder` package, `skills/.graph/skills.cypher` artifact, CI build step that asserts the dump matches what's checked in.
3. PR rewrites `decepticon.skillogy.{proto,server,client}/` in place: storage swaps from in-memory dict to Neo4j; wire surface gains `Traverse` / `CypherRead` / `MocSummary` / `Schema` RPCs; Bearer-token auth preserved; container image now bakes the `skills.cypher` dump and connects to Neo4j on `decepticon-net`. The `DECEPTICON_USE_SKILLOGY` env var is renamed `DECEPTICON_SKILL_BACKEND` with a one-cycle compat shim.
4. PR introduces the new `SkillogyMiddleware` as a thin REST/gRPC client of the rewritten skillogy service. Old `SkillsMiddleware` untouched in this step.
5. Per-agent opt-in via `DECEPTICON_SKILL_BACKEND=skillogy_brain` (per-factory override). Decepticon orchestrator stays on `skills` until specialists are validated one by one.
6. 50-case routing benchmark + token-cost report on each opt-in.
7. Once all 16 specialists pass: flip default to `skillogy_brain`.
8. One release cycle later: delete `SkillsMiddleware` AND drop `COPY packages/decepticon/decepticon/skills` from `containers/langgraph.Dockerfile`. The skillogy image becomes the sole owner of the catalog at runtime.

### 10.2 Phase 1a → 1b

Schema-additive. CI build produces embeddings; runtime middleware registers `recall` as a 4th tool. No agent factory changes.

### 10.3 Plugin SDK compat

`decepticon-sdk` plugin authors keep writing `SKILL.md`. Their files are picked up by `skillogy.builder` from the configured plugin tree (`packages/decepticon/decepticon/skills/plugins/`). No SDK API change.

---

## 11. Relation to Existing Code

| File / area | Change |
|---|---|
| `packages/decepticon/decepticon/middleware/skills.py` | Kept through migration; deleted after one release cycle on `skillogy_brain` as default. **Note**: this class subclasses `deepagents.middleware.skills.SkillsMiddleware` and overrides ~all of its prompt-building methods. Removing it also removes Decepticon's runtime dependency on the deepagents skill machinery (the deepagents library itself remains for its non-skill middleware). |
| `packages/decepticon/decepticon/middleware/skillogy.py` | **Rewritten** — thin REST/gRPC client of the skillogy service. 3 tools (Phase 1a), 4 tools (Phase 1b). Imports nothing from `neo4j`; the langgraph image no longer needs the Neo4j driver. Does NOT subclass `deepagents.middleware.skills.SkillsMiddleware` — directly extends `langchain.agents.middleware.AgentMiddleware`. |
| `packages/decepticon/decepticon/skillogy/proto/` | **Rewritten in place** — adds `Traverse`, `CypherRead`, `MocSummary`, `Schema` RPCs to the existing surface; preserves the `Skillogy.proto` service identity for backward-compat. protoc codegen wired into the build this time. |
| `packages/decepticon/decepticon/skillogy/server/` | **Rewritten in place** — FastAPI + grpcio app. Now owns the Neo4j driver (Bolt connection on `decepticon-net`), loads `skills.cypher` at boot, serves read-only Cypher with parameterisation + AST safety, supports Bearer-token auth (preserved from PR `23918e9`). |
| `packages/decepticon/decepticon/skillogy/client/` | **Rewritten in place** — REST + gRPC client behind a shared `SkillogyClient` Protocol. No Neo4j dependency. Used by the middleware and by future non-Python agent runtimes. |
| `containers/skillogy.Dockerfile` | **Rewritten** — bakes `skills.cypher` into the image, runs the new server, exposes `${SKILLOGY_REST_PORT:-9100}` (REST) and `${SKILLOGY_GRPC_PORT:-50051}` (gRPC). |
| `docker-compose.yml` skillogy service | **Kept and updated** — same service name (`decepticon-skillogy-skillogy`), new image tag, depends_on Neo4j now. |
| `containers/langgraph.Dockerfile` | **Trimmed at Phase 1a final cutover**: the `COPY packages/decepticon/decepticon/skills` line is removed once `SkillsMiddleware` is deleted. |
| `packages/decepticon/decepticon/skills/**/SKILL.md` | Normalized through Phase 0 (frontmatter, MITRE) — **DONE (PR #519)**. |
| `packages/decepticon/decepticon/skills/.graph/skills.cypher` | **New**, checked-in build artifact. Reviewable diff per PR. |
| `packages/decepticon/decepticon/skillogy/builder/` | **New** package — CI-time graph compiler. Lives next to the runtime package since it produces the artifact the runtime consumes. |
| `packages/decepticon/decepticon/tools/skillogy.py` | **New** — agent tool factories that wrap the `SkillogyClient`. |
| `packages/decepticon/decepticon/skill_audit/` | Phase 0 validator package — **DONE (PR #519)**. Used by CI as `make audit-skills-strict`. |
| `docs/skill-schema.md`, `docs/skill-cleanup-process.md`, `docs/skill-cleanup-progress.md` | Phase 0 docs — **DONE (PR #519)**. |
| `CONTRIBUTING.md` "Authoring Skills" section | **DONE (PR #519)**. |
| `docs/design/skillogy.md` | Annotated with a "Superseded" notice pointing to `docs/design/skillogy-brain-redesign.md`; kept in tree for history and diff review. |

---

## 12. Effort Estimate

| Phase | Effort | Gate |
|---|---|---|
| Phase 0 — Corpus cleanup | 4–6 weeks (co-design, batched by subdomain) | All 251 SKILL.md pass `validate_skills.py`; 65 unmapped skills have MITRE; subdomain aliases collapsed |
| Phase 1a — Brain Anatomy | 6 weeks | `skillogy.builder` ships, `skills.cypher` checked in, `SkillogyMiddleware` rewritten, per-specialist benchmark passes |
| Phase 1b — Associative Memory | 3–4 weeks | `:Skill.embedding` populated, `recall` tool ships, p95 ≤ 100 ms |
| Phase 2 — LLM-inferred edges + tool/agent/RoE | TBD | Phase 1b benchmark indicates need |
| Phase 3 — Plasticity + capability plane | TBD | Stable trace pipeline + planning use case |

Total Phase 0 + 1a + 1b: **~14–17 weeks** to land the full "brain v1." Compared to a single big-bang B implementation (16 weeks risk-loaded), the phased path ships first value at week 6 (Phase 0) and validates routing improvement at week 12 (Phase 1a benchmark).

---

## 13. Changelog

- **2026-06-03 (v0.2.1, amendment)** — Service-architecture pivot. The original v0.2 plan retired the existing `decepticon.skillogy.*` REST/proto package and had `SkillogyMiddleware` open a Bolt connection directly to Neo4j from the langgraph process. After implementing Phase 0, the user reframed the intent: **skillogy should remain a standalone communication service**, not a library-style middleware. The amendment:
  1. **Rebuilds the existing REST/proto/client package on a Neo4j backend** instead of deleting it. Wire surface preserved; storage swapped; `Traverse`, `CypherRead`, `MocSummary`, `Schema` RPCs added.
  2. **Reframes `SkillogyMiddleware` as a thin REST/gRPC client** of the service. The middleware imports nothing from `neo4j`. Multi-tenant SaaS, hot-swap, and non-Python agent runtimes (Go, Rust, TypeScript) are now first-class concerns of the service container.
  3. **Trims `containers/langgraph.Dockerfile` at the final Phase 1a cutover** — drops the `COPY packages/decepticon/decepticon/skills` line. The skillogy container becomes the sole owner of the catalog at runtime; the agent image becomes catalog-free, removing a stale-catalog footgun and shrinking the image.
  4. Renames `DECEPTICON_USE_SKILLOGY` to `DECEPTICON_SKILL_BACKEND ∈ {skills, skillogy_brain}` with a one-cycle compat shim.
  Phase 0 deliverables (validator + cleanup + docs) are marked DONE (PR #519, merged 2026-06-03). Architecture diagram (§3.1), components table (§3.2), middleware example (§5.10), migration plan (§5.11 + §10.1), and file table (§11) are updated. No change to the graph schema (§5.1–§5.4) or the agent-facing tool semantics — those decisions stay.
- **2026-06-03** — Initial draft. Supersedes the 2026-05-28 v0.1 design (`docs/design/skillogy.md`) in four ways: (a) body lives in the graph node, not on disk; (b) agents get read-only Cypher access in addition to curated tools; (c) Phase 1a graph schema is matrix-agnostic (single `:Technique` label with `matrix` enum property) so ICS / Mobile / ATLAS importers can be added in Phase 1b/2 without breaking changes — **Phase 1a loads ATT&CK Enterprise v19.1 only**, non-Enterprise frontmatter (ICS T0xxx, ATLAS AML.T, AATMF) is preserved as raw and promoted to edges when its importer lands; (d) the `:Skill` schema is slimmed to only fields the audit confirmed are read by production middleware — `allowed-tools`, `metadata.kind`, `metadata.safety_critical`, `metadata.gated_by_conops` are explicitly dropped (the v0.1 spec treated `kind` as load-bearing for validation; the production data shows 4/251 occurrences and 0 readers). Adds Phase 0 corpus cleanup as a pre-condition. Adds §1.4 frontmatter-field audit. Specifies that `SkillogyMiddleware` extends `AgentMiddleware` directly and does NOT subclass the deepagents skill base. Originally proposed deleting the in-memory REST skillogy package; superseded by the 2026-06-03 v0.2.1 amendment above.

---

## 14. References

### Internal
- `docs/design/skillogy.md` (2026-05-28 v0.1 draft, superseded by this doc)
- `docs/skills.md` (current `SkillsMiddleware`)
- `docs/knowledge-graph.md` (existing attack graph; Neo4j shared)
- `docs/design/attack-graph-schema.md` (label conventions)
- `docs/agents.md` (16 specialist agents)
- `CLAUDE.md` (repo guidelines: extensibility, network isolation, plugin contract)

### MITRE (verified 2026-06-03)

Phase 1a:
- ATT&CK Enterprise v19.1 (latest as of 2026-06-03) — `attack.mitre.org/resources/updates/updates-april-2026/`
- ATT&CK STIX bundles — `github.com/mitre-attack/attack-stix-data`
- ATT&CK v19 changelog (Defense Evasion split) — `medium.com/mitre-attack/attack-v19-ff329cb65d66`

Future phases (importer config only when promoted):
- ATT&CK Mobile matrix — `attack.mitre.org/matrices/mobile/`
- ATT&CK ICS matrix — `attack.mitre.org/matrices/ics/`
- MITRE ATLAS v5.4 — `atlas.mitre.org/`, `github.com/mitre-atlas/atlas-navigator-data`

### Prior art (selective)
- Ontolocy MitreAttackParser (Neo4j label conventions for ATT&CK)
- pyattck (Swimlane) — multi-matrix Python access
- attackcti (OTRF) — TAXII multi-collection merge pattern
- LiteGraph-MCP, GoS (Graph of Skills) — graph-as-discovery patterns
- ESCO-PrereqSkill — LLM-inferred prerequisite edges (Phase 2 reference)
