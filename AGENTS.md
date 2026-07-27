# Decepticon — Codex Guidelines

> Decepticon is a professional autonomous Red Team agent.
> The OSS repo is an **extensible agent core** that commercial products
> (SaaS) and community plugins extend. Treat it that way: changes that
> close the plugin contract or harden the agent loop are valued over
> changes that bolt new features onto the framework layer.

## Core philosophy (read once, then internalize)

1. **OSS = extensible core.** The published surface (`decepticon-core` +
   `decepticon-sdk`) is the API that downstream products and plugin authors
   build against. Treat it like a public API — even pre-1.0. If you change
   it, you must justify it in the PR description.
2. **Real kill chains, not checkbox scans.** Every architectural decision
   must serve agents that execute real attack chains under RoE/OPPLAN
   discipline. Reject changes that optimize for benchmark numbers at the
   cost of realistic operational behavior.
3. **Fresh context per objective.** 16 specialist agents, each spawned with
   a clean context window and the minimum prompt surface needed. Do not
   widen this without a strong reason — context bloat is the most common
   regression vector.
4. **Network isolation is non-negotiable.** Two Docker networks
   (`decepticon-net` for management, `sandbox-net` for operations). The
   sandbox must never reach LiteLLM / PostgreSQL / LangGraph / Web over
   TCP. Neo4j is the one intentional shared service.
5. **Offense serves defense.** Long-term direction is the Offensive
   Vaccine loop (attack → defend → verify). Keep designs compatible with
   a future defense component.
6. **Pre-1.0 cleanup mode.** Breaking changes to the API surface are
   allowed and expected. SemVer discipline kicks in at `1.0.0`. The
   `decepticon.compat` shim ships for one minor cycle when we break
   something obvious.

The authoritative design spec for the package split and plugin contract
is `docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md`.
Read it before touching anything in `packages/decepticon-core/`.

---

## Repository layout

This is a **uv workspace** with three published Python packages plus
client apps. The workspace root carries shared tooling config only and
is never published.

```
packages/
  decepticon-core/         # Contracts: types, protocols, registry. ZERO langchain/langgraph deps.
    decepticon_core/
      contracts/           # Plugin contracts (Backend, LLM, Tool, Middleware, Skill, Bundle)
      protocols/           # Runtime Protocols (BackendProtocol, …)
      registry/            # Plugin registry primitives + collision diagnostics
      types/               # State, OPPLAN, RoE, engagement schemas (Pydantic v2)
      utils/
      plugin_loader.py     # Entry-point group loader

  decepticon/              # Opinionated framework. Depends on decepticon-core.
    decepticon/
      agents/              # 16 specialist agent factories (decepticon, soundwave, recon, exploit, AD, cloud, …)
      middleware/          # 11 middleware slots (roe, opplan, hitl, skills, budget, …)
      llm/                 # LiteLLM router, model profiles, provider/OAuth handlers
      tools/               # Agent tools (bash → sandbox HTTP, kg_*, cve_lookup, web, etc.)
      backends/            # HTTPSandbox client + transports
      sandbox_kernel/      # Sandbox-side tmux session manager
      sandbox_server/      # HTTP server inside the sandbox container
      skills/              # Markdown skill catalogs (standard/, shared/, benchmark/, plugins/)
      skillogy/            # Skill-as-a-service layer (gRPC + REST)
      runtime/             # Graph builders, streaming, recording/replay
      server/              # LangGraph server entrypoint
      cli/                 # decepticon-cli helpers (auth, scan, etc. — TS CLI is separate)
      blue_cell/           # Defense-side scaffolding (Offensive Vaccine direction)
      compat/              # One-cycle shims for pre-1.0 renames
      telemetry/           # OpenTelemetry exporter alongside LangSmith
      plugin_loader.py     # Framework-side bundle activation
      _boot.py             # Process bootstrap

  decepticon-sdk/          # Plugin author entrypoint. Re-exports core + fixtures + scaffolding.
    decepticon_sdk/
      scaffold/            # `decepticon-sdk plugin new --kind=...` generator
      testing/             # FakeBackend / FakeLLM / pytest fixtures

clients/
  cli/                     # Ink (React 19) interactive terminal UI (TypeScript, @decepticon/cli)
  web/                     # Next.js 16 web dashboard (TypeScript, Prisma, PostgreSQL)
  launcher/                # Go CLI launcher (`decepticon` binary, Cobra + Huh v2)
  shared/                  # Shared TypeScript packages (@decepticon/streaming, etc.)

containers/                # Dockerfiles: langgraph, litellm, sandbox, web, cli, c2-sliver, skillogy
config/                    # LiteLLM proxy config (litellm.yaml + dynamic_config.py)
benchmark/                 # XBOW validation-benchmarks runner + provider + results
docs/
  superpowers/specs/       # Authoritative design specs (read these before redesigns)
  design/                  # Feature design notes (attack-graph schema, opplan middleware, …)
scripts/install.sh         # curl | bash installer
```

