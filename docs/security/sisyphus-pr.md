# Sisyphus PR — security hardening + Offensive Vaccine completion

> Massive PR addressing all six tiers from the gap analysis:
> prompt-injection defense, RoE audit log, per-engagement Neo4j
> scoping, sandbox hardening, three new specialist agents, and the
> Blue Cell runtime that closes the Offensive Vaccine loop.

## Commits (in order)

| # | Commit | Lines | Files | Tests |
|---|--------|-------|-------|-------|
| 1 | chore: local CRLF normalization (prep) | — | 45 | — |
| 2 | feat(neo4j): allowlist-only APOC + client-side safety guard | +570 | 6 | +31 |
| 3 | feat(safety): UntrustedOutputMiddleware | +1138 | 7 | +38 |
| 4 | feat(safety): RoE enforcement + HMAC-chained audit log | +1329 | 8 | +40 |
| 5 | fix(security): cross-engagement Neo4j leak + hardcoded creds + verify=False | +94 | 3 | — |
| 6 | feat(neo4j): per-engagement scoping + Decepticon self-threat-model | +487 | 5 | +33 |
| 7 | feat(sandbox): minimum-cap hardening + per-engagement isolation design | +280 | 2 | — |
| 8 | feat(agents): add Phisher, MobileOperator, WirelessOperator | +1148 | 15 | — |
| 9 | feat(blue_cell): runtime Offensive Vaccine loop — tap + Sigma matcher | +976 | 7 | +12 |
| **Total** | | **+6022** | **53 changed** | **+154** |

## What this PR delivers, by tier

### Tier 4a — Neo4j APOC hardening (commit 2)

Removes the dual-homed-Neo4j sandbox→management exfil path. Replaces
`NEO4J_dbms_security_procedures_unrestricted: apoc.*` +
`apoc_export_file_enabled` + `apoc_import_file_enabled` with an
explicit allowlist of safe APOC procedures. File-I/O, runFile, system-db
reach, and trigger procedures are unreachable.

Plus a client-side `_apoc_safety.ensure_safe()` belt-and-braces check
that rejects banned procedures in any Cypher string before it reaches
the driver, with a no-overlap invariant test ensuring allowlist and
denylist can't both contain the same procedure.

Plus a latent Cypher-injection bug fix in `Neo4jStore.query_by_kind`:
the fallback `label = kind if kind in _ALL_NODE_LABELS else kind`
interpolated caller-supplied labels into the Cypher template. Now
raises `ValueError` on unknown kinds.

[docs/security/neo4j-hardening.md](./neo4j-hardening.md)

### Tier 1 — Prompt-injection defense (commit 3)

`UntrustedOutputMiddleware`: structurally quarantines every byte the
agent reads from the network or workspace.

- `<UNTRUSTED_TOOL_OUTPUT origin="bash" tool_call_id="..." risk="..." categories="...">`
  envelope around every result from `bash`, `bash_output`, `bash_kill`,
  `bash_status`, `read_file`, `kg_query`, `kg_neighbors`, `kg_stats`,
  `kg_backend_health`.
- 21 regex patterns across 8 categories detect known injection
  payloads (instruction-override, role-hijack, tool-call-hijack,
  exfil-markdown, system-prompt-leak, cypher-injection,
  shell-injection-hint, invisible-text). Risk tag promotes to `high`
  when two+ matches or any tool-call-hijack / cypher-injection /
  exfil-markdown match.
- Static system-prompt policy block (Anthropic prompt-cached) tells
  the model to treat envelope content as DATA, not COMMANDS.
- Optional JSONL quarantine ledger when `DECEPTICON_QUARANTINE_LEDGER`
  is set: every `risk="high"` event appended with SHA-256 fingerprint,
  match excerpts, and engagement context.

[docs/security/prompt-injection-defense.md](./prompt-injection-defense.md)

### Tier 2 — RoE enforcement + tamper-evident audit (commit 4)

Three new building blocks:

1. **`decepticon_core.types.roe.MachineEnforcement`** — optional
   `machine_enforcement` block in `roe.json`. Three modes: audit
   (default, log only), warn (log + warn the model), enforce (block
   the call). Scope rules accept CIDRs, domain globs, literal IPs,
   literal hostnames. Cloud-metadata endpoints
   (169.254.169.254 / metadata.google.internal / metadata.azure.com /
   100.100.100.200 / fd00:ec2::254) denied by default. Custom
   forbidden_command_patterns are regex.

2. **`decepticon.middleware._command_targets.extract_targets`** —
   best-effort target extraction for nmap, masscan, rustscan, naabu,
   ssh, scp, sftp, impacket-*, plus generic IP/CIDR/URL/hostname
   scraping. Feeds the evaluator.

3. **`decepticon.middleware._audit_sink.RoEAuditSink`** —
   append-only JSONL ledger with SHA-256 chain + optional HMAC
   binding to operator-held secret. `verify_ledger()` detects
   tampering at the first bad sequence number. Hot-reload safe.

