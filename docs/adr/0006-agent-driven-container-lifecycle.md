# 0006. Agent-driven domain-tool container lifecycle via an ops-control sidecar

- **Status:** Proposed
- **Date:** 2026-06-05
- **Deciders:** @PurpleCHOIms
- **Related:** [ADR-0005](0005-bloodhound-via-bhce-rest-client.md) (BHCE introduced as a sidecar, currently always-on); CLAUDE.md invariants on Bash-as-single-execution-surface and sandbox/management isolation

## Context

decepticon already runs each engagement objective through a fresh
specialist sub-agent.  The orchestrator agent (`decepticon`) uses
`SubAgentMiddleware` and a `task()` tool to delegate work to
`ad_operator`, `c2_operator`, `recon_operator`, etc., and each
specialist receives **only** the tool surface for its own domain —
e.g. `ad_operator` sees `AD_TOOLS` (legacy + `BHCE_TOOLS` after
PR #586), and `recon_operator` does not see those at all.  Agent-level
tool gating is therefore already in place.

What is **not** in place is the matching **container lifecycle gating**.
After ADR-0005 the BHCE sidecar (API + dedicated Neo4j) is wired into
`docker-compose.yml` without a `profiles:` clause and boots
unconditionally on `make dev` / `docker compose up`.  The same applies
in spirit to `c2-sliver` (profile-gated but with `COMPOSE_PROFILES=
c2-sliver` set in `.env.example` as the default), to a future
wireless rig service, to the Ghidra MCP sidecar, and to any other
domain-specific multi-container stateful tool.

Three problems flow from that mismatch:

1. **Idle cost.**  An engagement that never reaches AD still pays for
   BHCE's `dawgs` index build, its Neo4j heap, and the BHCE API
   process for the whole session.  Same for an engagement that never
   uses Sliver paying for the Sliver team server.

2. **Attack-surface stretch.**  A compromised sandbox network plane
   that never needed BHCE should not have BHCE's services as
   neighbours on `decepticon-net`.  Whatever isolation the network
   already provides is strictly more defensible when the unused
   service simply isn't running.

3. **Agentic model mismatch.**  decepticon's own design principle is
   *"fresh context per objective"*.  Its specialist-spawn lifecycle
   should drive its container lifecycle, not the other way around.
   The current setup is the inversion: a static set of containers
   defines what the agent could in theory reach, and tool-level
   gating only hides them.  The owner's stated intent (2026-06-05) is
   that **recon identifies AD → orchestrator decides to spawn
   ad_operator → that same decision should also bring up BHCE**.

The constraint we will not relax: the existing CLAUDE.md invariant
that *the Bash tool is the single execution surface* and that
**only the sandbox container has access to the Docker socket** for
host-level execution.  Giving the langgraph container a docker
socket bind would let any prompt-injection escalation walk straight
out of management into host control; that is a non-starter.

## Decision

We introduce a new sidecar **`ops-control`** that owns container
lifecycle on behalf of the agent system, and route specialist-driven
service activation through it.  Four sub-decisions:

1. **`ops-control` sidecar — the only container that touches the
   docker socket.**  `containers/ops-control.Dockerfile` ships a
   minimal Go (or Python) binary on `decepticon-net` with
   `/var/run/docker.sock` bind-mounted **read-only where possible**.
   It exposes a tiny HTTP API on an internal port (not host-exposed):

   ```
   POST /v1/profiles/{name}/start   → 202 Accepted (idempotent)
   POST /v1/profiles/{name}/stop    → 202 Accepted (idempotent)
   GET  /v1/profiles                → [{name, state, since}]
   GET  /v1/health                  → liveness
   ```

   `{name}` is matched against a server-side **allowlist** (`ad`,
   `c2-sliver`, `c2-havoc`, `reversing`, `wireless`, …).  Anything
   else returns 400 without touching docker.  Implementation calls
   `docker compose --profile <name> up -d` (or the equivalent SDK
   call) and `docker compose --profile <name> stop`.  No raw
   `docker run` / image pull / volume create / network edit — those
   surfaces never exist.

2. **Agent surface — `decepticon.tools.ops`.**  Three LangChain
   `@tool` wrappers:

   - `ops_start(profile: str) -> str`
   - `ops_stop(profile: str) -> str`
   - `ops_status() -> str`

   They speak HTTP to `ops-control` over `decepticon-net`.  Only the
   orchestrator agent (`decepticon`) carries these in its toolbox —
   specialist sub-agents do not, so a compromised sub-agent cannot
   spin up unrelated infrastructure.  The orchestrator's system
   prompt is updated to say: *"Before delegating to a specialist
   whose domain needs a sidecar service, call ops_start(<profile>)
   and wait for healthy; after the specialist returns, call
   ops_stop(<profile>) unless another pending task in the OPPLAN
   still needs it."*

3. **Default-off for every domain-specific service.**  `bhce` +
   `bhce-neo4j` gain `profiles: [ad]`.  `c2-sliver` already has
   `profiles: [c2-sliver]` but the **default value of
   `COMPOSE_PROFILES` is removed from `.env.example`** so a vanilla
   `make dev` brings up only the core plane (litellm + postgres +
   neo4j-KGStore + langgraph + web + sandbox + skillogy +
   `ops-control`).  Domain services are inert until something
   `ops_start`s them.

4. **HITL is an orthogonal toggle.**  An optional
   `HumanInTheLoopMiddleware` slot intercepts `ops_start` /
   `ops_stop` calls when `OPS_REQUIRE_APPROVAL=true` is set on the
   orchestrator.  Default is autonomous for unattended /
   scheduled runs; training / evaluation runs flip the toggle and
   get explicit one-click approvals via the existing HITL UI.

5. **Runtime-agnostic interface.**  ops-control is the *interface*
   the orchestrator depends on, not a Docker-specific component.
   The HTTP API above is deliberately generic — `profile` is an
   opaque allowlist key, not a docker-compose feature.  The bundled
   OSS implementation backs that interface with a Docker Compose
   adapter (the simplest concrete case), but the interface admits
   alternative orchestrator backends (Kubernetes API,
   HashiCorp Nomad, container-runtime SDKs, managed cluster
   environments) under the same allowlist + same HTTP contract.
   Those alternative adapters live outside this repo; the OSS
   surface ships only the Docker Compose path.  Keeping the agent
   side independent of which lifecycle backend runs underneath is
   what lets the same `ops_start("ad")` call work in a developer's
   docker-compose stack and in a managed cluster without any
   change to agent code.

### CLAUDE.md invariant update

The existing rule:

> Bash tool is the single execution surface.  All commands flow
> through `DockerSandbox.execute_tmux()` — persistent tmux sessions
> with interactive prompt detection.  Do not add side-channel exec
> paths.

is amended (separate docs PR) to:

> Bash tool is the single execution surface for in-target commands.
> `ops-control` is the single lifecycle surface for compose-defined
> services.  Docker socket binds are limited to those two containers
> (sandbox, ops-control) and nowhere else — langgraph, web, cli, c2,
> bhce all cannot reach the docker socket.

## Consequences

- **Easier**
  - Idle cost goes to zero for any service whose specialist never
    runs.  Many engagements (web-only, cloud-only, smart-contract,
    OSINT) will never start BHCE or Sliver.
  - The agent system's "fresh context per objective" principle now
    extends to "fresh process plane per objective" — closer to the
    framework's stated philosophy.
  - The attack surface of `decepticon-net` shrinks during the
    session: services that don't need to exist aren't reachable.
  - One canonical place — `ops-control`'s allowlist — describes
    every spawnable side service.  New domains plug in by adding a
    profile and an allowlist entry.

- **Harder**
  - One additional sidecar (+1 container) on the management plane.
    Mitigated by ops-control being a single tiny binary, not a stack.
  - Container start latency surfaces to the agent: BHCE cold start
    is ~30 s (Neo4j heap + goose migrations).  Specialist sub-agent
    must tolerate that gap, which means the orchestrator should call
    `ops_start` *before* `task()` rather than concurrently.
  - HMAC token lifecycle for BHCE now has to follow the lifecycle of
    the BHCE container itself — token bootstrap (admin login →
    POST /api/v2/tokens) becomes part of the start path, not the
    boot path.  We will run that inside the BHCE start handler in
    `ops-control` and pass the resulting token back to langgraph
    over `decepticon-net` (HTTP — never to disk on the host).

- **Given up**
  - Predictability of `docker compose ps` for an outside observer:
    the running container set now depends on what the engagement
    has needed so far in the current session.  We mitigate by
    `ops_status()` and a future Web Dashboard panel.
  - The convenience of a "the whole stack is up after make dev"
    mental model for new contributors.  The README onboarding flow
    will spell out the new default explicitly.

- **Migration timeline**
  - Sprint 1: this ADR + scaffold `containers/ops-control.Dockerfile`
    + minimal HTTP API + `tools/ops` LangChain wrappers; **no**
    behaviour change to existing services yet.
  - Sprint 2: add `profiles: [ad]` to `bhce` + `bhce-neo4j`; remove
    `COMPOSE_PROFILES=c2-sliver` default from `.env.example`; update
    orchestrator system prompt to call `ops_start` / `ops_stop`.
  - Sprint 3: BHCE token bootstrap moves into `ops-control`'s start
    handler; langgraph receives the token over HTTP, not env var.
  - Sprint 4: CLAUDE.md + `docs/architecture.md` invariant edit;
    Web Dashboard `ops_status` panel.

## Alternatives considered

- **(M1) Give langgraph a docker socket bind so its `@tool` can run
  `docker compose up -d <profile>` directly.**  Rejected.  Any
  prompt-injection in langgraph then has full host-Docker control
  (`docker run -v /:/host …`).  This is the trapdoor the existing
  CLAUDE.md invariant exists to close, and there is no upside that
  ops-control's narrow allowlist API doesn't already deliver.

- **(M3) Human-in-the-loop only — no autonomous lifecycle.**
  Rejected as the *default*; the agent system has to be able to run
  unattended (scheduled engagements, long-running automated runs).
  Folded back in as the `OPS_REQUIRE_APPROVAL` toggle so HITL is
  available without being forced.

- **(M4) Move lifecycle into the host-side Go launcher
  (`clients/launcher`) and have the launcher poll OPPLAN to decide
  what to bring up.**  Rejected for this cycle: the launcher is
  currently boot-only (one shot), and turning it into a long-lived
  bidirectional control plane is a much bigger redesign than
  ops-control.  May become attractive later when the launcher already
  has a daemon mode for other reasons.

- **(M5) Static profile-gate + manual `COMPOSE_PROFILES=` on every
  run.**  Rejected as the *only* mechanism: it solves idle cost but
  not the agentic-model mismatch.  Pieces of it (profile gating on
  the domain services) survive into sub-decision #3 of this ADR;
  what we reject is **stopping there**.

- **(M6) Run each domain stack as a separate compose project the
  operator launches by hand (`decepticon-bhce`, `decepticon-c2`,
  etc.).**  Rejected: defeats the integrated agent experience and
  doubles the secret/network plumbing.  Better revisited if/when the
  project splits OSS core from operator-managed extensions.
