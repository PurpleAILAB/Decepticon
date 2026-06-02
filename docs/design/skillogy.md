# Skillogy — Knowledge-Graph-Backed Skill System

> **⚠ Superseded (2026-06-03)**
>
> This document is the **v0.1 draft** (2026-05-28). It has been superseded by
> [docs/design/skillogy-brain-redesign.md](skillogy-brain-redesign.md) (v0.2,
> the "Brain" redesign). The successor differs in load-bearing ways:
>
> 1. Body lives in the graph node, not on disk (this doc kept an Index-Only pointer model).
> 2. Agents get read-only Cypher access in addition to curated tools.
> 3. Phase 1a graph schema is matrix-agnostic but loads ATT&CK Enterprise only;
>    ICS / Mobile / ATLAS are deferred to Phase 1b/2 (this doc treated MITRE as
>    Enterprise-only by default, with no slot for other matrices).
> 4. The `:Skill` schema is slimmed against the production-code audit; `kind`,
>    `safety_critical`, `gated_by_conops`, and `allowed-tools` are dropped.
> 5. Phase 0 corpus cleanup is added as a pre-condition.
>
> This doc is kept for history and diff review. Read the successor for the
> current direction.

---

**Status**: design draft, awaiting implementation
**Replaces**: text-matching skill autoload in `SkillsMiddleware`
**Target version**: Skillogy v0.1
**MITRE reference version**: ATT&CK Enterprise v19.1 (released 2026-05-12)

---

## TL;DR

Skillogy replaces Decepticon's flat, text-matching skill catalog with a **typed Neo4j knowledge graph** built at CI time and exposed to agents through five MCP-style tools. Skills, MITRE techniques, asset types, capabilities, agents, and Map-of-Concepts (MoC) categories become first-class graph nodes connected by typed edges. The LLM remains in autonomous control — it just calls a smarter set of tools.

Skill source files (`SKILL.md`) are unchanged. They continue to be the ground truth and trust boundary; the graph is a **discovery layer** that points to them.

---

## 1. Motivation

### 1.1 Current skill system

`SkillsMiddleware` ([packages/decepticon/decepticon/middleware/skills.py](../../packages/decepticon/decepticon/middleware/skills.py)) implements three-stage progressive disclosure:

| Stage | What loads | Token cost | Trigger |
|---|---|---|---|
| 1 | YAML frontmatter (~50–100 tok/skill) of every relevant skill | ~3–4 KB system prompt | Agent boot |
| 2 | Full `SKILL.md` body | ~500–2 000 tok | `read_file()` after LLM picks a match |
| 3 | `references/` | variable | Skill body instructs |

The agent picks a skill by matching the natural-language `description` and `metadata.when_to_use` against its current task — a **flat text-matching retrieval** decision made entirely inside the LLM.

### 1.2 Structural limitations (all confirmed by 2024–2026 research)

| Issue | Evidence |
|---|---|
| Native LLM tool selection drops to ~49 % at 100 + tools | Opus 4 measurements; RAG-MCP study |
| Vector RAG over flat tool list degrades to near-random past 100 entries | RAG-MCP |
| `when_to_use` is a comma-separated keyword string — no ranking, no relations | [packages/decepticon/decepticon/skills/standard/recon/passive-recon/SKILL.md](../../packages/decepticon/decepticon/skills/standard/recon/passive-recon/SKILL.md) frontmatter |
| Routing skills (e.g. `exploit/web/SKILL.md`) hand-list 30 + sub-skills; adding a sub-skill requires editing the parent | `skills/standard/exploit/web/SKILL.md` |
| Catalog injected at every agent boot — ~4 KB even before any tool call | Measured |
| No machine-readable relation between skills (prereq, composes-with, substitutes, forbidden) | Frontmatter schema |
| No audit trail — "why did the agent pick X?" is opaque | RoE / red-team audit requirement |
| 41 % of 146 SKILL.md files have no MITRE mapping; 11 instances of tactic IDs misused as technique IDs (fixed 2026-05-28); zero coverage of v19 AI-adversary techniques (T1682, T1683.x, T1588.007) | Mapping audit, May 2026 |

### 1.3 Research consensus (2024–2026)

Across academic work and OSS:

- **Typed knowledge graphs out-perform flat lists** on tool routing accuracy, especially multi-hop (≈ 86 % vs 32 % on FamilyTool / NESTFUL-style benchmarks).
- **GraphRAG with relations as primary signal** (GoS, Graph RAG-Tool Fusion, kingjulio8238/skill_graph, ColorC/LiteGraph-MCP, ry-animal/mcp-skill-graph) consistently reports 90 %+ token savings vs "load everything."
- **Index-Only / Pointer-Only** patterns separate the discovery layer from the ground-truth layer — critical for security-domain audit and to avoid the staleness of summarized text in graphs.
- **Zero-shot prerequisite inference by frontier LLMs** is now accurate enough (ESCO-PrereqSkill, 2025) to bootstrap a skill dependency graph without hand authoring.

These directly inform the Skillogy design choices below.

---

## 2. Concept

### 2.1 One-line definition

> Skillogy is a **Neo4j knowledge graph of skills, MITRE techniques, asset types, capabilities, agents and concepts**, built deterministically at CI time from the existing `SKILL.md` corpus, and exposed to the agent through five tools managed by `SkillogyMiddleware`. The LLM autonomously decides when to call the tools; the graph decides which skills are applicable.

