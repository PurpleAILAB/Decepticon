# Skillogy

Skillogy is Decepticon's knowledge-graph-backed skill discovery system. It replaces text-matching autoload with a typed Neo4j graph built at CI time and exposed to agents through five tools. Skills are still authored as `SKILL.md` files — Skillogy is the discovery layer on top of them.

> **Status**: v0.1 design — see [docs/design/skillogy.md](design/skillogy.md) for the full specification.
>
> The current production path is still the text-matching `SkillsMiddleware` ([docs/skills.md](skills.md)). Skillogy ships behind a feature flag and becomes default once benchmark validation passes.

---

## Why a Graph?

The legacy `SkillsMiddleware` injects all 146+ skill `name + description` strings into the system prompt at agent boot, then relies on the LLM to read this catalog and pick the right skill by keyword match. This breaks down at scale:

- LLM tool selection drops to ~49 % accuracy past 100 tools.
- Skill descriptions are flat text — no machine-readable prerequisite, composition, or RoE constraints.
- Routing skills (e.g. `exploit/web/SKILL.md`) hand-list dozens of sub-skills; adding a sub-skill requires editing the parent.
- "Why did the agent pick X?" is unaudits — the choice is opaque LLM reasoning.

Skillogy moves the routing signal out of text and into a typed graph: phase, MITRE technique, asset type, prerequisite skill, RoE constraint, capability, and Map-of-Concepts category all become first-class nodes connected by typed edges. The agent calls `find_skill(...)`; the graph traversal returns ranked candidates with reasoning paths.

The LLM stays autonomous. Its tools get smarter.

---

## How It Works

### Build time (CI)

```
SKILL.md (146+) ─┐
MITRE STIX v19.1 ┼─► graph_builder ─► skills/.graph/skills.cypher
AssetType seed ──┘                    (checked into repo, reviewable in PR diff)
```

A Python pipeline (`packages/decepticon/decepticon/graph_builder/`) parses every `SKILL.md` frontmatter, imports the pinned MITRE STIX bundle, seeds asset type / phase / agent / MoC nodes, runs an LLM pass to infer prerequisite and applicability edges, validates the result with SHACL-like Cypher rules, and emits a deterministic Cypher dump. The dump is checked into the repo so changes show up in PR diffs.

### Runtime (agent)

```
SkillogyMiddleware
  before_agent():
    - load skills.cypher idempotently
    - inject ~300-token MoC summary for the current phase
  get_tools(): registers 5 tools
```

The agent's system prompt no longer carries a 4 KB catalog. It sees a tiny navigation map for its current phase (e.g. "you are in reconnaissance; concepts available: passive-recon, active-recon, web-recon, ad-recon — call `find_skill(...)` for specifics") and reaches into the graph on demand.

---

## Node Types

| Label | Purpose | Example |
|---|---|---|
| `:Skill` | One `SKILL.md` file | `passive-recon`, `sqli`, `kerberoasting` |
| `:Tactic` | MITRE ATT&CK tactic | `TA0043 Reconnaissance`, `TA0005 Stealth` |
| `:Technique` | MITRE technique | `T1190 Exploit Public-Facing App` |
| `:SubTechnique` | MITRE sub-technique | `T1595.001 Active Scanning: IP Blocks` |
| `:AssetType` | Engagement-asset taxonomy | `web-service`, `mysql`, `active-directory`, `aws-s3` |
| `:Capability` | Abstract output a skill produces / consumes | `valid-credential`, `shell-on-target`, `ai-provider-access` |
| `:Tool` | External tool | `nmap`, `sqlmap`, `bloodhound` |
| `:Phase` | Kill-chain phase | `reconnaissance`, `initial-access`, `lateral-movement` |
| `:MoC` | Map-of-Concepts navigation category | `web-exploitation`, `ad-attacks`, `cloud-pivot` |
| `:Agent` | Decepticon specialist agent | `soundwave`, `recon`, `exploit`, `decepticon` |
| `:RoEConstraint` | Explicit Rules-of-Engagement constraint | `no-data-exfil`, `scope-internal-only` |

---

## Edge Types

### From `SKILL.md` frontmatter (explicit, no LLM)

| Edge | Meaning |
|---|---|
| `(:Skill)-[:IN_PHASE]->(:Phase)` | Skill belongs to a kill-chain phase |
| `(:Skill)-[:IMPLEMENTS]->(:Technique \| :SubTechnique)` | MITRE mapping |
| `(:Skill)-[:USES_TOOL]->(:Tool)` | Skill invokes an external tool |
| `(:Skill)-[:BELONGS_TO]->(:MoC)` | Skill is in a navigation category |
| `(:Agent)-[:CAN_USE]->(:Skill)` | Agent is the default caller |
| `(:Tactic)-[:HAS_TECHNIQUE]->(:Technique)` | MITRE hierarchy |
| `(:Technique)-[:HAS_SUBTECHNIQUE]->(:SubTechnique)` | MITRE hierarchy |
| `(:AssetType)-[:HAS_SUBTYPE]->(:AssetType)` | Asset taxonomy hierarchy |

### LLM-inferred (v0.1)

| Edge | Meaning |
|---|---|
| `(:Skill)-[:REQUIRES]->(:Skill)` | Prerequisite skill (`lateral-movement-smb` requires `credential-dump-lsass`) |
| `(:Skill)-[:APPLICABLE_TO]->(:AssetType)` | Skill targets this kind of asset (`web-recon` → `web-service`) |

Every LLM-inferred edge carries `confidence`, `provenance`, `justification`, `inferred_at`, `inferrer_model` properties — every routing decision can be traced back to its evidence.

### Reserved for v0.2

