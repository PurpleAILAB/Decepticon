## Summary

<!--
One paragraph: what observable behavior changes (or "no-op refactor;
behavior preserved"), and why. Avoid restating the diff in prose.
-->

## Changes

<!-- Bullet list of key changes. -->

-

## Intent

- **Issue / ADR this satisfies:** <!-- #123, docs/adr/NNNN-*.md, or "release-blocker" -->
- **Anti-goal** (one thing this PR could have done but deliberately does not):

## Blast radius

Tick the row that best matches this change. No branch rule enforces
this — it sets how much scrutiny you owe the diff and whether to wait
for a review. See
[docs/adr/0012-retire-codeowners-merge-gate.md](../docs/adr/0012-retire-codeowners-merge-gate.md).

- [ ] **Tier-auto** — tests, internal refactors, non-policy docs, lockfile-only dep bumps.
- [ ] **Tier-delegate** — agent prompts, skill bodies, middleware internals, web/CLI features.
- [ ] **Tier-supply-chain** — CI/workflows, package manifests and lockfiles, install script, compose / Dockerfiles, plugin contracts, `.semgrep/**`. Reaches every OSS user on the next release: request a review and wait for it.
  - If ticked, paste a **Why this touches a supply-chain surface** paragraph below, and confirm the PR changes that surface and nothing else:

<!-- Why this touches a supply-chain surface: ... -->

## Diff budget

Per [QUALITY_BAR §Hard limits](../docs/QUALITY_BAR.md#hard-limits): ≤ 400 runtime-code lines, ≤ 10 files, 1 logical concern. `docs/**`, `tests/**`, `.github/**`, `.semgrep/**` are excluded.

- [ ] My diff fits the budget.
- [ ] **Or** I am requesting `large-diff-approved` from `@PurpleCHOIms` because:

<!-- Justify the size if you ticked the second box. -->

## End-to-end verification

**Required.** One paragraph naming the exact commands you ran on your
machine and the exact behavior you observed. "Tested locally," "all
tests pass," and "should work" are not verification statements — they
are reasons to close the PR. See
[QUALITY_BAR §Wired end-to-end](../docs/QUALITY_BAR.md#wired-end-to-end-locally-verified--no-exceptions).
If you genuinely could not run a part of the change locally, say so
explicitly here and name what you did instead.

<!--
Example that meets the bar:

> Brought the stack up with `make dev`, ran `make cli`, executed an
> engagement against `target=10.0.2.4` with `profile=AUTOBANK`. The
> new c2_tier=short_haul field propagated through to Sliver implant
> generation (verified via sliver-client implants — output attached).
> Confirmed c2_tier=long_haul produces a DNS implant. `make smoke`
> healthy on a clean volume.
-->

## Testing

<!-- Paste the last ~20 lines of relevant output, or link to a CI
artifact. Do not tick a box you did not actually run. -->

- [ ] `make quality` passes (Python + CLI + Web)
- [ ] `make smoke` succeeds (clean local build + OSS-style up + health checks)
- [ ] `pytest tests/` passes (run this if you touched `docker-compose.yml` or `tests/`)
- [ ] Every new/changed test was watched to fail without the change and pass with it
- [ ] Every new/changed code path was **executed on my machine**, not just unit-tested in isolation
- [ ] Manual testing (describe):

## Quality Bar self-check

Confirm — by ticking — that you have personally verified each item
against your diff. These are conditions of merge per
[QUALITY_BAR.md](../docs/QUALITY_BAR.md) and
[CONTRIBUTING_AGENT.md](../CONTRIBUTING_AGENT.md), regardless of
whether AI assistance was used.

- [ ] No banned pattern from [QUALITY_BAR §Banned patterns](../docs/QUALITY_BAR.md#banned-patterns--pr-closed-on-sight) appears in the diff (no `except Exception: pass`, no bare `except`, no bare `# type: ignore` / `# noqa`, no `_ = call()`, no `print(` in production code, no mutable defaults, no wildcard imports, no `TODO` without issue link, no `raise NotImplementedError` in a delivered feature, no `pytest.mark.skip` / `xfail` without linked issue, no mocked-system-under-test, no `# pragma: no cover` for coverage chasing).
- [ ] No AI-slop signature from [QUALITY_BAR §AI-slop signatures](../docs/QUALITY_BAR.md#ai-slop-signatures) survives (no defensive `if x is not None:` the types already prove, no helper-used-once, no speculative `**kwargs`, no `data`/`result`/`item` placeholder names, no docstrings restating the signature, no em-dash salad, no "leverages X to robustly handle Y").
- [ ] Every changed line traces to the stated intent. No drive-by formatting, renaming, or reordering.
- [ ] Every public function I added/changed has explicit type annotations including return type, and every raised exception is a named class.
- [ ] I would merge this PR if a stranger opened it.
- [ ] If I were tired and reviewing this at the end of a long day, I would still merge it.

## AI-assisted contribution attestation

By opening this PR, you confirm — whether or not AI assistance was
used — that you followed [CONTRIBUTING_AGENT.md](../CONTRIBUTING_AGENT.md)
and meet the [QUALITY_BAR.md](../docs/QUALITY_BAR.md):

- You read the diff in full and can defend every line on demand.
- You actually ran the verification you ticked above.
- You did not bundle unrelated work.
- You did not weaken offensive-security guard rails (RoE, SafeCommand,
  EngagementContext, OPSEC skills, semgrep rules, compose isolation,
  capability / PID / memory limits) without a linked ADR.
- You materially edited any AI-generated output before pushing — the
  diff is not raw model output.

No checkbox is required for this section. The bar applies whether or
not you disclose tool use; this section exists so the expectation is
visible at the point of contribution.

## Related Issues

<!-- Link related issues: Fixes #123, Closes #456 -->
