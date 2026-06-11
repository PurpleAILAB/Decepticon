# Launcher ↔ Image Version Decoupling

**Status:** draft (design exploration, no decision yet)
**Author:** v1.1.12 release retrospective
**Related:** PR #632 (silent auto-update default), PR #637 (--no-update flag + legacy + drop-in), `[deferred] 3a: tag-suffix detection for image-only patch releases`

## Problem

Every Decepticon hotfix today requires a **full release cycle** — PyPI publish + 7 GHCR images + GoReleaser binaries + Cosign signing + GitHub release — even when the fix only touches one Python file and a single image's contents. Two costs:

1. **Maintainer toil.** ~30 minutes of CI per cycle, three pypi-release approvals per run, occasional transient Cosign failures (v1.1.12's c2-sliver merge needed a re-run).
2. **Release pollution.** Every hotfix creates a new GitHub release entry, a new PyPI version, a new git tag — even when only one image changed.

The original v1.1.12 plan included **3a: tag-suffix detection** (`vX.Y.Z` = full release, `vX.Y.Z.N` = image-only patch) to cut hotfix cycles to ~5 minutes. During implementation we found the design doesn't close because of a deeper coupling, captured below.

## The coupling

`clients/launcher/cmd/start.go:283` sets:
```go
cliEnv["DECEPTICON_VERSION"] = version   // the launcher binary's stamped version
```

`docker-compose.yml` interpolates that on every image:
```yaml
image: ghcr.io/purpleailab/decepticon-langgraph:${DECEPTICON_VERSION:-latest}
```

`clients/launcher/internal/compose/compose.go:264` strips the `v` prefix, so a launcher built at tag `v1.1.12` resolves images at `:1.1.12`.

**Consequence:** an image-only patch tag `v1.1.12.1` builds and pushes `:1.1.12.1` images to GHCR, but every user still on the v1.1.12 launcher binary keeps pulling `:1.1.12`. The patched image never reaches them — even though silent auto-update for the launcher is now the default. The image-only model never closes.

Two parallel blockers stack on top:

- **`compareSemver` is 3-segment.** `updater/updater.go:88` uses `SplitN(a, ".", 3)`; `1.1.12.1` collapses to `["1","1","12.1"]` and `Sscanf("12.1", "%d", ...)` reads `12`. Auto-update sees `v1.1.12` and `v1.1.12.1` as equal and skips the patch even if delivery worked.
- **`prerelease` detection.** `release.yml`'s `[[ "$version" == *-* ]]` happens to treat `1.1.12.1` as stable (no `-`), but the workflow's downstream `if:` gates need a re-audit before relying on it.

## Options

### A. Launcher resolves the latest release tag at start

Drop the binding `DECEPTICON_VERSION = version`. The launcher queries `releases/latest` at start (already does for the self-update check), caches the result, and sets `DECEPTICON_VERSION` to **that** tag's stripped form. Image-only patches show up immediately.

**Pros**
- Image-only patches reach users on the next `decepticon start` with zero launcher binary rebuild.
- Combines naturally with silent auto-update — the launcher already polls `releases/latest`.

**Cons**
- Version skew risk: if the launcher binary expects a flag/env present only in newer images, an older launcher pinned by `--no-update` could pull mismatched images.
- Offline / air-gapped installs that can't reach GitHub need a graceful fallback (probably: cache last-known-good tag in `$DECEPTICON_HOME/.last-release`).
- Currently `DECEPTICON_VERSION` is also used in CLI env (start.go:283), web `WEB_PORT` interpolation, etc. — audit downstream consumers.

### B. Always build the launcher binary on patch tags

Keep `DECEPTICON_VERSION = version`. On a patch tag (`vX.Y.Z.N`), the launcher job runs, just with no Go source diff. The stamped version still bumps, so compose pulls the patched images.

**Pros**
- Zero launcher code change. Easiest to ship.
- Preserves the "launcher version == image version" invariant — easy mental model for support.

**Cons**
- Defeats the ~30-min → ~5-min cycle speedup we wanted from 3a (launcher binary build + GoReleaser + Cosign is still on the critical path).
- Cosign keyless signing has hit transient HTTP/2 INTERNAL_ERROR (v1.1.12 c2-sliver) — the more we sign per patch, the higher the re-run rate.

### C. Pin compose to `:latest`

Drop `${DECEPTICON_VERSION:-latest}` interpolation and just always use `:latest`. The :latest tag is promoted by `publish-release` after every successful release, so users always pull whatever is current.

**Pros**
- Trivially simple — no launcher changes, no compose interpolation, no version skew detection.

**Cons**
- **Loses reproducibility.** Users on different days are running different image versions despite seemingly identical launchers. Bug reports become unreproducible.
- An accidentally-promoted `:latest` (e.g. a partial release that survived `publish-release`'s verify gate) silently lands on every user.
- Conflicts with the `decepticon` operator who wants to pin a specific version for a multi-day engagement.

## Recommendation

**Option A** with a versioned fallback chain:

1. Launcher reads `releases/latest` at start (cache hit → use cached; cache miss → fetch with 5s timeout).
2. If reachable, set `DECEPTICON_VERSION = stripped(latest_tag)` and persist `$DECEPTICON_HOME/.last-release`.
3. If unreachable, fall back to `$DECEPTICON_HOME/.last-release` (last known good).
4. If neither exists, fall back to the launcher binary's stamped `version` (the current behaviour — safe default).
5. Override hooks for power users: `DECEPTICON_VERSION` set in `.env` always wins; `--pin-version=v1.1.12` CLI flag for one-shot.

This keeps reproducibility for operators who pin via `.env`, makes image-only patches deliver to default users, and degrades gracefully offline.

Once A is in place, 3a becomes:
- Detect `vX.Y.Z.N` tag pattern in `release.yml`.
- Skip the `publish-pypi` and `launcher` jobs (no Python wheels, no Go binary diff).
- Run only the docker / docker-heavy / docker-web matrices + `publish-release`.
- Extend `compareSemver` to 4-segment so the launcher's own self-update check picks up the patch tag.
- Audit `publish-release`'s `if:` gates to confirm `1.1.12.1` flows through the stable promotion path.

Estimated reduction: ~30 min → ~5–8 min per image-only hotfix.

## Open questions

- **Cache invalidation.** How often should the launcher re-query `releases/latest` after it's cached? Per-start, or with a TTL? A long TTL means a patch sits unapplied for hours; per-start re-fetches GitHub on every launch.
- **CI / dev mode.** `version == "dev"` is the existing skip-self-update signal. In dev mode should `DECEPTICON_VERSION` resolve to `:latest`, the binary-stamped `dev`, or something else? Today `make dogfood` stamps `version=dev` and compose interpolates `:dev` which the dev images do tag.
- **Multi-tenant test stacks.** Some users run multiple stacks via `DECEPTICON_STACK_NAME` — does each stack pick up its own `DECEPTICON_VERSION` resolution, or is it global per-host?
- **`:latest` promotion atomicity across 7 images.** `publish-release` promotes :latest on every image in series; a failure mid-sequence leaves some images at the new tag and others at the old. Not new but more acute under A.

## Out of scope

- The user-facing AUTO_UPDATE default flip (already shipped in v1.1.12).
- Cosign keyless retry policy improvements (separate issue — v1.1.12 hit it once for c2-sliver).
- Nightly `:nightly` cron build (originally proposed as 3b; defer until A lands so it has a clean handle).

## Decision needed

Before any code change:

1. Confirm **A** is the direction (vs B's simpler-but-defeats-the-point, or C's lose-reproducibility).
2. Pick the cache invalidation policy for the latest-release lookup.
3. Decide whether `--pin-version` lives on `decepticon start` (per-launch) or in `.env` (per-install).