`PRODUCES` / `CONSUMES` (capability plane), `COMPOSES_WITH`, `SUBSTITUTES`, `FORBIDDEN_BY` (RoE filtering), `IMPLEMENTS_ATLAS` (MITRE ATLAS dual-tag for AI-target skills).

### Runtime bridge to the attack graph

| Edge | Created by |
|---|---|
| `(:Service)-[:IS_OF]->(:AssetType)` | DetectionRule when a service is discovered |
| `(:Credential)-[:REALIZES]->(:Capability)` | Post-exploit when a credential is verified |
| `(:Agent)-[:OBTAINS]->(:Capability)` | Startup, e.g. Decepticon obtains `ai-provider-access` (T1588.007) |

These bridges let `find_skill` reason over engagement state without leaving Neo4j.

---

## Tools Exposed to the Agent

All five tools are registered by `SkillogyMiddleware.get_tools()`. The graph returns pointers; bodies stay on disk.

| Tool | What it does | v0.1 |
|---|---|---|
| `find_skill(query, phase?, asset_hint?)` | Top-K skills for the current task, with reasoning path | ✅ |
| `load_skill(name_or_path)` | Read the full `SKILL.md` body from disk | ✅ |
| `get_prereqs(skill_name)` | Prerequisite skills (via `REQUIRES`) | ✅ |
| `suggest_next(last_skill)` | Likely next skill (via `COMPOSES_WITH` + capability chain) | v0.2 |
| `get_skill_chain(target_capability)` | Backward-chained skill sequence to reach a capability | v0.2 |

`find_skill` example response:

```json
[
  {
    "name": "web-recon",
    "path": "/skills/standard/recon/web-recon/SKILL.md",
    "score": 0.92,
    "reasoning": [
      "phase:reconnaissance",
      "implements:T1595.002",
      "applicable_to:web-service (specificity=1)"
    ],
    "prereqs_met": true,
    "roe_compliant": true
  }
]
```

The reasoning path makes every routing decision auditable. RoE-violating skills are filtered out by `FORBIDDEN_BY` edges (v0.2) — they never appear in results.

---

## MITRE ATT&CK Version

Skillogy pins **MITRE ATT&CK Enterprise v19.1** (released 2026-05-12). The STIX bundle URL is hard-coded; bumping the version is an explicit PR. Two v19 changes are handled by the importer:

- **Defense Evasion split** — `TA0005` was renamed to "Stealth"; new tactic `TA0112` "Defense Impairment" was introduced. STIX consumers that only check IDs silently mis-interpret. The importer applies a known-rename map.
- **AI-adversary techniques** (relevant because Decepticon *is* an AI attacker):
  - `T1682` — Query Public AI Services
  - `T1683.001` — Generate Content: Written Content (mapped to Soundwave's planning artifacts)
  - `T1588.007` — Obtain Capabilities: AI (mapped to LLMFactory)

The build pipeline validates that no skill maps to a tactic ID (`TA0xxx`) — only techniques and sub-techniques. It also fails on deprecated / revoked technique mappings.

For the audit that led to this work, see the project's MITRE mapping review notes (out-of-tree in the knowledge vault).

---

## What Doesn't Change

- **`SKILL.md` format** — frontmatter, body, `references/`, `scripts/` are unchanged. Plugin authors continue to write skills the same way.
- **The 10 specialist agents** and the orchestrator. Their code is unmodified except for the middleware swap.
- **Neo4j infrastructure** — the skill graph and the existing attack graph ([docs/knowledge-graph.md](knowledge-graph.md)) share one instance, distinguished by node labels.

---

## Migration

Skillogy ships behind a feature flag:

```python
# agent_config.yaml
skill_backend: skills        # default — text-matching SkillsMiddleware
# or:
skill_backend: skillogy      # opt-in — graph-backed SkillogyMiddleware
```

Steps:

1. v0.1 lands with `skills` as default; `skillogy` is opt-in.
2. Benchmark on a 50-case failure set + NESTFUL-style multi-hop. Compare token cost, routing accuracy, latency.
3. Once benchmark passes, flip the default to `skillogy`.
4. After one release cycle, remove `SkillsMiddleware`.

Plugin SDK authors are unaffected at every step.

---

## Source Code Layout (planned)

```
packages/decepticon/decepticon/
├── middleware/
│   ├── skills.py              # legacy SkillsMiddleware (kept until deprecation)
│   └── skillogy.py            # NEW — SkillogyMiddleware
├── graph_builder/             # NEW — build-time pipeline
│   ├── build_skill_graph.py   # CLI entry point
│   ├── extract_frontmatter.py
│   ├── import_mitre_stix.py
│   ├── seed_asset_types.py
│   ├── seed_phases_mocs_agents.py
│   ├── infer_relations.py
│   ├── validate_graph.py
│   ├── emit_cypher.py
│   └── emit_manifest.py
└── tools/
    └── skillogy_tools.py      # NEW — find_skill, get_prereqs, etc.

skills/.graph/                  # NEW — build artifacts (checked in)
├── skills.cypher
└── manifest.json
```

---

## Related Docs

- **[docs/design/skillogy.md](design/skillogy.md)** — full design specification (schema, Cypher, build stages, validation rules, prior art)
- **[docs/skills.md](skills.md)** — current text-matching skill system (still production until migration completes)
- **[docs/knowledge-graph.md](knowledge-graph.md)** — existing attack graph that Skillogy shares Neo4j with
- **[docs/design/attack-graph-schema.md](design/attack-graph-schema.md)** — attack graph label conventions Skillogy follows
- **[docs/agents.md](agents.md)** — the 10 specialist agents represented as `:Agent` nodes
