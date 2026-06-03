---
name: lookalike-domain
description: >
  Register and provision a lookalike / Punycode phishing domain with DNS and TLS so
  GoPhish and evilginx2 lures resolve and pass modern mail + browser checks.
metadata:
  subdomain: phishing
  when_to_use: "lookalike domain, punycode, typosquat domain, idn homograph, phishing infrastructure, dns spf dkim dmarc, tls acme for lure"
  mitre_attack:
    - T1583.001
    - T1566
    - T1656
  tags:
    - phishing
    - infrastructure
    - domain
    - dns
---

# Lookalike Domain

The lure link's domain must look plausible and pass SPF/DKIM/DMARC or
modern inboxes drop the mail and browsers flag the page. This skill
stands up the domain that `gophish-campaign` and `evilginx2-proxy`
sit behind.

## Choose the name

- Combosquat / lookalike: `acme-portal.example`, `login-acme.example`,
  `acme-sso.example` (a real word the victim associates with the
  brand). Prefer this over raw typos.
- IDN homograph (Punycode): visually-similar Unicode characters
  (`аcme.example` with a Cyrillic а → `xn--cme-8cd.example`). Use only
  when the RoE allows and the mail path won't strip it.

```bash
python3 - <<'PY'
import idna
print(idna.encode("аcme.example").decode())   # punycode (xn--...)
PY
```

- NEVER pick a name confusable with a DIFFERENT customer's brand
  (`plan/roe.json` scope only).

## DNS

```
A     @            <sandbox-ip>
A     login        <sandbox-ip>
MX    @            10 mail.<lookalike>.
TXT   @            "v=spf1 a mx ip4:<sandbox-ip> -all"
TXT   default._domainkey  "v=DKIM1; k=rsa; p=<pubkey>"
TXT   _dmarc       "v=DMARC1; p=none; rua=mailto:dmarc@<lookalike>"
```

For evilginx2, delegate NS to the sandbox so it can answer ACME
challenges itself.

## TLS

```bash
acme.sh --issue --standalone -d login.acme-portal.example
# or let evilginx2 manage Let's Encrypt automatically
```

## Verify before sending

```bash
dig +short login.acme-portal.example
# check SPF/DKIM/DMARC alignment with a test send to a controlled box
swaks --to test@controlled.example --from it@acme-portal.example --server localhost
```

## Evidence

Record the domain, registration date, and DNS records in
`plan/phisher/infrastructure.md`; this feeds the mandatory
`lure-deconfliction` handshake payload (the blue team needs the lure
domain + registration date). Create an `Infrastructure` node in the
knowledge graph.

## Failsafe

On stop, `dns_failover_to_safe`: repoint the domain to a static
"authorized security test — contact your security team" page within 5
minutes.
