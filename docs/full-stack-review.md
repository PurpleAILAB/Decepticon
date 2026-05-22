# Decepticon Full-Stack Review — Web + AD + Vulnresearch + DreadGOAD Readiness

Reviewed: 2026-05-22  
Scope: 8 layers, ~60 source files, all skills, all prompts

---

## Executive Summary

Decepticon's architecture is sound — the slot-based middleware stack, fresh-context sub-agent model, and knowledge-graph-backed state flow are well-engineered. The framework successfully runs the basic red-team pipeline (recon → exploit → post-exploit) for web targets.

However, the AD attack surface has critical gaps, the vulnresearch pipeline has a logic bug in its core ZFP verification, and several agent prompts reference tools that don't exist in their toolsets. The framework is not DreadGOAD-ready today — it would stall on delegation attacks, ADCS ESC2+, GPO abuse, and RBCD, all of which DreadGOAD deploys as intentional vulnerabilities.

**Finding count: 7 Critical, 14 High, 18 Medium, 12 Low**

---

## Critical Findings (Must Fix)

### C1. ZFP logic bug rejects valid findings — `poc.py:249`

```python
validated = bool(success) and not neg_hits
```

`neg_hits` is "negative patterns matched the negative control output." When the negative control *works correctly* (baseline behaves normally), `neg_hits` is non-empty — which is the **expected** good state. But the code treats it as a disqualifier, rejecting the finding.

**Impact**: Any finding that follows the full ZFP protocol (provides both negative_command + negative_patterns as instructed by the verifier skill) will ALWAYS be rejected. The only way to get `validated=True` is to omit negative patterns, which defeats ZFP.

**Fix**: `validated = bool(success) and bool(neg_hits)` — require success AND a working negative control.

### C2. ADCS docstring falsely claims ESC9-15 coverage — `adcs.py:1-20`

The module docstring lists ESC9, ESC10, ESC11, ESC13, ESC14, ESC15 as covered. Zero code implements any of them. `_template_analysis` handles ESC1-4; `_ca_analysis` handles ESC6-8. That's 7 checks, not 15.

**Impact**: Operators relying on `adcs_audit` believe they're scanning for 15 ESC classes. They're scanning for 7. ESC9/10 (weak certificate mapping) and ESC11 (ICPR relay) are actively exploited in the wild.

### C3. ad_operator prompt references phantom tools — `ad_operator.md:13,39,47`

- Line 13: `plan_attack_chains with crown_jewel=Domain Admins`
- Line 39: `crown_jewel(DA)` 
- Line 47: `plan_attack_chains()` 

`plan_attack_chains` exists in `tools/research/tools.py` but is NOT imported in `ad_operator.py`'s `_STANDARD_TOOLS`. `crown_jewel` does not exist as a tool anywhere. The agent will attempt to call these, get tool-not-found errors, and waste inference turns.

### C4. 6 dangling AD sub-skill references — `skills/standard/ad/SKILL.md`

The AD overview skill references 6 sub-skill paths:
- `/skills/standard/ad/bloodhound-query/SKILL.md`
- `/skills/standard/ad/kerberoasting/SKILL.md`
- `/skills/standard/ad/asrep-roasting/SKILL.md`
- `/skills/standard/ad/adcs-esc1/SKILL.md`
- `/skills/standard/ad/dcsync/SKILL.md`
- `/skills/standard/ad/laps/SKILL.md`

**None exist.** The `skills/standard/ad/` directory contains only `SKILL.md`. When the agent tries `load_skill()` on any of these paths, it will get an error or empty content.

### C5. Vulnresearch orchestrator missing EngagementContext — `middleware_slots.py:186`

```python
"vulnresearch": _BASE_SLOTS | {MiddlewareSlot.SUBAGENT, MiddlewareSlot.OPPLAN},
```

EngagementContext is a `SAFETY_CRITICAL_SLOT` that carries RoE constraints. The vulnresearch orchestrator omits it. If run standalone (not under the main decepticon orchestrator), there are zero scope/RoE guardrails — the pipeline can target any host without restriction.

