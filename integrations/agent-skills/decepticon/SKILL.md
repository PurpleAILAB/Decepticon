---
name: decepticon
description: Drive Decepticon autonomous red-team engagements over MCP — launch an authorized penetration test or bug-bounty engagement against a target, monitor progress, and pull findings. Use when the user asks to run a pentest, security engagement, recon, or bug bounty with Decepticon.
metadata: { "version": "1.0.0", "homepage": "https://github.com/PurpleAILAB/Decepticon" }
---

# Decepticon engagements

Drive **Decepticon** — an autonomous multi-agent red-team framework — through
its MCP server. Use it to run an authorized engagement end to end: recon →
exploitation → post-exploitation → reporting, across web, network, AD, cloud,
mobile, smart-contract, and binary targets.

## Prerequisites

- A Decepticon **LangGraph server** must be running and reachable (default
  `http://localhost:2024`, set via the MCP server's `DECEPTICON_API_URL`).
- The **`decepticon` MCP server** must be registered in your runtime
  (`decepticon-mcp`, from `pip install 'decepticon[mcp]'`). See
  `docs/integrations/external-agents.md` in the Decepticon repo.

## Authorization — read first

Only run engagements against assets you are **explicitly authorized** to test.
Always pass scope and rules of engagement in the `instruction` argument of
`decepticon_start_engagement` (what is in scope, what is out of scope). The
orchestrator enforces RoE on every tool call, but you are responsible for
giving it correct scope. Never start an engagement against a target the user
has not confirmed is in scope.

## Tools

- `decepticon_list_graphs()` — discover available engagement graphs
  (`decepticon` = full kill chain, `recon` = recon only, `soundwave` = planning).
- `decepticon_start_engagement(targets, instruction, scan_mode, engagement_name?, assistant?)`
  — launch a **background** engagement. Returns
  `{engagement_name, thread_id, run_id, status}`.
- `decepticon_engagement_status(thread_id, run_id, engagement_name)` — poll run
  status and whether findings are available yet.
- `decepticon_engagement_findings(engagement_name, include_sarif?)` — fetch a
  findings summary (counts by severity) or the full SARIF v2.1.0 document.
- `decepticon_cancel_engagement(thread_id, run_id)` — stop a run.

## Workflow

1. (Optional) `decepticon_list_graphs()` to pick the right graph.
2. `decepticon_start_engagement(targets=["https://target"], instruction="In scope: target.example.com and *.target.example.com. Out of scope: production billing.", scan_mode="standard")`.
   Keep the returned `engagement_name`, `thread_id`, and `run_id`.
3. Poll `decepticon_engagement_status(thread_id, run_id, engagement_name)`
   periodically. Engagements take minutes — **do not block**; check back and
   keep the user updated.
4. When `findings_available` is true (or `status` is terminal — `success`,
   `error`, `timeout`), call
   `decepticon_engagement_findings(engagement_name, include_sarif=true)` and
   report results to the user: severity, affected target, and reproduction.

## Notes

- `scan_mode`: `quick` | `standard` | `deep` (depth/timeout profile).
- For bug bounties, set `instruction` to the program's scope verbatim and
  summarise findings with severity + reproduction steps from the SARIF results
  so they can be pasted into a report.
