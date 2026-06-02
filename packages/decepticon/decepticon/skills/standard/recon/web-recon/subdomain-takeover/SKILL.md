---
name: web-subdomain-takeover
description: "Subdomain takeover via dangling DNS/CNAME — GitHub Pages, Heroku, Azure, Fastly, Shopify, Netlify, Surge, Tumblr, Beanstalk, Zendesk, etc."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "subdomain takeover, dangling CNAME, dangling DNS, NXDOMAIN provider, can-i-take-over-xyz, subjack, subzy, nuclei takeover, orphaned subdomain"
  tags: subdomain-takeover, dangling-dns, cname, recon, bug-bounty
  mitre_attack: T1583.001
---

# Subdomain Takeover (Dangling DNS / CNAME)

A subdomain CNAMEs to a SaaS provider (GitHub Pages, Heroku, S3, etc.) but the underlying tenant has been deleted, expired, or never claimed. Whoever registers the orphaned tenant name controls a trusted `*.<TARGET>` origin. Severity is almost always **High → Critical** because the attacker inherits the parent domain's cookie scope, CORS allowlist, OAuth `redirect_uri` whitelist, CSP `*.<TARGET>` allowance, and reputation.

## 1. Asset surface — enumerate every subdomain

```bash
# Passive (no traffic to target)
subfinder -d <TARGET> -all -silent -o subs.txt
amass enum -passive -d <TARGET> -o subs.amass.txt
assetfinder --subs-only <TARGET> >> subs.txt
findomain -t <TARGET> -q >> subs.txt
curl -s "https://crt.sh/?q=%25.<TARGET>&output=json" | jq -r '.[].name_value' | tr '\n' '\n' | sort -u >> subs.txt
sort -u subs.txt -o subs.txt

# Active resolution + CNAME extraction
dnsx -l subs.txt -cname -resp -silent -o subs.cname.txt
# subs.cname.txt format:  app.<TARGET>  [cname.provider.net]
```

## 2. CNAME → provider fingerprints

Resolve each subdomain, capture the CNAME, and match against the dangling-provider table below.

```bash
while read sub; do
  cname=$(dig +short CNAME "$sub" | head -n1)
  [ -z "$cname" ] && continue
  echo "$sub -> $cname"
done < subs.txt | tee cname.map
```

| Provider | CNAME pattern | Vulnerable fingerprint in HTTP body |
|---|---|---|
| GitHub Pages | `*.github.io` | `There isn't a GitHub Pages site here.` |
| Heroku | `*.herokuapp.com`, `*.herokussl.com` | `No such app` / `herokucdn.com/error-pages/no-such-app.html` |
| AWS S3 | `*.s3*.amazonaws.com` | `NoSuchBucket` |
| AWS Elastic Beanstalk | `*.elasticbeanstalk.com` | NXDOMAIN on CNAME target |
| Azure CloudApp | `*.cloudapp.net`, `*.cloudapp.azure.com` | NXDOMAIN |
| Azure Traffic Manager | `*.trafficmanager.net` | NXDOMAIN |
| Azure Edge / Front Door | `*.azureedge.net`, `*.azurefd.net` | NXDOMAIN |
| Azure Websites | `*.azurewebsites.net` | `404 Web Site not found` |
| Fastly | `*.fastly.net` | `Fastly error: unknown domain` |
| Shopify | `shops.myshopify.com` | `Sorry, this shop is currently unavailable.` |
| Netlify | `*.netlify.app`, `*.netlify.com` | `Not Found - Request ID` (and the site is unclaimed) |
| Surge.sh | `*.surge.sh` | `project not found` |
| Tumblr | `domains.tumblr.com` | `Whatever you were looking for doesn't currently exist at this address.` |
| Read the Docs | `readthedocs.io` | `unknown to Read the Docs` |
| Zendesk | `*.zendesk.com` | `Help Center Closed` |
| Unbounce | `unbouncepages.com` | `The requested URL was not found on this server.` |
| Pantheon | `*.pantheonsite.io` | `The gods are wise, but do not know of the site which you seek.` |
| Help Scout | `*.helpscoutdocs.com` | `No settings were found for this company` |
| Cargo | `cargocollective.com` | `404 Not Found` + Cargo branding |
| Tilda | `*.tilda.ws` | `Please renew your subscription` |
| Webflow | `proxy-ssl.webflow.com` | `The page you are looking for doesn't exist or has been moved.` |
| Smartling | `*.smartling.com` | `Domain is not configured` |
| Worksites.net | `*.worksites.net` | `Hello! Sorry, but the website you're looking for doesn't exist.` |
| Ghost | `*.ghost.io` | `Site unavailable / The thing you were looking for is no longer here, or never was` |
| LaunchRock | `*.launchrock.com` | `It looks like you may have taken a wrong turn somewhere.` |

Canonical reference (updated by EdOverflow community): `can-i-take-over-xyz`.

## 3. Detection — body fingerprint

