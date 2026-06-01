# Changelog

All notable changes to the Decepticon project. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/) from `1.0.0`
onward (the `0.x` cycle is pre-stable per the core/framework/sdk split
design spec, §13.4).

## [1.1.5] — 2026-06-01

Patch release. Fixes a release-pipeline gap that broke `decepticon start`
for every published install since the Skillogy layer landed in `v1.1.4`.

### Fixed

- **Skillogy image is now published** — the release pipeline never built,
  pushed, verified, or promoted `ghcr.io/purpleailab/decepticon-skillogy`,
  even though the always-on compose `skillogy` service pulls it. Every
  release since `v1.1.4` therefore failed at `decepticon start` with
  `No such image: ghcr.io/purpleailab/decepticon-skillogy:<version>` /
  `error from registry: denied`. `decepticon-skillogy` is now part of the
  multi-arch `docker` build matrix and the `publish-release` verify +
  `:latest` promote lists (and `release-recover.yml`), so a missing image
  now fails the release loudly instead of shipping a broken compose file.
  (#450)

### Changed

- **`make dogfood`** now tears down any prior repo-root stack before
  starting, to avoid a container-name conflict. (#447)
- **`.env.example`** — the `LANGSMITH_API_KEY` placeholder is commented
  out so it no longer triggers 403 tracing-spam when LangSmith tracing is
  off. (#448)

## [1.1.4] — 2026-05-30

Capability + safety expansion on top of `v1.1.3`. Lands the Sisyphus
mega-PR (#350) [16 sub-PRs] and the 6-tier hardening + Offensive Vaccine
runtime (#342), the static-analysis CI arsenal (#343), three new
specialist agents, the Skillogy skill-as-a-service layer, six new
safety/security middleware, and the Makefile-as-single-source-of-truth
CI refactor (#443). The OSS default runtime, public plugin contract
(`decepticon-core` / `decepticon-sdk` surface), and three-package layout
are unchanged. All three Python packages release in lockstep.

### Added

- **Three specialist agents** — `Phisher`, `MobileOperator`,
  `WirelessOperator`. Each ships with a prompt under
  `agents/prompts/standard/` and a factory under `agents/standard/`.
  (#342)
- **Skillogy — skill-as-a-service** — dedicated gRPC + REST layer at
  `packages/decepticon/decepticon/skillogy/` (Dockerfile under
  `containers/skillogy.Dockerfile`). v0.1 design spec in
  `docs/design/skillogy.md`; user docs in `docs/skillogy.md`. Skill
  authoring (`SKILL.md`) is unchanged — Skillogy is a discovery layer
  on top. Ships behind a feature flag until benchmark validation
  passes. (#350, #445)
- **Blue cell — Offensive Vaccine runtime** — `blue_cell/` adds the
  tap + Sigma matcher infrastructure for the attack → defend → verify
  loop. Sigma/YARA → SIEM/EDR push exporters. (#342)
- **Six new safety / security middleware** — `PromptInjectionShield`
  (agent self-defense), `BudgetEnforcementMiddleware` (spend caps),
  `UntrustedOutputMiddleware` (structural quarantine for tool output),
  `HITLApprovalMiddleware` (transport-abstracted human-in-the-loop),
  `RoEMiddleware` (RoE enforcement + HMAC-chained audit log),
  `SkillogyMiddleware` (dynamic skill graph dispatch). (#342, #350)
- **OpenTelemetry exporter** — opt-in spans for engagement / agent /
  tool / LLM events; runs alongside LangSmith. New runtime deps
  `opentelemetry-{api,sdk,exporter-otlp}>=1.27`. (#350)
- **Static-analysis CI arsenal (18 tools)** — Semgrep custom rules
  (`.semgrep/`), bandit, deptry, vulture, refurb, radon, xenon, mypy,
  yamllint added under a new `lint` dependency group. OpenSSF
  Scorecard workflow. Consolidated `security.yml` and
  `security-scan-example.yml` workflows. (#343)
- **SARIF v2.1.0 export** for GitHub code scanning + DefectDojo. (#350)
- **Sandbox tool expansion** — Caido proxy bundle (capture / replay /
  scope / sitemap), persistent Playwright browser sessions
  (`browser_action` multiplex), `tmux pipe-pane → asciicast v2`
  evidence export, WAVE-4 6.1 Buttercup benchmark integration,
  WAVE-5 sandbox tools. (#350)
- **`decepticon-cli`** — `decepticon-cli auth` (headless provider /
  auth introspection); `decepticon-cli scan` + GitHub Action template
  for CI/CD parity. (#342, #350)
- **Runtime infrastructure** — bounded graceful SIGTERM/SIGINT
  shutdown library; append-only engagement `events.jsonl` log;
  record/replay layer for deterministic re-execution; CART skeleton
  with OPPLAN-matrix adapter seam; `SubAgentTaskSpec` data contract
  for scoped child dispatch; skill registry + slug/fuzzy resolver for
  dynamic `load_skill`. (#350)
- **Per-engagement isolation** — sandbox minimum-cap hardening;
  Neo4j per-engagement scoping (closes cross-engagement leak);
  allowlist-only APOC with client-side safety guard; Decepticon
  self-threat-model documented at
  `docs/security/decepticon-threat-model.md`. (#342)
- **Five new security docs** under `docs/security/` — decepticon
  threat model, Neo4j hardening, prompt-injection defense, sandbox
  isolation, sisyphus-pr top-level summary. (#342)
- **`Makefile` two-tier gate** — `make quality` mirrors the CI PR
  lane (`ci-lint` + `ci-test` + CLI + Web); `make quality-strict`
  mirrors the CI main-push lane (coverage 35% gate + full
  basedpyright warning audit). `.github/workflows/ci.yml` dispatches
  via `make` so local and CI cannot drift. (#443)
- **`scripts/check_basedpyright_errors.py`** — testable extraction of
  the inline Python that gated CI on basedpyright errors. (#443)

### Changed

- **Skill metadata schema** — `metadata.kind` (`reporting` |
  `analytic`) added to four `SKILL.md` files (the reporting +
  kill-chain-analysis set) for Skillogy graph node classification.
  Redundant `mitre_attack:` lists cleared on these four; the mappings
  move into typed graph edges. Other SKILL.md files unchanged. (#445)
- **`docs/skills.md`** — heads-up note linking to Skillogy as the
  planned successor to text-matching `SkillsMiddleware`. (#445)
- **`codeql.yml` workflow removed**, replaced by the consolidated
  `security.yml` (Semgrep custom rules + Trivy + bandit, deptry,
  vulture, etc.). (#343)
- **`xbow-validation-benchmarks` submodule** bumped
  `ec45927 → 1c15c32` — XBEN-099-24 FLAG plumbing (4 fixes),
  XBEN-084-24 base image bump (`node:14-alpine` → `node:18-alpine`),
  `.gitignore` for OMC local state. (#444)

### Fixed

- **`bash` tool — cross-thread fallback for HTTPSandbox `ContextVar`**.
  (#345)
- **streaming events** — `tool_call_id` included in
  `subagent_tool_call` / `subagent_tool_result` events so downstream
  consumers can correlate calls and results. (#346)
- **engagement workspace** — auto-materialized at orchestrator start;
  internal paths masked in error messages. (#347)
- **LLM subscription routing** — configured subscriptions used by
  default (auth priority). Fixes a regression introduced by the
  Sisyphus mega-PR. (#351)
- **Claude API `cache_control`** — capped when system blocks share
  content, preventing the 4-block hard limit from being exceeded.
  (#402)
- **OSS launcher UX** — de-duplicate `ctrl+o` hint; silence
  `DECEPTICON_STACK_NAME` compose warning when the stack name is the
  default. (#344)
- **Sandbox zombie reaper** — replaced the in-process SIGCHLD handler
  (clobbered exit codes) with `tini` (`init: true` on the sandbox
  compose service). (#340)
- **`asyncio.wait_for` timeout wrapper** around LiteLLM `acompletion`
  — caps provider hangs. (#297)
- **proxy env vars** inherited into sandbox tmux sessions for
  consistent `HTTP{S}_PROXY` / `NO_PROXY` propagation. (#296)
- **Five `test_initialize_*` mocks** in `test_session_log.py` — cover
  the `_sync_passthrough_env()` calls added by #296. Without this,
  every initialize test raised `StopIteration` under the stricter
  PR gate. (#443)
- **Cross-engagement Neo4j leak**, multiple hardcoded credentials,
  and one `verify=False` regression. (#342)
- Numerous post-#350 audit fixes — semgrep rule exclusions, GHAS
  findings, basedpyright `Optional` guards, codex token leak,
  JWT non-string headers, recording-replay fidelity, reverser
  robustness, RoE FQDN normalization, sandbox token const-time
  comparison, web engagement path traversal, AD BloodHound zipbomb
  stats, others. (#350)

### Security

- **PromptInjectionShield middleware** — agent self-defense against
  prompt injection in tool output. (#342)
- **UntrustedOutputMiddleware** — structural quarantine for tool
  output before it reaches the model. (#342)
- **RoE enforcement + HMAC-chained audit log** — RoE violations are
  rejected at middleware boundary; every dispatch logged with HMAC
  chaining for tamper-evidence. (#342)
- **Per-engagement Neo4j scoping** — closes the cross-engagement leak
  where one engagement's KG findings were visible to another. (#342)
- **Sandbox minimum-cap hardening** — drops unnecessary Linux
  capabilities from the sandbox container by default. (#342)
- **18-tool static-analysis CI** — bandit, Semgrep custom rules,
  Trivy, deptry, vulture, refurb, etc. integrated into the PR gate;
  SARIF uploaded to GitHub code scanning. (#343)

### Notes

- All three Python packages (`decepticon-core`, `decepticon`,
  `decepticon-sdk`) release in lockstep at `1.1.4`.
- `decepticon-core` and `decepticon-sdk` surface (the public
  plugin-author contract) is unchanged in this release. All additions
  land in `decepticon` (the framework).
- Pre-1.0 cleanup mode continues — see the design spec at
  `docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md`
  for the rationale.

## [1.1.3] — 2026-05-27

Consolidation release on top of `v1.1.2` (the core/framework/sdk split).
Lands a backlog of contributor PRs across skills, cross-OS support,
reverse engineering, CLI/launcher, web dashboard, vulnresearch, runtime
stability, and CI — each re-reviewed and re-merged on current `main` with
conflicts resolved and dead code dropped. The OSS default runtime,
public API, and three-package layout are unchanged; every change is
additive or a fix.

### Added

- **Native Windows support** — `scripts/install.ps1` PowerShell installer
  (StrictMode, SHA-256 verification, Docker pre-flight); the Go launcher
  gains an OS/arch/distro + Docker-readiness System Check at `onboard`;
  release artifacts now include `windows_amd64` + `windows_arm64`. README +
  setup guide document the native path alongside WSL2. (#281)
- **Podman + nerdctl container runtimes** — the launcher auto-detects
  docker → podman → nerdctl (first reachable wins) with a
  `DECEPTICON_CONTAINER_RUNTIME` override; Podman socket discovery injects
  `DOCKER_HOST` so nested Docker-API consumers keep working. Docker users
  see zero behavioral change. (#292)
- **Ghidra 12.1 reverse-engineering backend** — `decepticon/tools/reversing/ghidra.py`
  (headless `analyzeHeadless` + optional MCP-bridge sidecar): `ghidra_analyze`,
  `ghidra_decompile`, `ghidra_xrefs`, `ghidra_status`. Gated behind
  `INSTALL_REVERSING=false` so the default sandbox image stays lean; the
  `ghidra-mcp` sidecar opts in via the `reversing` compose profile. (#288)
- **76 new skill playbooks** across two batches, all under the canonical
  `<skill-name>/SKILL.md` layout with `metadata.when_to_use` routing:
  - AD (ADCS ESC1/coercer/ntlm-relay/dcsync/kerberoasting/LAPS/netexec…),
    Cloud (IMDS/k8s/S3/Terraform + container escapes), Smart Contracts
    (access-control/flash-loan/oracle/signature-replay/proxy + bridge/
    governance/MEV), Web Exploit (jwt/oauth/saml/nosqli/…), LLM Red Team
    (AATMF T01–T15, under `plugins/`), Mobile, Reverser, Supply Chain. (#281, #291)
  - Modern API (gRPC/SOAP/WebSocket/SSE), ICS-OT (Modbus/BACnet/S7Comm/DNP3,
    with SAFETY-CRITICAL write-scope confirmation), C2 (Havoc/Mythic). (#291)
- **AD attack tooling** — new `delegation.py` (unconstrained/constrained/RBCD),
  `gpo.py` (GPO ACL abuse), `shadow_creds.py` (msDS-KeyCredentialLink);
  BloodHound-CE ingest format; `dcsync` multi-domain; kerberos AES128
  pre-auth pattern. (#290)
- **Web `@tool` surface** — `http_request` / `http_history` exposed to the
  agent; graphql IDOR heuristic; OAuth state-length + PKCE-downgrade checks. (#290)
- **Release scaffolding** — `RELEASE.md` documenting the 0.0.0-sentinel +
  tag-time version stamping flow; the Soundwave engagement bundle and its
  docs aligned to the full 8-document output. (#287)

### Fixed

- **Soundwave interview loop** — the picker's `" (Recommended)"` UI marker
  leaked into the agent's tool-result, so the model treated it as part of
  the engagement name, rejected it, and re-asked the same question forever.
  `ask_user_question` now strips the trailing marker on the agent-visible
  return (single + multi-select), leaving the picker UI unchanged. (#339, issue #328)
- **Codex/ChatGPT OAuth handler** dropped function names mid-stream
  (synthesized `function_call` had `name=""`, looping the model with
  "is not a valid tool") — added `response.output_item.added/.done`
  handlers. Fixes the empty-tool-name error reported in #321. (#295)
- **Streaming**: `StreamingRunnable` now subclasses `RunnableBinding` so it
  survives deepagents' `_get_subagents()` `.with_config()` call — the
  LangGraph Platform HTTP `stream_mode=["custom"]` path now delivers
  `subagent_*` events (was 0). (#324)
- **Sandbox zombie processes** — reparented `tmux`/`bash` grandchildren
  accumulated as `<defunct>` zombies until the PID table filled and
  `fork()` failed (`EAGAIN`). Now reaped by an init process (tini, run as
  PID 1 via `init: true` on the sandbox compose service) plus
  `kill_all_sessions()` on daemon shutdown. An earlier in-process SIGCHLD
  reaper was replaced after it was found to race with the daemon's own
  `subprocess.run` calls and clobber command exit codes to 0. (#336, #340)
- **`langgraph dev` BlockingError** — a sync `httpx` call inside the
  third-party `deepagents` subagent dispatch aborted runs ~85s in. The
  langgraph service now defaults to `--allow-blocking` (downgrades to a
  warning), with `LANGGRAPH_STRICT_ASYNC=1` to restore fatal behavior for
  debugging. Complements #295's structural fix for Decepticon's own sync
  calls. (#333)
- **LiteLLM truncated tool_use** — Claude models had no `max_tokens`, so
  LiteLLM fell back to its 4096 default and cut off 30–50KB report writes.
  Set per-model caps (Opus 4.7 = 128k, Sonnet/Haiku = 64k) across all three
  model groups. (#295)
- **poc.py inverted ZFP logic** — valid findings that demonstrated impact
  were being rejected; sandbox-runner errors now sentinel-prefixed. (#290)
- **CVE lookups**: capped 3 unbounded `httpx.AsyncClient` timeouts (NVD 30s /
  OSV 15s) that caused intermittent false-negatives. (#294)
- **`bash_kill` BlockingError** under `langgraph dev` — `session_log_path()`
  wrapped in `asyncio.to_thread`. **GraphRecursionError** — 7 sub-agents
  bumped 250 → 1000. (#295)
- **Web dashboard (≈16)** — terminal clears on tab switch (resize-to-0 PTY
  corruption), heartbeat pong-timer leak, health API real probe, N+1
  findings fetch, duplicate-name 409, infinite redirect loop, unmount
  guards, O(n²) event accumulation, findings parser CVSS/CWE/MITRE. (#307)
- **CLI Ink TUI** — empty-filter `selectedIndex=-1`, autocomplete dedupe,
  O(1) event push, tilde expansion, synchronous update check, subagent id
  no longer hardcoded. (#285, #307)
- **Silent exception swallows** surfaced to `log.debug` across
  research `_state`/`chain`/`cve` and the prompt compat shim. (#289, #294)
- **Docker startup race** — `sandbox` now waits on `neo4j` via
  `service_healthy` (was `service_started`). **sandbox.pids_limit** 1024 →
  4096 for parallel Go/Rust toolchains. (#307, #295)
- **Local test suite on macOS/Windows** — `posixpath` for virtual workspace
  paths, `pytest -n auto` class-state isolation, `USERPROFILE` alongside
  `HOME` in launcher tests. (#286, #284)

### Changed

- **Skill layout unified** to nested `<skill-name>/SKILL.md` (canonical
  Agent Skills spec) — migrated 23 legacy flat `exploit/web/*.md` +
  `recon/web-recon/*.md` files; 25+ `load_skill()` routing references
  updated. (#291 review follow-up)
- **`prompts/__init__.py`** (533 lines) split into a re-export shim +
  `builder.py` + `registry.py`; `llm/factory.py` and `sandbox_kernel`
  oversized helpers extracted. Public API unchanged. (#289)
- **Retired the dead docker-exec transport** — `_docker_tmux` → `_tmux`,
  `exec_prefix` defaults to `[]`; `HTTPSandbox` → in-container
  `DaemonSandbox` is the only path. (#289 review follow-up)
- **`DECEPTICON_LLM__TIMEOUT`** default 120s → 600s for long Opus
  generations. (#295)

### Dev infrastructure

- **Pre-commit hook gate** — file hygiene + shellcheck + hadolint + typos
  (with a `.typos.toml` allowlist for offensive-security jargon), run on
  every PR via a `pre-commit` CI job. (#293)
- **Tree-wide LF renormalization** — 45 files committed with CRLF brought
  into line with the `.gitattributes` `eol=lf` policy. (#293)
- **CI matrix** — Python lane is ubuntu-only by design (the backend runs in
  the Linux langgraph container); the Go launcher runs ubuntu+macOS+windows;
  PR-time `linux/arm64` Docker smoke build for cli+langgraph. Coverage gate
  raised 30% → 35%. (#284, #292, #318, #310)
- **Repo hygiene** — `skills/_corpus/` ignored, stale `clients/ee/` ignore
  rules removed, internal design specs untracked, `xbow-validation-benchmarks`
  submodule bumped to the buster apt-archive fix. (#282)

## [1.1.2-localfixes.1] — 2026-05-25 (fork — mohamedq9900/Decepticon)

Runtime-stability fork of upstream `v1.1.2` carrying four targeted fixes
that surfaced under sustained engagement load (multi-hour audits, large
report writes, parallel sub-agent fan-out). All changes are minimal and
preserve upstream contracts.

### Fixed

- **`bash_kill` BlockingError under `langgraph dev`** —
  `_sandbox.session_log_path()` was called synchronously inside the
  ASGI event loop, tripping `blockbuster`'s detector with
  `BlockingError: socket.socket.send`. Wrapped in `asyncio.to_thread`
  to match the pattern already used for the surrounding `kill_session`
  call. The CLI previously surfaced this as "An internal error
  occurred" on every successful session kill.
  ([`packages/decepticon/decepticon/tools/bash/bash.py`](packages/decepticon/decepticon/tools/bash/bash.py))

- **`GraphRecursionError: Recursion limit of 250 reached`** —
  bumped `_RECURSION_LIMIT` from `250` to `1000` on seven sub-agents
  that genuinely need deeper graphs for large engagements (recon
  sweeps with many candidates, parallel CVE probes, multi-target
  static analysis): `analyst`, `cloud_hunter`, `contract_auditor`,
  `ad_operator`, `reverser`, `exploiter`, `vulnresearch`. Other
  agents (`recon`, `exploit`, `postexploit`, `soundwave`,
  orchestrator) were already sized at ≥400 and remain unchanged.
  Cap of 1000 was chosen to cover observed worst-case depth without
  unbounded headroom.
  ([`packages/decepticon/decepticon/agents/standard/*.py`,
  `packages/decepticon/decepticon/agents/plugins/*.py`](packages/decepticon/decepticon/agents/))

- **`auth/gpt-*` Codex OAuth handler dropped tool names mid-stream** —
  the streaming handler only processed
  `response.function_call_arguments.delta` events, which carry the
  arguments fragment but NOT the function `name`. Synthesized
  function_calls ended up with `name=""`; on the next turn the model
  saw a history full of mis-named tool_calls and looped re-calling
  the same tool (e.g. `load_skill`) because tool_results couldn't be
  linked back to the original call. Added handlers for
  `response.output_item.added` (primary path, captures `name` +
  `call_id` when the function_call item starts) and
  `response.output_item.done` (defensive backfill for upstream
  variants that emit only `done`).
  ([`config/codex_chatgpt_handler.py`](config/codex_chatgpt_handler.py))

- **LiteLLM truncated `tool_use` JSON mid-`content` field** —
  `litellm_params` for every Claude model omitted `max_tokens`, so
  LiteLLM defaulted Anthropic requests to its 4096-token OpenAI
  fallback. Long `write_file` calls (a typical 30-50 KB markdown
  report ≈ 10-15 K output tokens) were cut off mid-stream and the
  `content` field arrived missing from the parsed tool_use, yielding
  `content: Field required` validation errors. Set `max_tokens`
  explicitly per model to match Claude Code's canonical caps:
  Opus 4.7/4.6 → 128000, Sonnet 4.6 → 64000, Haiku 4.5 → 64000.
  Applied to all three groups (`anthropic/`, `auth/`,
  `openrouter/anthropic/`).
  ([`config/litellm.yaml`](config/litellm.yaml))

### Changed

- **`sandbox.pids_limit`: `1024` → `4096`** — analyst sub-agents that
  drive Go/Rust toolchains in parallel (`gosec` + `cargo` + `semgrep`
  × fan-out) blow through the 1024-pid cgroup cap, then
  `subprocess.run()` in the sandbox FastAPI daemon fails with
  `BlockingIOError: [Errno 11] Resource temporarily unavailable`,
  which the daemon surfaces as HTTP 500 and the CLI prints as "An
  internal error occurred". 4096 has held under multi-hour Cosmos
  and Web3 audits.
  ([`docker-compose.yml`](docker-compose.yml))

- **Default `DECEPTICON_LLM__TIMEOUT`: `120` → `600` (10 min)** —
  with `max_tokens` bumped to 128K (fix above), long Opus generations
  with extended thinking + large tool_use payloads routinely exceed
  120s mid-stream. The langgraph httpx client aborted the connection
  while LiteLLM proxy kept streaming successfully (200 OK in proxy
  logs), surfacing in the CLI as `APITimeoutError: Request timed
  out`. Documented in `.env.example`; defaults pass through via the
  `DECEPTICON_LLM__*` Pydantic settings.
  ([`.env.example`](.env.example))

### Compatibility

- Patches apply on top of upstream `v1.1.2` commit `e1afba6`.
- No API or import surface changed; downstream code that imports
  any of the modified modules works unchanged.
- Reverting any single fix is a one-line revert against this branch.

### Tested against

Fedora 43, Docker 27.x, SELinux permissive. Engagement workload:
sustained multi-hour Cosmos / Web3 / Web2 bug-bounty audits with
parallel sub-agent fan-out, large recon outputs, and 30-50 KB
report writes on `auth/claude-opus-4-7` and `auth/gpt-5.5`.

## [1.1.2] — 2026-05-23

This release introduced the three-package split (additive — every
legacy import path keeps working via compat shims), shipped as
``v1.1.2`` on the OSS series. Removal of
the compat shims, ``PluginBundle`` aggregate shape, and the legacy
``decepticon.agents.middleware_slots.MiddlewareSlot`` re-export is
deferred to ``2.0.0`` (see "Deprecated" table below).

### Added — three-package split (core / framework / sdk)

OSS shifts from a monolithic `decepticon` wheel to three coordinated
wheels. The split exposes a stable contract layer that commercial
products, downstream frameworks, and the community can extend without
touching framework internals. Full design rationale in the
core/framework/sdk split design spec.

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
  `/skills/` default — load-bearing per the split design spec
  §16.4 #5 for the future B2B Enterprise tier.
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
  tool/middleware names (closes gap #10). Additive-only per the split
  design spec §16.4 #4 — plugins cannot remove safety on OSS-declared
  names.
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