### 2.2 Four principles

| # | Principle | Implication |
|---|---|---|
| 1 | **Knowledge graph as skill backend** | All routing signal (phase, MITRE, asset type, prereq, RoE constraint) lives in Neo4j as typed nodes + edges, not in text |
| 2 | **Build-time construction** | Graph is generated by CI, validated, then checked into `skills/.graph/skills.cypher`. Runtime never calls an LLM to build the graph — guarantees determinism, auditability, and zero cold-start |
| 3 | **Tool-based exposure** | Five tools (`find_skill`, `load_skill`, `get_prereqs`, `suggest_next`, `get_skill_chain`). No automatic injection, no forced gating — the LLM remains autonomous |
| 4 | **Middleware integration** | `SkillogyMiddleware` (replaces `SkillsMiddleware`) loads the graph, registers the tools, and injects a tiny ~300-token MoC summary for the current agent's phase into the system prompt |

### 2.3 Paradigm shift, side by side

| Axis | Current (catalog + LLM picks) | Skillogy (tool + LLM autonomous) |
|---|---|---|
| Trigger surface | LLM reads ~4 KB frontmatter catalog, picks | LLM calls `find_skill(...)`, graph returns ranked candidates |
| System prompt cost / boot | ~4 KB | ~300 tokens (current-phase MoC summary) |
| Selection basis | LLM reasoning over keywords (opaque) | Cypher traversal + Personalized PageRank (auditable reasoning path) |
| Missed-skill failure mode | "LLM forgot it existed" | 0 % — every relevant skill is in the graph result set |
| RoE enforcement | Prompt-level (best-effort) | `FORBIDDEN_BY` edge filters skill out of results |
| Token cost per turn | ~4 KB always | ~300 tokens + one tool call when needed |
| Skill body location | Same file | Same file — graph stores pointer only (Index-Only trust boundary) |
| Authoring impact | None | None — `SKILL.md` format is unchanged |

The LLM keeps its autonomy. We make its tools smarter, not its leash shorter.

### 2.4 What does **not** change

- `SKILL.md` format. Frontmatter, body, `references/`, `scripts/` — all unchanged.
- The 10 specialist agents and the orchestrator.
- Authoring workflow. Contributors continue editing `SKILL.md` files.
- Neo4j infrastructure. Skill graph and the existing attack graph share one instance.

---

## 3. Architecture

```
                       ┌─────────────────────────────────────────┐
                       │            BUILD TIME (CI)              │
SKILL.md (146+) ───────┤                                         │
MITRE STIX v19.1 ──────┼─► graph_builder ─► skills/.graph/       │
AssetType seed ────────┤   (Python)         ├ skills.cypher      │
RoE seed ──────────────┤                    └ manifest.json      │
                       │                    ▲                    │
                       │                    │ checked into repo  │
                       └────────────────────│────────────────────┘
                                            │
                                            ▼ on container start
                       ┌─────────────────────────────────────────┐
                       │              RUNTIME (Agent)            │
                       │                                         │
                       │ ┌─────────────────────────────────────┐ │
                       │ │ SkillogyMiddleware                  │ │
                       │ │  before_agent():                    │ │
                       │ │   - ensure Neo4j connected          │ │
                       │ │   - idempotently load skills.cypher │ │
                       │ │   - inject ~300-tok MoC summary for │ │
                       │ │     current agent phase             │ │
                       │ │  get_tools(): register 5 tools      │ │
                       │ └─────────────────────────────────────┘ │
                       │            │                            │
                       │            ▼                            │
                       │ ┌─────────────────────────────────────┐ │
                       │ │ LLM (autonomously calls)            │ │
                       │ │  - find_skill(...)                  │ │
                       │ │  - load_skill(name | path)          │ │
                       │ │  - get_prereqs(name)                │ │
                       │ │  - suggest_next(name)               │ │
                       │ │  - get_skill_chain(target_cap)      │ │
                       │ └─────────────────────────────────────┘ │
                       │            │                            │
                       │            ▼                            │
                       │ ┌─────────────────────────────────────┐ │
                       │ │ Neo4j (one instance, label-split)   │ │
                       │ │  skill_graph labels:                │ │
                       │ │   :Skill :Tactic :Technique         │ │
                       │ │   :SubTechnique :AssetType          │ │
                       │ │   :Capability :Tool :Phase :MoC     │ │
                       │ │   :Agent :RoEConstraint             │ │
                       │ │  attack_graph labels (unchanged):   │ │
                       │ │   :Host :Service :Vulnerability     │ │
                       │ │   :Credential :User :Group :Domain  │ │
                       │ │  bridge edges:                      │ │
                       │ │   (:Service)-[:IS_OF]->(:AssetType) │ │
                       │ │   (:Credential)-[:REALIZES]->(:Cap) │ │
                       │ └─────────────────────────────────────┘ │
                       └─────────────────────────────────────────┘
```

Decepticon already runs Neo4j on `sandbox-net` for the attack graph (see [docs/knowledge-graph.md](../knowledge-graph.md) and [docs/design/attack-graph-schema.md](attack-graph-schema.md)). The skill graph adds new node labels in the same database and adds a small number of bridge edges between the two.

