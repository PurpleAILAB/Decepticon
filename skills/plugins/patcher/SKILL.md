---
name: patcher-overview
description: Stage 4 patch generation playbook. Minimal diffs for validated findings with mandatory patch_verify. Load at patcher-agent startup.
---

# Patcher Skill

You fix validated findings and prove the fix holds. Minimal diffs, one
concern at a time, mandatory `patch_verify` before claiming done.

## Iteration loop

```
while not patched and attempts < 3:
    1. kg_query(kind="vulnerability", min_severity="medium")
       → pick validated=True, patched!=True
    2. Read the function around (file, line)
    3. Design minimal fix (validate / escape / parameterize / safe API)
    4. patch_propose(vuln_id, diff, commit_message) → patch_id
    5. Apply diff via Edit or bash patch
    6. (optional) bash: run repo tests, abort on failure
    7. patch_verify(patch_id, poc_command, success_patterns,
                    test_cmd=optional)
    8. if status == "verified": done
       elif status == "tests_failed": revert, retry
       elif status == "regressed": revert, analyze, retry
    attempts += 1
```

## Diff style

- **Unified diff.** Use `git diff --no-color` output or write one by hand.
- **Minimal hunk.** One concern. No formatting. No renames. No "while I'm
  here" cleanups. No new files (unless adding one regression test).
- **Safe-API preference.**

| Bug class               | Preferred fix                                        |
|-------------------------|------------------------------------------------------|
| SQL injection           | Parameterized query / ORM.filter(), NOT escaping     |
| Command injection       | Arg-list subprocess, shell=False                     |
| Path traversal          | `os.path.realpath` + prefix check                    |
| SSRF                    | Allowlist + resolve → check not private/loopback     |
| Deserialization         | Switch to safe loader (`yaml.safe_load`, JSON, etc.) |
| Broken auth             | Move check to pre-hook, not inside handler           |
| Reflected XSS           | Framework auto-escape, remove `Markup`/`safe`        |

- **Add a regression test** in the same diff when the repo has a test
  directory for the affected module. One test that exercises the fixed
  path is sufficient.

## Commit message format

Conventional commits. Example:

```
fix(auth): use constant-time comparison in verify_hmac

Prevents timing side-channel recovery of the HMAC. CWE-208.
```

## Decisive-completion rule

Only report "patched" after `patch_verify.status == "verified"`. A
green test suite is NOT sufficient — the PoC must actually fail.

If all 3 attempts fail, STOP on the finding, record a note via
`kg_add_node` on the vuln (`patch_attempts=3, last_failure=...`) and
return to the orchestrator. Do not spiral.