```bash
# Single subdomain
curl -sk -H 'Host: app.<TARGET>' "https://app.<TARGET>/" -o body.html -w '%{http_code}\n'
grep -iEf <(printf '%s\n' \
  "There isn't a GitHub Pages site here" \
  "no such app" "NoSuchBucket" "Fastly error: unknown domain" \
  "Sorry, this shop is currently unavailable" "project not found" \
  "Help Center Closed" "unknown to Read the Docs" \
  "The gods are wise" "Whatever you were looking for doesn't currently exist" \
  ) body.html
```

NXDOMAIN cases (Azure, Beanstalk) are detected at DNS layer — no HTTP body:

```bash
cname=$(dig +short CNAME "app.<TARGET>" | head -n1)
[ -n "$cname" ] && dig +short "$cname" | grep -q . || echo "DANGLING: $cname"
```

## 4. Mass detection

```bash
# subjack — fingerprints + claim hints
subjack -w subs.txt -t 50 -timeout 30 -ssl -c ~/go/pkg/mod/github.com/haccer/subjack/fingerprints.json -v -o subjack.out

# subzy — newer, maintained, more providers
subzy run --targets subs.txt --concurrency 50 --hide_fails --verify_ssl --output subzy.json

# nuclei takeover templates — most up-to-date provider list
nuclei -l subs.txt -t http/takeovers/ -severity high,critical -o nuclei.takeover.out

# Manual sanity check on hits
for s in $(awk '/VULNERABLE/{print $NF}' subjack.out); do
  echo "=== $s ==="; curl -sk -m 10 "https://$s/" | head -c 400; echo
done
```

## 5. Claim / PoC

`can-i-take-over-xyz` lists per-provider claim steps. General pattern: register an account on the provider, create the resource with the exact unclaimed name from the CNAME, deploy a marker page, and prove control.

```bash
# Marker page content — keep it boring, no defacement
cat > index.html <<EOF
<!doctype html><html><body>
<h1>Subdomain takeover PoC — authorized bug-bounty research</h1>
<p>Subdomain: app.<TARGET></p>
<p>Reported by: <RESEARCHER></p>
<p>Date: $(date -u +%FT%TZ)</p>
<p>Contact: <EMAIL></p>
</body></html>
EOF
# Deploy via the provider's normal flow (git push, heroku create, etc.)
# Then prove:
curl -sk "https://app.<TARGET>/" | grep -i 'authorized bug-bounty research'
```

OPSEC: never collect cookies, never serve JavaScript, never accept POSTs. Marker file + screenshot + DNS chain in the report is sufficient.

## 6. Chains — why this is rarely "informational"

| Chain | How takeover unlocks it |
|---|---|
| Cookie theft | Cookies scoped to `.<TARGET>` are sent to your subdomain → session hijack on the parent app. |
| OAuth redirect_uri | Many IdPs allow any `*.<TARGET>` as `redirect_uri`. Takeover → host the callback → exfil auth `code`. |
| CSP bypass | If parent app uses `script-src *.<TARGET>` or `connect-src *.<TARGET>`, you host attacker JS that the parent CSP trusts. |
| postMessage / CORS | `Access-Control-Allow-Origin` reflecting `*.<TARGET>` now trusts attacker JSON. |
| SAML / SSO | ACS URL allowlists by domain → forge assertions delivered to attacker subdomain. |
| Service Worker | A SW served from `app.<TARGET>` can intercept fetches inside its scope on that origin — full client-side compromise of any future user landing there. |
| Phishing / malware delivery | Trusted parent reputation + valid TLS → email filters and users trust the link. |
| Mixed-content / referrer leakage | Internal tools that whitelist `*.<TARGET>` as image / iframe source leak referrers and IDs to attacker. |

## 7. Detection signatures (for defenders)

| Signal | Source |
|---|---|
| CNAME RDATA pointing to provider where NXDOMAIN on the target | DNS audit |
| Provider error body served from `*.<TARGET>` | HTTP probe |
| `subjack`/`subzy`/`nuclei` "VULNERABLE" line | Mass scan |
| Provider tenant deleted but DNS not removed in IaC drift | Terraform / Route53 audit |
| Recently expired SaaS subscription + still-resolving CNAME | Procurement cross-check |

Remediation: remove the dangling DNS record OR re-claim the resource. Treat CNAMEs to external providers as production assets in CI/CD.

## 8. Decision gate

| Observation | Action |
|---|---|
| CNAME → provider on the table AND fingerprint body matches | Proceed to claim PoC → high/critical report |
| CNAME → provider AND NXDOMAIN at resolver | Same — claim PoC required, often even higher |
| CNAME → provider but body shows a live tenant page | Out of scope, move on |
| No CNAME, but A record to provider IP range with no app | Often false positive — verify provider docs before claiming |
| Subdomain in scope but parent program forbids subdomain takeover testing | Stop — report dangling DNS without claiming |

## Cross-references

- OAuth chain: `skills/standard/exploit/web/oauth/SKILL.md`
- Open redirect / cookie scoping: `skills/standard/exploit/web/open-redirect/SKILL.md`
- WAF / origin discovery (sister recon): `skills/standard/recon/web-recon/waf-detection/SKILL.md`
- Upstream: https://github.com/EdOverflow/can-i-take-over-xyz
