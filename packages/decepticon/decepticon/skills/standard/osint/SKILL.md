---
name: osint-overview
description: >
  Use when the engagement requires passive reconnaissance only — no
  packets to the target's authoritative infrastructure. Splits off from
  the Recon agent so bug-bounty and pre-engagement work can run with
  outbound-only network policy. Maltego, Shodan, Censys, Hunter.io,
  breach-data lookups, GitHub code search, Wayback Machine archives,
  certificate transparency, BGP/ASN mapping.
metadata:
  subdomain: osint
  when_to_use: "osint passive reconnaissance maltego shodan censys hunter breach data github code search wayback machine certificate transparency bgp asn outbound only bug bounty"
  subdomain: osint
  tags: osint, passive-recon, shodan, censys, breach-data, ct-logs, bgp
  mitre_attack: T1589, T1590, T1591, T1593, T1594, T1596
  network_policy: outbound-only
---

# OSINT-Only Operator Skill Catalog

This catalog is **passive**. No packets reach the target. Sandbox network
policy must restrict outbound to known-OSINT endpoints only (Shodan,
Censys, Hunter, GitHub API, crt.sh, Wayback, etc.).

## Playbooks

| Skill | Use for |
|---|---|
| `/skills/standard/osint/domain-pivots/SKILL.md` | Whois history, reverse-IP, related-domain enumeration |
| `/skills/standard/osint/ct-logs/SKILL.md` | crt.sh / Censys cert search for subdomain enumeration |
| `/skills/standard/osint/shodan-fingerprint/SKILL.md` | Shodan host search; service / banner / ssl.cn pivots |
| `/skills/standard/osint/censys-pivots/SKILL.md` | Censys cert/host/services pivots |
| `/skills/standard/osint/github-code-search/SKILL.md` | GitHub code search for org's leaked secrets / config |
| `/skills/standard/osint/wayback-archives/SKILL.md` | Wayback Machine API; retired endpoints, deleted docs |
| `/skills/standard/osint/breach-data/SKILL.md` | HIBP / DeHashed (RoE-permitted only); credential reuse paths |
| `/skills/standard/osint/employee-profiling/SKILL.md` | LinkedIn search (Sales Nav / manual), email-format inference |
| `/skills/standard/osint/asn-bgp/SKILL.md` | ASN ownership, BGP table snapshots, RIR records |
| `/skills/standard/osint/maltego/SKILL.md` | Maltego CLI graph projection; transform chain |
| `/skills/standard/osint/cryptocurrency/SKILL.md` | Chain analysis (Etherscan / Mempool.space / Arkham) for crypto-adjacent targets |
| `/skills/standard/osint/geospatial/SKILL.md` | Image geolocation, EXIF mining, satellite/streetview cross-reference |

## Workflow

1. **Seed**: from the engagement target (domain, company name, brand).
2. **Domain layer**: whois, reverse-IP, CT logs → enumerate every
   subdomain and adjacent domain.
3. **Service layer**: Shodan + Censys against discovered IPs → service
   inventory (NO probing; just consume cached scan data).
4. **Code layer**: GitHub code search for the target's org name, domain
   names, internal package names, AWS account IDs.
5. **People layer**: employees via LinkedIn; email format inference;
   HaveIBeenPwned for credential reuse.
6. **Infrastructure layer**: BGP + ASN ownership; Wayback retired
   endpoints; SSL/TLS cert history.
7. **Synthesis**: project the graph into Neo4j as a pre-engagement map;
   hand off to the Recon agent for active confirmation only if RoE
   permits.

## Network policy

```
[osint-operator container] → outbound to: shodan.io, api.censys.io,
                              api.hunter.io, api.github.com,
                              crt.sh, archive.org, hibp/api/v3,
                              maltego.com, etherscan.io, ...
                              NO outbound to the engagement target.
```

The sandbox-net policy for OSINT engagements pins this allowlist. Any
attempted egress to the actual target IP/domain triggers a SafeCommand
refusal.

## Why split from Recon

Recon is active by default — port scans, version probing, directory
brute-forcing. Bug-bounty programs and pre-engagement scoping work
explicitly forbid touching production. OSINT-only enforces the
no-touch contract structurally rather than relying on the agent prompt
to remember.
