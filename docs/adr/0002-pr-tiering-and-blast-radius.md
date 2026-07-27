# 0002. PR tiering by blast radius

- **Status:** Superseded by [ADR-0012](0012-retire-codeowners-merge-gate.md)
- **Date:** 2026-06-04
- **Deciders:** @PurpleCHOIms
- **Related:** [.github/CODEOWNERS](../../.github/CODEOWNERS), [docs/COWORK.md](../COWORK.md), [CONTRIBUTING_AGENT.md](../../CONTRIBUTING_AGENT.md)

## Context

Decepticon receives contributions from human maintainers, write-access
collaborators, external forked-PR contributors, and a growing volume of
AI-assisted PRs. With one full-time owner today (`@PurpleCHOIms`),
manually reviewing every PR is not viable, and "every PR self-merges on
green CI" is unsafe for the surfaces that can compromise downstream
users in one merge (CI workflows, install scripts, base images,
published packages, plugin contracts).

`.github/CODEOWNERS` already implements a per-path strategy: a small
set of supply-chain-critical paths require owner review, everything
else self-merges. `docs/COWORK.md §4.3` describes this strategy in
narrative form. This ADR records the *reasoning* behind the strategy so
it can be cited from CONTRIBUTING\_AGENT.md, future ADRs, and
discussions about whether a given path should join the protected set.

## Decision

Contributions are classified by **blast radius** — the worst-case scope
of damage a malicious or careless change to the file could cause — and
routed to one of three review tiers:

| Tier | What it covers | Reviewer | Merge gate |
|---|---|---|---|
| **Tier-auto** | Tests, internal refactors with no public-API change, docs that are not policy docs, lockfile-only dependency bumps with green security scan | None (CI is the reviewer) | Green required CI + contributor self-review |
| **Tier-delegate** | Agent prompts, skill bodies, middleware internals, web/CLI features, schema changes that do not break contracts | Maintainer or named delegate | Green CI + 1 review approval |
| **Tier-owner** | Anything under a `CODEOWNERS`-gated path: `.github/workflows/**`, `pyproject.toml` / lockfiles / package manifests, `packages/decepticon-core/.../contracts/**`, `scripts/install.sh`, `docker-compose.yml`, `containers/*.Dockerfile`, `.semgrep/**`, `SECURITY.md`, `docs/security/**`, `docs/COWORK.md`, `docs/adr/**`, `CONTRIBUTING_AGENT.md`, release tooling | Owner (`@PurpleCHOIms` today) | Green CI + 1 owner approval; release jobs additionally gated by the `pypi-release` GitHub Environment |

A path enters Tier-owner when *both* of these are true:

1. The change can compromise downstream users without their action
   (supply-chain, install path, runtime container, network isolation).
2. The change cannot be fully validated by an automated check.

If only (1) is true, the right move is to add the missing automated
check; if only (2) is true, the path stays in Tier-delegate.

## Consequences

- **Easier:** routine work lands fast; the owner's review time is spent
  where it matters. Contributors know up-front whether to expect a wait.
- **Harder:** adding a new high-blast-radius surface (e.g. a new
  container image, a new install script, a new policy doc) requires
  updating CODEOWNERS in the same PR. The CONTRIBUTING_AGENT.md
  self-review checklist names this explicitly.
- **Given up:** flat "all reviews equal" governance. We accept that
  some paths are categorically more dangerous than others and process
  them accordingly.
- **Migration:** the CODEOWNERS file in this PR brings policy
  files (`.semgrep/**`, `docs/security/**`, `SECURITY.md`,
  `docs/COWORK.md`, `docs/adr/**`, `CONTRIBUTING_AGENT.md`) into the
  protected set. No existing path leaves the protected set.

## Alternatives considered

- **Blanket `* @owner` in CODEOWNERS.** Rejected: owner becomes the
  bottleneck for trivial changes, contribution velocity drops, and
  review fatigue erodes the attention the owner-tier surfaces actually
  need.
- **No CODEOWNERS, rely on branch-protection ruleset + CI.** Rejected:
  CI cannot catch a malicious `.github/workflows/*.yml` change that
  disables CI itself. Human review on workflow files is the
  defense-in-depth layer.
- **Per-author trust tiering instead of per-path.** Rejected for now:
  introduces social complexity (who is "trusted"?) and does not address
  the AI-author case where the identity is the human but the diff was
  produced by a tool. Per-path is the simpler invariant.
