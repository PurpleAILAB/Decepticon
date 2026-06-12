# Agent File & Reporting Conventions

> How Decepticon's agents write to disk, hand work off to each other, and
> report back to the orchestrator. This is the authoritative reference for
> the workspace file contract that the 16 specialist agents, the skill
> catalogs, and the client UIs all depend on.

Decepticon's multi-agent loop is **file-mediated, not memory-mediated**.
Each specialist agent is spawned with a fresh context window (no parent
transcript), does its work, writes its results to agreed-upon paths in the
engagement workspace, and returns a short summary. The orchestrator reads
those files on the next turn to decide what to dispatch next. Findings
survive context summarization, agent restarts, and process crashes because
they live on disk, not in the LangGraph message history.

This document covers:

1. [Where files physically live](#1-where-files-physically-live)
2. [The workspace directory layout](#2-the-workspace-directory-layout)
3. [The file-writing tools agents have](#3-the-file-writing-tools-agents-have)
4. [Per-phase artifact contracts](#4-per-phase-artifact-contracts) (recon / exploit / post-exploit / analyst)
5. [Terminal-state handoff artifacts](#5-terminal-state-handoff-artifacts)
6. [The orchestrator read protocol](#6-the-orchestrator-read-protocol)
7. [Cross-agent shared conventions](#7-cross-agent-shared-conventions)
8. [Planning documents (Soundwave)](#8-planning-documents-soundwave)
9. [Final report generation](#9-final-report-generation)
10. [The knowledge graph as a parallel channel](#10-the-knowledge-graph-as-a-parallel-channel)
11. [Benchmark / CTF mode differences](#11-benchmark--ctf-mode-differences)
12. [Client-side surfacing](#12-client-side-surfacing)
13. [Lifecycle and checkpointing](#13-lifecycle-and-checkpointing)
14. [Writing a plugin agent that fits the contract](#14-writing-a-plugin-agent-that-fits-the-contract)

---

## 1. Where files physically live

Agents see a single virtual root: **`/workspace`**. Three layers sit
between that virtual path and the host disk:

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| Agent-facing | `FilesystemMiddleware` (`middleware/filesystem.py`) | Exposes `ls / read / write / edit / grep / glob / download_files`. No `execute` tool — shell goes through the bash tool. |
| Engagement scoping | `EngagementFilesystemBackend` | Maps virtual `/workspace` → real `/workspace/<engagement-slug>` and rejects path traversal (`/workspace/../etc`). Writes a `.engagement` marker at the root on first use. |
| Transport | `HTTPSandbox` (`backends/http_sandbox.py`) | Forwards every file op over HTTP to the sandbox daemon (`/upload_files`, `/download_files`, …). |

Inside the sandbox container, the daemon (`sandbox_server/app.py` wrapping
`sandbox_kernel/`) executes the actual disk operations. The container's
`/workspace` is **bind-mounted** from the host:

```
~/.decepticon/workspace/<engagement-slug>/   (host)
        ⇅  docker volume bind
/workspace/                                   (container, what the agent sees)
```

So a write to `/workspace/findings/FIND-001.md` lands at
`~/.decepticon/workspace/<slug>/findings/FIND-001.md` on the host and is
visible to the web dashboard (which mounts the same tree read-only).

**Engagement isolation is physical, not state-level.** Each engagement is
its own subdirectory; the scoping backend prevents any agent from reaching
another engagement's tree. This is why state-merge reducers between agents
are minimal — agents don't pass files through LangGraph state, they share a
bound directory.

Two side-channel logs live alongside the workspace and are written by
middleware, not agents:

- `events.jsonl` — append-only structured event log (`EventLogMiddleware`,
  `runtime/event_log.py`): engagement start, agent turns, LLM/tool calls,
  findings, OPPLAN updates. Failures here never break the agent.
- `audit.jsonl` — HMAC-chained RoE decision ledger (`_audit_sink.py`).
  Every RoE pass/refuse is stamped with `seq`, `hash`, `prev_hash`, `hmac`;
  tampering with record N invalidates all later records.

---

## 2. The workspace directory layout

```
/workspace/                              ← virtual root (real: /workspace/<slug>)
├── plan/                                ← planning bundle (Soundwave-authored, JSON)
│   ├── roe.json                         ← Rules of Engagement (read before every dispatch)
│   ├── conops.json                      ← Concept of Operations
│   ├── deconfliction.json
│   ├── threat-profile.json
│   ├── data-handling.json
│   ├── cleanup.json
│   ├── abort.json                       ← optional
│   └── opplan.json                      ← Operational Plan (objectives + status)
│
├── recon/                              ← reconnaissance artifacts (lazy)
│   ├── SUMMARY.md                       ← MANDATORY terminal handoff (terminal token inside)
│   ├── report_<target>.md               ← detailed markdown recon report
│   └── probed.txt                       ← HTTP probe dedup log (append-only)
│
├── exploit/                            ← initial-access / exploitation artifacts (lazy)
│   ├── shells.json                      ← active session inventory
│   ├── creds/
│   │   ├── initial.json                 ← captured credentials (structured)
│   │   └── credentials.md               ← verbatim high-value secrets (written first, always)
│   ├── ACTIVE.md                        ← vector lock during an active attempt
│   ├── CONVERGED.md                     ← convergence terminal state
│   ├── PIVOT.md                         ← pivot terminal state
│   └── EXIT_REPORT.md                   ← exit-report terminal state
│
├── post-exploit/                       ← post-exploitation artifacts (lazy)
│   └── creds/                           ← extends exploit/creds/ across the kill chain
│
├── findings/                           ← cross-phase findings namespace
│   ├── FIND-001.md                      ← one finding per file (operational tier)
│   ├── FIND-002.md
│   └── evidence/                        ← raw evidence backing findings
│
├── report/                             ← final deliverables (generated at close)
│   ├── executive-summary.md
│   ├── technical-report.md
│   └── finding-NNN.md                   ← deliverable-tier promotions of FIND-NNN.md
│
├── timeline.jsonl                       ← append-only activity/finding timeline
├── .sessions/                           ← per-session tmux logs (<session>.log)
└── .engagement                          ← scoping marker
```

**Lazy creation is a hard rule.** Agents create a parent directory only
immediately before writing a required artifact. Scaffolding empty
directories or placeholder files (`README`, `INDEX`, `SUMMARY` stubs,
`ASSESSMENT`) is explicitly forbidden across all agent prompts — it wastes
context and provides no operational value.

**Markdown for deliverables, JSON for operational data.** Every
human-facing document (findings, reports, summaries) is Markdown. JSON is
reserved for machine-read operational state: `opplan.json`, `shells.json`,
`creds/initial.json`, `timeline.jsonl`.

---

## 3. The file-writing tools agents have

The filesystem middleware exposes these tools to every agent that mounts it:

| Tool | Use |
|------|-----|
| `write_file(path, content)` | Create/overwrite a workspace file |
| `read_file(path)` | Read a workspace file (orchestrator uses this to read sub-agent output) |
| `edit_file(path, …)` | In-place edit |
| `ls(path)` | List a workspace directory |
| `glob(pattern)` | Find files by pattern (e.g. `findings/*.md`) |
| `grep(pattern, …)` | Search workspace file contents |
| `download_files(...)` | Pull files out of the sandbox |

There is no `execute`/shell tool in the filesystem middleware — all command
execution flows through the single bash tool (`DockerSandbox.execute_tmux`),
which runs in persistent tmux sessions and logs to `.sessions/<name>.log`.

**The `${WORKSPACE}` anchor (hard rule).** Operational agents'
first bash action sets and exports the workspace root:

```bash
WORKSPACE="$(pwd)"
export WORKSPACE
```

All subsequent artifact writes use `"${WORKSPACE}/recon/..."`,
`"${WORKSPACE}/findings/..."`, never bare relative paths. This prevents path
drift when sub-shells, background jobs, or tool wrappers change the working
directory mid-task. Agents must not assume `pwd` equals the engagement root
after any `cd`.

**The orchestrator (decepticon) has no bash tool at all.** It only has
OPPLAN CRUD tools (`add_objective`, `update_objective`, `get_objective`,
`list_objectives`) plus the workspace file tools (`read_file`, `write_file`,
`ls`) for reading sub-agent artifacts. All offensive work is delegated via
`task(subagent, prompt)`. The filesystem tools on the orchestrator are for
workspace artifacts only — `grep`/`glob`/`ls`/`read_file` against a remote
URL or domain is forbidden; remote recon goes through `task("recon", ...)`.

---

## 4. Per-phase artifact contracts

Each phase agent observes its own output discipline (a cap on how many files
it may produce) and writes a specific set of artifacts.

### Recon (`recon.md`)

- **Output cap:** max 2 files per objective — `recon/report_<target>.md`
  (detailed markdown report) plus optionally one raw scan-data file.
- **Mandatory handoff:** the LAST action before returning **must** be
  `write_file("recon/SUMMARY.md", ...)` with a terminal-state token on its
  own line (see §5). Returning without `SUMMARY.md` is treated as a
  sub-agent crash by the orchestrator.
- **Dedup log:** `recon/probed.txt` — every iterating HTTP probe appends its
  URL here and checks before re-probing; the file survives summarization, so
  the agent resumes from the last line rather than rescanning.
- **Observation-only:** recon records what it *saw* (banners, status codes,
  reflected payloads, exposed paths, captured sessions), never a
  vulnerability class and never a recommended skill path. Classification is
  the orchestrator's job.
- **Findings:** for each verified discovery, `load_skill(
  "/skills/shared/finding-protocol/SKILL.md")` then write
  `findings/FIND-{NNN}.md`; raw evidence to `findings/evidence/`.

### Exploit (`exploit.md`)

- **Output cap:** max 3 files per objective — `exploit/shells.json`,
  `exploit/creds/initial.json`, plus optionally one notes file.
- **Reads first:** always `read_file("recon/SUMMARY.md")` before the first
  probe — for *evidence context* (payload selection), not for routing
  (recon doesn't classify; the orchestrator's `task()` prompt already cites
  the skill to load first).
- **Credential preservation (Rule 15):** the moment any high-value secret is
  captured, `write_file("exploit/creds/credentials.md", "<verbatim secret>")`
  **before doing anything else**, so it survives summarization. `creds/` is
  the canonical credentials location across the kill chain; post-exploit
  reads and extends it at `post-exploit/creds/`.
- **Vector lock:** while a confirmed vector is being worked but access isn't
  yet achieved, `exploit/ACTIVE.md` holds the working state; switching vuln
  class without writing `exploit/PIVOT.md` is forbidden.
- **Mandatory handoff:** exactly one terminal artifact — `findings/FIND-NNN.md`
  (success), `exploit/CONVERGED.md`, `exploit/PIVOT.md` + negative
  `findings/FIND-NNN.md`, or `exploit/EXIT_REPORT.md` (see §5).

### Post-exploit (`postexploit.md`)

- Extends the credentials tree at `post-exploit/creds/`.
- Writes `findings/FIND-NNN.md` for privilege escalation, credential access,
  lateral movement, and discovery, following the same finding protocol.

### Analyst (`analyst.md`)

- Primary output is the **knowledge graph**, not flat files: every
  meaningful observation is written via `kg_record(...)` (atomic batch of
  nodes/edges) or `kg_ingest(scanner_kind, path)` (bulk scanner parse).
  Free-text notes are forgotten next iteration; the graph survives.
- Promotes to a `Finding` node only with a validated PoC (success +
  negative-control evidence) and full CVSS vector, and writes the
  corresponding `findings/FIND-NNN.md`.

---

## 5. Terminal-state handoff artifacts

Every phase dispatch ends in exactly one terminal state, each with a
required exit artifact. The orchestrator greps for the token to detect
which one. **Returning without an exit artifact is a crash signal** — the
orchestrator has nothing to dispatch on. A documented failure beats an
undocumented success attempt.

### Recon terminal states (token inside `recon/SUMMARY.md`)

| State | Token (on its own line) | SUMMARY.md contains |
|-------|-------------------------|---------------------|
| Success | `RECON_OBSERVATIONS: <one-line evidence summary>` | Service/stack inventory, endpoints (status/size/behavior), captured sessions, source/backup exposure |
| Surface exhausted | `RECON_BUDGET_EXHAUSTED` | What was probed, what was negative, what surface remains untried |
| Blocked | `RECON_BLOCKED: <reason>` | Specific blocker, what was tried, recommended next step |

### Exploit terminal states

| State | Exit artifact | Contents |
|-------|---------------|----------|
| Success | `findings/FIND-NNN.md` (+ `exploit/creds/credentials.md` if a secret was captured) | Verified evidence: commands, output, access level |
| Convergence | `exploit/CONVERGED.md` | Vector class, timestamp, working evidence curl/script, next concrete step, known risks. Telemetry tag: `<!-- converged:<ts>:<vector_class> -->` |
| Pivot | `exploit/PIVOT.md` + negative `findings/FIND-NNN.md` | Most-promising remaining vector + the recorded negative result. Driven by the **3-class pivot rule** (3 same-class payload fails → next class; 3 classes fail on an endpoint → endpoint hardened) |
| Exit report | `exploit/EXIT_REPORT.md` | What was tried, what was ruled out (tied to recon SUMMARY's "ruled out" list), most-promising remaining angle, why the dispatch is closing |

---

## 6. The orchestrator read protocol

After **every** recon `task()` returns, the orchestrator (decepticon)
executes a fixed decision tree (in `decepticon.md`):

1. `read_file("recon/SUMMARY.md")`. If missing/empty → treat as crash.
2. Grep for the terminal token.
3. If `RECON_OBSERVATIONS:` (or any noteworthy observation — captured
   session, default-cred login, source-exposure hit): the **next turn must
   be `task("exploit", ...)`**. Not more recon, not bash, not more planning.
   `OPPLANMiddleware` rejects `update_objective(status="blocked")` in this
   state — there is observable surface; exploit just hasn't tried it yet.
4. The orchestrator does the classification recon refused to do: it loads
   the domain router skill (`/skills/standard/exploit/<domain>/SKILL.md`),
   maps observations → sub-skill, and **cites that skill in the exploit
   `task()` prompt** ("Load this skill BEFORE the first probe: `load_skill(
   '/skills/standard/exploit/<domain>/<X>.md')`").
5. The exploit dispatch context must include: workspace path, the
   `RECON_OBSERVATIONS:` line verbatim, relevant SUMMARY.md excerpts, target
   URL + observed parameters, captured tokens, prior findings, lessons
   learned. Sub-agents start with zero parent context.

**Anti-poisoning safeguard:** if exploit returns BLOCKED because the cited
vector failed validation, the orchestrator must NOT re-dispatch the same
classification. It re-reads SUMMARY.md and either picks a different sub-skill
or dispatches a focused secondary recon. Confidence inflation on the first
classification is the cycle's #1 failure mode.

### Sub-agent failure modes

The orchestrator distinguishes three fault classes (`decepticon.md`):

| Fault | Signal | Response |
|-------|--------|----------|
| INFRA | `task()` error contains `TimeoutExpired`, `tmux capture-pane`, `docker exec`, `connection reset`, `broken pipe`, `sandbox unavailable` | Retry same sub-agent ONCE, same prompt. Second failure → `update_objective(blocked, "sandbox infra fault: …")` |
| CRASH | `task()` returns `{}` / empty, no error | Retry ONCE. Second empty → `update_objective(blocked, "sub-agent crash: empty return on 2 attempts")` |
| WANDERING | summary names same-shape repeated calls with zero results ("tried many URLs all 404") | Re-read SUMMARY.md, re-dispatch a NARROWED prompt naming a different vector, or switch sub-agent. After two consecutive wandering dispatches → `update_objective(blocked, "wandering: no convergence")` |

### Objective state discipline

- Always `get_objective(id)` **before** `update_objective` (never in
  parallel).
- Never mark `passed` without a finding file and evidence in the notes.
- Never mark `blocked` without documenting what was attempted.
- All OPPLAN objectives must reach a terminal status
  (passed/blocked/cancelled/failed) before the engagement closes.

---

## 7. Cross-agent shared conventions

These conventions are shared by all phase agents, injected through shared
skills and the prompt builder.

- **Finding protocol** — `/skills/shared/finding-protocol/SKILL.md` defines
  the operational `FIND-{NNN}.md` template: YAML frontmatter (`id`,
  `severity`, `title`, `agent`, `objective_id`, `discovered_at`,
  `evidence_pointer`) plus `## Description`, `## Evidence`, `## Next`
  sections. One vulnerability per file; the next ID is `ls findings/*.md |
  wc -l + 1`. The `FIND-NNN` namespace is **shared across all phases** —
  recon, exploit, and post-exploit all draw from one counter.
- **Timeline** — a single append-only `timeline.jsonl` records real activity
  and finding events for the whole engagement; never initialized as a
  placeholder.
- **Inventory linking** — every `SHELL-NNN` in `shells.json` and every
  `CRED-NNN` in `creds/initial.json` must carry a `finding_id` pointing at
  the `FIND-NNN.md` that explains it.
- **Cross-cutting prompt fragments** — the prompt builder
  (`agents/prompts/builder.py`) injects shared sections into operational
  agents: faithful reporting (report observations exactly), a verification
  gate (verify CRITICAL/HIGH findings a second way), a finding-protocol
  pointer, output discipline (1–2 sentence inter-tool text, full structure
  only in the final artifact), and an analyst mindset. The orchestrator gets
  a subset (no verification gate). Static sections sit before a prompt-cache
  boundary; dynamic sections (date, skills metadata, engagement context)
  after it.

### Scoped sub-agent dispatch (`task_spec.py`)

Delegation is a deterministic, scoped handoff — the child receives no parent
transcript. `SubAgentTaskSpec` carries: `objective`, `scope` (RoE limits),
`inputs` (tool-arg key/values the parent gathered), `expected_outputs`
(artifact names expected back), `parent_artifacts` (workspace paths the
child may *read* — never inlined content), `engagement_id`, and
`parent_agent`. `render()` sorts dict keys so identical inputs produce
identical text, enabling prompt caching for the child run.

---

## 8. Planning documents (Soundwave)

Before any offensive dispatch, the **Soundwave** planning agent (and its
`/skills/standard/soundwave/*` templates) author the JSON planning bundle in
`plan/`. Each validates against a Pydantic v2 schema in
`decepticon_core.types`:

| File | Skill | Schema |
|------|-------|--------|
| `plan/roe.json` | `roe-template` | `RoE` |
| `plan/conops.json` + `plan/deconfliction.json` | `conops-template` | `CONOPS`, `DeconflictionPlan` |
| `plan/threat-profile.json` | `threat-profile` | `ThreatProfile` |
| `plan/data-handling.json` | `data-handling-template` | `DataHandlingPlan` |
| `plan/opplan.json` | `opplan-converter` | `OPPLAN` |
| `plan/cleanup.json` | `cleanup-template` | `CleanupPlan` |
| `plan/abort.json` (optional) | `abort-template` | — |

OPPLAN objectives use `OBJ-{NNN}` IDs and each carries acceptance criteria
that must include a scope check, an OPSEC check, and an output-persistence
criterion naming the artifact path the work will produce. `roe.json` is the
contract the orchestrator re-reads before **every** `task()` dispatch.

---

## 9. Final report generation

At engagement close, the orchestrator runs the final-report sequence
(`decepticon.md` → `/skills/standard/decepticon/final-report/SKILL.md`):

1. `load_skill("/skills/standard/decepticon/final-report/SKILL.md")`.
2. Generate `report/executive-summary.md` (C-level, no tool names/jargon).
3. Generate `report/technical-report.md` (findings detail, attack-path
   narratives, detection-gap analysis, activity timeline, remediation
   roadmap, MITRE ATT&CK coverage).
4. Promote each operational `findings/FIND-NNN.md` to a deliverable-tier
   `report/finding-NNN.md` (heavyweight CVSS 4.0 vector, CWE, MITRE
   mapping, remediation), cross-referenced against the CONOPS success
   criteria.
5. Call `ops_cleanup_engagement()` to stop any sidecar workloads (BHCE,
   Sliver) tagged to the engagement.

---

## 10. The knowledge graph as a parallel channel

Alongside flat files, agents share structured state through a Neo4j-backed
knowledge graph (`KGMiddleware` builds `KGStore` + the `kg_*` tools). The KG
is the one intentionally shared service across both Docker networks, scoped
per engagement via a `set_active_engagement(label)` contextvar so all writes
carry the engagement label.

- Analyst writes `Host / Service / Vulnerability / Finding / Credential /
  Secret / Entrypoint / CrownJewel / Hypothesis / AttackPath` nodes via
  `kg_record` / `kg_ingest`.
- The chain planner queries the KG for attack paths.
- Blue Cell (read-only, no bash) records `DetectionFired` nodes linked via
  `USES_RULE` / `DETECTED` edges and emits a `defense_brief`.

Flat files are the human-facing, grep-friendly handoff channel; the KG is
the queryable, relationship-aware channel. Findings exist in both: a
`FIND-NNN.md` on disk and a `Finding` node in the graph.

---

## 11. Benchmark / CTF mode differences

When `benchmark/SKILL.md` is active, the deliverable is a flag string, and
two generic rules are intentionally suspended:

- **No planning bundle** — no `roe`/`conops`/`deconfliction` required (the
  flag is the deliverable).
- **No final report** — no executive summary; the flag string *is* the
  report.

On a verified flag/flag-equivalent credential, the orchestrator marks
remaining objectives `passed` and its **very next response must re-echo the
flag verbatim** (e.g. `Flag captured: FLAG{...}`) — the harness scans only
the orchestrator's final message. CTF flag-path conventions
(`/tmp/flag_sweep.txt` from a single batched filesystem sweep) live **only**
in `/skills/benchmark/` — the generic exploit skills under
`/skills/standard/exploit/` deliberately exclude flag conventions so the
core capability stays benchmark-agnostic.

---

## 12. Client-side surfacing

The host-mounted workspace tree is what the clients render.

- **Web dashboard** (`clients/web`): the Documents page scans the folders
  `recon`, `exploit`, `post-exploit`, `findings`, `report` via
  `/api/workspace/<name>/files` and renders a folder tree + file viewer
  (`.md` / `.json` / plaintext), with per-domain icons. `plan/` is excluded
  from Documents — it has its own Plan page. The Findings viewer parses
  `findings/FIND-NNN.md` directly.
- **CLI** (`clients/cli`): no dedicated file browser; sub-agent tool calls
  and results stream through `StreamingRunnable` (LangGraph SDK), so findings
  appear inline in the event flow as they are written.

---

## 13. Lifecycle and checkpointing

- **Lazy directories** — every phase directory is created on first write,
  never scaffolded ahead of time.
- **Survival across summarization** — agents write SUMMARY/credentials/probe
  logs to disk *before* anything else precisely so the next cold-context
  cycle can resume from files rather than memory.
- **Graceful shutdown** — on SIGINT/SIGTERM, `runtime/shutdown.py` flushes
  in-flight `findings/FIND-*.md`, the `plan/opplan.json` checkpoint, a
  partial `report/report_partial_executive.md`, and `events.jsonl`, so a
  killed engagement still leaves a coherent workspace.
- **Orphan reaping** — on daemon startup, decepticon-named tmux sockets from
  a crashed prior run are reaped before new sessions start.

---

## 14. Writing a plugin agent that fits the contract

A community/SaaS plugin agent (registered under the `decepticon.subagents`
entry-point group, declaring `parent_agents=("decepticon",)`) inherits the
file contract for free if it:

1. **Mounts `FilesystemMiddleware`** so it gets the scoped `/workspace`
   tools — never write outside `/workspace`.
2. **Anchors `${WORKSPACE}`** in its first bash call and uses absolute
   workspace paths for every artifact.
3. **Writes findings via the finding protocol** — `load_skill(
   "/skills/shared/finding-protocol/SKILL.md")`, one `findings/FIND-NNN.md`
   per discovery, evidence under `findings/evidence/`, drawing from the
   shared `FIND-NNN` counter.
4. **Returns a terminal handoff artifact** — define the equivalent of
   recon's `SUMMARY.md` token or exploit's terminal files so the orchestrator
   can detect completion state by grep, and document it in the agent's
   prompt. Returning with no exit artifact reads as a crash.
5. **Keeps deliverables Markdown, operational data JSON**, and observes an
   output-file cap to avoid context bloat.

Because dispatch is file-mediated and context is fresh per objective, a
plugin agent that honors these five points is indistinguishable from a
built-in specialist to the orchestrator — no changes to the OSS core are
needed.

---

### See also

- [`docs/engagement-workflow.md`](engagement-workflow.md) — the phase
  walkthrough and the `## Outputs` workspace summary.
- [`docs/agents.md`](agents.md) — agent roster, middleware stacks, and the
  fresh-context model.
- [`docs/architecture.md`](architecture.md) — network topology, container
  boundaries, and the single-objective data-flow diagram.
- [`docs/skill-schema.md`](skill-schema.md) — `SKILL.md` frontmatter and
  validation rules.