**Schemas note:** Pydantic v2 state/OPPLAN/RoE/engagement schemas live in
`packages/decepticon-core/decepticon_core/types/`. The framework does not
re-define them — it imports from core.

---

## Tech stack

- **Backend (Python 3.13)**: uv workspace, LangGraph, LangChain (`create_agent`),
  deepagents, Pydantic v2. Ruff + basedpyright shared config at root.
- **CLI**: TypeScript + React 19 + Ink (`clients/cli`, npm workspace).
- **Web**: Next.js 16 + TypeScript + Prisma + PostgreSQL (`clients/web`).
- **Launcher**: Go 1.24 + Cobra + Charmbracelet Huh v2 (`clients/launcher`).
- **Infra**: Docker Compose, LiteLLM proxy, Neo4j, PostgreSQL, Sliver C2.
- **Telemetry**: LangSmith (primary) + optional OpenTelemetry exporter.
- **CI/CD**: GitHub Actions, GoReleaser v2, Cosign keyless signing,
  PyPI OIDC Trusted Publishing.

---

## Git

- Do NOT add `Co-Authored-By: Codex` or any AI co-author trailer to commits.
- Commit message style: `type(scope): description`
  (e.g., `fix(docker): resolve OSS install failures`).
- **No integration / mega-PRs.** PRs that bundle N unrelated branches
  ("merge all open PRs", "consolidated backlog") are closed on sight —
  they hide review surface and corrupt blame history. Land the individual
  PRs instead. See `CONTRIBUTING.md` for full PR etiquette.

---

## CI/CD pre-push verification

Before committing or pushing any code change, replicate every gating
check in `.github/workflows/ci.yml` locally so PRs don't fail in CI.
This is mandatory — running tests once isn't enough; the formatter and
typechecker must also pass.

**Run the relevant subset for what you changed:**

```bash
# Python (any change under packages/**, config/*.py, benchmark/**)
uv run ruff check .
uv run ruff format --check .          # CI fails on un-formatted files; run `uv run ruff format .` to fix
uv run basedpyright --level error
uv run pytest -n auto -q -m "not slow"

# Go launcher (clients/launcher/)
cd clients/launcher && go vet ./... && go test ./...

# CLI (clients/cli/) — workspace-rooted
npm run build --workspace=@decepticon/streaming     # streaming must build first
npm run typecheck --workspace=@decepticon/cli
npm run build --workspace=@decepticon/cli
npm run test --workspace=@decepticon/cli

# Web dashboard (clients/web/)
cd clients/web && npx prisma generate && npx eslint src/ --max-warnings 0 && npm run build
```

If you only touched Go or only touched Python, run only that lane —
but always run **the full lane**, including the formatter and
typechecker, not just tests.

### Aggregate gates

The Makefile is the **single source of truth** for what CI runs;
`.github/workflows/ci.yml` dispatches via `make` so local and CI cannot
drift. Two tiers:

```bash
make quality          # PR gate — mirrors CI PR lane:
                      #   ci-lint (errors-only typecheck) + ci-test (-m "not slow") + CLI + Web
                      # Use before opening a PR. Passing locally guarantees CI will pass.

make quality-strict   # Release gate — mirrors CI main-push lane + full basedpyright audit:
                      #   ci-lint + ci-test-coverage (--cov-fail-under=35) + CLI + Web
                      #   + full basedpyright (warnings + info, non-blocking)
                      # Use before tagging a release.
```

Sub-targets (invoke directly when isolating a failure):
- `make ci-lint` — ruff check + format + basedpyright (errors-only via `scripts/check_basedpyright_errors.py`)
- `make ci-test` — `pytest -n auto -q -m "not slow"` (PR lane)
- `make ci-test-coverage` — `pytest -n auto --cov --cov-fail-under=35` (main-push lane)

The legacy `make lint` and `make test-local` are preserved for
exploratory local use (full basedpyright output, ARGS passthrough)
but are **not** what CI runs.

When CI fails after a push, pull the failed step's log
(`gh run view <run-id> --log-failed`) and reproduce it with the same
command locally before pushing a fix. Don't push speculative fixes.

---

## Live verification before every PR (mandatory)

Passing unit tests is **not** sufficient evidence that a change does what it
was designed to do. **Before opening (or pushing to) any PR, run the change
against real, executing code and observe the actual behavior end-to-end** —
not just `pytest`/`npm test`.

- Stand up whatever the change touches (the service, the gateway, the CLI,
  the agent loop) and drive a realistic scenario through it, then inspect the
  real output to confirm it matches intent.
- For data/telemetry/redaction changes: feed real-shaped input through the
  actual runtime path and verify the actual payload that comes out (e.g.
  middleware → sink → live gateway → backend), including the negative case
  (the thing that must NOT happen — a leak, a wrong status — actually doesn't).
- Tear down any temporary infra and scrub temp files/secrets afterward.
- State the live-verification evidence in the PR description, not just "tests
  pass". If you could not live-verify, say so explicitly and why.

This complements (does not replace) the CI mirror above and the dogfood gate
below.

---

## Pre-release dogfood verification (mandatory before tagging)

Every release must be dogfooded against local code via the Makefile
before tagging. The release workflow can verify image digests, but only
the launcher → onboard → engagement → CLI flow exercises the OSS user UX
end-to-end. Skipping this has shipped broken installs in the past.

**Required gating order before `git tag`:**

```bash
make quality-strict   # 1. Release gate (mirrors CI main-push lane + warning audit)
make smoke            # 2. Compose-only sanity (no launcher) — fast
make dogfood          # 3. Full OSS UX (launcher onboard → CLI)
git tag v{x.y.z} && git push origin v{x.y.z}
```

For PR-only changes (no tag), `make quality` (PR-lane mirror) is the
minimum gate.

No version-bump commit is needed. All three Python packages
(`packages/decepticon-core`, `packages/decepticon`, `packages/decepticon-sdk`)
and the JS workspaces (`clients/cli`, `clients/web`) carry a `"0.0.0"`
sentinel in source and are stamped with the real version at Docker build
time via `--build-arg VERSION=<tag>`. The release workflow injects this
from `${GITHUB_REF_NAME#v}` automatically. The three Python packages
release **lockstep** — same version, atomically published to PyPI via OIDC.

`make dogfood` runs against an isolated `.dogfood/` (`$DECEPTICON_HOME`),
so the user's real `~/.decepticon` is untouched. `make clean` purges the
dogfood state (`.dogfood/` + compose volumes) when a fresh onboard
wizard run is needed.

---

## Common commands

```bash
# Pre-release verification (see "Pre-release dogfood verification" above)
make dogfood          # Full OSS UX (launcher → onboard → CLI) on local code
make smoke            # Compose-only sanity (no launcher) — fast
make clean            # Teardown (compose volumes + .dogfood/)

# Development
make dev              # Backend hot-reload (compose watch)
make cli-dev          # CLI locally + backend hot-reload
make web-dev          # Web (Next.js) locally + backend hot-reload

# Quality gates (CI mirror — single source of truth in Makefile)
make quality          # PR gate (mirrors CI PR lane: ci-lint + ci-test + CLI + Web)
make quality-strict   # Release gate (ci-lint + ci-test-coverage + CLI + Web + full basedpyright)
make ci-lint          # ruff check + format + basedpyright errors-only
make ci-test          # pytest -n auto -q -m "not slow"
make ci-test-coverage # pytest -n auto --cov --cov-fail-under=35
make test             # pytest inside langgraph container
make test-local       # pytest locally, takes ARGS= (full basedpyright on `make lint`)
make lint             # local exploratory: ruff check + ruff format --check + full basedpyright
make lint-fix         # ruff auto-fix
make web-build        # Prisma generate + Next build
make web-lint         # ESLint

# Go launcher (single check)
cd clients/launcher && go vet ./... && go test ./...

# Benchmarks
make benchmark ARGS="--ids XBEN-034-24,XBEN-084-24"
```

---

## Plugin architecture (when you're changing core/sdk)

`decepticon-core` is the contract layer. **External plugin authors must be
able to write a complete plugin importing only from `decepticon_sdk`** —
no underscore-prefixed framework internals. Before adding to core, ask:

- Is this a **Protocol** (runtime contract) or a **Type** (data shape)?
  Protocols go under `protocols/`, types under `types/`.
- Does it require `langchain` / `langgraph` / `deepagents` to define?
  If yes, it belongs in the framework, not core. Core has zero runtime
  dependency on those libraries.
- Does it expand an existing **entry-point group**
  (`decepticon.agents`, `.subagents`, `.tools`, `.middleware`, `.callbacks`,
  `.skills`, `.bundles`)? If yes, document the contract change and add a
  registry test under `packages/decepticon-core/tests/`.

The plugin loader honors the `[tool.decepticon.plugins].enabled` list in
the CWD's `pyproject.toml` (defaults to `["standard"]` for OSS end users;
SaaS Docker images set `DECEPTICON_PLUGINS=standard,saas`).