---

## 4. Knowledge Graph Schema

### 4.1 Node labels

| Label | Description | Key properties | Created by |
|---|---|---|---|
| `:Skill` | One `SKILL.md` = one node | `name` (unique), `path` (unique), `subdomain`, `kind` (`offensive` / `reporting` / `analytic`), `description`, `allowed_tools[]`, `tags[]`, `commit_sha`, `built_at` | frontmatter parser |
| `:Tactic` | MITRE ATT&CK tactic | `id` (unique, e.g. `TA0005`), `name`, `description`, `attck_version`, `deprecated`, `revoked` | STIX importer |
| `:Technique` | MITRE technique | `id` (e.g. `T1190`), `name`, `description`, `platforms[]`, `is_subtechnique=false`, `attck_version`, `deprecated`, `revoked`, `kill_chain_phases[]` | STIX importer |
| `:SubTechnique` | MITRE sub-technique | `id` (e.g. `T1590.001`), `name`, `parent_id`, `is_subtechnique=true`, `attck_version`, `deprecated`, `revoked` | STIX importer |
| `:AssetType` | Engagement-asset taxonomy node | `name` (unique, e.g. `mysql`, `active-directory`), `category` (parent name) | seed + LLM inference |
| `:Capability` | Abstract artifact a skill produces/consumes (STRIPS-style) | `name` (e.g. `valid-credential`, `shell-on-target`, `ai-provider-access`), `category` | seed (v0.1) + LLM (v0.2) |
| `:Tool` | External tool referenced by a skill | `name` (e.g. `nmap`, `sqlmap`), `category`, `os[]` | frontmatter `allowed-tools` |
| `:Phase` | Kill-chain phase | `name` (e.g. `reconnaissance`), `kill_chain_order`, `mitre_tactic`, `kind` (`offensive` / `meta`) | seed |
| `:MoC` | Map-of-Concepts category for navigation / disclosure | `name` (e.g. `web-exploitation`), `description`, `parent_phase` | seed + computed |
| `:Agent` | Decepticon specialist agent | `name` (e.g. `soundwave`, `recon`), `role`, `description`, `code_path` | seed |
| `:RoEConstraint` | Explicit Rules-of-Engagement constraint | `name` (e.g. `no-data-exfil`), `description` | seed |

### 4.2 Edge types

#### Explicit (provenance = `frontmatter` or `seed`)

| Edge | From → To | Meaning |
|---|---|---|
| `IN_PHASE` | `:Skill` → `:Phase` | Skill belongs to a kill-chain phase (from `metadata.subdomain`) |
| `IMPLEMENTS` | `:Skill` → `:Technique` \| `:SubTechnique` | Skill implements a MITRE technique (from `metadata.mitre_attack`) |
| `USES_TOOL` | `:Skill` → `:Tool` | Skill uses an external tool (from `allowed-tools`) |
| `BELONGS_TO` | `:Skill` → `:MoC` | Skill belongs to a Map-of-Concepts category |
| `CAN_USE` | `:Agent` → `:Skill` | Agent is the default caller of this skill |
| `HAS_TECHNIQUE` | `:Tactic` → `:Technique` | MITRE hierarchy (STIX) |
| `HAS_SUBTECHNIQUE` | `:Technique` → `:SubTechnique` | MITRE hierarchy (STIX) |
| `HAS_SUBTYPE` | `:AssetType` → `:AssetType` | Asset-type taxonomy hierarchy |

#### LLM-inferred — v0.1 scope (provenance = `body-llm`)

| Edge | From → To | Inferred by | Notes |
|---|---|---|---|
| `REQUIRES` | `:Skill` → `:Skill` | LLM | Prerequisite skill (e.g. lateral-movement-smb requires credential-dump-lsass) |
| `APPLICABLE_TO` | `:Skill` → `:AssetType` | LLM | Skill targets this kind of asset (e.g. `web-recon` → `web-service`) |

All inferred edges carry: `confidence` (0–1), `provenance`, `justification` (text from SKILL.md), `inferred_at`, `inferrer_model`.

#### Reserved for v0.2 (schema defined, not populated in v0.1)

| Edge | Purpose |
|---|---|
| `PRODUCES` / `CONSUMES` | `:Skill` ↔ `:Capability` — STRIPS-style precondition/effect |
| `COMPOSES_WITH` | `:Skill` → `:Skill` — frequently chained |
| `SUBSTITUTES` | `:Skill` → `:Skill` — alternative for the same intent |
| `FORBIDDEN_BY` | `:Skill` → `:RoEConstraint` — RoE-aware filtering |
| `IMPLEMENTS_ATLAS` | `:Skill` → `:AmlTechnique` — MITRE ATLAS dual-tag for AI-target skills |

#### Bridge to the attack graph (runtime, not in `skills.cypher`)

| Edge | From → To | Created by |
|---|---|---|
| `IS_OF` | `:Service` → `:AssetType` | runtime detection rule |
| `REALIZES` | `:Credential` → `:Capability` | runtime when a credential is verified |
| `OBTAINS` | `:Agent` (framework) → `:Capability` (e.g. `ai-provider-access`) | runtime startup |

### 4.3 MITRE v19.1 considerations

