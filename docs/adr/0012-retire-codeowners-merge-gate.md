# 0012. Retire the CODEOWNERS merge gate; keep required CI and the release environment

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** @PurpleCHOIms
- **Supersedes:** [ADR-0002](0002-pr-tiering-and-blast-radius.md)
- **Related:** [docs/COWORK.md](../COWORK.md), [CONTRIBUTING_AGENT.md](../../CONTRIBUTING_AGENT.md)

## Context

ADR-0002 routed PRs into three review tiers and made a set of
supply-chain-critical paths require owner review through
`.github/CODEOWNERS`. Two things are now known about that gate.

**1. It never produced the review it promised.** The `main` ruleset
carried `require_code_owner_review: true` together with
`required_approving_review_count: 0`. What was observed against the live
API: across the last 150 merged PRs none ever reported
`REVIEW_REQUIRED`, and PRs #681, #682 and #773 — touching
`docs/adr/**`, `containers/sandbox.Dockerfile` and `uv.lock`
respectively — were merged with **zero approving reviews**, by a
collaborator holding neither of the ruleset's two bypass roles
(`OrganizationAdmin`, `RepositoryRole 5`).

Two readings fit that: either the `0`-approval setting leaves the
code-owner rule non-blocking, or GitHub treats the requirement as
satisfied when the only code owner is the PR author (which those three
were). We did not run the controlled experiment to separate them,
because the decision does not turn on which is true. Under the first
reading the gate blocked nothing. Under the second it blocked only PRs
that the owner did not author, and #686 — authored by the other
collaborator, touching `packages/decepticon/pyproject.toml` and
`uv.lock`, code owner auto-requested — still merged with zero approving
reviews. Either way the "Green CI + 1 owner approval" gate that
ADR-0002 recorded, that `docs/COWORK.md §4.3` described, and that the PR
template asked contributors to respect was not the thing deciding what
landed on `main`.

**2. Enforcing it is self-blocking at the current team size.**
`@PurpleCHOIms` is the only code owner. Raising required approvals to 1
to activate the gate makes every owner-tier PR *authored by the owner*
unmergeable — there is no second code owner who can approve it — so the
owner would bypass the rule on every such PR. A rule its own author has
to break on every use is not a control.

Landing on `main` also does not reach downstream users. Users install
from GHCR images, PyPI wheels, and launcher binaries, and every job in
`release.yml` / `release-recover.yml` that produces an externally
visible artifact declares `environment: pypi-release` — one required
reviewer, deployment branch policy restricted to `refs/tags/v*`. The
human gate between code and users is the release approval, not the
merge.

## Decision

Delete `.github/CODEOWNERS` and clear `require_code_owner_review` on the
`main` ruleset. Two hard gates remain, both enforced in repository
configuration rather than in prose:

1. **`CI OK (required status)`** — a required status check on `main`. The
   same ruleset blocks deletion and non-fast-forward updates of `main`.
   A PR cannot merge until the aggregate check reports success.
2. **`pypi-release` environment approval** — required before any
   externally visible artifact is published, and usable only from `v*`
   tags. `tag-immutability-v` additionally blocks delete / update /
   non-fast-forward of a `v*` tag once created.

Both gates are subject to the ruleset's existing `bypass_actors`
(`OrganizationAdmin` and `RepositoryRole 5` / repository admin, both
`bypass_mode: always`). `GET /repos/{owner}/{repo}/rules/branches/main`
returns the rules that apply to the *calling* user, and for the owner it
returns `[]` — no rule on `main` applies to them, `CI OK` included. That
is left as-is: it is what makes tag recovery and a wedged-CI unblock
possible, and it is why write/maintain collaborators — who hold no
bypass — are the population the required check actually governs. It is
also the reason no collaborator should be given the repository **admin**
role casually: admin is a bypass actor here, and can edit the rulesets
and the `pypi-release` reviewers besides.

Blast-radius awareness survives as guidance, not as a gate. The PR
template's *Blast radius* section and `CONTRIBUTING_AGENT.md §2.3` still
ask the author to classify their change; both now describe themselves as
self-review prompts rather than as merge conditions.

## Consequences

- **Easier:** the documented process and the repository configuration
  agree. Contributors are no longer told to wait for a review that
  nothing was requiring, and the owner no longer needs a standing
  bypass to merge their own supply-chain PRs.
- **Given up — stated plainly:** the defense-in-depth layer ADR-0002
  named when it rejected this exact alternative — "CI cannot catch a
  malicious `.github/workflows/*.yml` change that disables CI itself."
  Human review of workflow files is no longer required by
  configuration. One structural mitigation survives:
  `CI OK (required status)` is a *required* check, so deleting or
  renaming the `ci-ok` job leaves the check permanently unreported and
  the PR permanently unmergeable. A workflow edit that keeps the job
  name and makes it pass unconditionally is caught by nothing. That
  residual risk is accepted: with two collaborators who can both
  already push `v*` tags, an unenforced review requirement was not what
  stood between that change and a published release — the
  `pypi-release` approval is.
- `actionlint` in `ci.yml` continues to lint workflow syntax, and
  `security.yml` continues to run pip-audit and gitleaks. Neither is a
  substitute for review; both are cheaper than one.
- **Reversible.** Restoring the file and setting
  `required_approving_review_count: 1` re-establishes the gate. The
  right time to do that is when the project has **two or more code
  owners**, because the self-blocking problem in Context (2) disappears
  then.

## Alternatives considered

- **Shrink `CODEOWNERS` to the true supply-chain paths and drop the
  policy-doc paths (`docs/adr/**`, `docs/COWORK.md`,
  `CONTRIBUTING_AGENT.md`, `docs/QUALITY_BAR.md`, `SECURITY.md`,
  `docs/security/**`).** Those paths ship no runtime behavior, so they
  fail ADR-0002's own first entry condition for Tier-owner. Rejected
  anyway: shrinking keeps a gate that still blocks nothing while
  required approvals is 0, preserving the documentation/reality gap this
  ADR exists to close.
- **Set required approvals to 1 and keep `CODEOWNERS`.** Rejected for
  the self-blocking reason in Context (2). Revisit at ≥2 code owners.
- **Blanket `* @owner`.** Rejected by ADR-0002 for review-fatigue
  reasons that still hold, and it fails harder on the self-blocking
  problem.