The `RoEEnforcementMiddleware` (new safety-critical slot
`ROE_ENFORCEMENT`, position 2 after `ENGAGEMENT_CONTEXT`) chains them:

```
tool call -> read plan/roe.json:machine_enforcement
          -> evaluate command + extracted targets
          -> append decision to audit ledger
          -> in enforce mode: short-circuit refused calls with
             [ROE_REFUSED] ToolMessage
             in warn mode: prepend [ROE_WARN] to original output
             in audit mode: just log
```

### Security fix commit (commit 5) — gap-audit findings

The background gap-audit agent surfaced three critical bugs unrelated
to the six tiers but discovered during the audit pass:

1. `clients/web/src/app/api/engagements/[id]/graph/route.ts` ignored
   the engagement id and returned the full Neo4j graph. Cross-tenant
   data leak. Fixed: Prisma ownership check + scoped Cypher with
   `WHERE n.engagement = $engagement`.
2. Same file fell back to the public default Neo4j password
   `decepticon-graph`. Now refuses to query.
3. `clients/web/src/app/api/health/route.ts` hardcoded
   `LITELLM_API_KEY = "sk-decepticon-master"` AND faked Neo4j /
   Postgres "ok" without probing them. Now actually probes both;
   refuses LiteLLM check without explicit env.
4. `packages/decepticon/decepticon/tools/web/tools.py` initialized
   the global HTTP session with `verify=False`. Now defaults to ON;
   CTF runs opt out via `DECEPTICON_HTTP_VERIFY_TLS=true`.

### Tier 4b — Per-engagement Neo4j scoping + Decepticon self-threat-model (commit 6)

`decepticon.tools.research._engagement_scope`: context-var based
active-engagement getter/setter. `EngagementContextMiddleware`
propagates `engagement_name` from `config.configurable` into the
contextvar during `before_agent`. Neo4j upsert paths
(`upsert_node`, `upsert_edge`, `batch_upsert_nodes`,
`batch_upsert_edges`) auto-inject `n.engagement` / `r.engagement` on
every write. The web `engagements/[id]/graph` route's
`WHERE n.engagement = $engagement` filter now returns real data
instead of empty.

[docs/security/decepticon-threat-model.md](./decepticon-threat-model.md) —
full STRIDE walk: three trust planes, four bridges, per-asset tables
covering Neo4j, LiteLLM, Sandbox, LangGraph, Web dashboard, Plugin
author surface. Five highest-impact compromise chains ranked by
realistic damage.

### Tier 3 — Sandbox capability hardening + isolation design (commit 7)

`docker-compose.yml`'s sandbox service:

- `cap_drop: [ALL]` + minimum `cap_add` set (NET_RAW, NET_ADMIN,
  NET_BIND_SERVICE, SYS_PTRACE, SETUID, SETGID, CHOWN, DAC_OVERRIDE,
  FOWNER, KILL). Removes ~25 default Docker capabilities.
- `security_opt: [no-new-privileges:true]` — blocks setuid escalation
  within the container.
- `mem_limit: 4g` — caps a runaway fuzzer at 4 GiB.

[docs/security/sandbox-isolation.md](./sandbox-isolation.md) documents
the per-engagement-container design (named
`decepticon-sandbox-<slug>`, per-engagement Docker network,
per-acquire SANDBOX_TOKEN rotation, archive-on-release lifecycle)
with a working Go skeleton for `clients/launcher/internal/sandbox.Lifecycle`.

### Tier 5 — Three new specialist agents (commit 8)

| Agent | Role | Priority | Tier |
|-------|------|----------|------|
| Phisher | `phisher` | 15 (early) | MID |
| MobileOperator | `mobile_operator` | 55 | MID |
| WirelessOperator | `wireless_operator` | 85 | LOW |

Each ships with:
- Factory file under `agents/standard/<role>.py`
- System prompt under `agents/prompts/standard/<role>.md`
- `SUBAGENT_SPEC` + entry-point registration
- Workflow + at least one core skill (Phisher: lure-deconfliction,
  Wireless: wpa2-psk; Mobile builds on the pre-existing
  `skills/standard/mobile/`)

The Phisher prompt **mandates a lure-deconfliction handshake** with
the blue-team contact in `plan/roe.json` BEFORE any campaign sends —
the legal coverage that makes paid phishing engagements possible.

### Tier 6 — Blue Cell runtime (commit 9)

`decepticon.blue_cell` package:

- `BlueCellTap` — tails `/workspace/.sessions/*.log` + optional
  target sidecar telemetry; yields normalized `TapEvent` objects.
- `RuleMatcher` — Sigma-flavored matcher with substring/regex
  field patterns + boolean condition (and/or/not over named
  selections). Two rule formats (simple `match` + multi-selection
  `condition`).
- `score_mttd()` — time-to-detect in seconds.
- 10 baseline rules covering Kerberoast, AS-REP roast, DCSync,
  Pass-the-Hash, web shell drop, PowerShell download cradle,
  password spray, aggressive nmap, mimikatz, curl-piped-to-bash.