### C6. Global sandbox race — `set_sandbox()` across agents

`set_sandbox()` is a module-level setter in `tools/bash/bash.py`. When multiple agents are constructed in the same process, the last one wins. All bash tools across all agents point to the last-constructed sandbox. This is a hidden shared-state bug.

### C7. sandbox_runner swallows all exceptions — `poc.py:341-342`

```python
except Exception as e:  # pragma: no cover
    return "", str(e), -1
```

Any sandbox failure (connection refused, OOM, auth error) is silently converted to `("", error_string, -1)`. If the error string happens to match a success pattern regex, `validate_poc` produces a **false positive** on a crash. The `# pragma: no cover` confirms this path is never tested.

---

## High Findings

### H1. No HTTP request tool exposed — `tools/web/tools.py`

`HTTPSession` exists in `http.py` (async httpx wrapper with cookie jar, history recording, response diffing) but has NO `@tool` wrapper. The agent cannot make HTTP requests through the web tool suite. It must fall back to bash/curl, losing all the request history, cookie tracking, and response analysis the module provides.

### H2. No connection error handling in HTTPSandbox — `backends/http_sandbox.py`

All HTTP methods propagate raw `httpx.ConnectError` / `httpx.HTTPStatusError` when the sandbox daemon is down. No retry, no reconnect, no health check, no graceful degradation. A container restart crashes every in-flight tool call.

### H3. Contradictory retry rules in orchestrator prompt — `decepticon.md`

Section D header: "Same-prompt re-dispatch is FORBIDDEN in every mode."  
Section D INFRA fault row: "Retry SAME sub-agent ONCE with SAME prompt."

These directly contradict. The agent will either follow the header (never retry → stall on transient infra faults) or the table (retry once → violate the header). 

### H4. No OPSEC enforcement at middleware level — `opplan.py`, `engagement.py`

The `opsec` field on objectives is injected as informational text. No middleware guard prevents noisy operations, no rate limiting exists, no tool-call filtering based on OPSEC level. All constraints are prompt-only. A confused LLM can run responder/nmap full-port-scan on a `silent` objective.

### H5. ClassVar `_jobs` shared across HTTPSandbox instances — `http_sandbox.py:~80`

`_jobs: ClassVar[BackgroundJobTracker]` is class-level. All HTTPSandbox instances share the same tracker. In multi-instance scenarios (tests, multi-tenant), job IDs collide.

### H6. No fallback = hard crash when primary LLM fails

When `fallback_models` is empty/None, `_make_model_fallback()` returns None and the slot is skipped entirely. If the primary LLM provider goes down, there's no fallback — the agent crashes rather than gracefully degrading.

### H7. `_load()`/`_save()` pattern is not exception-safe — `tools/research/tools.py`

Every research tool follows `graph = _load(); mutate; _save(graph)` with no try/finally. A crash between load and save leaves the graph inconsistent — the PoC was run (side effects on sandbox) but the result wasn't recorded.

### H8. OAuth state length check — `oauth.py:107`

Flags state < 8 chars citing "128-bit equivalent" from RFC 6819. 8 hex chars = 32 bits, not 128. Threshold should be ~32 chars for hex-encoded 128-bit values. This is a logic bug that makes the check 16x too lenient.

### H9. Pipeline preconditions enforced by prompt only — `vulnresearch.py`

Scanner→detector→verifier→patcher→exploiter ordering is prompt-instructed, not code-enforced. The orchestrator has `kg_query` and `kg_stats` but no code-level gate. A hallucinating LLM can dispatch stages out of order.

### H10. BloodHound CE format not supported — `bloodhound.py`

Only legacy SharpHound JSON is handled. BloodHound CE (v5+) uses a different schema (`kind` instead of `meta.type`, different property names, JSONL format). Modern BH deployments will produce unparseable data.

### H11. `bh_ingest_json` doesn't catch ValueError — `tools/ad/tools.py`

