# Open-web acquisition: `web_search` / `web_fetch`

Two agent tools give Decepticon first-class open-web reach for OSINT and recon,
backed by a site-agnostic fetch engine that gets past the WAF/anti-bot defenses
most real targets sit behind. Design record: [ADR-0010](../adr/0010-open-web-acquisition.md).

## The tools

| Tool | Purpose | RoE |
|------|---------|-----|
| `web_search(query, provider="duckduckgo")` | Keyword search → ranked result URLs/titles/snippets | OSINT: allowlisted provider, audited, **target-exempt** |
| `web_fetch(url, selector="", device="auto")` | Fetch one URL's content, escalating past blocks | **Target-gated** on the URL host, fail-closed |

Typical flow: `web_search` to discover URLs → `web_fetch` to read a specific
in-scope page. Pass a `selector` (e.g. `article`, `#main`) to `web_fetch` when
you know what "the real content loaded" looks like — without it, a `200` with a
tiny or challenge body is treated as suspect, not success.

## How it works

The engine (`decepticon/sandbox_web/`) runs **inside the sandbox**; the tools
dispatch it over the existing bash execution surface
(`python3 -m decepticon.sandbox_web …`). Every byte of egress therefore happens
in `sandbox-net`, behind the nftables/DNS allowlist compiled from the
engagement's `roe.json` — there is no management-side egress and no new
transport.

Per fetch, the engine runs an escalating chain and records every attempt in a
`trace`:

1. **probe** — curl-impersonation (Safari TLS) with a self-referer.
2. **validate (4 layers)** — challenge markers / size fingerprint / cookie
   sensor / `success_selectors`. **HTTP 200 is an inspection-start condition,
   not success.** Verdicts: `strong_ok`, `weak_ok`, `challenge`, `blocked`,
   `unknown`.
3. **detect + grid** — rank the WAF product, then try the
   `url_transform × tls_impersonate × referer` grid (it does *not* stop on the
   first 200).
4. **browser fallback** — a headless browser tier on JS challenges (optional;
   absent → a clean `unknown`, the curl result stands).

## RoE & safety (three layers)

1. **Management-side gate** — `RoEGuardrailMiddleware` refuses out-of-scope
   `web_fetch` URLs before the tool runs (fail-closed). `web_search` is gated
   for audit/throttle but target-exempt (OSINT over an allowlisted provider).
2. **Engine `scope_check`** — every transformed/redirected hop is re-checked
   against `roe.json` (`evaluate_target`), so a `www.→m.` transform or a
   redirect to a new host is skipped if out of scope.
3. **Sandbox nftables/DNS allowlist** — the authoritative backstop: an
   out-of-scope connection cannot leave the sandbox regardless of the above.

Open-web content is attacker-influenceable, so both tools' output is
prompt-injection-quarantined (`UNTRUSTED_TOOL_NAMES`). TLS-impersonation and the
browser tier are conservative by default.

## No-Site-Name rule

The engine never hardcodes a target site (host/selector/referer) — that
knowledge enters only at call time via `selector` / `user_hint`. A CI gate
(`python -m decepticon.sandbox_web.bias_check`) enforces it. The one exception
is the `web_search` provider allowlist (the agreed OSINT entry points).

## Provenance

The engine is precisely derived from [`fivetaku/insane-search`](https://github.com/fivetaku/insane-search)
(MIT) — its Verdict model, WAF-profile ranking, transform/TLS grid, and
No-Site-Name rule — with the governance **inverted** for Decepticon: every hop
RoE-gated (vs anti-allowlist "try everything"), sandbox-only egress (vs
in-process), build-time deps (vs runtime auto-install), and untrusted-output
wrapping. See ADR-0010 for the full mapping.
