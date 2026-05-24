# Changelog

All notable changes to the Decepticon project. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/) from `1.0.0`
onward (the `0.x` cycle is pre-stable per
[spec §13.4](docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md)).

## [Unreleased] — targets v1.1.2

This release introduces the three-package split (additive — every
legacy import path keeps working via compat shims). Targets
``v1.1.2`` against the OSS series currently at ``v1.1.1``. Removal of
the compat shims, ``PluginBundle`` aggregate shape, and the legacy
``decepticon.agents.middleware_slots.MiddlewareSlot`` re-export is
deferred to ``2.0.0`` (see "Deprecated" table below).

### Added — three-package split (core / framework / sdk)

OSS shifts from a monolithic `decepticon` wheel to three coordinated
wheels. The split exposes a stable contract layer that commercial
products, downstream frameworks, and the community can extend without
touching framework internals. Full design rationale in
[`docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md`](docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md).

- **`decepticon-core`** (new) — pure types, protocols, plugin contracts,
  registry primitives. Zero `langchain` / `langgraph` / `deepagents` /
  `httpx` / `fastapi` runtime dependency. Safe to pin from any context
  (CLI tooling, serverless workers, type-check-only environments).
  - 7 runtime-checkable `Protocol`s for plugin authors
    (`BackendProtocol`, `MiddlewareProtocol`, `ToolProtocol`,
    `CallbackProtocol`, `LLMProtocol`, `SandboxProtocol`,
    `AgentProtocol`).
  - 5 focused contribution dataclasses (`ToolContribution`,
    `MiddlewareContribution`, `PromptContribution`,
    `SubAgentContribution`, `SafetyDeclaration`) replacing the
    kitchen-sink `PluginBundle` shape.
  - `RoleRegistry`, `SkillSourceRegistry`, `PluginRegistry` with
    `PluginConflictWarning` + `RoleResolution` introspection types.
- **`decepticon-sdk`** (new) — single-import surface for plugin
  authors. Re-exports 23 stable symbols from `decepticon-core`. Ships
  `decepticon_sdk.testing` (`FakeBackend` / `FakeLLM` / `FakeSandbox`
  that satisfy their respective `Protocol`s at runtime) and a
  `decepticon-sdk plugin new` scaffolder covering six plugin kinds
  (tool / middleware / agent / callback / skill / prompt).
- **`decepticon`** (relocated to `packages/decepticon/src/decepticon/`) —
  the opinionated framework. Same agent factories, middleware, tools,
  LLM router as before; depends on `decepticon-core` for every
  contract surface it touches.

### Added — plugin extension primitives (closes 9 of 12 spec §8 gaps)

