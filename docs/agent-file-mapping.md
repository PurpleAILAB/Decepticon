# Agent & Skill → File-Write Mapping

> Authoritative mapping of **which agent / which skill is instructed to write
> which file**, extracted verbatim from the agent system prompts
> (`packages/decepticon/decepticon/agents/prompts/standard/*.md`) and the
> skill catalogs (`packages/decepticon/decepticon/skills/**/SKILL.md`).
>
> This is a *literal* inventory of the instructions as written — not a
> normative spec. Where the prompts and skills disagree on a path, both are
> recorded under [§4 Known inconsistencies](#4-known-inconsistencies); those
> are the seeds for the planned external-research improvement pass.
>
> For the architecture behind these files (where they physically live, the
> orchestrator read protocol, client surfacing) see
> [`agent-file-conventions.md`](agent-file-conventions.md).
>
> **Redesign applied (2026-06-12).** The §4 inconsistencies have been resolved
> in the skill/prompt contract, informed by
> [`design/evidence-and-findings-conventions-research.md`](design/evidence-and-findings-conventions-research.md).
> Key outcomes: operational findings keep the stable `findings/FIND-NNN.md`
> key; deliverable findings now use a severity-sorted, human-readable
> `report/<severity><NN>-<slug>.md` (e.g. `report/critical01-struts-rce.md`)
> with `id: FIND-NNN` retained in frontmatter; credentials unified to
> `exploit/creds/initial.json`; and optional `cwe`/`vrt` fields plus the
> CVSS-vector requirement were added to the finding templates. See §4 for the
> per-item resolution.

All paths are relative to the engagement workspace root (`/workspace`, which
maps to `~/.decepticon/workspace/<engagement-slug>/` on the host).

---

## 1. Per-agent write instructions

Each row is an instruction found in that agent's system prompt. "When"
summarizes the trigger; "Cite" is the prompt line.

### Orchestration tier

#### Decepticon (orchestrator) — `agents/prompts/standard/decepticon.md`

No bash; writes only via workspace file tools and OPPLAN CRUD.

| File | Format | When / why | Cite |
|------|--------|-----------|------|
| `exploit/creds/credentials.md` | Markdown (verbatim secret) | Immediately when a `task()` return yields a high-value secret, before `update_objective` | decepticon.md:60 |
| `report/executive-summary.md` | Markdown | Final-report sequence at engagement close | decepticon.md:124 |
| `report/technical-report.md` | Markdown | Final-report sequence | decepticon.md:125 |
| `report/finding-NNN.md` | Markdown | Promote each `findings/FIND-NNN.md` to deliverable tier | decepticon.md:126 |
| `plan/opplan.json` | JSON | Auto-persisted by `add_objective`/`update_objective` (not a manual write) | decepticon.md:21 |

Reads (not writes): `plan/roe.json` before every dispatch; `recon/SUMMARY.md` after every recon return.

#### Soundwave (planner) — `agents/prompts/standard/soundwave.md`

`write_file` is its primary output tool; it produces **eight planning JSON
documents** and explicitly does NOT write the OPPLAN.

| File | Schema | Notes | Cite |
|------|--------|-------|------|
| `plan/roe.json` | `RoE` | Always written first (legal scope) | soundwave.md:52,136 |
| `plan/threat-profile.json` | `ThreatProfile` | MITRE-mapped adversary persona | soundwave.md:53,137 |
| `plan/conops.json` | `CONOPS` | Threat model + kill chain, inside RoE | soundwave.md:54,140 |
| `plan/deconfliction.json` | `DeconflictionPlan` | Red-team vs real-threat identifiers | soundwave.md:55,143 |
| `plan/contact.json` | `ContactPlan` | Operator + escalation + abort recipients | soundwave.md:56,145 |
| `plan/data-handling.json` | `DataHandlingPlan` | Retention + encryption + chain-of-custody | soundwave.md:57,148 |
| `plan/abort.json` | `AbortPlan` | Halt triggers + AI-aware safety gates | soundwave.md:58,152 |
| `plan/cleanup.json` | `CleanupPlan` | Expected artifact inventory + removal commands | soundwave.md:59,157 |

### Phase tier (kill-chain specialists)

#### Recon — `agents/prompts/standard/recon.md`

Output cap: **2 files/objective** (report + optionally one raw scan file).

| File | Format | When / why | Cite |
|------|--------|-----------|------|
| `recon/SUMMARY.md` | Markdown + terminal token | **Mandatory** last action before returning; contains `RECON_OBSERVATIONS:` / `RECON_BUDGET_EXHAUSTED` / `RECON_BLOCKED:` | recon.md:82 |
| `recon/report_<target>.md` | Markdown | Detailed recon report (the capped deliverable) | recon.md:21,167 |
| `recon/probed.txt` | Text (append) | Dedup log for every iterating HTTP probe | recon.md:26–37 |
| `findings/FIND-{NNN}.md` | Markdown | Per verified discovery (after loading finding-protocol skill) | recon.md:24 |
| `findings/evidence/` | Raw | Evidence backing a finding | recon.md:24 |
| `timeline.jsonl` | JSON Lines (append) | Real activity/finding events only | recon.md:24 |
| one raw scan-data file | tool-native | Optional; nmap XML / ffuf JSON saved, not inlined | recon.md:21,23 |

#### Exploit — `agents/prompts/standard/exploit.md`

Output cap: **3 files/objective** (`shells.json`, `creds/initial.json`, one notes file).

| File | Format | When / why | Cite |
|------|--------|-----------|------|
| `exploit/creds/credentials.md` | Markdown (verbatim) | **Immediately** on capturing any high-value secret, before anything else (Rule 15) | exploit.md:77,91 |
| `exploit/shells.json` | JSON | Active session inventory | exploit.md:23,181,186 |
| `exploit/creds/initial.json` | JSON | Captured credentials from initial exploitation | exploit.md:23,185 |
| `exploit/tried.txt` | Text (append) | Probe dedup log | exploit.md:44–45 |
| `exploit/ACTIVE.md` | Markdown | Vector lock while a confirmed vector is being worked | exploit.md:49 |
| `findings/FIND-{NNN}.md` | Markdown | Success terminal artifact (verified exploitation) | exploit.md:24,89 |
| `exploit/CONVERGED.md` | Markdown | Convergence terminal artifact (vector confirmed, extraction incomplete) | exploit.md:101 |
| `exploit/PIVOT.md` | Markdown | Pivot terminal artifact (+ negative `FIND-NNN.md`) | exploit.md:116 |
| `exploit/EXIT_REPORT.md` | Markdown | Exit-report terminal artifact (no working oracle) | exploit.md:124 |
| `findings/evidence/` | Raw | Evidence backing a finding | exploit.md:24 |
| `timeline.jsonl` | JSON Lines (append) | Real activity/finding events | exploit.md:24 |

#### Post-exploit — `agents/prompts/standard/postexploit.md`

Output cap: **5 files/objective** across the `post-exploit/` tree.

| File | Format | When / why | Cite |
|------|--------|-----------|------|
| `findings/FIND-{NNN}.md` | Markdown | Success terminal artifact (new cred/escalation/lateral hop) | postexploit.md:20,33 |
| `post-exploit/creds/` | JSON/loot | Credential storage (plaintext only here, encrypt loot) | postexploit.md:16,35 |
| `post-exploit/privesc/` | Markdown/loot | Privilege-escalation artifacts | postexploit.md:35 |
| `post-exploit/lateral/` | Markdown/loot | Lateral-movement artifacts | postexploit.md:35 |
| `post-exploit/loot/` | loot | Collected loot | postexploit.md:35 |
| `post-exploit/network_map.json` | JSON | Internal network topology | postexploit.md:35 |
| `post-exploit/EXIT_REPORT.md` | Markdown | Escalation-block / exit terminal artifact | postexploit.md:37,51 |
| `findings/evidence/` | Raw | Evidence backing a finding | postexploit.md:20 |
| `timeline.jsonl` | JSON Lines (append) | Real activity/finding events | postexploit.md:20 |

#### Analyst — `agents/prompts/standard/analyst.md`

Primary output is the **knowledge graph**, not flat files.

| Target | Tool | When / why | Cite |
|--------|------|-----------|------|
| KG nodes/edges | `kg_record(observations)` | Every meaningful observation; promote validated finding with `kind="Finding"` | analyst.md:17,24,33 |
| KG bulk ingest | `kg_ingest(scanner_kind, path)` | Bulk-parse scanner output (sarif/nuclei_jsonl/httpx_jsonl/nmap_xml) | analyst.md:18,61,120 |
| scanner output files | `bash(... -o /workspace/<file>)` | e.g. `nuclei … -o /workspace/nuclei.jsonl` then ingest | analyst.md:119–120 |

(Analyst writes `findings/FIND-NNN.md` only via the shared finding protocol when promoting a confirmed finding.)

### Domain specialists

| Agent | File(s) instructed | When / why | Cite |
|-------|-------------------|-----------|------|
| AD operator (`ad_operator.md`) | `findings/credentials/` (obtained certs/creds); KG via `kg_record` (`kind="Credential"`/`Finding`) | Cert/credential capture, manual-confirmed AD work | ad_operator.md:23,56 |
| Cloud hunter (`cloud_hunter.md`) | `findings/secrets/SECRET-<NNN>.md` | Every plaintext secret | cloud_hunter.md:30 |
| Contract auditor (`contract_auditor.md`) | `findings/FIND-NNN.md`; KG via `kg_record` (`kind="Finding"`) | Foundry-validated findings | contract_auditor.md:21,26 |
| Reverser (`reverser.md`) | `findings/FIND-NNN.md`; `findings/binaries/<binary>.md` | Every observation; one record per binary examined | reverser.md:16,23 |
| Mobile operator (`mobile_operator.md`) | `findings/credentials/`; `findings/components/`; `recon/endpoints.md` | Creds, exported components, backend URLs | mobile_operator.md:23–24 |
| Phisher (`phisher.md`) | `findings/credentials/CAMPAIGN-<id>.md`; `evidence/`, `findings/credentials/` | Per campaign capture | phisher.md:29,44 |
| Wireless operator (`wireless_operator.md`) | `recon/airspace.md` | Airspace recon (BSSID/PMF/clients) | wireless_operator.md:25 |
| Blue Cell (`blue_cell.md`) | No files — `defense_brief(engagement_name=...)` tool + `DetectionFired` KG nodes | Read-only out-brief | blue_cell.md:41 |
| Forensicator (`forensicator.md`) | Skill-driven (loads `skills/standard/dfir/SKILL.md`); analysis-only, no fixed file contract in prompt | — | forensicator.md:13 |
| OSINT / ICS / IoT / Supply-chain operators | Skill-driven (load their `skills/standard/<domain>/SKILL.md` catalog); file outputs come from the loaded subskill, no fixed path in the agent prompt | — | osint_operator.md:11; ics_operator.md:27; iot_operator.md:45; supply_chain_operator.md:12 |

---

## 2. Per-skill write instructions

Skills that define a file template, naming scheme, or write step.

### Shared

| Skill | Defines | Cite |
|-------|---------|------|
| `shared/finding-protocol/SKILL.md` | Canonical `findings/FIND-{NNN}.md` operational template (YAML frontmatter + Description/Evidence/Next); ID = `ls findings/*.md \| wc -l`; raw evidence → `findings/evidence/FIND-{NNN}_{desc}.txt`; timeline append to `timeline.jsonl`; deliverable promotion to `report/finding-NNN.md` | finding-protocol:22,44,75,90 |

### Reporting skills

| Skill | Defines | Cite |
|-------|---------|------|
| `standard/recon/reporting/SKILL.md` | Recon finding docs in `findings/`; evidence `findings/evidence/FIND-{NNN}_{tool}.txt`; consolidated `report_<target>_final.md` | recon/reporting:36,83,420 |
| `standard/exploit/reporting/SKILL.md` | `findings/FIND-{NNN}.md` (heavyweight CVSS 4.0 template); `exploit/shells.json` (SHELL-NNN→finding_id); `exploit/creds_initial.json` (CRED-NNN→finding_id); attack paths `findings/attack-paths/PATH-{NNN}.md`; evidence under `findings/evidence/` | exploit/reporting:19,194,219,252 |
| `standard/post-exploit/reporting/SKILL.md` | Phase-specific `findings/FIND-{NNN}.md` (cred-access/privesc/lateral); attack paths `findings/attack-paths/PATH-{NNN}.md`; creds `post-exploit/creds/`; `network_map.json`; detection-gap matrix | post-exploit/reporting:27,396,509 |
| `standard/decepticon/final-report/SKILL.md` | Reads all `findings/*.md` + `findings/attack-paths/PATH-*.md` + `timeline.jsonl` + `plan/*.json`; writes `report/executive-summary.md` and `report/technical-report.md` | final-report:14,19–25 |

### Soundwave planning templates

Each template validates against a `decepticon_core.types` schema and writes
to `plan/`:

| Skill | Output file | Schema |
|-------|-------------|--------|
| `soundwave/roe-template` | `plan/roe.json` | `RoE` |
| `soundwave/conops-template` | `plan/conops.json` + `plan/deconfliction.json` | `CONOPS`, `DeconflictionPlan` |
| `soundwave/threat-profile` | `plan/threat-profile.json` | `ThreatProfile` |
| `soundwave/contact-template` | `plan/contact.json` | `ContactPlan` |
| `soundwave/data-handling-template` | `plan/data-handling.json` | `DataHandlingPlan` |
| `soundwave/abort-template` | `plan/abort.json` | `AbortPlan` |
| `soundwave/cleanup-template` | `plan/cleanup.json` | `CleanupPlan` |
| `soundwave/opplan-converter` | (guidance for orchestrator's `plan/opplan.json`) | `OPPLAN` |

### Benchmark / CTF

| Skill | Defines | Cite |
|-------|---------|------|
| `benchmark/SKILL.md` | Single batched flag sweep to `/tmp/flag_sweep.txt` (+ `/tmp/find_flag.txt` for non-standard paths); no SUMMARY/report — the flag string echoed in the orchestrator's final message IS the deliverable; suspends planning + final-report rules | benchmark/SKILL.md:23,31,48–57 |

---

## 3. File namespace summary

| Namespace | Owner(s) | Counter / naming |
|-----------|----------|------------------|
| `plan/*.json` | Soundwave (8 docs) + orchestrator (`opplan.json`) | fixed names |
| `recon/SUMMARY.md` | Recon | single (overwritten per dispatch) |
| `recon/report_<target>.md`, `recon/endpoints.md`, `recon/airspace.md` | Recon, Mobile, Wireless | per-target |
| `findings/FIND-{NNN}.md` | Recon, Exploit, Post-exploit, Reverser, Contract auditor, Analyst | **shared** counter (`ls findings/*.md \| wc -l`) |
| `findings/attack-paths/PATH-{NNN}.md` | Exploit, Post-exploit, Analyst | per chain (≥2 findings) |
| `findings/evidence/FIND-{NNN}_{desc}.txt` | all phase agents | tied to FIND-NNN |
| `findings/credentials/`, `findings/secrets/SECRET-<NNN>.md`, `findings/components/`, `findings/binaries/` | AD, Cloud, Mobile, Phisher, Reverser | domain-specific |
| `exploit/{shells.json, creds/initial.json, creds/credentials.md, ACTIVE.md, CONVERGED.md, PIVOT.md, EXIT_REPORT.md, tried.txt}` | Exploit (+ orchestrator writes `creds/credentials.md`) | fixed names |
| `post-exploit/{creds/, privesc/, lateral/, loot/, network_map.json, EXIT_REPORT.md}` | Post-exploit | fixed names |
| `report/{executive-summary.md, technical-report.md, finding-NNN.md}` | Orchestrator | final deliverables |
| `timeline.jsonl` | all phase agents (append) | single global |

---

## 4. Known inconsistencies — RESOLVED 2026-06-12

These were conflicts **between** the prompts and the skills, or across skills,
found while compiling this map. All were resolved in the redesign pass; each
item below records the original conflict and its **Resolution**.

1. **Credential file path: subdir vs underscore.**
   - Exploit prompt + post-exploit prompt: `exploit/creds/initial.json`
     (`exploit.md:23`, `postexploit.md:71`).
   - Exploit reporting skill: `exploit/creds_initial.json`
     (`exploit/reporting:219`).
   These name the same artifact two different ways. Downstream readers
   (post-exploit "reads from `creds/` tree") assume the subdir form.
   **Resolution:** standardized on the subdir form `exploit/creds/initial.json`
   in exploit/reporting (4 sites + file-layout tree), co-located with
   `creds/credentials.md`.

2. **Finding filename scheme: `FIND-{NNN}.md` vs `{severity}-{slug}.md`.**
   - `finding-protocol` (the canonical shared template) mandates
     `findings/FIND-{NNN}.md` with the ID as cross-reference
     (`finding-protocol:22`).
   - `recon/reporting` example tree shows
     `findings/critical-exposed-mysql-api-example-com.md` i.e.
     `{severity}-{slug}.md` (`recon/reporting:242,422`).
   - `final-report` reads "every `findings/*.md` (named `{severity}-{slug}.md`)"
     (`final-report:37`) — it expects the slug form, while every agent prompt
     writes the `FIND-NNN` form.
   This is the highest-impact mismatch: the final report's frontmatter parse
   assumes a filename convention the agents do not produce.
   **Resolution:** operational tier keeps the stable `findings/FIND-NNN.md`
   key (the code already agrees: `shutdown.py` globs `FIND-*.md`, the SARIF
   renderer and every `finding_id` cross-ref key on it). The stray
   `{severity}-{slug}.md` prose in recon/reporting (two trees), exploit/reporting
   (tree + checklist), post-exploit/reporting (tree), and final-report:37 was
   corrected to `FIND-NNN.md`. The **deliverable tier** adopts a separate
   human-readable, severity-sorted scheme `report/<severity><NN>-<slug>.md`
   (e.g. `report/critical01-struts-rce.md`) — safe because it is a terminal
   snapshot (severity final, no inbound cross-refs) and retains `id: FIND-NNN`
   in frontmatter for traceability.

3. **`SUMMARY.md` listed as both forbidden and mandatory (recon).**
   - Output-discipline rule forbids creating "SUMMARY" organizational docs
     (`recon.md:21`).
   - The pre-return invariant mandates `write_file("recon/SUMMARY.md", ...)`
     (`recon.md:82`).
   Reconcilable in spirit (the ban targets *ad-hoc* summary docs, the
   mandate is the *handoff* artifact) but the literal wording collides.

4. **Recon report filename: `report_<target>.md` vs `report_<target>_final.md`.**
   - Recon prompt: `recon/report_<target>.md` (`recon.md:21,167`).
   - Recon reporting skill workspace tree: `report_<target>_final.md`
     (`recon/reporting:420`).

5. **`recon/SUMMARY.md` is overwritten, not versioned.** Multiple recon
   dispatches against the same engagement each rewrite the single
   `recon/SUMMARY.md`. The orchestrator only ever reads the latest; earlier
   dispatch observations are lost unless they were promoted to `FIND-NNN.md`.
   (Behavioral, not a path conflict — flagged for the redesign.)

6. **Plan-document paths: bare `roe.json` vs `plan/roe.json`.** The code is
   canonical: `middleware/roe.py:125` reads `<workspace>/plan/roe.json`,
   `tools/opplan.py:28` writes `/workspace/plan/opplan.json`, and
   `runtime/shutdown.py:420` checkpoints `plan/opplan.json`. soundwave writes
   the planning bundle to `plan/*.json`. But several prompts and skills
   referenced the docs **without** the `plan/` prefix (e.g. analyst/exploit/
   postexploit "check `roe.json`", soundwave templates "Read/Write `roe.json`",
   `decepticon/orchestration` and `exploit/reporting` file-layout trees showing
   root-level docs). **Resolution:** every *path-action* reference (read / write
   / check / update / file-layout tree) was normalized to the `plan/` prefix
   across the standard prompts and skills. Purely conceptual document-name
   shorthand in soundwave's authoring playbooks (e.g. "copy the kill chain into
   `conops.json`") was intentionally left, since those describe content
   assembly, not a file path the agent reads.

---

### Source files

- Agent prompts: `packages/decepticon/decepticon/agents/prompts/standard/*.md`
- Skills: `packages/decepticon/decepticon/skills/{shared,standard,benchmark}/**/SKILL.md`
- Schemas: `packages/decepticon-core/decepticon_core/types/`
