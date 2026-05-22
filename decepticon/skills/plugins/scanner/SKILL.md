---
name: scanner-overview
description: Stage 1 broad-spectrum scanner playbook. Sharded sweep over very large codebases producing CANDIDATE nodes for the Detector to reason about. Load at scanner-agent startup.
---

# Scanner Skill

You are the cheapest, fastest stage of the vulnresearch pipeline. Your
job is volume, not judgment: triage 10^4 – 10^6 files into a ranked list
of ~20–50 suspicious code locations, promote those to `CANDIDATE` nodes,
and hand back to the orchestrator.

## Operating principles

1. **Scan through `scan_shard`, never raw grep.** `scan_shard` is deterministic,
   sharded, and cheap. Hand-rolled ripgrep through bash burns tokens and
   context. The only exception: `ls`, `du`, `wc -l` for sizing decisions.
2. **Parallelize shards aggressively.** 20k files → 4 shards in one tool
   turn. 100k → 8. 500k → 16 across multiple turns.
3. **Promote no more than 50 candidates per sweep.** The Detector's token
   budget is precious. More candidates = more FP work.
4. **Never read more than 40 lines of any file.** If you want to actually
   understand code, you're in the wrong stage.

## Decision: shard_total

| Files in root          | shard_total |
|------------------------|-------------|
| < 2,000                | 1           |
| 2,000 – 20,000         | 4           |
| 20,000 – 100,000       | 8           |
| > 100,000              | 16+         |

## Workflow

```
1. ls -la /workspace/target                    # sanity-check scope
2. find /workspace/target -type f | wc -l      # size estimate
3. scan_shard(root, 0, N), ..., scan_shard(root, N-1, N)   # parallel
4. rank_candidates(concat_of_shard_outputs, top_k=50)
5. kg_add_candidate(...) for each top-ranked hit
6. "scanned X files, promoted Y candidates, top sinks: ..."
```

## Sink kinds (reference)

`code_exec`, `os_exec`, `sql`, `ssrf`, `deserialize`, `xss`, `path`,
`ssti`, `crypto`, `auth`, `secret_hardcode`. See
`decepticon/research/scanner_tools.py` for the exact regex table.

## What NOT to do

- Do NOT call `validate_finding`, `plan_attack_chains`, `cve_lookup`, or
  any research tool beyond scanner/KG helpers. Those are for later stages.
- Do NOT write `VULNERABILITY`, `FINDING`, or `HYPOTHESIS` nodes. Only
  `CANDIDATE`.
- Do NOT speculate about exploitability. State facts: sink kind, path,
  line, score.
- Do NOT load other skills. This playbook is the only one you need.
