---
name: bash-patterns
description: "Mandatory bash patterns for all sub-agents: workspace anchoring, output redirection, background job management, and path hygiene. Load before any bash() call sequence."
metadata:
  when_to_use: "workspace anchor, path drift, pwd, WORKSPACE, bash patterns, background jobs, output redirect, artifact paths"
---

# Shared Bash Patterns

Mandatory patterns that ALL sub-agents (recon, exploit, post-exploit) MUST follow in every task invocation.

## Workspace Anchor (MANDATORY — First Bash Call)

Path drift occurs when sub-shells, tool wrappers, or background jobs change the working directory. Prevent it by anchoring at the start of every task:

```bash
# ALWAYS the first lines of your first bash call
WORKSPACE="$(pwd)"
export WORKSPACE
echo "Workspace: ${WORKSPACE}"
```

All artifact writes MUST use the anchor:

```bash
# CORRECT — anchored paths
mkdir -p "${WORKSPACE}/recon"
curl -s "http://<TARGET>/page" -o "${WORKSPACE}/recon/page.html"
echo "finding" >> "${WORKSPACE}/findings/FIND-001.md"

# WRONG — bare relative paths (break after any cd or background spawn)
mkdir -p recon
curl -s "http://<TARGET>/page" -o recon/page.html
```

**Why this matters**: A single `cd /tmp` inside a pipe, a tool that changes cwd, or a background job that inherits a different cwd will silently write artifacts to the wrong location. The operator never sees them, and the next agent re-derives everything from scratch — wasting the entire task budget.

## Output Redirection (MANDATORY for any response >2KB)

Every curl, nmap, gobuster, ffuf, and similar tool MUST redirect output to a file. Never inline large outputs:

```bash
# CORRECT
curl -s "http://<TARGET>/page" -o "${WORKSPACE}/recon/page.html"
head -20 "${WORKSPACE}/recon/page.html"

# WRONG — inlines multi-KB output, triggers compaction
curl -s "http://<TARGET>/page"
```

## Background Job Management

Launch long-running scans as background jobs, then do productive work while they run:

```bash
# Launch in background with output anchored
nmap -sV -p- "<TARGET>" -oN "${WORKSPACE}/recon/nmap_full.txt" &
NMAP_PID=$!

# Do parallel work here
curl -s "http://<TARGET>/" -o "${WORKSPACE}/recon/homepage.html"

# Check background job when ready
wait $NMAP_PID
grep "open" "${WORKSPACE}/recon/nmap_full.txt" | head -20
```

## Deduplication Log Pattern

When iterating over IDs, paths, or parameter variants, maintain a dedup log:

```bash
PROBE_LOG="${WORKSPACE}/recon/probed.txt"
URL="http://<TARGET>/api/item/$ID"

if grep -Fxq "$URL" "$PROBE_LOG" 2>/dev/null; then
  echo "SKIP: $URL"
else
  echo "$URL" >> "$PROBE_LOG"
  curl -s "$URL" -o "${WORKSPACE}/recon/item_${ID}.json"
fi
```

**The log survives context summarization. Trust the file, not memory.**

## Path Safety Checklist

Before any bash sequence, verify:
- [ ] `WORKSPACE="$(pwd)"` set and exported in first call
- [ ] All `-o` / `>` / `>>` targets use `${WORKSPACE}/...`
- [ ] No bare `cd` without reassigning `WORKSPACE` afterward
- [ ] Background jobs inherit `WORKSPACE` (it is exported)
