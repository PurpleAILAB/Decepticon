---
name: decepticon
description: Drive Decepticon autonomous red-team engagements over MCP — launch an authorized penetration test or bug-bounty engagement, watch it live, steer it by chatting, and pull findings. Use when the user asks to run a pentest, security engagement, recon, or bug bounty with Decepticon.
metadata: { "version": "2.0.0", "homepage": "https://github.com/PurpleAILAB/Decepticon" }
---

# Decepticon engagements

Drive **Decepticon** — an autonomous multi-agent red-team framework — through
its MCP server, as if you had its CLI in chat. Run an authorized engagement end
to end (recon → exploitation → post-exploitation → reporting) across web,
network, AD, cloud, mobile, smart-contract, and binary targets, **watch it
progress, and steer it as it runs**.

## Prerequisites

- A Decepticon **LangGraph server** must be running and reachable (default
  `http://localhost:2024`, set via the MCP server's `DECEPTICON_API_URL`).
- The **`decepticon` MCP server** must be registered in your runtime
  (`decepticon-mcp`, from `pip install 'decepticon[mcp]'`). Launch it with
  `DECEPTICON_SKIP_BOOT=1` so it starts fast. See
  `docs/integrations/external-agents.md` in the Decepticon repo.

## Authorization — read first

Only run engagements against assets you are **explicitly authorized** to test.
Always pass scope and rules of engagement in the `instruction` argument of
`decepticon_start_engagement` (what is in scope, what is out of scope). The
orchestrator enforces RoE on every tool call, but you are responsible for
giving it correct scope. Never start an engagement against a target the user
has not confirmed is in scope.

## Tools

Everything is keyed by `thread_id` (the engagement handle from
`decepticon_start_engagement` / `decepticon_list_engagements`).

- `decepticon_list_graphs()` — discover graphs (`decepticon` = full kill chain,
  `recon` = recon only, `soundwave` = planning).
- `decepticon_list_engagements(limit)` — browse/resume recent engagements.
- `decepticon_start_engagement(targets, instruction, scan_mode, engagement_name?, assistant?)`
  — launch a **background** engagement; returns `{thread_id, run_id, engagement_name, status}`.
- `decepticon_transcript(thread_id, after_index, limit)` — read the orchestrator
  narrative incrementally (poll the returned `next_index`).
- `decepticon_watch(thread_id, max_seconds, max_events)` — tail the live
  sub-agent stream for a few seconds.
- `decepticon_send_message(thread_id, message, assistant?)` — steer focus,
  answer the coordinator, or switch models with `/model <id>`.
- `decepticon_engagement_state(thread_id)` — OPPLAN / objectives / scope / phase.
- `decepticon_engagement_status(thread_id, engagement_name?)` — run status +
  whether findings are persisted yet.
- `decepticon_engagement_findings(engagement_name, include_sarif?)` — findings
  summary (counts) or the full SARIF v2.1.0 document.
- `decepticon_cancel_engagement(thread_id)` — stop the active run.

## Workflow

1. (Optional) `decepticon_list_graphs()` to pick the right graph.
2. `decepticon_start_engagement(targets=["https://target"], instruction="In scope: target.example.com and *.target.example.com. Out of scope: production billing.", scan_mode="standard")`.
   Keep the returned `thread_id`.
3. Watch: poll `decepticon_transcript(thread_id, after_index=<last next_index>)`
   and narrate progress to the user. Use `decepticon_watch(thread_id)` for a
   live sub-agent feed. Engagements take minutes — **do not block**; check back.
4. Steer when useful: `decepticon_send_message(thread_id, "skip the staging host, dig into the API")`.
5. When `status` is terminal or findings appear, call
   `decepticon_engagement_findings(engagement_name, include_sarif=true)` and
   report severity + reproduction. Use `decepticon_engagement_state` for the OPPLAN.

## Notes

- `scan_mode`: `quick` | `standard` | `deep` (depth/timeout profile).
- For bug bounties, set `instruction` to the program scope verbatim and
  summarise findings with severity + reproduction from the SARIF results.
- Resume any engagement later via `decepticon_list_engagements()` →
  `decepticon_transcript(thread_id)`.
