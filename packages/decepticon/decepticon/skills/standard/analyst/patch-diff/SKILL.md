---
name: patch-diff-research
description: "Authorized patch-diff workflow for deriving and validating vulnerability variants from a known vulnerable-to-fixed source change."
allowed-tools: Read Write Bash
metadata:
  subdomain: analyst
  when_to_use: "patch diff n-day variant analysis vulnerable fixed commit regression source change known advisory"
  upstream_ref: "Decepticon analyst lane: authorized patch-diff research"
---

# Patch-Diff Research

Use this workflow only on source, commits, and test targets the engagement is
authorized to inspect. A patch is evidence of a changed security boundary, not
proof that every neighboring line is exploitable.

## Inputs

- Pinned vulnerable and fixed revisions from the same repository.
- Build instructions and a local or intentionally vulnerable test target.
- The advisory, failing test, or exact behavior corrected by the patch.

## Loop

1. **Pin both sides.** Record repository URL, vulnerable commit, fixed commit,
   clean working-tree state, dependency lockfile hashes, and build commands.
2. **Explain the security delta.** Identify the source, guard, sink, trust
   boundary, and behavior changed by the patch. Ignore formatting-only hunks.
3. **Build a differential test.** The positive case must reproduce on the
   vulnerable revision; the negative control is the exact same case on the
   fixed revision. Record both raw outputs.
4. **Search for siblings.** Search only for the abstract cause—not the exact
   line text. For every hit, confirm framework, data flow, authorization state,
   and reachability before treating it as a candidate.
5. **Validate candidates independently.** Each candidate gets its own minimal
   positive and baseline command through ``validate_workspace_finding``. Do not
   inherit validation from the original CVE.
6. **Report the boundary.** Record rejected siblings and why they differ.
   Group only independently confirmed findings under the common root cause.

## Required artifacts

```
research/patch-diff/<advisory>/
  revisions.json                 # commits and dependency hashes
  security-delta.md              # source / guard / sink explanation
  original-positive.txt          # vulnerable revision output
  original-fixed-control.txt     # fixed revision output
  variants/<candidate>/positive.txt
  variants/<candidate>/baseline.txt
  variants/<candidate>/verification.json
```

A variant is promotable only when its own verification artifact validates and
the original fixed-side control demonstrates the intended remediation boundary.