- `make_agent_backend(extra_routes=...)` with longest-prefix-wins
  routing (closes gap #1, gap #3). Tenant-specific paths like
  `/skills/tenant/<id>/` deterministically override the generic
  `/skills/` default — load-bearing per [spec §16.4
  #5](docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md)
  for the future B2B Enterprise tier.
- `RoleRegistry.register(name, *, slots, skill_sources,
  llm_role_fallback)` for custom agent roles (closes gap #5).
  Idempotent on identical parameters (multi-process worker startup
  safe). The framework registers all 16 OSS roles at boot via
  `decepticon._boot.run()`.
- `PluginRegistry.load()` walks the nine `decepticon.*` entry-point
  groups (`tools`, `middleware`, `agents`, `subagents`, `callbacks`,
  `skills`, `bundles`, `roles`, `prompts`) and surfaces same-key
  collisions as `PluginConflictWarning` (closes gap #4, gap #7).
- `SkillSourceRegistry.register(source, owner)` validates `/skills/`
  prefix + collision detection (closes gap #12). Malformed paths
  fail registration loudly.
- `SafetyDeclaration` for plugin-extended safety-critical
  tool/middleware names (closes gap #10). Additive-only per [spec
  §16.4 #4](docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md) —
  plugins cannot remove safety on OSS-declared names.
- `PromptContribution` + `decepticon.prompts` entry-point group for
  prompt-only plugins (closes gap #8). No longer requires wrapping in
  `PluginBundle`.
- `roles=` / `parent_agents=` now explicitly required on every
  contribution (closes gap #6). Empty tuple raises at registration.

### Added — author tooling + docs

- Scaffolding CLI: `decepticon-sdk plugin new --kind=KIND --name=NAME
  --path=PATH`. Generates a buildable plugin package (`pyproject.toml`
  + `README.md` + `src/<module>/__init__.py`) wired to the matching
  entry-point group.
- Six runnable example plugins under
  [`packages/decepticon-sdk/examples/`](packages/decepticon-sdk/examples/),
  one per kind. All six build to wheel + sdist via `uv build`.
- New audience-specific guides:
  - [`docs/plugin-author-guide.md`](docs/plugin-author-guide.md)
  - [`docs/library-consumer-guide.md`](docs/library-consumer-guide.md)
  - [`docs/contributor-architecture.md`](docs/contributor-architecture.md)
  - [`docs/migration/from-0.0.x.md`](docs/migration/from-0.0.x.md)

### Changed

- Source tree relocated: `decepticon/` and `tests/` moved into
  `packages/decepticon/src/decepticon/` and
  `packages/decepticon/tests/` respectively (history preserved via
  `git mv`). End-user CLI commands and the Docker stack UX are
  unchanged.
- The root `pyproject.toml` is now a workspace umbrella
  (`[tool.uv] package = false`). Workspace members live under
  `packages/*`. Run `uv sync` from the workspace root to install all
  three packages in lockstep.
- Framework imports rewritten to consume `decepticon_core.*` directly
  (71 files). Legacy import paths keep working via thin re-export
  shims for one release; see migration guide.
- `containers/langgraph.Dockerfile` switches to `uv sync --no-dev
  --frozen --extra neo4j` against the workspace; `langgraph.json`
  graph paths repointed to `./packages/decepticon/src/decepticon/`.

### Deprecated

The following legacy import paths keep working but emit a
`DeprecationWarning` via `decepticon.compat.register_legacy_imports()`
(default-on; opt-out via `DECEPTICON_NO_COMPAT=1`). Shims removed at
**2.0.0**.

| Legacy path | Canonical path |
|-------------|----------------|
| `decepticon.core.schemas` | `decepticon_core.types.engagement` |
| `decepticon.llm.models` | `decepticon_core.types.llm` |
| `decepticon.tools.research.graph` | `decepticon_core.types.kg` |
| `decepticon.plugin_loader` | `decepticon_core.plugin_loader` |
| `decepticon.core.config` | `decepticon_core.utils.config` |
| `decepticon.core.logging` | `decepticon_core.utils.logging` |
| `decepticon.agents.middleware_slots.{MiddlewareSlot, SLOTS_PER_ROLE, SAFETY_CRITICAL_SLOTS}` | `decepticon_core.contracts.slots.*` |

### Notes

- `decepticon-core` LOC: 4,130 (spec §10 Phase 6 budget: ≤4,000).
  Modest over-shoot from the registry + protocols modules; trim in a
  follow-up if it remains a concern. None of the over-budget code
  imports langchain/langgraph/deepagents (defended by
  [`test_no_runtime_deps`](packages/decepticon-core/tests/test_no_runtime_deps.py)).
- All three packages ship a PEP 561 `py.typed` marker.
- Three packages release in lockstep with a single version string
  stamped from the git tag — verified by the release workflow at tag
  time.

### Deferred to subsequent releases

- `LLMFactory` consumption of `RoleRegistry.skill_sources` /
  `llm_role_fallback` fields (completes gap #5).
- `PluginRegistry.introspect_role()` real implementation (completes
  gap #7; currently a typed stub).
- Per-import `DeprecationWarning` emission via `sys.modules` aliasing
  (current implementation emits a single boot-time warning listing all
  legacy paths).
- Ruff `flake8-tidy-imports.banned-api` rule for `decepticon-core`
  (defended by runtime test at present).
- PyPI Trusted Publisher OIDC configuration for the three-wheel
  atomic release.
- Downstream `decepticon_saas` lockstep migration PR.