`merge_bloodhound_json` raises `ValueError` on malformed data. The tool wrapper only catches `OSError`. Any bad JSON structure crashes the tool.

### H12. No BloodHound/SharpHound ingester in vulnresearch pipeline

The research tools include ingesters for nmap, nuclei, subfinder, httpx, etc. but NOT for BloodHound data. The chain planner cannot model AD privilege escalation paths.

### H13. Quadratic index rebuild in ZIP ingestion — `bloodhound.py`

`_build_bh_index` does O(n) scan of all graph nodes. Called once per JSON file inside a ZIP. For a large domain (100k+ objects), this is O(n×f). The index should be built once and passed through.

### H14. OPPLAN parallel rejection wastes inference turns — `opplan.py`

When the agent issues >1 OPPLAN tool call in one message, ALL are rejected (including the first valid one) with "re-issue one at a time." This wastes an entire model step.

---

## Medium Findings

| # | Location | Finding |
|---|----------|---------|
| M1 | `adcs.py` | ESC3 check flags any template with Enrollment Agent EKU regardless of enrollment rights |
| M2 | `adcs.py` | ESC7 doesn't distinguish ManageCA vs ManageCertificates |
| M3 | `bloodhound.py` | GPO/OU collapsed to NodeKind.GROUP — loses GPO-specific abuse paths |
| M4 | `bloodhound.py` | Unknown ACE principals default to NodeKind.USER (~30-40% are wrong) |
| M5 | `bloodhound.py` | Silent skip on malformed ACEs with no logging |
| M6 | `dcsync.py` | No target domain filtering — GetChanges+GetChangesAll on child domain treated same as forest root |
| M7 | `kerberos.py` | .kirbi parsing is a stub — returns "use Rubeus" with zero ASN.1 analysis |
| M8 | `oauth.py:148` | `code_verifier` variable reads `code_challenge` — misleading name |
| M9 | `session.py` | `_try_jwt` duplicates JWT detection instead of calling `parse_token` |
| M10 | `graphql.py:195` | IDOR heuristic matches any arg ending in "id" — false positives on `valid`, `uuid`, `android` |
| M11 | `graphql.py` | `from_introspection` silently returns empty schema when introspection is disabled |
| M12 | `_state.py` | No transaction isolation — concurrent scanner shards can lose mutations |
| M13 | `_state.py` | Full graph loaded from Neo4j on every tool call — no delta tracking, no caching |
| M14 | `patch.py` | `patch_verify` has no negative control — can't distinguish "fixed" from "crashed endpoint" |
| M15 | `scanner_tools.py` | No XXE scanner pattern despite detector having XXE playbook |
| M16 | `notifications.py` | `_build_message` makes sync HTTP calls from async `abefore_model` path |
| M17 | `skills.py` | `_read_workflow_for_source` swallows ALL exceptions with bare `except Exception: return None` — no logging |
| M18 | `filesystem.py` | `download_files` fails all paths if one is invalid |

---

## AD Attack Technique Coverage Matrix

