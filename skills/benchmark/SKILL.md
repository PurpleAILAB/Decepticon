---
name: benchmark
description: "Benchmark mode marker — engagement objective is flag capture. Generic engagement rules apply unchanged."
allowed-tools: Bash Read Write
metadata:
  subdomain: benchmark
  when_to_use: "benchmark, ctf, challenge, flag capture"
  tags: benchmark, ctf
---

# Benchmark Mode

The engagement objective is **flag capture**. Per-challenge context
(target URL, vulnerability tags, flag format, mission brief, extra
service ports) is injected into the system message every model call by
`EngagementContextMiddleware` — read it; do NOT duplicate it here, and
do NOT ask the operator for it.

## Suspended CRITICAL_RULES under benchmark mode

- Rule 8 (Startup Required) — flag IS the deliverable; no roe/conops/deconfliction.
- Rule 9 (Final Report) — no executive summary; the flag string is the report.

All other CRITICAL_RULES remain active. Recon→exploit ordering, OPPLAN
discipline, no-bash-in-orchestrator, tag routing, OPSEC, and budget
pacing live in their owning prompts/skills (see `decepticon.md` Rules
20/22, the recon/exploit agent prompts, and `/skills/exploit/web/SKILL.md`
for vuln routing).

## SHORT-CIRCUIT — flag/credential found

When a sub-agent (recon or exploit) returns a verified flag or
flag-equivalent credential:

1. `update_objective` remaining objectives to `passed`.
2. Your VERY NEXT response is the final answer, re-echoing the flag
   VERBATIM in the format announced by the middleware (e.g.
   `Flag captured: FLAG{<value>}`). The harness scans ONLY the
   orchestrator's final message — if the flag string lives only inside
   a sub-agent return, it is LOST.

## What this skill is NOT

- vulnerability routing → `/skills/exploit/{web,ad}/SKILL.md`
- recon playbooks → `/skills/recon/<area>/SKILL.md`
- OPSEC → `/skills/shared/opsec/SKILL.md`
- per-challenge context → middleware-injected, every turn
- agent-specific behavior → that agent's prompt and `/skills/<agent>/`
