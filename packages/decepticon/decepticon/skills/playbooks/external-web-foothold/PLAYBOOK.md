---
name: external-web-foothold
description: "Run at the start of an external web-application engagement: ordered chain from passive intelligence through web enumeration to a first injection foothold. Triggers on: 'external web pentest', 'web app foothold', 'start web engagement', 'attack surface to entry point'."
metadata:
  phase: web-exploitation
  steps:
    - passive-recon
    - web-recon
    - sqli
---

# Playbook — External Web Foothold

The default opening for an external web target: build the surface
without touching it, enumerate the application, then convert the
highest-signal sink into a foothold. This is the boring, reliable path
— use it before reaching for exotic bug classes.

## Steps

| # | Skill | Goal | Gate to next step |
|---|-------|------|-------------------|
| 1 | `passive-recon` | Map the surface without touching the target: subdomains, ASN, CT logs, DNS, tech stack. | A scoped list of live hosts / apps exists. |
| 2 | `web-recon` | Enumerate the app: content discovery, API enumeration, CMS/WAF fingerprint, auth-surface mapping. | Parameterised endpoints and an auth surface are mapped. |
| 3 | `sqli` | Convert a high-value parameter into data access or auth bypass. | Injection confirmed, or ruled out across all sinks. |

## Decision gates

- **After step 2** — let the enumerated sinks pick the step-3 bug
  class. `sqli` is the default first probe, but if `web-recon` surfaced
  IDOR-shaped object IDs, an SSTI reflection, or an upload, branch to
  the matching `exploit/web/*` skill instead of forcing SQLi. The
  playbook is the spine, not a straitjacket.
- **After step 3** — a confirmed injection hands off to the analyst
  exploit-chain skills (`chains/*`) to escalate from foothold to
  objective; a clean negative loops back to step 2 for the next-ranked
  sink.

## OPSEC

Step 1 is zero-touch and always safe. Step 2 onward generates traffic —
honour the engagement rate limits and the shared `web-recon` request
deduplication pattern so summarised context never causes re-probing.