ATT&CK v19 (April 2026) is the largest structural change in years and **must be handled correctly** by the STIX importer:

1. **Defense Evasion split** — `TA0005` was renamed to **"Stealth"** (same STIX ID, new meaning). A new tactic `TA0112` "Defense Impairment" was introduced. STIX consumers that only look at IDs will silently mis-interpret skill mappings.
2. **New AI-adversary techniques** (relevant to Decepticon itself, since Decepticon *is* an AI attacker):
   - `T1682` — Query Public AI Services
   - `T1683` / `T1683.001` (Written Content) / `T1683.002` (A/V Content) — Generate Content
   - `T1588.007` — Obtain Capabilities: Artificial Intelligence
3. **Detections → Detection Strategies + Analytics** (v18 carry-over). Doesn't affect skill mapping directly but the STIX schema changed.

Mapping policy:
- All MITRE IDs in `metadata.mitre_attack` MUST be `T\d{4}(\.\d{3})?` — never `TA0xxx`.
- `:Skill {kind: 'offensive'}` MUST have `≥ 1` `IMPLEMENTS` edge after build (validator rule).
- `:Skill {kind: 'reporting' | 'analytic'}` is exempt from MITRE mapping.
- The framework itself (`:Agent {name: 'decepticon'}`) `OBTAINS` `:Capability {name: 'ai-provider-access', mitre: 'T1588.007'}` — captures the fact that Decepticon acquires AI capability as attack infrastructure.
- Soundwave (`:Agent {name: 'soundwave'}`) `IMPLEMENTS` `:SubTechnique {id: 'T1683.001'}` — captures AI-generated planning artifacts authorizing social engineering.

The STIX importer pins the bundle version explicitly:

```
https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-19.1.json
```

Version bumps require an explicit PR; the importer never silently picks up a newer release.

### 4.4 Engagement-graph bridge (runtime)

The skill graph is static (built at CI). The attack graph is dynamic (built at engagement runtime). They meet through three bridge edges:

```cypher
// 1. Engagement discovers a service → tag it with an AssetType
MATCH (svc:Service {port: 80, banner: 'nginx/1.18'})
MATCH (at:AssetType {name: 'http'})
MERGE (svc)-[:IS_OF]->(at);

// 2. Engagement obtains a credential → realize a Capability
MATCH (cred:Credential {username: 'admin', verified: true})
MATCH (cap:Capability {name: 'valid-credential'})
MERGE (cred)-[:REALIZES]->(cap);

// 3. Framework/agent obtains an AI provider → OBTAINS capability
MATCH (a:Agent {name: 'decepticon'})
MATCH (c:Capability {name: 'ai-provider-access'})
MERGE (a)-[:OBTAINS]->(c);
```

This is how `find_skill` becomes context-aware: it sees the engagement state (via the attack graph) and ranks skills accordingly.

---

## 5. Tool Interface

All five tools are registered by `SkillogyMiddleware.get_tools()`. They follow the **Index-Only** principle: the graph returns *pointers* (skill name + file path + reasoning), and the agent reads the actual `SKILL.md` body from disk via `load_skill`.

### 5.1 `find_skill(query: str, phase: str | None = None, asset_hint: str | None = None, limit: int = 5)`

Primary routing entry point. Returns ranked skill candidates with reasoning paths.

```python
{
    "name": "web-recon",
    "path": "/skills/standard/recon/web-recon/SKILL.md",
    "score": 0.92,
    "reasoning": [
        "phase:reconnaissance",
        "implements:T1595.002",
        "applicable_to:web-service (specificity=1)"
    ],
    "prereqs_met": True,
    "roe_compliant": True
}
```

Internally it executes:
1. **Seed retrieval** — Cypher join over (current phase) × (asset types in scope) × (skill.kind = 'offensive') → 10–20 seed skills.
2. **Personalized PageRank** — GDS PPR (or APOC fallback) walks `REQUIRES` and `APPLICABLE_TO` edges from the seed set, pulling in prerequisite skills the seed query missed (GoS pattern).
3. **Top-K** — return top `limit` skills with reasoning path attached.

### 5.2 `load_skill(name_or_path: str)`

Reads the full `SKILL.md` body from disk. Identical to the existing `read_file` flow — the graph stores only the pointer, never the body. This preserves the trust boundary: the graph helps find the file; the file is the ground truth.

### 5.3 `get_prereqs(skill_name: str)`

Returns prerequisite skills (v0.1: direct `REQUIRES`; v0.2: adds capability-based `CONSUMES`).

```cypher
MATCH (s:Skill {name: $name})-[:REQUIRES]->(prereq:Skill)
RETURN prereq.name AS name,
       prereq.path AS path,
       prereq.subdomain AS subdomain;
```

### 5.4 `suggest_next(last_skill: str, current_findings: dict | None = None)` *(v0.2)*

Returns likely next skills after `last_skill`, combining frequency (`COMPOSES_WITH`) and logic (`PRODUCES`/`CONSUMES` chains).

### 5.5 `get_skill_chain(target_capability: str)` *(v0.2)*

Backward chaining: returns one or more skill sequences that reach `target_capability` (e.g. `shell-on-target`). STRIPS-style planning.

> The agent never gets raw Cypher access. The five tools cover all intended access patterns and can be audited.

