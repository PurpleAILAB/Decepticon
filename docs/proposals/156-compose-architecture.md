# Proposal: resolve the dual `docker-compose.yml` architecture (issue #156)

**Status**: draft, awaiting maintainer direction
**Issue**: [#156](https://github.com/PurpleAILAB/Decepticon/issues/156)
**Author**: VoidChecksum

---

## Problem recap

Two `docker-compose.yml` files participate in the running Decepticon stack:

| Path | Purpose | Owner |
|---|---|---|
| `~/.decepticon/docker-compose.yml` | OSS install (downloaded by `scripts/install.sh` from the release tag) | end user |
| `<repo>/docker-compose.yml` + `<repo>/docker-compose.override.yml` | Dev clone (`make dev`, `make cli-dev`, benchmark harness) | contributor |

Compose merges files by directory, so `docker compose ls` reports the active project as the union of whichever files are in `cwd` (and an `override.yml` if present). The two installs produce *different* stacks — the dev override hot-bind-mounts `./skills/` into the sandbox; the OSS install does not (skills are baked into the image).

The issue catalogues seven concerns. Walking the current `main` (commit at the time of writing the proposal):

| # | Severity | Issue claim | Current state |
|---|----------|------------|---------------|
| 1 | CRITICAL | Override placement ambiguity — overrides in `~/.decepticon/` are silently ignored when running from the repo dir | **Still real.** The override file at the repo root is auto-merged by Compose any time `docker compose up` is run from the repo. A user who follows OSS docs and edits `~/.decepticon/docker-compose.override.yml` (a path that doesn't exist in the install) will see no effect; a contributor who edits the repo `docker-compose.override.yml` will affect dev runs but not OSS-style runs. The semantics depend on `cwd`, which is implicit and surprising. |
| 2 | CRITICAL | 7 host port collisions (4000, 5432, 7474, 7687, 2024, 3000, 3003) prevent dual-stack | **Partial.** Of the seven, 5 ports (`LITELLM_PORT`, `POSTGRES_PORT`, `LANGGRAPH_PORT`, `WEB_PORT`, `TERMINAL_PORT`) are now env-overridable with sensible defaults. **Neo4j's `7474` and `7687` are still hardcoded** — fixed in this proposal's companion patch (see "Companion patch" below). |
| 3 | CRITICAL | All 8 services have hardcoded `container_name`, blocking dual-stack | **Still real.** Every service still pins `container_name: decepticon-<svc>`. Removing those is a behaviour change for downstream tooling that targets containers by exact name (the launcher binary's `decepticon logs`/`stop` use them; user docs and runbooks reference them). Best resolved as part of the architectural decision below, not piecemeal. |
| 4 | HIGH | Entrypoint divergence — dev override changes entrypoint to `/patched/init.sh langgraph dev …` | **Already addressed.** The current `docker-compose.override.yml` (23 lines) only adds `./skills:/skills:ro` for the sandbox. There is no entrypoint override. |
| 5 | HIGH | `DECEPTICON_WORKSPACE_PATH=/workspace` set only in dev override; OSS sandbox missing it | **Already addressed.** The base `docker-compose.yml`'s `sandbox` service binds `${DECEPTICON_ENGAGEMENT_WORKSPACE:-${DECEPTICON_HOME:-~/.decepticon}/workspace}` to `/workspace`. The env var is implicit through the bind mount, not a separate declaration. |
| 6 | MEDIUM | Healthcheck compatibility risk between dev `langgraph dev` and prod `langgraph` server | **Already addressed.** Same reason as #4 — the override no longer changes the entrypoint, so the prod healthcheck (`/ok`) applies in both modes. |
| 7 | MEDIUM | Override mounts `./skills:/skills:ro` which fails if `./skills/` is missing | **Edge case.** The repo always ships with `skills/`; this only triggers if a contributor deletes it locally. Adding the mount as `:ro` over a missing source is a Docker-level error that surfaces immediately. Documenting this in the override file's preamble is enough. |

So **two of the original seven concerns are demonstrably moot**, **two are partially addressed by env-parameterization plus the companion patch**, and **three (CRITICAL #1, half of #2, #3) remain — and they cannot be resolved cleanly without picking a direction**.

## Maintainer's stated framing

From the issue thread (PurpleCHOIms, 2026-05-09):

> Resolving cleanly requires picking a direction:
> 1. Keep installed config authoritative; deprecate the repo `docker-compose.override.yml` for end users.
> 2. Or unify on a single source per environment (one for dev, one for OSS install) and document the boundary.

This proposal recommends **Direction 1** for the reasons in the next section, then concretely lays out what that means in code, docs, and migration. Direction 2 is sketched at the end for completeness.

## Recommendation: Direction 1, with the dev override renamed and explicitly opt-in

### Why Direction 1

- **The OSS install path is the surface area users actually live in.** They never see the repo. Anything that resolves the ambiguity in the OSS path's favour means *no end user* hits the silent-override footgun.
- **Direction 2 (one compose per environment) doubles the maintenance surface.** Two YAMLs to keep aligned every time a service is added, every time a healthcheck changes, every time an env var is added. The current single base + dev-only delta is genuinely smaller — provided the dev delta is unambiguous about *being* a dev delta.
- **The repo's `docker-compose.override.yml` is already only 23 lines and does one thing** (skills hot-reload). It's not load-bearing in any user-facing way; it's a contributor convenience. Renaming it to `docker-compose.dev.yml` and gating it behind `make dev` (rather than implicit Compose merging) makes the dev path explicit without breaking it.

### Proposed changes

#### A. Rename the dev override and make it explicitly opt-in

- Rename `docker-compose.override.yml` → `docker-compose.dev.yml`. The new name **does not** auto-merge.
- Update `Makefile`'s `dev`, `cli-dev`, `web-dev`, `infra` targets to pass `-f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.watch.yml` explicitly (some already pass `docker-compose.watch.yml`).
- Document in the new file's preamble that running raw `docker compose up` from the repo will produce the OSS image behaviour, matching `~/.decepticon/`.

After this change, `docker compose ls` from the repo (without `make`) reports the same merged config as `docker compose ls` from `~/.decepticon/` — the surprise is gone.

#### B. Document the OSS-install path as the user-facing override surface

- Add a section to [`docs/setup-guide.md`](../setup-guide.md) titled "Customizing the install": tell users they can drop a `docker-compose.override.yml` into `~/.decepticon/` and Compose will merge it (since the launcher runs Compose from that directory).
- Note explicitly that **edits to `<repo>/docker-compose.override.yml` will not affect the launcher-driven OSS stack** — a one-liner that closes the trap the issue identified.

#### C. Address the remaining hardcoded port (CRITICAL #2 partial)

The companion patch in this branch parameterizes Neo4j's HTTP and Bolt ports:

```yaml
  neo4j:
    ports:
      - "127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474"
      - "127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687"
```

Plus the matching `.env.example` entries with the same defaults. Existing installs are unchanged; the env var is overridable for users running side-by-side stacks.

#### D. Address the container_name collision (CRITICAL #3) — phased

The launcher binary references containers by exact name (`decepticon logs <svc>`, `decepticon stop`, `decepticon status`). Dropping `container_name` would break those. Two options:

- **D1** (recommended): keep `container_name` for the OSS install, but parameterize via Compose project name. `decepticon-${COMPOSE_PROJECT_NAME:-default}-postgres` etc. Default `COMPOSE_PROJECT_NAME=default` reproduces today's names.
- **D2**: drop `container_name` entirely, teach the launcher to resolve services by Compose label (`com.docker.compose.service=postgres`). This is a larger launcher change.

D1 is the right tradeoff for an incremental fix. The launcher-side change to read `${COMPOSE_PROJECT_NAME}` is small and backwards-compatible.

#### E. CI guardrail

Add a GitHub Actions step that runs `docker compose -f docker-compose.yml config` and `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` and asserts neither errors. Catches drift early — if a future PR adds a service to the dev override that doesn't exist in base, CI fails.

### Migration plan

1. Land the companion port-parameterization patch (low-risk, no breaking changes). ✅ included in this branch.
2. Add the proposal's CI guardrail (no behaviour change, fail-fast for compose validity).
3. Decision point: maintainer accepts Direction 1.
4. Rename `docker-compose.override.yml` → `docker-compose.dev.yml`. Update Makefile targets. Update `docs/setup-guide.md`.
5. (Phase 2, optional) Container-name parameterization (D1 above) — separate PR; touches the launcher.

Steps 1–2 are safe to land before the architectural decision; they are cleanup. Steps 3–5 wait on maintainer sign-off.

## Direction 2 sketch (if the maintainer prefers it)

If the dual-target maintenance cost is acceptable, the alternative is two separate compose files, both checked in:

- `docker-compose.yml` — OSS install, identical to today's base.
- `docker-compose.dev.yml` — dev clone, **complete** (not an override). Includes everything from base plus the dev-mode bind mounts and watch directives. Run via `docker compose -f docker-compose.dev.yml up`.

The OSS installer continues to download `docker-compose.yml` only. The repo's `Makefile` targets explicitly use `docker-compose.dev.yml` — no implicit merging.

This eliminates the override-merge ambiguity entirely (since override files no longer participate), at the cost of two YAMLs to keep aligned. CI guardrails are even more important under this model.

## Companion patch in this branch

This branch's diff is intentionally minimal:

- `docker-compose.yml`: parameterize Neo4j ports (CRITICAL #2 partial fix).
- `.env.example`: add `NEO4J_HTTP_PORT` / `NEO4J_BOLT_PORT` defaults so users discover the knob.
- `docker-compose.override.yml`: extend the comment header to explicitly call out the auto-merge behaviour and that edits here will not affect the launcher's OSS stack — closing the documentation half of CRITICAL #1 without committing to the rename.
- `docs/proposals/156-compose-architecture.md`: this document.

No service rename, no `container_name` change, no override file rename. Those wait on the maintainer's direction call per the issue thread.
