# OSS PyPI Distribution — Strategic Value to the Commercial Product

> Analysis of what publishing the OSS `decepticon` core to PyPI buys the
> commercial (SaaS/EE) product. Grounded in the current packaging and
> plugin architecture, with risks and execution prerequisites.

## TL;DR

The commercial product is **not a fork** of Decepticon — it is a
downstream Python package that depends on the OSS `decepticon` core and
extends it through entry-point plugin groups (`decepticon.bundles`,
`decepticon.subagents`, `decepticon.skills`, …). Today that downstream
package can only pull the core as a **git dependency**
(`decepticon @ git+https://…@v1.x.y`). Publishing the core to PyPI turns
the core into a normal, versioned upstream dependency. That single change
upgrades dependency hygiene, release decoupling, API-contract stability,
the adoption funnel, and the enterprise trust story — all of which accrue
directly to the paid product. The cost is a SemVer maintenance commitment,
a real version-stamping flow, and supply-chain hardening.

## 1. Current state

- **OSS core is already a pip-installable package.** `pyproject.toml`
  builds a `decepticon` wheel via hatchling (`pyproject.toml:149-154`),
  Apache-2.0 licensed (`pyproject.toml:10`). The package is import-ready
  as a library — `docs/library-usage.md` documents three integration
  paths plus the declarative `PluginBundle` override surface.
- **It is not on PyPI.** Distribution is Docker/GHCR images installed via
  `curl | bash` (`scripts/install.sh` requires Docker + Compose v2). The
  `version` field is a `0.0.0` sentinel stamped with the git tag at Docker
  build time (`pyproject.toml:1-7`) — there is no published-version flow.
- **The commercial product layers on via entry-points.** The SaaS bundle
  (`bundle="saas"`) is activated with `DECEPTICON_PLUGINS=standard,saas`
  (`pyproject.toml:111-123`, `decepticon/plugin_loader.py:527-529`). The
  OSS default stays lean (`["standard"]`); SaaS images opt their bundle in.
- **The only documented way for SaaS to consume the core is a git pin.**
  `docs/library-usage.md:383-393` recommends
  `decepticon @ git+https://github.com/PurpleAILAB/Decepticon.git@v1.x.y`
  and states: *"PyPI publication is on the roadmap once the public API
  surface is stable enough to commit to."*
- `docs/contributing.md:114` already assumes the end state:
  *"End-user installs that just `pip install decepticon` get the lean
  standard-only default."*

**Why this matters:** because the commercial product is a *dependent
package*, every property of how the core is distributed propagates into
the paid product's build, release, and stability story.

## 2. Benefits to the commercial product

### 2.1 Dependency hygiene: git pin → versioned PyPI dependency

A git dependency is the weakest link in a Python dependency graph:

| Concern | git dependency (today) | PyPI dependency |
|---------|------------------------|-----------------|
| Resolver | uv/pip/poetry cannot range-resolve a git ref | `decepticon>=1.4,<2` resolves normally |
| Auth | needs git access in every build context | anonymous index fetch |
| Reproducibility | ref can move; needs commit-pin discipline | immutable versioned wheels + hashes |
| CI speed | full clone (incl. history) per build | cached wheel download |
| Docker layers | clone + build-from-source in image | `pip install decepticon==X` like any dep |

For the SaaS image and CI, this is the most concrete, immediate win.

### 2.2 Decoupled release cadence

With a published core, the SaaS plugin pins a **published version range**
and upgrades on its own schedule. The version sentinel design
(`pyproject.toml:1-7`) already anticipates independent versioning — PyPI
makes the core a true upstream that the paid product tracks deliberately,
instead of chasing a moving branch/tag.

### 2.3 A stable, committed public API contract

`docs/library-usage.md` explicitly gates PyPI publication on API
stability — and the override surface the commercial product relies on is
exactly that public API: factory kwargs (`tools`/`middleware`/
`system_prompt`/`backend`/`llm`/…), `PluginBundle`, `build_middleware(slots=…)`,
and the building-blocks table (`docs/library-usage.md:297-313`).
Publishing under SemVer turns that surface into a contract the core
**commits not to break within a major version**. The paid product gets
fewer surprise breakages and a clear upgrade signal (major bump = review).