---

## 6. SkillogyMiddleware

Replaces `SkillsMiddleware`. Lives at `packages/decepticon/decepticon/middleware/skillogy.py`.

```python
class SkillogyMiddleware(BaseMiddleware):
    """
    Loads the Skillogy graph and exposes five tools.
    Replaces SkillsMiddleware (catalog injection).
    """

    def __init__(
        self,
        neo4j_uri: str,
        skill_repo_path: Path,
        graph_dump_path: Path,  # skills/.graph/skills.cypher
        agent_phase: str,        # injected by orchestrator
    ):
        self.driver = neo4j.GraphDatabase.driver(neo4j_uri)
        self.skill_repo = skill_repo_path
        self.graph_dump = graph_dump_path
        self.agent_phase = agent_phase

    def before_agent(self, state):
        # 1. Idempotently apply the Cypher dump.
        #    The dump only touches skill_graph labels;
        #    attack_graph labels are untouched.
        ensure_skill_graph_loaded(self.driver, self.graph_dump)

        # 2. Inject ~300-token MoC summary for the current phase.
        moc_summary = query_phase_moc(self.driver, self.agent_phase)
        state.system_prompt += render_skillogy_guide(moc_summary)

    def get_tools(self):
        return [
            build_find_skill_tool(self.driver, self.skill_repo),
            build_load_skill_tool(self.skill_repo),
            build_get_prereqs_tool(self.driver),
            build_suggest_next_tool(self.driver),       # v0.2
            build_get_skill_chain_tool(self.driver),    # v0.2
        ]
```

The MoC summary injected into the system prompt looks like:

```
You have a Skillogy graph available via the `find_skill` tool.

Current phase: reconnaissance
Available concepts in this phase:
- passive-recon      — OSINT, DNS, certificate transparency
- active-recon       — port scanning, service enumeration
- web-recon          — HTTP fingerprinting, content discovery
- ad-recon           — Active Directory enumeration

Call `find_skill(query, asset_hint?)` to discover specific skills.
Call `load_skill(name)` to read a skill's full instructions.
```

About 300 tokens. The agent doesn't see the 146-skill catalog; it sees the *navigation map*.

---

## 7. Build Pipeline

A new Python package `graph_builder/` under `packages/decepticon/` (alongside `middleware/`, `agents/`, `skills/`).

### 7.1 Module layout

```
packages/decepticon/decepticon/graph_builder/
├── __init__.py
├── build_skill_graph.py       # entry point — orchestrates the 12 stages below
├── extract_frontmatter.py     # SKILL.md → :Skill + explicit edges
├── import_mitre_stix.py       # MITRE v19.1 STIX → :Tactic / :Technique / :SubTechnique
├── seed_asset_types.py        # ~35-node AssetType taxonomy
├── seed_phases_mocs_agents.py # :Phase / :MoC / :Agent / :RoEConstraint
├── infer_relations.py         # LLM inference for REQUIRES + APPLICABLE_TO
├── validate_graph.py          # SHACL-like integrity rules
├── emit_cypher.py             # → skills/.graph/skills.cypher
└── emit_manifest.py           # → skills/.graph/manifest.json
```

CLI:

```bash
decepticon graph-build              # full build
decepticon graph-build --validate   # validate without writing
decepticon graph-build --diff       # show diff vs checked-in dump
```

### 7.2 The 12 stages

1. **Clear skill-graph labels** — `MATCH (n) WHERE any(l IN labels(n) WHERE l IN [...]) DETACH DELETE n`. Attack-graph labels (`Host`, `Service`, etc.) are untouched.
2. **Apply constraints + indexes** — see §8.1.
3. **Import MITRE STIX v19.1** — pinned file from `mitre-attack/attack-stix-data`. Emits `:Tactic`, `:Technique`, `:SubTechnique`, plus `HAS_TECHNIQUE` / `HAS_SUBTECHNIQUE` edges. Filters `revoked = true`.
4. **Seed AssetType taxonomy** — ~35 nodes (see §9). Creates `HAS_SUBTYPE` edges from `category` property.
5. **Seed Phase / MoC / Agent / RoEConstraint** — small fixed lists.
6. **Parse SKILL.md frontmatter** — for each `SKILL.md`:
   - Create `:Skill {name, path, subdomain, kind, ...}`.
   - For each `mitre_attack` ID: `MERGE (:Skill)-[:IMPLEMENTS]->(:Technique|:SubTechnique)`. Fail build if ID format is `TA0xxx`.
   - For each `allowed-tools` entry: `MERGE (:Skill)-[:USES_TOOL]->(:Tool {name})`.
   - Link to `:Phase` via `subdomain` match.
   - Compute `:MoC` membership.
7. **LLM inference — REQUIRES** — for each skill, prompt Claude Haiku 4.5 with the skill body and ask which other skills are prerequisites. `temperature=0`, fixed seed. Output gets `confidence`, `provenance='body-llm'`, `justification`, `inferred_at`, `inferrer_model`. Edges with `confidence < 0.6` go to `inferred_low_confidence.cypher` for human review.
8. **LLM inference — APPLICABLE_TO** — same shape, against the AssetType seed list.
9. **Validate** — see §10. Build fails on any violation.
10. **Emit Cypher dump** — write `skills/.graph/skills.cypher`. Deterministic ordering (sorted by node name) so diffs are reviewable.
11. **Emit manifest** — `skills/.graph/manifest.json` with stats (counts, validation results, version pins).
12. **CI diff comment** — GitHub Action posts a summary of `skills.cypher` diff to the PR.

