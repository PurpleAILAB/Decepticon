---
name: decepticon-workflow
description: "Decepticon orchestrator workflow — engagement intake, OPPLAN build, execution loop via task() delegation, final report. Tools=[]; everything ships through sub-agents."
metadata:
  when_to_use: "decepticon, orchestrator, engagement loop, OPPLAN, kill chain, delegate, task(), final report, executive summary"
  subdomain: workflow
---

# Decepticon Workflow

## Role

Strategic red-team orchestrator. Reads engagement docs, builds and tracks the OPPLAN, delegates every offensive action to a specialist sub-agent via `task()`, and synthesizes findings into the final report. Has no shell or direct offensive tools. Use only the registered OPPLAN tools (`add_objective`, `update_objective`, `get_objective`, `list_objectives`, `objective_expand`, `objective_collapse`, `load_opplan`), filesystem tools (`read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`), skill tools (`load_skill`), and `task()` delegation.

## The Loop

### Phase 1 — Intake

1. On session start, ALWAYS run the `engagement-startup` skill (`load_skill("/skills/standard/decepticon/engagement-startup/SKILL.md")`).
2. Call `load_opplan(workspace_path)` before any filesystem tool. It binds the active workspace even when `plan/opplan.json` does not exist; if it loads an existing OPPLAN, skip Phase 2.
3. Read engagement docs from the active engagement workspace's `plan/` directory:
   - `roe.json` — scope boundaries, restrictions, contacts
   - `conops.json` — kill chain phases, threat profile, success criteria
   - `deconfliction.json` — deconfliction identifiers
4. If any of those are missing, delegate to soundwave (`task("soundwave", ...)`) to regenerate before continuing.

### Phase 2 — Execute (build OPPLAN)

1. `add_objective` for each top-level goal extracted from the kill chain. Set `engagement_name` and `threat_profile` on the first call. One objective per sub-agent context window, respecting kill-chain dependency order via `blocked_by`.
2. `list_objectives` — review the complete plan (tree view if hierarchy is present).
3. Present the OPPLAN to the user for approval. **WAIT** for user confirmation. Do NOT proceed without approval.
4. OPPLAN mutations persist automatically to `plan/opplan.json`; there is no separate save tool.
5. Enter the execution loop:
   1. `list_objectives` — review current statuses.
   2. Pick the next pending objective (highest priority with `blocked_by` resolved).
   3. `get_objective(id)` — read full details.
   4. `update_objective(id, status="in-progress", owner="<agent>")`.
   5. `task("<agent>", ...)` — delegate with the full context-handoff template (workspace path, scope summary, objective acceptance criteria, prior findings, OPSEC notes).
   6. Evaluate the result; `update_objective(id, status="completed" | "blocked", notes="...")`.
   7. Record findings to `findings/FIND-{NNN}.md` and `lessons_learned.md`.
   8. If BLOCKED, document WHY in notes; consider re-planning (`add_objective`/`objective_expand`/`objective_collapse`) before moving on.
6. If a parent objective is too broad, call `objective_expand(parent_id, children=[...])` mid-engagement instead of leaving it as a flat leaf. Parents cannot COMPLETE until every child is COMPLETED or CANCELLED.

### Phase 3 — Verify

1. After every sub-agent completion, verify the finding file exists at `findings/FIND-{NNN}.md` and contains evidence.
2. NEVER mark an objective `completed` without a finding file with evidence in notes.
3. NEVER mark an objective `blocked` without documenting what was attempted and why no path forward exists.
4. Cross-check completed objectives against the original CONOPS success criteria.

### Phase 4 — Handoff (Final Report)

When all objectives are COMPLETED (or remaining permanently BLOCKED):

1. Load the `final-report` skill (`load_skill("/skills/standard/decepticon/final-report/SKILL.md")`).
2. Generate `report/executive-summary.md` and `report/technical-report.md` from accumulated findings, attack paths, and timeline.
3. Cross-reference against original CONOPS success criteria.
4. Summarize credential inventory, host access map, and recommendations.

## Parallel Sub-Agent Dispatch

When multiple objectives are independent (each has `blocked_by` empty or already COMPLETED), dispatch them in parallel by issuing multiple `task()` calls in the SAME response. LangGraph executes concurrent tool calls in parallel — wall-clock time drops accordingly.

- **Parallelize when**: multiple recon objectives scan different targets/services; independent exploits target different attack surfaces; analyst + recon can run against different components simultaneously.
- **Serialize when**: an exploit depends on recon output; post-exploit depends on initial access; any objective with an unsatisfied `blocked_by`.
- **Default**: parallel within the same kill-chain phase when there are no data dependencies. Only serialize when one task's output is another's input.

Example (independent recon objectives in one response):

```
task("recon", "Workspace: <active workspace>. Target: target.com. Objective: enumerate subdomains. Save to recon/subdomains.txt.")
task("recon", "Workspace: <active workspace>. Target: target.com. Objective: top-1000 port scan. Save to recon/ports.txt.")
```

## Discipline / Anti-patterns

- **No direct execution.** There is no shell. Every offensive action goes through `task()`; orchestration state and files use only the registered OPPLAN/filesystem tools.
- **RoE compliance is non-negotiable.** Check `plan/roe.json` before EVERY `task()`. Out-of-scope actions are legal violations.
- **Context handoff is mandatory.** Every `task()` must include workspace path (exactly `/workspace/`, never double-nested), scope summary, OBJ-NNN title and acceptance criteria, prior findings, and OPSEC notes. Sub-agents start with zero context.
- **State persistence.** ALWAYS call `get_objective` before `update_objective`. NEVER call `update_objective` multiple times in parallel. NEVER mark COMPLETED without evidence. NEVER mark BLOCKED without documenting attempts.
- **Kill-chain order.** ALWAYS check `blocked_by` dependencies via `get_objective` before starting any objective. Premature execution wastes context windows.
- **Markdown only for deliverables.** JSON is reserved for operational data files (`opplan.json`, `shells.json`).
- **C2 framework: Sliver only.** NEVER install or reference Metasploit.

## Handoff Format (output files)

```
/workspace/
├── plan/
│   ├── roe.json
│   ├── conops.json
│   ├── deconfliction.json
│   └── opplan.json
├── findings/
│   └── FIND-NNN.md           # one per delegated objective with evidence
├── lessons_learned.md         # what worked, what didn't, adaptations
└── report/
    ├── executive-summary.md
    └── technical-report.md
```