[docs/features/blue-cell.md](../features/blue-cell.md) walks the
architecture, the rule schema, the knowledge-graph integration
(`DetectionFired` node + `DETECTED`/`USES_RULE` edges), the
adaptive-feedback loop spec, and the Defense Brief format.

## What this PR does NOT ship (tracked for follow-up)

Each tier has explicit follow-up tracking in its corresponding doc.
The most consequential omissions:

- **Per-engagement sandbox spawn** — Go code in `clients/launcher/internal/sandbox/`. Designed in Tier 3, not implemented.
- **Per-engagement Cypher user** — separate `decepticon-sandbox-<slug>` Cypher user with rotating Bolt token. Designed in Tier 4b threat model, not implemented.
- **Blue Cell agent factory + orchestrator feedback hook** — the read-only `create_blue_cell_agent()` + the orchestrator's pre-iteration hook reading recent `DetectionFired` events. Designed in Tier 6, not implemented.
- **Per-engagement budget cap** — model-tier spend tracking + auto-downgrade. Documented in Tier 4 threat model, not implemented.
- **Phisher / Mobile / Wireless tool modules** — the gophish API wrapper, evilginx2 controller, frida controller, adb wrapper, airmon-ng wrapper. Tier 5 ships agents using bash-only for maximum portability; SDK wrappers come per-domain.
- **pysigma loader for Blue Cell** — full Sigma compatibility instead of the bootstrap regex matcher.
- **Compose profiles** — `phisher` (gophish + evilginx2 sidecar), `mobile` (Android emulator), `wireless` (USB passthrough).
- **Migration helper** for legacy Neo4j nodes without the `engagement` property. Current behavior: legacy nodes show as `_legacy` engagement until migrated.

## Test summary

154 new tests across the PR. 142 pre-existing tests still pass (zero
regressions). Total `pytest` count in changed test directories: 296
passing.

Test breakdown by tier:

| Tier | New tests | What they cover |
|------|-----------|-----------------|
| 4a | 31 | APOC allowlist + denylist + no-overlap invariant + case-insensitive matching + multi-violation reporting + safety-error contract |
| 1 | 38 | 21 detector patterns + envelope wrapping (low/high/non-tool-message/tool-call-id/truncation) + system-prompt injection + quarantine ledger + slot registration |
| 2 | 40 | MachineEnforcement schema + scope evaluation + command evaluation + target extraction (8 tool-specific + 4 generic) + audit sink (append/chain/tamper/HMAC/hydration) + middleware (audit/enforce/warn/ungated/missing-RoE/records) + slot registration |
| 4b | 33 | Engagement label validation + contextvar set/get/reset + env fallback + override semantics + Neo4j Cypher source-level shape invariants |
| 6 | 12 | Rule compilation (substring/regex/no-match) + boolean conditions (and/or/not) + MTTD scoring + rule loading (JSONL/dir) + end-to-end kerberoast detection |

## Risk and roll-back

Every tier is gated by an env var or RoE field so deployers can
re-enable prior behavior:

| Tier | Roll-back |
|------|-----------|
| 4a APOC | Revert the compose env block; the client-side check stays as defense-in-depth |
| 1 prompt-injection | Set `DECEPTICON_ALLOW_SAFETY_OVERRIDES=1` + disable the slot via PluginBundle |
| 2 RoE | Omit `machine_enforcement` block from `roe.json` (defaults to audit-only, zero behavior change) |
| 4b engagement scope | Roll back the upsert patches; the read-side filter degrades to empty result (operator notices immediately) |
| 3 sandbox caps | Revert the compose block (re-adds default caps) |
| 5 new agents | The agents are entry-point registered; uninstall the package OR set `DECEPTICON_PLUGINS` to exclude `standard` |
| 6 Blue Cell | The package is import-only with no auto-wiring; nothing changes until the follow-up agent factory ships |

## Reviewer checklist

- [ ] Read [docs/security/sisyphus-pr.md](./sisyphus-pr.md) (this file).
- [ ] Run `pytest packages/decepticon/tests/unit/research/ packages/decepticon/tests/unit/middleware/test_roe.py packages/decepticon/tests/unit/middleware/test_untrusted_output.py packages/decepticon/tests/unit/blue_cell/` — expect 296 pass, 0 fail.
- [ ] Verify Tier 4a hardening: `docker compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "CALL apoc.cypher.runFile('file:///etc/passwd')"` should fail.
- [ ] Verify Tier 3 sandbox hardening: `docker exec decepticon-sandbox cat /proc/1/status | grep CapEff` should show a tiny set, NOT 0x000001ffffffffff.
- [ ] Verify Tier 5 agents: `python -c "from decepticon_core.contracts.slots import SLOTS_PER_ROLE; print('phisher' in SLOTS_PER_ROLE, 'mobile_operator' in SLOTS_PER_ROLE, 'wireless_operator' in SLOTS_PER_ROLE)"` should print `True True True`.
- [ ] Check that `clients/web/src/app/api/engagements/[id]/graph/route.ts` no longer falls back to public default password.
- [ ] Confirm `docs/security/decepticon-threat-model.md` accurately describes the deployment.