### 7.3 Determinism

- LLM calls: `temperature=0`, fixed model version (`claude-haiku-4-5-20251001`), fixed prompt templates.
- The Cypher dump is **checked into the repo**. CI rebuilds and asserts the dump matches what is checked in — humans review LLM changes through PR diffs, not by re-running the LLM at deploy time.
- MITRE STIX bundle version is pinned (`enterprise-attack-19.1.json`); bumping is an explicit PR change.

---

## 8. Neo4j Setup

### 8.1 Unique constraints

```cypher
CREATE CONSTRAINT skill_name_unique IF NOT EXISTS
  FOR (s:Skill) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT skill_path_unique IF NOT EXISTS
  FOR (s:Skill) REQUIRE s.path IS UNIQUE;
CREATE CONSTRAINT tactic_id_unique IF NOT EXISTS
  FOR (t:Tactic) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT technique_id_unique IF NOT EXISTS
  FOR (t:Technique) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT subtechnique_id_unique IF NOT EXISTS
  FOR (s:SubTechnique) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT asset_type_name_unique IF NOT EXISTS
  FOR (a:AssetType) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT capability_name_unique IF NOT EXISTS
  FOR (c:Capability) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT tool_name_unique IF NOT EXISTS
  FOR (t:Tool) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT phase_name_unique IF NOT EXISTS
  FOR (p:Phase) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT moc_name_unique IF NOT EXISTS
  FOR (m:MoC) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT agent_name_unique IF NOT EXISTS
  FOR (a:Agent) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT roe_name_unique IF NOT EXISTS
  FOR (r:RoEConstraint) REQUIRE r.name IS UNIQUE;
```

### 8.2 Performance indexes

```cypher
CREATE INDEX skill_subdomain IF NOT EXISTS FOR (s:Skill) ON (s.subdomain);
CREATE INDEX skill_kind      IF NOT EXISTS FOR (s:Skill) ON (s.kind);
CREATE INDEX technique_deprecated IF NOT EXISTS FOR (t:Technique) ON (t.deprecated);
CREATE INDEX technique_revoked    IF NOT EXISTS FOR (t:Technique) ON (t.revoked);
CREATE INDEX asset_type_category  IF NOT EXISTS FOR (a:AssetType) ON (a.category);
CREATE INDEX rel_provenance IF NOT EXISTS FOR ()-[r:REQUIRES]-() ON (r.provenance);
CREATE INDEX rel_confidence IF NOT EXISTS FOR ()-[r:REQUIRES]-() ON (r.confidence);
```

### 8.3 GDS projection (for PPR)

```cypher
CALL gds.graph.project(
  'skillogy_routing',
  ['Skill', 'AssetType', 'Capability', 'Phase'],
  {
    REQUIRES:      { orientation: 'NATURAL' },
    APPLICABLE_TO: { orientation: 'NATURAL' },
    IN_PHASE:      { orientation: 'NATURAL' },
    HAS_SUBTYPE:   { orientation: 'NATURAL' },
    PRODUCES:      { orientation: 'NATURAL' },   // v0.2
    CONSUMES:      { orientation: 'NATURAL' }    // v0.2
  }
);
```

If GDS is not installed, the build falls back to `apoc.algo.pageRank` (lower precision but acceptable for v0.1).

---

## 9. AssetType Seed (v0.1, ~35 nodes)

