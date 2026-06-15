# 0010. Acquire open-web content with a sandbox-side, RoE-gated fetch engine

- **Status:** Proposed
- **Date:** 2026-06-15
- **Deciders:** @PurpleCHOIms
- **Related:** #593 (Tier-1 open-web search), [ADR-0006](0006-agent-driven-container-lifecycle.md)
  (sandbox/host boundary), the RoE guardrail (`middleware/roe.py`,
  `middleware/egress.py`), `middleware/untrusted_output.py`. Supersedes the
  earlier Scrapling-engine draft (PR #605) and the httpx/DDG `web_search`
  draft (PR #650), both closed.

## Context

The agent needs first-class open-web reach — keyword search (`web_search`) and
URL content acquisition (`web_fetch`) — for OSINT and recon. The hard part is
not fetching; it is fetching **under RoE/network-isolation discipline** while
still getting past the WAF/anti-bot defenses that gate most real targets.

Two forces collide. (1) Real targets sit behind Akamai/Cloudflare/DataDome/F5
etc.; a single `httpx.get` that bails on the first non-200 returns a challenge
page and the agent concludes "blocked" when the content was reachable. The
`fivetaku/insane-search` project (MIT) solves exactly this with a site-agnostic
escalation engine — Verdict-based validation ("HTTP 200 is an inspection-start
condition, not success"), WAF-product detection as a ranking, a
transform×TLS-impersonate×referer grid, and a browser fallback — governed by a
"No-Site-Name" rule that keeps the engine generic. (2) That project's *posture*
is the opposite of ours: anti-allowlist ("try everything"), runtime
auto-install of evasion tooling, in-process browser, raw output to the model,
stealth always on. For a RoE-gated red-team tool every one of those is a
liability — egress must never fire outside engagement scope, the dependency
surface is CODEOWNERS-gated, and fetched bytes are attacker-influenceable.

The invariant that shapes the answer: **the sandbox is the only egress surface,
and the bash tool is the single execution path into it** (no side-channel exec
paths — see CLAUDE.md). Web egress must therefore happen *inside* the sandbox,
behind the nftables/DNS allowlist compiled from `roe.json`, not from the
LangGraph/management process.

## Decision

Adopt an **insane-search-derived fetch engine, shipped inside the sandbox**, and
expose it through two RoE-gated agent tools. We keep insane-search's engine
intelligence and invert its governance.

1. **Engine (`decepticon/sandbox_web/`), runs in the sandbox.** Ported,
   site-agnostic: `validators` (4-layer Verdict), `waf_detector` +
   `waf_profiles.yaml` (ranked WAF-product detection with graceful in-code
   fallback), `url_transforms`, `fetch_chain` (probe → detect → grid →
   browser fallback, recording every attempt in a `trace`), `executor`
   (capability-matched browser tier), and `bias_check` (the No-Site-Name CI
   gate). Site knowledge enters ONLY at runtime via `success_selectors` /
   `user_hint`.

2. **Egress is sandbox-only, reached over the existing bash surface.** The tool
   wrappers run the engine as `python3 -m decepticon.sandbox_web …` through
   `DockerSandbox.execute_tmux()`. No new HTTP route, no side channel. Physical
   egress happens in `sandbox-net` behind the Layer-2 nftables/DNS allowlist.

3. **Double RoE enforcement, fail-closed.** The tool wrapper calls
   `evaluate_target` on the management side before dispatch (fast fail + audit);
   the sandbox edge enforces the allowlist authoritatively. `web_fetch` is
   target-gated; `web_search` is provider-allowlisted and target-exempt (OSINT)
   but audited. Every transformed/redirected hop is re-validated against scope.

4. **No runtime install.** Engine deps (`curl_cffi`, `beautifulsoup4`, `pyyaml`,
   and the optional Playwright tier) are baked into the sandbox image at build
   time. The engine never `pip install`s at runtime.

5. **Untrusted output + default-off stealth.** Both tools are added to
   `UNTRUSTED_TOOL_NAMES` (prompt-injection quarantine). TLS impersonation and
   the browser tier are off by default and opt-in per engagement (mirroring
   `allow_sensitive_tlds`).

## Consequences

- **Easier:** the agent gets past real WAFs without a human; "blocked" becomes a
  last resort after an exhaustive, evidence-traced grid; the `trace` gives OPSEC
  visibility into which bypass path succeeded (an audit asset).
- **Harder:** the sandbox image grows (curl_cffi + optional Playwright); the
  engine must be exercised through the bash surface, so tool tests mock the
  sandbox dispatch and the engine is unit-tested in isolation.
- **Given up:** insane-search's zero-friction posture — no auto-install, no
  unconditional "try everything," no in-process browser. Convenience is traded
  for scope/isolation discipline.
- **Migration:** new package `decepticon/sandbox_web/`; `beautifulsoup4` added to
  the framework install set (sandbox mounts decepticon, per the FastAPI/uvicorn
  precedent); `containers/sandbox` gains the engine deps; `web_search`/`web_fetch`
  added to `GATED_TOOL_NAMES`, `NETWORK_TARGET_EXTRACTORS`, and
  `UNTRUSTED_TOOL_NAMES`; `bias_check` wired as a CI gate. No change to existing
  tools.

## Alternatives considered

- **Scrapling engine, light core in-process + browser in sandbox** (the original
  #605 draft). Rejected: splits egress across the management and sandbox
  processes, weakening the single-egress-surface invariant; and Scrapling's
  value (stealth fetchers) is the part we most need to gate, not the part we most
  need in-process.
- **httpx + regex DDG `web_search` only** (the #650 draft). Rejected: no WAF
  escalation (bails on first challenge), and its RoE gate read a non-existent env
  var so filtering/audit were inert in production.
- **All egress agent-side (curl light, browser later)** — the maintainer
  considered and rejected this in favor of sandbox-only egress for strict
  network isolation.
- **A new sandbox HTTP route for web fetch.** Rejected: it is a side-channel exec
  path, which CLAUDE.md forbids; the bash surface already reaches the sandbox.