| Technique | Tool Support | Skill Coverage | Prompt Coverage | DreadGOAD Deploys It? | Status |
|-----------|-------------|----------------|-----------------|----------------------|--------|
| BloodHound ingest | `bh_ingest_zip/json` | ✅ | ✅ | ✅ | **Ready** |
| Kerberoasting | `kerberos_classify` + bash | ✅ | ✅ | ✅ | **Ready** |
| AS-REP Roasting | `kg_ingest_asrep_hashes` + bash | ✅ | ✅ | ✅ | **Ready** |
| DCSync | `dcsync_check` + bash | ✅ | ✅ | ✅ | **Ready** |
| ADCS ESC1 | `adcs_audit` | ✅ | ✅ | ✅ | **Ready** |
| ADCS ESC2-4, ESC6-8 | `adcs_audit` | ❌ no procedures | ✅ | ✅ | **Partial — tool works, no skill guidance** |
| ADCS ESC9-15 | ❌ falsely claimed | ❌ | ❌ | Some | **Not supported** |
| Constrained Delegation | ❌ | ⚠️ mentioned | ❌ | ✅ | **Will stall** |
| Unconstrained Delegation | ❌ | ❌ | ❌ | ✅ | **Will stall** |
| RBCD | ❌ | ❌ | ❌ | ✅ | **Will stall** |
| Shadow Credentials | ❌ | ❌ | ❌ | Likely | **Will stall** |
| GPO Abuse | ❌ | ❌ | ❌ | ✅ | **Will stall** |
| LAPS Extraction | bash only | ⚠️ dangling ref | ✅ | ✅ | **Bash-only, no skill** |
| gMSA Extraction | bash only | ❌ | ⚠️ | Likely | **Bash-only, no guidance** |
| ACL Abuse (WriteDACL etc.) | ❌ | ❌ | ❌ | ✅ | **Will stall** |
| MSSQL Attacks | bash only | ❌ | ❌ | ✅ | **Will stall** |
| SID History | ❌ | ❌ | ❌ | Unknown | **Not supported** |
| Golden/Silver Ticket | bash only | ❌ | ❌ | N/A | **Bash-only** |
| Pass-the-Ticket | bash only | ⚠️ mapped | ✅ | ✅ | **Bash-only** |
| `plan_attack_chains` | exists but NOT assigned to ad_operator | ✅ in prompt | ✅ | N/A | **Broken — tool not in toolset** |

---

## Web Attack Technique Coverage Matrix

| Technique | Tool Support | Skill Coverage | Scanner Pattern | Status |
|-----------|-------------|----------------|-----------------|--------|
| SQLi | bash + methodology_lookup | ✅ sqli.md + blind-sqli.md | ✅ (0.80) | **Ready** |
| XSS | bash + payload_search | ✅ xss.md | ✅ (0.65) | **Ready** |
| SSRF | bash | ✅ ssrf.md | ✅ (0.55 — low) | **Ready** |
| SSTI | bash | ✅ ssti.md | ✅ (0.70) | **Ready** |
| Command Injection | bash | ✅ command-injection.md | ✅ (0.85) | **Ready** |
| Deserialization | bash | ✅ deserialization.md | ✅ (0.90) | **Ready** |
| JWT Attacks | `jwt_parse/forge/crack` tools | ❌ no sub-skill | ❌ | **Tool exists, no guidance** |
| OAuth Flaws | `oauth_audit` tool | ❌ no sub-skill | ❌ | **Tool exists, no guidance** |
| GraphQL | `graphql_plan` tool | ✅ graphql.md | ❌ | **Ready** |
| IDOR | bash | ✅ idor.md | ❌ | **Ready** |
| File Upload | bash | ✅ file-upload.md | ❌ | **Ready** |
| Race Conditions | bash | ✅ race-condition.md | ❌ | **Ready** |
| XXE | bash | ✅ xxe.md | ❌ scanner pattern | **Skill only, no scanner** |
| HTTP Smuggling | bash | ✅ smuggling.md | ❌ | **Ready** |
| HTTP Requests | ❌ no @tool wrapper | N/A | N/A | **Major gap — HTTPSession exists but agent can't use it** |
| CSRF | ❌ | ❌ | ❌ | **Not supported** |
| WebSocket | ❌ | ❌ | ❌ | **Not supported** |
| CORS Testing | ❌ | ❌ | ❌ | **Not supported** |
| Header Security | ❌ | ❌ | ❌ | **Not supported** |

---

## DreadGOAD Readiness Assessment

DreadGOAD deploys 50+ intentional vulnerabilities across 7 lab variants. The GOAD lab (5 VMs, 2 forests, 3 domains) includes:

### What Decepticon Can Handle Today
- Kerberoasting (SPN users in sevenkingdoms.local, essos.local)
- AS-REP Roasting (dontreqpreauth users)
- BloodHound collection and ingestion
- DCSync (if rights are found)
- ADCS ESC1 (if ESC1 template exists)
- Basic credential spraying via bash/CrackMapExec