```cypher
// === Root ===
MERGE (:AssetType {name: 'service', category: 'root'});

// === Web ===
MERGE (:AssetType {name: 'web-service',  category: 'service'});
MERGE (:AssetType {name: 'http',         category: 'web-service'});
MERGE (:AssetType {name: 'https',        category: 'web-service'});
MERGE (:AssetType {name: 'websocket',    category: 'web-service'});
MERGE (:AssetType {name: 'api-rest',     category: 'web-service'});
MERGE (:AssetType {name: 'api-graphql',  category: 'web-service'});

// === Database ===
MERGE (:AssetType {name: 'database',  category: 'service'});
MERGE (:AssetType {name: 'mysql',     category: 'database'});
MERGE (:AssetType {name: 'mssql',     category: 'database'});
MERGE (:AssetType {name: 'postgres',  category: 'database'});
MERGE (:AssetType {name: 'mongodb',   category: 'database'});
MERGE (:AssetType {name: 'redis',     category: 'database'});
MERGE (:AssetType {name: 'oracle-db', category: 'database'});

// === Directory / Identity ===
MERGE (:AssetType {name: 'directory-service', category: 'service'});
MERGE (:AssetType {name: 'active-directory',  category: 'directory-service'});
MERGE (:AssetType {name: 'ldap',              category: 'directory-service'});
MERGE (:AssetType {name: 'kerberos',          category: 'directory-service'});

// === Remote Access ===
MERGE (:AssetType {name: 'remote-access', category: 'service'});
MERGE (:AssetType {name: 'ssh',           category: 'remote-access'});
MERGE (:AssetType {name: 'rdp',           category: 'remote-access'});
MERGE (:AssetType {name: 'winrm',         category: 'remote-access'});
MERGE (:AssetType {name: 'vpn',           category: 'remote-access'});

// === File / Share ===
MERGE (:AssetType {name: 'file-share', category: 'service'});
MERGE (:AssetType {name: 'smb',        category: 'file-share'});
MERGE (:AssetType {name: 'nfs',        category: 'file-share'});
MERGE (:AssetType {name: 'ftp',        category: 'file-share'});

// === Cloud ===
MERGE (:AssetType {name: 'cloud-resource', category: 'service'});
MERGE (:AssetType {name: 'aws-resource',   category: 'cloud-resource'});
MERGE (:AssetType {name: 'aws-s3',         category: 'aws-resource'});
MERGE (:AssetType {name: 'aws-ec2',        category: 'aws-resource'});
MERGE (:AssetType {name: 'aws-iam',        category: 'aws-resource'});
MERGE (:AssetType {name: 'azure-resource', category: 'cloud-resource'});
MERGE (:AssetType {name: 'gcp-resource',   category: 'cloud-resource'});

// === Container / Orchestration ===
MERGE (:AssetType {name: 'container',  category: 'service'});
MERGE (:AssetType {name: 'kubernetes', category: 'container'});
MERGE (:AssetType {name: 'docker',     category: 'container'});

// === ICS / OT ===
MERGE (:AssetType {name: 'ics-ot',       category: 'service'});
MERGE (:AssetType {name: 'modbus',       category: 'ics-ot'});
MERGE (:AssetType {name: 'siemens-s7',   category: 'ics-ot'});

// === Email ===
MERGE (:AssetType {name: 'email-server', category: 'service'});
MERGE (:AssetType {name: 'smtp',         category: 'email-server'});
MERGE (:AssetType {name: 'imap',         category: 'email-server'});

// === Auto-create HAS_SUBTYPE from category ===
MATCH (parent:AssetType), (child:AssetType)
WHERE child.category = parent.name
MERGE (parent)-[:HAS_SUBTYPE]->(child);
```

Roughly 39 nodes. Categories were chosen to cover every `subdomain` in the current skill corpus plus the AI-adversary mapping discussion. The seed is intentionally small — extending it is an explicit decision tracked in [docs/skillogy-roadmap.md](../skillogy-roadmap.md) (TBD).

---

## 10. Validation Rules

`validate_graph.py` runs these as Cypher queries and fails the build on any violation:

```cypher
-- R1: no orphan offensive skills (must be in a phase)
MATCH (s:Skill {kind: 'offensive'})
WHERE NOT (s)-[:IN_PHASE]->(:Phase)
RETURN s.name AS violation_orphan;

-- R2: no REQUIRES cycles
MATCH path = (s:Skill)-[:REQUIRES*]->(s)
RETURN [n IN nodes(path) | n.name] AS violation_cycle;

-- R3: every offensive skill has ≥ 1 MITRE mapping
MATCH (s:Skill {kind: 'offensive'})
WHERE NOT (s)-[:IMPLEMENTS]->()
RETURN s.name AS violation_unmapped;

-- R4: TA0xxx never appears as IMPLEMENTS target
MATCH (s:Skill)-[:IMPLEMENTS]->(t:Tactic)
RETURN s.name AS skill, t.id AS violation_tactic_misuse;

-- R5: no deprecated/revoked techniques are mapped
MATCH (s:Skill)-[:IMPLEMENTS]->(t)
WHERE t.deprecated = true OR t.revoked = true
RETURN s.name AS skill, t.id AS violation_deprecated;

-- R6: T1190 over-reliance (≥ 10 skills mapped to a single technique)
MATCH (s:Skill)-[:IMPLEMENTS]->(t)
WITH t.id AS tech_id, count(s) AS n
WHERE n >= 10
RETURN tech_id, n AS warning_over_used;

-- R7: subdomain ↔ Phase consistency
MATCH (s:Skill)
WHERE NOT EXISTS {
  MATCH (s)-[:IN_PHASE]->(p:Phase) WHERE p.name = s.subdomain
}
RETURN s.name, s.subdomain AS violation_phase_mismatch;
```

R6 is a warning (not a failure) — over-reliance is a smell, not a bug.

Coverage analysis (informational only, attached to the PR diff comment):

```cypher
-- Techniques with zero skill coverage (across both Technique and SubTechnique)
MATCH (t:Technique)
WHERE t.deprecated = false AND t.revoked = false
  AND NOT (t)<-[:IMPLEMENTS]-(:Skill)
  AND NOT (t)-[:HAS_SUBTECHNIQUE]->(:SubTechnique)<-[:IMPLEMENTS]-(:Skill)
MATCH (tac:Tactic)-[:HAS_TECHNIQUE]->(t)
RETURN tac.id AS tactic, t.id AS technique, t.name AS name
ORDER BY tactic, technique;
```

---

## 11. Migration from `SkillsMiddleware`

Skillogy ships behind a feature flag during transition.

