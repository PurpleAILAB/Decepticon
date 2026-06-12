# 0010. Acquire open-web content via Scrapling, behind RoE-gated tools

- **Status:** Proposed
- **Date:** 2026-06-05 (renumbered 0008 → 0010 on 2026-06-06: this draft sat
  while #614's skillogy-ACL ADR took 0008 and #610's HITL ADR took 0009 — per
  the README lifecycle rule, the sitting draft renumbers)
- **Deciders:** @PurpleCHOIms
- **Related:** #593 (roadmap — open-web `web_search` Tier-1 item), ADR-0006
  (agent-driven container lifecycle), ADR-0008 (skillogy hard ACL, #614 — took
  the 0008 slot), [Scrapling](https://github.com/D4Vinci/Scrapling),
  [insane-search](https://github.com/fivetaku/insane-search) (surveyed exemplar)

## Context

Decepticon's recon can ingest the output of external scanners, but the
agent itself has **no way to reach the open web**: no internet search, and
no resilient page fetch/parse. Two concrete gaps follow from that. OSINT
objectives (breach lookups, employee/infra footprinting, vendor advisory
reading) have no `web_search` primitive — the agent guesses from training
data. And fetching an in-scope target's web content goes through the raw
`http_request` tool, which returns bytes the agent must parse by hand and
which is trivially blocked by a WAF/anti-bot layer the engagement is
authorized to test through.

[Scrapling](https://github.com/D4Vinci/Scrapling) (BSD-3-Clause) is a
strong fit: an adaptive scraping framework whose `Selector` parser
survives markup changes, with a tiered fetcher stack — `Fetcher`
(HTTP + TLS fingerprint), `StealthyFetcher` (Cloudflare-Turnstile bypass
via camoufox), `DynamicFetcher` (Playwright/Chromium). But adopting it is
not a drive-by `uv add`: the stealth/dynamic fetchers pull a **browser
runtime** (Chromium/camoufox, downloaded out-of-band by `scrapling
install`), it performs **outbound egress** that must obey the RoE, and its
**anti-bot evasion** is exactly the capability that must never fire outside
an authorized scope. That blast radius — supply chain + egress + evasion —
is why this is an ADR and not a feature PR.

## Decision

Adopt Scrapling as the web-acquisition engine, **dependency-tiered to
preserve the existing sandbox isolation**, and expose it only through
RoE-gated tools:

1. **Core parser in the agent process; browsers only in the sandbox.**
   The light `scrapling` core (the `Selector` parser + `Fetcher` HTTP
   client) is an agent-process dependency. The browser-backed fetchers
   (`StealthyFetcher` / `DynamicFetcher` and the camoufox/Chromium runtime
   from `scrapling install`) run **only inside the existing browser
   sandbox container** (`tools/browser/`), never in the agent process —
   the same isolation boundary ADR-0006 and the browser sandbox already
   enforce. No browser binary is added to the langgraph image.

2. **Two new tools, both RoE-gated + audited + untrusted-wrapped:**
   - `web_search(query)` — OSINT search via a small **allowlisted
     provider set** (not arbitrary egress). The provider host is exempt
     from the in-scope *target* check (a search engine is OSINT
     infrastructure, not the engagement target) but every query is written
     to the HMAC audit ledger so the operator can review what left the
     perimeter.
   - `web_fetch(url)` — fetch + parse a single URL through the tiered
     fetcher. The URL **is** a target, so it is subject to the normal
     `evaluate_target` in-scope/out-of-scope gating like `http_request`.
   Both are added to `GATED_TOOL_NAMES`, and both wrap their returned
   content in `UntrustedOutput` / `PromptInjectionShield` — scraped pages
   and search results are attacker-influenceable and must not re-author
   the agent's instructions.

3. **Stealth tier is opt-in per engagement.** `StealthyFetcher`'s anti-bot
   evasion is gated behind an explicit engagement flag (default off); the
   plain `Fetcher` is the default. Evasion is a capability the operator
   consciously authorizes, mirroring `allow_sensitive_tlds` /
   `allow_cloud_metadata`.

## Consequences

- **Easier:** OSINT search and resilient, adaptive scraping of authorized
  targets become first-class agent capabilities; the `Selector` API gives
  the agent structured extraction instead of byte-parsing; anti-bot bypass
  is available for in-scope WAF-fronted targets.
- **Harder:** a new dependency to track; the sandbox image grows a browser
  runtime + `scrapling install` step; two new egress surfaces to keep
  inside the RoE/audit envelope.
- **Given up:** nothing in the core. The browser tier is deliberately kept
  out of the agent process, so the langgraph image stays browser-free.
- **Migration:** add `scrapling` (core) to the agent package and
  `scrapling[fetchers]` + `scrapling install` to the browser sandbox
  image; register `web_search` / `web_fetch`; extend `GATED_TOOL_NAMES`
  and the engagement schema with the stealth opt-in flag. No existing tool
  changes behavior.

## Prior art surveyed — insane-search

[insane-search](https://github.com/fivetaku/insane-search) is a second open-web
fetch/search stack (a Claude Code skill) surveyed to pressure-test §1 against a
real implementation rather than a single-source rationale. Three of its design
choices bear directly on this ADR:

- **Light-fetcher / browser-fetcher boundary → process boundary.** Its
  4-phase adaptive scheduler escalates `WebFetch`/Jina/`curl` (Phase 1) →
  `curl_cffi` TLS-impersonation + identity spoofing (Phase 2) → **a full
  browser behind the Playwright *MCP server*** (Phase 3). The browser runtime
  sits behind an IPC/process boundary, never in the calling process —
  independently corroborating §1's split (light `scrapling` core in-process,
  browser-backed fetchers out-of-process in the sandbox) and ADR-0006's revised
  out-of-process placement model. It confirms the boundary; it does not suggest
  a different one.
- **Escalate-on-signal, not always-on.** It only invokes the heavier tier when
  the lighter one returns a blocking signal (`403`/`429`/WAF headers/challenge
  body). Worth adopting for `web_fetch`: within the stealth opt-in, escalate
  `Fetcher` → `StealthyFetcher` on a detected block rather than reaching for
  evasion indiscriminately — narrower egress footprint for the same coverage.
- **Its posture is the anti-pattern we must invert.** insane-search is
  deliberately *anti-allowlist* ("don't pre-exclude any method", "no
  access-denied list") and **auto-installs evasion deps** (`pip install
  curl_cffi`/`yt-dlp` transparently). For a general scraper that maximizes
  reach; for a RoE-gated red-team tool it is exactly wrong — evasion must never
  fire outside authorized scope, and a CODEOWNERS-gated dependency surface
  cannot auto-install. The contrast sharpens §1 (allowlisted `web_search`,
  `evaluate_target`-gated `web_fetch`) and §3 (stealth default-off, per
  engagement) and the pinned-runtime decision over `scrapling install`-on-demand.

Net: the survey confirms the §1 runtime-placement boundary and adds the
escalate-on-signal refinement, while its permissive posture validates — by
contrast — the RoE/allowlist gating this ADR puts around the same mechanism.

## Alternatives considered

- **`httpx`/`http_request` only (status quo).** Rejected: no adaptive
  parsing, no anti-bot, no search — the recon gap the roadmap names.
- **`requests` + `beautifulsoup4` in-house.** Rejected: reimplements a
  worse version of Scrapling's parser and gets no stealth/fetcher tiering;
  more code to own, less capability.
- **Scrapling `[all]` in the agent process.** Rejected: pulls the browser
  runtime into the langgraph image and runs Chromium next to the agent —
  breaks the sandbox-isolation invariant ADR-0006 and the browser sandbox
  exist to hold.
- **A bespoke search-API client (Google/Bing paid API).** Rejected for the
  default: ties OSINT to a paid key and a single vendor; an allowlisted
  no-key provider keeps the OSS default usable, and a paid provider can be
  added to the allowlist later.