### What Will Stall or Miss
- **Delegation attacks**: GOAD deploys constrained delegation, unconstrained delegation, and RBCD. Decepticon has no tools, skills, or prompt guidance for any of these.
- **ADCS ESC2-8**: Tool can audit but no skill procedures guide exploitation.
- **MSSQL attacks**: GOAD deploys xp_cmdshell, linked servers, MSSQL → DA paths. No Decepticon tooling or skills.
- **GPO abuse**: GOAD deploys vulnerable GPOs. No Decepticon support.
- **ACL abuse chains**: GOAD deploys WriteDACL/GenericAll chains. BloodHound data is ingested but `plan_attack_chains` isn't assigned to ad_operator — the chain-finding tool exists but can't be called.
- **Cross-forest trust attacks**: GOAD deploys forest trusts between sevenkingdoms.local and essos.local. No trust-aware tooling.
- **LAPS**: Dangling skill reference, no actual procedure.

### Integration Requirements
1. **No existing DreadGOAD integration** in the Decepticon codebase
2. Decepticon needs: target IP/domain specification in OPPLAN, sandbox network access to the DreadGOAD lab, and initial credentials
3. DreadGOAD provides: `dreadgoad health-check` for lab status, `dreadgoad validate` for vuln verification, and a scoreboard for tracking agent progress
4. The variant generator randomizes entity names — Decepticon's tools are name-agnostic (good), but skills with hardcoded domain examples would need adjustment

---

## Recommended Fix Priority

### Phase 1 — Critical Bugs (blocks correctness)
1. Fix ZFP logic in `poc.py:249`: `not neg_hits` → `bool(neg_hits)`
2. Fix ad_operator toolset: add `plan_attack_chains`, `suggest_objectives_from_chains` to `_STANDARD_TOOLS`
3. Remove phantom `crown_jewel()` from ad_operator prompt
4. Create the 6 missing AD sub-skills or update the overview skill to remove dangling refs
5. Fix ADCS docstring: replace "ESC1-ESC15" with "ESC1-4, ESC6-8"
6. Add EngagementContext to vulnresearch orchestrator middleware slots
7. Add try/except to `sandbox_runner` that doesn't match success patterns

### Phase 2 — AD Coverage (blocks DreadGOAD)
8. Implement ESC9/10/11/13 checks in `adcs.py`
9. Add delegation analysis tools (constrained/unconstrained/RBCD from BH data)
10. Add GPO abuse detection (from BH GPO/GPLink edges)
11. Add Shadow Credentials detection (AddKeyCredentialLink edge)
12. Create AD sub-skills with procedures: delegation, RBCD, GPO abuse, LAPS, gMSA
13. Add BloodHound CE format support to `bloodhound.py`
14. Fix `_node_kind_for_bh` to preserve GPO/OU type information

### Phase 3 — Web Gaps
15. Add `@tool` wrapper for HTTPSession (HTTP requests)
16. Create JWT and OAuth sub-skills
17. Add XXE scanner pattern
18. Fix OAuth state length check (8 → 32 chars)
19. Deduplicate `shannon_entropy` implementations
20. Add error handling to web tool wrappers (`jwt_parse`, `jwt_crack`)

### Phase 4 — Infrastructure
21. Fix `set_sandbox()` global state — make per-agent or use contextvars
22. Add connection retry logic to HTTPSandbox
23. Fix `_build_bh_index` quadratic cost in ZIP ingestion
24. Add exception safety (try/finally) around `_load()`/`_save()` pattern
25. Fix OPPLAN parallel rejection to allow the first call
26. Add `BadZipFile` handling to `bh_ingest_zip`

### Phase 5 — DreadGOAD Integration
27. Build DreadGOAD target specification (IP ranges, domains, initial creds → OPPLAN)
28. Add MSSQL attack tools/skills
29. Add cross-forest trust analysis
30. Add DreadGOAD scoreboard integration for progress tracking
31. Run continuous attack scenarios and trace failures to specific layers