| Step | Status | What |
|---|---|---|
| 1 | Skillogy v0.1 ships | `SkillogyMiddleware` exists; default agent config still uses `SkillsMiddleware` |
| 2 | A/B opt-in | Agents can opt in via `agent_config.skill_backend: skillogy`; both work side by side |
| 3 | Benchmark | Compare on a 50-case failure set + NESTFUL-style multi-hop. Token cost, routing accuracy, latency |
| 4 | Default flip | If benchmark passes, `skillogy` becomes the default; `SkillsMiddleware` enters deprecation |
| 5 | Remove | After one release cycle, delete `SkillsMiddleware` |

`SKILL.md` authoring is unchanged across all steps. Plugin authors are unaffected — `decepticon-sdk` continues to read frontmatter the same way; the graph build just sees their files too.

---

## 12. Open Questions

These are explicitly out of scope for v0.1; tracking them here so they aren't forgotten:

| ID | Question | Likely resolution |
|---|---|---|
| OQ-1 | Should Soundwave's 8 generated artifacts (RoE, CONOPS, Threat Profile, etc.) each get their own `:Skill` node, or just be `(:Agent)-[:GENERATES]->(:Artifact)`? | Agent-level for v0.1; per-artifact in v0.2 if the granularity proves useful |
| OQ-2 | Dual-tag `llm-redteam/*` skills with MITRE ATLAS techniques (`AML.T...`) | Defer to v0.2; needs separate ATLAS STIX importer |
| OQ-3 | Should `find_skill` be invoked automatically at phase transitions (Mode C) instead of purely on-demand? | Stay on-demand for v0.1 to preserve LLM autonomy; revisit after benchmark |
| OQ-4 | Monolithic skill decomposition (`exploit/web/SKILL.md` → 30 leaf nodes) | v0.2 — `decompose_skill` LLM pass + per-leaf MoC layer |
| OQ-5 | RL-style graph co-evolution (SkillGraph paper) from successful engagement traces | v0.3 — depends on having a stable trace pipeline |
| OQ-6 | Where do `DetectionRule` (Service banner → AssetType) entries live — code or graph? | Graph (own label `:DetectionRule`) — keeps "knowledge in graph, code does traversal" |

---

## 13. References

### Internal docs
- [docs/skills.md](../skills.md) — current skill system
- [docs/knowledge-graph.md](../knowledge-graph.md) — existing attack graph
- [docs/design/attack-graph-schema.md](attack-graph-schema.md) — attack graph schema (label conventions)
- [docs/agents.md](../agents.md) — 10 specialist agents

### MITRE
- ATT&CK Enterprise v19.1 — <https://attack.mitre.org/resources/updates/updates-april-2026/>
- STIX bundle — <https://github.com/mitre-attack/attack-stix-data>
- v19 Defense Evasion split discussion — <https://medium.com/mitre-attack/attack-v19-ff329cb65d66>
- CISA "Best Practices for ATT&CK Mapping" — <https://www.cisa.gov/sites/default/files/2023-01/Best%20Practices%20for%20MITRE%20ATTCK%20Mapping.pdf>
- MITRE ATLAS v5.4 (AI-as-target framework) — <https://atlas.mitre.org/>

### Prior art (selected — full list maintained out-of-tree)

| Work | What we adopted |
|---|---|
| GoS — Graph of Skills (arXiv 2604.05333) | Personalized PageRank routing over typed edges |
| LiteGraph-MCP (github.com/colorc/litegraph-mcp) | Index-Only response shape — pointers, not bodies |
| kingjulio8238/skill_graph | Five-tool MCP surface (find/load/prereqs/next/chain) |
| ESCO-PrereqSkill (arXiv 2507.18479) | Zero-shot LLM inference of prerequisite edges |
| SkillNet (arXiv 2603.04448) | Three-layer ontology (taxonomic / relational / package) |
| Agent-as-a-Graph (arXiv 2511.18194) | `:Agent` nodes co-equal with `:Skill`, type-specific RRF |
| Knowledge Conceptualization Impacts RAG (arXiv 2507.09389) | Justification for medium-complexity schema (11 labels, not 50) |
| MSC-Bench (HF 2510.19423) | Three benchmark anti-patterns to avoid (flat namespace, overlap, fragmented eval) |

### Frameworks we considered but did not adopt for v0.1

| Work | Why deferred |
|---|---|
| SSL — Scheduling/Structural/Logical representation (arXiv 2604.24026) | Requires re-authoring every `SKILL.md`; violates "organic" principle |
| CMO RDF/OWL + SHACL (arXiv 2605.01582) | Cypher properties express the same constraints with less authoring burden |
| Tool Graph Retriever (arXiv 2508.05152) | Requires 300 K labeled dependency pairs; over-investment at 146 skills |
| GraSP DAG compilation (arXiv 2604.17870) | Reserved for v0.2 (STRIPS plane with `PRODUCES`/`CONSUMES`) |
| SkillGraph RL co-evolution (arXiv 2605.12039) | Reserved for v0.3 (needs stable trace pipeline) |

---

## 14. Changelog

- **2026-05-28** — Initial design draft. v0.1 scope: 11 node labels, 8 explicit edge types + 2 LLM-inferred edge types, MITRE v19.1 importer with Defense Evasion split handling, ~35-node AssetType seed, 5-tool middleware interface, 12-stage CI build pipeline. v0.2 schema is sketched but not implemented (capability plane, composes-with, RoE forbid edges, MITRE ATLAS dual-tag).