---

## Architecture invariants (don't violate without an RFC)

- **Two isolated Docker networks** (`decepticon-net` + `sandbox-net`).
  Sandbox cannot reach management services over TCP.
- **Agent → sandbox = Docker socket only**, never TCP.
- **Neo4j is dual-homed** — the one intentional shared service for attack-graph
  reads/writes between agent and sandbox.
- **OSS users install via `curl | bash`** — no source code, only pre-built
  GHCR images. `docker-compose.yml` has `build:` sections for dev, but OSS
  uses `image:` with `--no-build`.
- **All `docker compose run` commands MUST include `--no-build`** when
  running against an OSS-style stack.
- **Config file downloads MUST use release tag URL (`v{version}`)**, not
  `main` branch, so the install path is deterministic per release.
- **Bash tool is the single execution surface.** All commands flow through
  `DockerSandbox.execute_tmux()` — persistent tmux sessions with interactive
  prompt detection. Do not add side-channel exec paths.

See `docs/architecture.md` for the full network diagram and the data-flow
walkthrough for a single objective.

---

## Release process

1. Run the pre-release gating order — see "Pre-release dogfood verification"
   above (`make quality-strict` → `make smoke` → `make dogfood`).
2. Tag: `git tag v{version} && git push origin v{version}`.
3. The release workflow does the rest:
   - Go binaries via GoReleaser (`-X cmd.version={tag}`).
   - Docker images to GHCR (`--build-arg VERSION={tag}` stamps `pyproject.toml`
     + `package.json` in every image).
   - **PyPI** publishes all three Python packages atomically via OIDC
     Trusted Publishing — no API token, no human PAT.
   - **Cosign** keyless signing for images.
   - GitHub Release created by `github-actions[bot]`.
4. All images must be in `release.yml` matrix (including litellm + skillogy).
5. Release notes via `gh release edit`.

Releases are restricted to maintainers. Contributors with `write` access
can technically push a tag — please don't. Hand release-ready changes to
a maintainer.
