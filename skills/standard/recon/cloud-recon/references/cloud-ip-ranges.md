# Cloud Provider IP Range Sources

Authoritative sources for identifying which cloud provider owns a given IP address.

## Live IP Range Endpoints

| Provider | URL | Format | Update Frequency |
|----------|-----|--------|-----------------|
| AWS | `https://ip-ranges.amazonaws.com/ip-ranges.json` | JSON | Updated frequently |
| Azure | `https://www.microsoft.com/en-us/download/details.aspx?id=56519` | JSON (download) | Weekly |
| GCP | `https://www.gstatic.com/ipranges/cloud.json` | JSON | Updated frequently |
| Cloudflare | `https://www.cloudflare.com/ips-v4` / `ips-v6` | Plain text | Updated as needed |
| Fastly | `https://api.fastly.com/public-ip-list` | JSON | Updated as needed |

## Quick IP Check Script

```bash
#!/bin/bash
# Check if an IP belongs to a major cloud provider
TARGET_IP="$1"

echo "=== Checking $TARGET_IP ==="

# AWS
curl -s https://ip-ranges.amazonaws.com/ip-ranges.json | python3 -c "
import sys, json, ipaddress
data = json.load(sys.stdin)
target = ipaddress.ip_address('$TARGET_IP')
for prefix in data['prefixes']:
    if target in ipaddress.ip_network(prefix['ip_prefix']):
        print(f\"AWS: {prefix['region']} / {prefix['service']}\")
" 2>/dev/null

# GCP
curl -s https://www.gstatic.com/ipranges/cloud.json | python3 -c "
import sys, json, ipaddress
data = json.load(sys.stdin)
target = ipaddress.ip_address('$TARGET_IP')
for prefix in data['prefixes']:
    net = prefix.get('ipv4Prefix') or prefix.get('ipv6Prefix')
    if net and target in ipaddress.ip_network(net):
        print(f\"GCP: {prefix.get('scope','unknown')} / {prefix.get('service','unknown')}\")
" 2>/dev/null

# Cloudflare
curl -s https://www.cloudflare.com/ips-v4 | while read cidr; do
    python3 -c "
import ipaddress
if ipaddress.ip_address('$TARGET_IP') in ipaddress.ip_network('$cidr'):
    print(f'Cloudflare: $cidr')
" 2>/dev/null
done
```

## CNAME → Provider Mapping

| CNAME Pattern | Provider | Service |
|---------------|----------|---------|
| `*.amazonaws.com` | AWS | Various |
| `*.s3.amazonaws.com` | AWS | S3 |
| `*.s3-<region>.amazonaws.com` | AWS | S3 (regional) |
| `*.cloudfront.net` | AWS | CloudFront CDN |
| `*.elasticbeanstalk.com` | AWS | Elastic Beanstalk |
| `*.elb.amazonaws.com` | AWS | Elastic Load Balancer |
| `*.execute-api.<region>.amazonaws.com` | AWS | API Gateway |
| `*.lambda-url.<region>.on.aws` | AWS | Lambda Function URL |
| `*.azurewebsites.net` | Azure | App Service |
| `*.blob.core.windows.net` | Azure | Blob Storage |
| `*.table.core.windows.net` | Azure | Table Storage |
| `*.queue.core.windows.net` | Azure | Queue Storage |
| `*.file.core.windows.net` | Azure | File Storage |
| `*.database.windows.net` | Azure | SQL Database |
| `*.redis.cache.windows.net` | Azure | Redis Cache |
| `*.vault.azure.net` | Azure | Key Vault |
| `*.azure-api.net` | Azure | API Management |
| `*.azureedge.net` | Azure | CDN |
| `*.azurefd.net` | Azure | Front Door |
| `*.trafficmanager.net` | Azure | Traffic Manager |
| `*.googleapis.com` | GCP | Various |
| `*.storage.googleapis.com` | GCP | Cloud Storage |
| `*.appspot.com` | GCP | App Engine |
| `*.run.app` | GCP | Cloud Run |
| `*.cloudfunctions.net` | GCP | Cloud Functions |
| `*.firebaseio.com` | GCP | Firebase |
| `*.web.app` | GCP | Firebase Hosting |
| `*.cdn.cloudflare.net` | Cloudflare | CDN |
| `*.herokuapp.com` | Heroku | Platform |
| `*.netlify.app` | Netlify | Hosting |
| `*.vercel.app` | Vercel | Hosting |
| `*.pages.dev` | Cloudflare | Pages |
| `*.workers.dev` | Cloudflare | Workers |
| `*.fly.dev` | Fly.io | Platform |
| `*.render.com` | Render | Platform |

## Response Header → Provider Mapping

| Header | Value Pattern | Provider |
|--------|--------------|----------|
| `Server` | `AmazonS3` | AWS S3 |
| `Server` | `cloudflare` | Cloudflare |
| `Server` | `gws` | Google |
| `X-Amz-*` | Any | AWS |
| `X-Ms-*` | Any | Azure |
| `X-Cloud-Trace-Context` | Any | GCP |
| `CF-RAY` | Any | Cloudflare |
| `X-Cache` | `Hit from cloudfront` | AWS CloudFront |
| `Via` | `*.cloudfront.net` | AWS CloudFront |
| `X-Azure-Ref` | Any | Azure Front Door |
| `X-Vercel-Id` | Any | Vercel |
| `X-Netlify-*` | Any | Netlify |
| `Fly-Request-Id` | Any | Fly.io |
