---
name: engagement-startup
description: "Mandatory first-turn startup procedure — checks for existing engagements, resume/new selection, workspace initialization."
allowed-tools: Bash Read
metadata:
  subdomain: orchestration
  when_to_use: "agent startup, first message, session start"
  tags: startup, engagement-selection, workspace-init, resume
  mitre_attack: []
---

# Engagement Startup Procedure

**Execute this procedure on every session start, before any other action.**

## Step 1: Discover Existing Engagements

```
bash(command="ls -1 /workspace/ 2>/dev/null || echo '[empty]'")
```

## Step 2: Present Options to Operator

### If engagements exist

Present a numbered list and ask:

```
Existing engagements found:
  1. acme-external-2026
  2. internal-audit-q1

Options:
  [number] Resume an engagement
  [new]    Start a new engagement

Which would you like?
```

### If no engagements exist

```
No existing engagements found. Let's set up a new one.
What is the target or scope for this engagement?
```

## Step 3A: Resume Existing Engagement

1. Read planning documents:
   ```
   read_file("<engagement>/plan/roe.json")
   read_file("<engagement>/plan/conops.json")
   read_file("<engagement>/plan/deconfliction.json")
   read_file("<engagement>/plan/opplan.json")
   read_file("<engagement>/findings.md")
   ```
2. Summarize progress to the operator:
   - Objectives completed / total
   - Current phase (recon / exploit / post-exploit)
   - Last completed objective and key findings
   - Next pending objective
3. Ask: "Continue from where we left off?"
4. Begin the Ralph execution loop

## Step 3B: New Engagement (docs already created by Soundwave)

Soundwave has already interviewed the operator and created the engagement documents
(RoE, CONOPS, Deconfliction Plan) before the orchestrator was activated. The workspace
and planning documents already exist.

1. Verify documents exist:
   ```
   bash(command="ls /workspace/plan/roe.json /workspace/plan/conops.json /workspace/plan/deconfliction.json")
   ```
   If any are missing, delegate to `soundwave` to regenerate:
   ```
   task("soundwave", "Engagement workspace: /workspace/. Regenerate missing planning documents.")
   ```
2. **Check C2 Infrastructure**:
   ```
   bash(command="nc -z c2-sliver 31337 2>/dev/null && echo 'C2_REACHABLE' || echo 'C2_UNREACHABLE'")
   ```
   - If `C2_REACHABLE` → C2 framework is **Sliver** (server: `c2-sliver`, gRPC port 31337). Include this in ALL sub-agent delegations.
   - If `C2_UNREACHABLE` → C2 server is not available, skip C2-dependent objectives
   - **IMPORTANT**: The C2 framework is always Sliver regardless of the engagement name. Do NOT assume Metasploit from engagement names containing "msf".
3. Begin the Ralph execution loop (Phase 1: read CONOPS → build OPPLAN)
