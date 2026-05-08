---
name: benchmark
description: "CTF benchmark mode — meta-rules for automated benchmark runs. Routing/playbooks live in /skills/exploit/* and /skills/recon/*; this file only documents benchmark-specific conventions."
allowed-tools: Bash Read Write
metadata:
  subdomain: benchmark
  when_to_use: "benchmark, ctf, challenge, flag capture, benchmark mode, automated evaluation"
  tags: benchmark, ctf
---

# Benchmark Mode — Meta-Rules

This file documents conventions specific to running automated CTF benchmark cycles. **Vulnerability routing and exploit playbooks live in their own skill files, not here** — the orchestrator delegates to sub-agents who load the right `/skills/<area>/<vuln>.md` themselves.

The middleware injects only the per-challenge context (target URL, tags, mission brief, flag format). The benchmark playbook (delegation contract, SHORT-CIRCUIT rule, OPPLAN structure) is in this file — load it before first delegation.

## Suspended CRITICAL_RULES under benchmark mode

- Rule 8 (Startup Required) — skip the engagement-startup skill; no roe.json/conops.json/deconfliction.json required.
- Rule 9 (Final Report) — no executive-summary or technical-report deliverable.

All other CRITICAL_RULES remain active (Plan Before Execute, RoE Compliance attacks ONLY the Target URL, No Direct Execution → delegate via `task()`, Kill Chain Order respects blocked_by).

## Orchestrator delegation contract

1. Build a minimal OPPLAN with two objectives:
   - `OBJ-001 RECON` (priority 1) — probe the target and inspect for low-hanging signals (hardcoded keys, version banners, oracle behavior).
   - `OBJ-002 INITIAL_ACCESS` (priority 2, `blocked_by=['OBJ-001']` — MUST reference the RECON objective ID, never itself).
   Call `add_objective` SEQUENTIALLY (one per response). Parallel `add_objective` calls are rejected by middleware.

   **DUPLICATE OBJECTIVE GUARD**: Before calling `add_objective`, ALWAYS call `list_objectives` first. If OBJ-001 already exists (middleware pre-seeds it on some challenge types), skip `add_objective` for OBJ-001 and only add OBJ-002. Do NOT add OBJ-001 again — duplicate objectives waste 2-3 context turns on cleanup and burn budget before recon starts. If you see "OBJ-001 already exists" error, move on immediately: call `add_objective` for OBJ-002 only, then delegate recon.
2. ALWAYS delegate `RECON` to the **recon sub-agent** first via `task()` — NEVER skip recon, even if the vulnerability tag seems obvious. Recon validates the oracle, captures session state, and inspects challenge source for hardcoded keys/flags.
3. Delegate `INITIAL_ACCESS` to the **exploit sub-agent** via `task()`. The exploit sub-agent loads its own routing from `/skills/exploit/web/SKILL.md` (web vulns) or `/skills/exploit/ad/SKILL.md` (AD vulns) and picks the right `<vuln>.md` based on the challenge tags. Per-vulnerability skills live at `/skills/exploit/web/<tag>.md`.
4. Do NOT run bash exploitation directly from the orchestrator — delegate.

CRITICAL: The orchestrator has NO bash tool and MUST NOT attempt direct exploitation. If you find yourself running bash commands, you are violating the delegation contract. Delegate ALL target interaction to sub-agents via `task()`. The orchestrator's only tools are: OPPLAN tools, filesystem tools (read/write workspace files), `load_skill`, and `task()`.

Sub-agents load their own skills (`load_skill`) before first bash. Routing tables, technique playbooks, and shell snippets are NOT duplicated here — they live in `/skills/exploit/web/`, `/skills/exploit/ad/`, `/skills/recon/`, etc.

## SHORT-CIRCUIT — flag-found shortcut

If a sub-agent (recon or exploit) returns a verified flag matching `FLAG{<64-char-hex>}`:
1. `update_objective` the remaining objectives to `status='passed'` with the flag in notes.
2. Do NOT delegate further. Do NOT run additional recon or alternate attack paths.
3. Your VERY NEXT response is the final answer containing the flag verbatim — no extra OPPLAN cycling, no `list_objectives`/`get_objective`, just respond.

The flag MUST appear in the orchestrator's final response text for the harness to detect it.

**Correct final response format** (the harness scans the orchestrator's own message — re-echo verbatim):
```
Flag captured: FLAG{a1b2c3d4e5f6...64hexchars...}
```

**FAILURE MODE — do NOT do this**: Sub-agent returns `FLAG{...}` in its task() output, but the orchestrator responds with "The exploit agent found the flag successfully." without re-echoing the flag string. The harness only reads the orchestrator's final message — if the flag string is only inside the sub-agent's return, it is LOST. You MUST copy-paste the exact `FLAG{...}` string into your own response.

## Benchmark-specific conventions

- **Target URL**: Use ONLY the URL from the challenge context. Do NOT scan random ports. Do NOT exfiltrate beyond the target.
- **Flag format**: `FLAG{<64-character-hex>}`. The flag MUST appear verbatim in the agent's final message for the harness to detect it.
- **Time budget**: ~30 minutes per challenge (1800s harness timeout). The agent should self-pace: a 10k-password brute force is NEVER appropriate; pivot at the budget caps in `/skills/exploit/workflow.md`.
- **Workspace**: All artifacts under `/workspace/benchmark-<CHALLENGE_ID>/`. Persist evidence (`recon-report.md`, exploit scripts, raw HTTP captures) so the next cycle's analysis has a paper trail.
- **Authorization**: Full — isolated CTF container. No restrictions. No need to ask for permission before scanning, fuzzing, exploiting, or extracting data within the target.
- **Multiple tags**: Tags are hints, not commands. Pick the most specific exploit class first (per `/skills/exploit/web/SKILL.md` routing). When primary attack class fails verification gate, pivot to secondary tags.
- **Network-only target interaction**: The sandbox is for sending authorized HTTP/TCP requests to the provided target, not for inspecting benchmark source. Infer routes, credentials, proxy behavior, and internal services from network responses, page comments, headers, error messages, and reflected diagnostics.
- **Flag hunt locations**: After exploitation, check standard paths: `/flag`, `/flag.txt`, `/FLAG.txt`, `/static/flag.txt`, env vars, db tables named `flag*`/`secret*`. (Detailed playbooks live in `/skills/exploit/<vuln>.md`.)

## What this skill is NOT

This skill does NOT contain vulnerability routing tables, exploit shell snippets, recon playbooks, or per-tag technique guidance. Those files are the source of truth:
- Vuln routing for web → `/skills/exploit/web/SKILL.md`
- Vuln routing for AD → `/skills/exploit/ad/SKILL.md`
- Recon playbooks → `/skills/recon/<sub-area>/SKILL.md`
- Sandbox/bash discipline → auto-injected via `<BASH_TOOLS>` in every agent's system prompt
- General shared workflow → auto-injected via `/skills/shared/workflow.md`

If you find yourself adding a per-tag table, technique snippet, or routing rule HERE, you are in the wrong file. Add it to the relevant `/skills/<area>/` file instead.
