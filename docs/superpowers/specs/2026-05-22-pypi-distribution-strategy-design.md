# PyPI Distribution Strategy — Design Spec

- **Date:** 2026-05-22
- **Status:** Approved (brainstorming), pending implementation plan
- **Branch:** `docs/pypi-distribution-strategy`
- **Companion analysis:** `docs/pypi-distribution-strategy.md` (the *why*; this doc is the *how*)

## Context & current state

- OSS `decepticon` is already a pip-buildable package (hatchling wheel,
  `packages = ["decepticon"]`, Apache-2.0) but is **not published to PyPI**.
  Distribution today is Docker/GHCR images via `curl | bash`
  (`scripts/install.sh`), with the `version = "0.0.0"` sentinel stamped
  with the git tag at Docker build time (`pyproject.toml:1-7`,
  `containers/langgraph.Dockerfile:27`).
- The commercial (SaaS/EE) product is a **downstream package** that depends
  on the core and extends it via entry-point groups
  (`decepticon.bundles`/`subagents`/`skills`/`tools`) with `bundle="saas"`,
  activated by `DECEPTICON_PLUGINS=standard,saas`
  (`pyproject.toml:82-123`, `decepticon/plugin_loader.py:527-529`). Its
  only documented way to consume the core today is a git pin
  (`docs/library-usage.md:383-393`).
- Skills (`skills/`) are **baked into the langgraph image at `/app/skills`**
  and served in-process by a local `FilesystemBackend` via
  `CompositeBackend`, which maps the logical `/skills/` prefix to the local
  tree (`decepticon/backends/__init__.py`,
  `containers/langgraph.Dockerfile:13,21`). The sandbox image no longer
  bakes skills. (Note: the prompt comment at `decepticon/middleware/skills.py:109-111`
  still claims skills live in the sandbox — this is **stale** and must be fixed.)

## Goals

Publish the OSS core to PyPI so that it serves **both** equally:
1. A clean, versioned dependency for the commercial product and integrators
   (replacing the git pin).
2. A reusable, composable security-agent SDK for the LangChain ecosystem
   (the `langchain → langgraph → deepagents → decepticon` layering).

## Non-goals (out of scope for this spec)

- Making a `pip install`-only user run a full agent without external
  services (the sandbox/infra stay containerized — see §5).
- A local-runtime convenience layer (`decepticon[runtime]` / CLI to spin a
  local sandbox) — deferred follow-on (the "C option").
- Switching the Docker images from build-from-source to `pip install
  decepticon==X` — optional follow-on (§5).

## Design

### 1. Package layout & wheel composition

Ship a **single `decepticon` wheel** (no modular `-core`/`-agents` split —
YAGNI, avoids version-coordination overhead). The commercial product then
depends on exactly one package.

```
decepticon/                      # single wheel (packages=["decepticon"])
├── agents/  middleware/  tools/  llm/  backends/  core/   # Python blocks
├── skills/                       # NEW: moved under the package (data)
├── sandbox_server/  sandbox_kernel/
```

Heavy/optional dependencies move to **extras** so the base install stays
lean for library consumers:

| Install | Contents |
|---------|----------|
| `pip install decepticon` | Core SDK (agents/middleware/tools/llm/backends) + skill assets |
| `decepticon[neo4j]` | `neo4j` (KG attack-chain graph) |
| `decepticon[all]` | Everything |

`langgraph`/`langchain`/`deepagents`/`fastapi` stay in the core
(agent-runtime essential). Only deps used by optional features (e.g.
`neo4j`) move to extras.

### 2. Skills packaging

- **Move** `skills/` → `decepticon/skills/` (package data). The
  agent-facing **logical `/skills/standard/recon/` convention is
  preserved** — `CompositeBackend` maps the `/skills/` virtual prefix to
  the package tree, so prompts, `load_skill()`, and `skills_sources_for()`
  are unchanged.
- **Path resolution:** replace the hardcoded
  `SKILLS_LOCAL_PATH = "/app/skills"` with an install-location lookup:
  ```python
  import importlib.resources
  SKILLS_LOCAL_PATH = str(importlib.resources.files("decepticon") / "skills")
  ```
  This resolves identically for wheel installs (site-packages), editable
  installs (repo), and Docker (`/app/decepticon/skills`). The langgraph
  image's `COPY skills/ skills/` (→ `/app/skills`) becomes redundant —
  skills now ship with `COPY decepticon/`.
- **Bundle selection for the public wheel:**

  | Bundle | In public wheel | Note |
  |--------|:---:|------|
  | `standard`, `shared` | ✅ | core OSS skills |
  | `plugins` (vulnresearch) | ✅ | opt-in OSS bundle |
  | `benchmark` | ❌ excluded | XBOW/CTF flag+tag conventions = eval-harness only; kept in-repo for `make benchmark`, excluded from the wheel via a hatch exclude |

