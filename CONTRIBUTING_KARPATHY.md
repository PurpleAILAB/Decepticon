# The Karpathy Rules — Contributor Discipline for Decepticon

**Status:** Canonical. Binding for all contributors — human and agent.
**Owner:** repo maintainers.
**Companion docs:** [`CONTRIBUTING.md`](./CONTRIBUTING.md),
[`CONTRIBUTING_AGENT.md`](./CONTRIBUTING_AGENT.md),
[`docs/QUALITY_BAR.md`](./docs/QUALITY_BAR.md).

---

## Why these rules

Most PRs that hurt a codebase do so the same handful of ways: they
add code nobody asked for, introduce abstractions with one caller,
re-implement something that already exists, hide behaviour behind
magic, or land unsupervised LLM output. The Karpathy Rules — named
after the body of public advice from Andrej Karpathy on keeping
codebases legible — are the project's compressed answer to those
failure modes.

They apply uniformly to:

- Human contributors opening a PR by hand.
- Agent contributors (Claude Code, Codex, Cursor, Antigravity,
  Gemini, OpenCode, etc.) opening a PR on a human's behalf.
- Maintainers landing their own work.

There are no exemptions for "I'm just the maintainer," "the bot did
it," or "it's only a small change."

---

## The 10 Rules — TL;DR

| # | Rule | Enforcement |
|---|------|-------------|
| K1 | A number must move. | **CI hard-block** (PR body regex) |
| K2 | Delete > add (net +LOC ≤ 300 for features). | **CI hard-block** (LOC + labels) |
| K3 | No new abstractions without 2 callers. | Reviewer judgment |
| K4 | Read more than you write (cite files read). | PR-template field |
| K5 | No magic. | Reviewer judgment |
| K6 | Reproducibility (seeded, one-command). | PR-template field |
| K7 | One person holds the system in their head (≤500 LOC / ≤7 public symbols per module). | Reviewer judgment |
| K8 | Empirical, not theoretical. | Reviewer judgment |
| K9 | Write CHANGELOG as you go. | **CI hard-block** (file-change) |
| K10 | Don't trust LLM unsupervised; human reviewer ≠ author. | **CI hard-block** (body + review) |

CI-blocking rules (K1, K2, K9, K10) live in
[`.github/workflows/karpathy-gates.yml`](./.github/workflows/karpathy-gates.yml).
Reviewer-judgment rules (K3, K5, K7, K8) are enforced at review time
against this document.

---

## K1 — A number must move

**Rule.** Every PR states one concrete metric and the direction it
moved. Latency, LOC, error rate, test count, coverage, container
boot time, anything — but it must be a number with a delta.

**Rationale.** Forcing a measurable Δ kills "this should be better"
and "feels cleaner" PRs. If you cannot name the number, you do not
yet understand the change.

**Compliant:**

> Metric / Δ: cold-start time on `make dev` reduced from 41s → 28s
> (median over 5 runs on a clean volume).

**Violation:**

> Metric / Δ: improved performance.

**Enforcement.** CI greps the PR body for a line matching
`^\s*Metric( ?/ ?| - )Δ\s*[:：]\s*\S+` (case-insensitive). Missing
or empty value → fail. Override: none — find a number.

---

## K2 — Delete more than you add (net +LOC ≤ 300 for features)

**Rule.** A net positive of more than 300 lines of code requires
either (a) the `karpathy/refactor` label (pure refactor, behaviour
unchanged) or (b) the `karpathy/override` label with a maintainer's
written justification in the PR body.