### 2.4 Larger adoption funnel → conversion

`pip install decepticon` is dramatically lower friction than
`curl | bash` + Docker for the Python/security-research audience. A bigger
OSS top-of-funnel feeds the upsell: SaaS users adopt the **same core they
already run**, then activate the `saas` bundle. PyPI also adds
discoverability (search, classifiers in `pyproject.toml:23-33`) and the
implicit trust of an inspectable, Apache-2.0 package.

### 2.5 Plugin ecosystem leverage

The entry-point model (`pyproject.toml:82-100`) only pays off if third
parties can install the core to build against. A PyPI core makes community
tools/middleware/subagents/skills viable; a richer plugin ecosystem
strengthens the platform the commercial product sits on (and can curate or
absorb the best plugins into the paid tier).

### 2.6 Trust & enterprise sales story

The safety gate lives in the **OSS core**: replacing/disabling
safety-critical slots or tools raises `SafetyOverrideViolation` unless
explicitly opted in (`docs/library-usage.md:272-293`). A published,
auditable core lets enterprise buyers verify the safety and trust-boundary
story independently — the paid product inherits and points to that open
guarantee rather than asking customers to trust a black box.

## 3. Risks & trade-offs to weigh

1. **Open-core boundary.** Publishing the core widens what is publicly
   inspectable/replicable. The OSS/EE line (which surfaces stay
   SaaS-only vs. land in core) must be deliberate — the `saas` bundle and
   the override surface already give a clean seam, but feature placement
   decisions get higher-stakes.
2. **SemVer maintenance commitment.** A public release contract means
   breaking changes cost a major bump and migration notes. Internals
   (`_resolve_overrides`, private factory helpers) are explicitly excluded
   (`docs/library-usage.md:378-381`) — that exclusion must be enforced.
3. **Supply-chain responsibility.** A published package is an attack
   surface. Need PyPI Trusted Publishing (OIDC from the release workflow),
   signed/attested artifacts, and 2FA on the project — consistent with the
   hardening already applied to `install.sh` against compose-file swaps
   (`scripts/install.sh:171`).
4. **Real version-stamping flow.** The `0.0.0` sentinel is stamped only at
   Docker build time today. PyPI needs a genuine version source (tag →
   wheel metadata) so published versions are correct and monotonic.
5. **Dependency weight.** The core's install set
   (`pyproject.toml:35-67`) pulls langchain/langgraph/neo4j/fastapi/etc.
   For pure-library consumers, consider optional-dependency extras so
   `pip install decepticon` stays reasonable.

## 4. Prerequisites & execution steps

1. **Freeze the public API surface** documented in
   `docs/library-usage.md` and mark internals as unstable (mostly done).
2. **Add a PyPI version flow** — derive the wheel version from the git tag
   in the release workflow (mirror the existing Docker `--build-arg
   VERSION` stamping, but for the wheel build).
3. **Wire PyPI Trusted Publishing** (OIDC) into the release workflow; add
   artifact attestation/signing.
4. **Decide the core install footprint** — keep the heavy agent deps as
   the default, or split optional extras (`decepticon[agents]`,
   `decepticon[neo4j]`) so library/plugin consumers can stay lean.
5. **Switch SaaS to a versioned dependency** — replace the git pin with
   `decepticon>=X,<Y` once the first version is published.
6. **Update docs** — `docs/library-usage.md:383-393` git-pin guidance and
   `docs/contributing.md:114` already assume `pip install decepticon`;
   align them with the published flow.

## 5. Recommendation

Publishing the OSS core to PyPI is **net-positive for the commercial
product** and is the natural completion of the plugin-package architecture
that already exists. The dominant immediate win is dependency hygiene and
release decoupling for the SaaS build; the durable wins are the SemVer API
contract and the adoption-funnel/trust story. Proceed once the public API
surface is committed and the version-stamping + Trusted-Publishing flow is
in place — none of which require architectural change, only release
plumbing and a deliberate open-core boundary.
