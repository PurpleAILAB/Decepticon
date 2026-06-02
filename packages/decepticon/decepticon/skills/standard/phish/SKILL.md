---
name: phish-overview
description: >
  Use ONLY when the engagement's ConOps explicitly declares
  phishing_engagement=true. Covers GoPhish campaign management, Evilginx2
  reverse-proxy MFA bypass, Modlishka live credential capture, and the
  deconfliction handshake with SOC / incident response.
metadata:
  subdomain: phish
  when_to_use: "phishing engagement gophish evilginx2 modlishka mfa bypass reverse proxy soc deconfliction conops phishing_engagement"
  tags: phishing, evilginx, gophish, modlishka, social-engineering, mfa-bypass
  mitre_attack: T1566, T1566.001, T1566.002, T1078, T1539, T1621
  gated_by_conops: phishing_engagement
---

# Phishing / Social Engineering Skill Catalog

**Gating**: every skill in this catalog refuses to execute unless ConOps
declares `phishing_engagement=true`. The Soundwave planner's
phishing-engagement template generates this flag along with:

- Sender domains (must be operator-owned).
- Target population scope (which AD groups, which email domains).
- Deconfliction window (operator-SOC notification cadence).
- Out-of-band failsafe contact for the SOC.

## Playbooks

| Skill | Use for |
|---|---|
| `/skills/standard/phish/gophish-campaign/SKILL.md` | GoPhish API: create user/group, template, landing page, campaign |
| `/skills/standard/phish/evilginx2-phishlet/SKILL.md` | Author and deploy a phishlet; capture session cookies past MFA |
| `/skills/standard/phish/modlishka-proxy/SKILL.md` | Modlishka 2FA bypass — real-time token relay |
| `/skills/standard/phish/o365-token-replay/SKILL.md` | Replay captured O365 access tokens via TokenTactics |
| `/skills/standard/phish/teams-meeting-bombing/SKILL.md` | Teams external-meeting OAuth flow abuse |
| `/skills/standard/phish/qr-code-phishing/SKILL.md` | Quishing — QR codes on physical artifacts, mobile-only landing |
| `/skills/standard/phish/voice-phish-vish/SKILL.md` | Pretexting + AI voice cloning for helpdesk SE (very restricted RoE) |
| `/skills/standard/phish/deconfliction-handshake/SKILL.md` | SOC notification protocol; "this is a test" headers; rollback |

## Infrastructure pattern

```
[Target inbox] -> [NGiNX reverse proxy on attacker domain]
                  ├─ /login → Evilginx2 phishlet (MFA bypass + session cap)
                  └─ /landing → GoPhish (campaign tracking + analytics)
```

Notes:

- The NGiNX layer is for OPSEC: blue-team URL classifiers see one domain;
  internally we route to phishlet vs landing based on path / referer.
- TLS certs from Let's Encrypt with `acme.sh` — keep ACME challenges
  off the same path the phishlet uses.
- DKIM/SPF/DMARC must be correctly set on the sender domain or modern
  inboxes drop the mail. Soundwave's phishing template walks the operator
  through DNS setup.

## Deconfliction

Each engagement gets a magic header (`X-Decepticon-Eng: <slug>`) on every
outbound mail. The SOC's mail-flow rule allow-lists that header so blue-team
can identify simulated phishing from real attack traffic. Without this,
phishing tests collide with real IR cases.

## Failsafe

If the operator's session is terminated or the SOC requests an immediate
stop, the phishing infrastructure must wind down within 5 minutes:

1. `gophish_pause_campaign` halts new mail.
2. `evilginx_disable_phishlet` returns 502 on the phishlet.
3. `dns_failover_to_safe` repoints the sender domain to a static "this
   was a test, contact your security team" page.

These steps are codified as the `phishing_failsafe` skill, which the
operator can invoke with one bash command.