- **Cleanup:** fix the stale comment at `decepticon/middleware/skills.py:109-111`.
- **Lint impact:** none — skills are `.md`, outside ruff/pyright (`.py`) scope.

### 3. Versioning & release flow

Add a **`publish-pypi` job** to the release workflow:
1. Stamp the version from the git tag (reuse the existing `sed` approach
   for consistency with the Docker build — single source of truth = git tag).
2. `hatch build` → wheel + sdist.
3. Publish via **PyPI Trusted Publishing (OIDC)** — no API token in secrets.
4. Register the job in the release matrix (mirrors the "all images in
   `release.yml`" rule).

Alternative considered: `hatch-vcs` (dynamic version from the tag) — also
satisfies the "no version commit" rule and is more idiomatic, but the first
cut reuses `sed` stamping to stay consistent with the current Docker flow.

**SemVer commitment:** the public surface in `docs/library-usage.md`
(factory kwargs, `PluginBundle`, `build_middleware`, building-blocks table)
is non-breaking within a major; internals (`_resolve_*`, private helpers)
are explicitly excluded.

### 4. OSS/EE boundary

| | Public (PyPI, Apache-2.0) | Private (commercial) |
|---|---|---|
| Code | all of `decepticon/` (agents standard+plugins, middleware, tools, llm, backends, core) | separate private package |
| Skills | standard / shared / plugins | saas-only skills |
| Extension | *defines* entry-point groups | *contributes* via `bundle="saas"` (downstream dep) |
| Activation | default `["standard"]` | `DECEPTICON_PLUGINS=standard,saas` |

- The commercial package is **not** published to PyPI (or goes to a private
  index); it depends on `decepticon`.
- **No-leakage guarantee:** the public wheel includes only `decepticon/`
  (EE already removed in #270) plus selected skill bundles (benchmark
  excluded, §2). Verify no saas-only code/skills exist in the tree.
- The safety gate (`SafetyOverrideViolation`,
  `docs/library-usage.md:272-293`) stays in the OSS core — trust story.
- This boundary is already clean; the strategy preserves it.

### 5. Coexistence & migration

- **Docker / `curl | bash` remains the turnkey end-user path** (full stack:
  langgraph + sandbox + litellm + postgres + neo4j). PyPI is **additive**
  for library / integrator / commercial use.
- **Runtime for pip users:** backing services are configured via env
  (`SAAS_SANDBOX_URL`, …), not bundled. A local-sandbox convenience layer is
  a deferred follow-on (non-goal).
- **Commercial product migration:** after the first publish, replace
  `decepticon @ git+…@tag` with `decepticon>=X,<Y`; update the git-pin
  guidance at `docs/library-usage.md:383-393` and `docs/contributing.md:114`.
- **Docker images (optional, later):** may switch build-from-source →
  `pip install decepticon==X` for cleaner layers; not required for this work.

## Implementation impact (high level)

- `decepticon/skills/` ← move from `skills/` (git mv); update
  `containers/langgraph.Dockerfile` (drop `COPY skills/`), `pyproject.toml`
  ruff/pyright exclude paths.
- `decepticon/backends/__init__.py` — `SKILLS_LOCAL_PATH` via
  `importlib.resources`.
- `pyproject.toml` — add `[project.optional-dependencies]` extras; move
  `neo4j` out of core; hatch exclude for `decepticon/skills/benchmark`;
  confirm hatchling includes `.md` package data.
- `decepticon/middleware/skills.py:109-111` — fix stale comment.
- Release workflow — add `publish-pypi` job + Trusted Publishing.
- Docs — `docs/library-usage.md`, `docs/contributing.md` migration notes.

## Risks & open questions

- **`importlib.resources` + editable installs:** verify `files()` resolves
  skill subdirectories correctly under `uv pip install -e .` (the langgraph
  image uses editable install).
- **Hatchling `.md` inclusion:** confirm data files under
  `decepticon/skills/` ship in the wheel by default; pin explicitly if not.
- **Benchmark exclusion vs in-repo dev:** the hatch exclude must not break
  `make benchmark` resolving `decepticon/skills/benchmark` from the editable
  checkout.
- **First published version number:** decide the initial PyPI version (the
  source tree carries the `0.0.0` sentinel; the tag drives the real number).
- **Guarded optional imports:** moving `neo4j` to an extra means the
  KG/research tools (`decepticon/tools/research/*`) must not import `neo4j`
  at module load — base `pip install decepticon` would otherwise fail to
  import those tools. The plan must make these imports lazy/guarded (and the
  agents that don't use the KG must import cleanly without the extra).
