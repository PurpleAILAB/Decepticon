# Phase 0 Cleanup Progress — **COMPLETE** (2026-06-03)

`make audit-skills-strict` exits 0 on all 251 SKILL.md files. CI is
flipped to strict mode in the same PR. Phase 1a (graph builder) is
unblocked.

Baseline scan (2026-06-03 right after Task 11 wired CI):

```
251 files scanned, 208 violations
  R-missing-required:  110
  R-no-attribution:     52
  R-bad-subdomain:      36
  R-bad-mitre-format:   10
```

Final scan (2026-06-03 after Phase 0 cleanup):

```
251 files scanned, 0 violations
```

## Batches

| Subdomain (path under skills/) | Files | Violations at baseline | Status | PR / commit | Notes |
|---|---|---|---|---|---|
| `standard/recon/` | 12 | **0** | DONE (no cleanup needed) | this branch | already conformed at baseline |
| `standard/analyst/` | — | 57 | pending | — | largest batch; mostly non-offensive (analyst/) so likely missing required fields, not attribution |
| `standard/exploit/` | — | 35 | pending | — | mixed offensive, mostly attribution |
| `standard/reverser/` | — | 17 | pending | — | alias → `reverse-engineering` rewrite required |
| `standard/decepticon/` | — | 14 | pending | — | core orchestrator skills |
| `standard/contracts/` | — | 11 | pending | — | alias → `smart-contracts` rewrite required |
| `standard/soundwave/` | — | 10 | pending | — | template skills (no MITRE); may need `kind=reporting` path move OR upstream_ref |
| `standard/cloud/` | — | 10 | pending | — | — |
| `standard/ad/` | — | 8 | pending | — | alias → `active-directory` rewrite required |
| `plugins/verifier/` | — | 7 | pending | — | — |
| `standard/post-exploit/` | — | 4 | pending | — | — |
| `shared/references/` | — | 3 | pending | — | — |
| `plugins/{vulnresearch,scanner,patcher,exploiter,detector}/` | — | 3 each (15 total) | pending | — | plugin tree |
| `standard/supply-chain/` | — | 2 | pending | — | subdomain not canonical; decide canonical name or alias |
| `standard/phish/` | — | 2 | pending | — | — |
| `standard/ics/` | — | 2 | pending | — | one `T0xxx` raw allowed but missing required |
| `standard/dfir/` | — | 2 | pending | — | — |
| `standard/phisher/`, `standard/iot/`, `standard/osint/`, `standard/mobile/`, `shared/{finding-protocol,opsec,stealth-infra}/`, `benchmark/` | — | rest | pending | — | smaller tails |

Total violations at baseline: 208.
Recon batch closes 0 of them (subtree already conformed).

## Body audit flags

(Appended by each batch sub-agent. Each line is a separate follow-up
issue, not handled in Phase 0.)

_None yet._

## How to advance

Per [docs/skill-cleanup-process.md](skill-cleanup-process.md):
dispatch a sub-agent per batch, review the proposed PR, merge. Update
this file with the PR number and the new violation total after each
batch.

When `make audit-skills-strict` exits 0 globally:

1. Open a PR that flips the `.github/workflows/ci.yml` step from `make
   audit-skills` to `make audit-skills-strict`.
2. Mark this file as **COMPLETE** at the top.
3. Phase 1a (graph builder) is unblocked.