`docs/**`, `tests/**`, lockfiles, generated files and `.github/**`
are excluded from the count where the existing
[Diff budget §QUALITY_BAR](./docs/QUALITY_BAR.md#hard-limits)
already excludes them.

**Rationale.** Code is liability. The path of least resistance for a
typing model — human or LLM — is to add. K2 puts a thumb on the
delete pan.

**Compliant:**

- Feature PR: +180 / -240 net -60.
- Refactor PR: +900 / -50, labelled `karpathy/refactor`.

**Violation:**

- Feature PR: +500 / -20, no label, no justification.

**Enforcement.** CI reads `additions`/`deletions` from
`gh pr view --json`. Net > 300 without `karpathy/refactor` or
`karpathy/override` → fail.

---

## K3 — No new abstractions without 2 callers

**Rule.** A new class, helper, decorator, ABC, protocol, factory or
indirection layer must have at least two real call sites in the
same PR. "It might be useful later" does not count.

**Rationale.** Premature abstraction is the most expensive form of
speculative work. Two callers is the minimum honest sample for
"is this a pattern."

**Compliant:** New `redact_secret(s)` helper is called from both the
Sliver adapter and the BloodHound adapter inside the same PR.

**Violation:** New `BaseAdapter` ABC with one concrete implementation
"to make future adapters easier."

**Enforcement.** Reviewer judgment. Reviewers should reject and ask
for inlining if only one caller exists.

---

## K4 — Read more than you write (cite files read with ranges)

**Rule.** The PR body lists files read while preparing the change,
with `path:start-end` line ranges. The total read should exceed the
total written.

**Rationale.** Surface-area awareness. Most regressions are caused
by changing code while ignoring the call sites that depend on it.

**Compliant:**

> Files read:
> - `clients/cli/src/runtime/session.rs:1-180`
> - `packages/core/src/orchestrator/state.py:42-310`
> - `docker-compose.yml:1-80, 220-260`

**Violation:** "Files read: see diff." (Reading only what you wrote
defeats the rule.)

**Enforcement.** PR template makes the field required. Reviewers
spot-check that listed ranges are plausible (i.e. the cited code is
actually relevant to the change).

---

## K5 — No magic

**Rule.** Behaviour is explicit. No metaclasses, no monkey-patching,
no dynamic `__getattr__` indirection, no environment-driven control
flow that is not documented at the call site, no copy-pasted snippets
from a third-party action without reading them in full.

**Rationale.** Magic is the runtime equivalent of a hidden import.
It makes the program impossible to hold in one head (see K7).

**Compliant:**

- Explicit dispatch table mapping a string to a function.
- Pinned GitHub Action with the SHA recorded in the diff.

**Violation:**

- `setattr(self, name, value)` over a public surface.
- `uses: someuser/some-action@main` (no pin, unaudited).

**Enforcement.** Reviewer judgment. The
[Banned patterns](./docs/QUALITY_BAR.md#banned-patterns--pr-closed-on-sight)
list in QUALITY_BAR overlaps and is enforced separately.

---

## K6 — Reproducibility (seeded, one-command)

**Rule.** Any benchmark, eval, smoke test, or "I ran this locally"
claim in the PR body must include the exact command and any seed or
fixture needed to reproduce it.

**Rationale.** Unreproducible numbers are worse than no numbers —
they invite false confidence.

**Compliant:**

> Repro:
> ```
> SEED=42 make smoke
> ```
> Median 28.4s ± 0.6s over 5 runs.

**Violation:** "Ran locally, all green." (No command, no seed, no
sample size.)

**Enforcement.** PR template makes the field required. The
[End-to-end verification](./docs/QUALITY_BAR.md#wired-end-to-end-locally-verified--no-exceptions)
section of QUALITY_BAR already enforces this for behaviour changes;
K6 lifts it for *any* metric claim.

---

## K7 — One person holds the system in their head

**Rule.** No single module exceeds ~500 LOC of runtime code or ~7
public symbols. If a PR pushes a module past either threshold, split
the module in the same PR or open a follow-up issue and link it.

**Rationale.** The Karpathy formulation: "the limit is whether one
person can hold the system in their head." 500 LOC / 7 symbols is a
proxy, not a fetish — reviewers should treat it as a smell, not a
hard test.

**Compliant:** Splitting `orchestrator.py` (612 LOC) into
`orchestrator/state.py`, `orchestrator/dispatch.py`,
`orchestrator/middleware.py` before adding the new feature.

**Violation:** Growing a single 900-LOC module to 1100 LOC in one PR.

**Enforcement.** Reviewer judgment. CI does **not** measure module
LOC because the right number depends on the module's role.

---

## K8 — Empirical, not theoretical

**Rule.** The PR shows the change running. Pasted log lines, screen
recordings, `gh run view` links, before/after profiler output, or a
saved transcript from the relevant `make` target — all fine. Pure
prose ("this should work") is not.

**Rationale.** The cheapest place to learn a change is broken is on
the author's machine, not in production.

**Compliant:**

> Ran `make smoke` on a clean volume.
> ```
> ✓ litellm healthy (1.2s)
> ✓ postgres healthy (0.4s)
> ✓ langgraph healthy (3.1s)
> ```

**Violation:** "Should work end-to-end."

**Enforcement.** Reviewer judgment. Overlap with QUALITY_BAR
"Wired end-to-end."

---

## K9 — Write CHANGELOG as you go

**Rule.** Any PR labelled `user-visible` (default-on; opt out with
`internal-only`) must touch `CHANGELOG.md`. No batched "I'll write
the changelog at release time."

**Rationale.** Release-time changelogs are reconstructions. They
lose intent. Authors write better changelog entries than maintainers
reading diffs three weeks later.

**Compliant:** PR modifies `CHANGELOG.md` in the same diff, under
`[Unreleased]`.

**Violation:** Feature PR with no `CHANGELOG.md` change and no
`internal-only` label.

**Enforcement.** CI reads `gh pr view --json files`. If the PR has
the `user-visible` label (or lacks `internal-only`) and no
`CHANGELOG.md` entry is in `files[]`, fail.

---

## K10 — Don't trust LLM unsupervised; reviewer ≠ author

**Rule.** Every PR body declares the author identity (human or
agent + model) and explicitly states "requires human reviewer ≠
author." For PRs opened by a known bot or agent account, at least
one approving review from a human account that is not the author is
required before merge.

**Rationale.** Agents produce surprisingly competent diffs and
surprisingly confident wrong diffs. The only known-good filter is a
human who can defend the change.

**Compliant:**

> Author: Claude Code (claude-opus-4-7) on behalf of @alice; requires
> human reviewer ≠ author.

…followed by an approving review from `@bob` (not `@alice`, not a
bot).

**Violation:**

- PR body omits the reviewer line.
- Bot-authored PR merged with only the bot's self-approval.
- PR body claims human authorship but the diff is uneditedly LLM-shaped
  (em-dash salad, helpers-used-once, "leverages X to robustly handle
  Y") — see
  [QUALITY_BAR §AI-slop signatures](./docs/QUALITY_BAR.md#ai-slop-signatures).

**Enforcement.** CI:

1. Greps the PR body for a line matching
   `^\s*Author\s*[:：].*requires human reviewer ≠ author` (Unicode
   "≠" or ASCII `!=` both accepted).
2. If the PR author login is in the known-bot allowlist
   (`github-actions[bot]`, `dependabot[bot]`, `renovate[bot]`,
   plus any login ending in `-bot` or `[bot]`, plus
   `VoidChecksum` for agent traffic), requires at least one
   `APPROVED` review from a different login that is itself not a
   bot.

---

## How to use the override labels

There are exactly two override labels. Each opts out of **one**
specific gate; there is no all-gate bypass by design.

| Label | Opts out of | Required justification |
|-------|-------------|------------------------|
| `karpathy/refactor` | K2 (LOC cap) | Refactor must preserve behaviour; PR body says so explicitly. |
| `karpathy/override` | K2 (LOC cap), one PR only | Maintainer comment in PR body explaining why the +LOC is unavoidable. |

K1 and K9 and K10 have **no override label**. If a PR cannot state a
metric, cannot touch the changelog, or cannot find a human
reviewer ≠ author, it is not ready to merge.

Labels are created and managed via the standard `gh label create`
flow; the workflow assumes the labels exist and treats absence as
"override not requested."

---

## How agent contributors must self-apply

Agent contributors (Claude Code, Codex, Cursor, Antigravity, Gemini,
OpenCode, etc.) must run the rules against their own PR before
pushing. The checklist:

1. State the metric (K1) — and pick one you can actually measure.
2. Compute net LOC and decide whether you need `karpathy/refactor`
   or `karpathy/override` (K2).
3. List the files you actually read with ranges (K4). If the list
   is shorter than the diff, stop and read more.
4. Decide whether the change is `user-visible` and touch
   `CHANGELOG.md` accordingly (K9).
5. Write the K10 line: `Author: <agent name> (<model>) on behalf of
   @<human>; requires human reviewer ≠ author.`
6. Run the workflow locally if possible (see *Manual repro* below).

If your runtime cannot satisfy any of K1/K2/K9/K10, return to the
human and ask them to either supply the missing piece or close the
PR. Do not push a PR that you know will fail CI.

---

## Manual repro for the CI workflow

The workflow is plain shell + `gh`. To dry-run a gate locally
against PR `<N>` in your fork:

```bash
# K1
gh pr view <N> --json body --jq .body \
  | grep -E -i '^\s*Metric ?(/| - ) ?Δ\s*[:：]\s*\S+' \
  && echo K1 OK || echo K1 FAIL

# K2
gh pr view <N> --json additions,deletions,labels --jq \
  '"\(.additions) \(.deletions) \([.labels[].name] | join(","))"'

# K9
gh pr view <N> --json files,labels --jq \
  '[.files[].path] | any(. == "CHANGELOG.md")'

# K10
gh pr view <N> --json body,author,reviews --jq \
  '{body: .body, author: .author.login, approvals: [.reviews[] | select(.state=="APPROVED") | .author.login]}'
```

The workflow YAML itself is the authoritative source of the gate
logic.

---

## What's *not* in scope here

- These rules do not replace QUALITY_BAR or CONTRIBUTING_AGENT —
  they sit on top. Where a Karpathy rule is stricter, it wins. Where
  QUALITY_BAR is stricter, QUALITY_BAR wins.
- These rules do not police taste, naming, or architecture choices
  beyond what K3/K5/K7 already cover.
- These rules are not a substitute for tests, type checks, or
  end-to-end verification — they are a contributor-discipline layer
  layered on top of those.

---

## Changes to this document

Edits to `CONTRIBUTING_KARPATHY.md` are CODEOWNERS-gated like any
other contributor-policy file. Open a PR, state the metric for why
the change is needed (e.g. "false-positive rate on K1 regex 14% → 3%
over last 50 PRs"), and link the discussion thread.
