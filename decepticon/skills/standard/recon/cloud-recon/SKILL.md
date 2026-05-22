---
name: cloud-recon
description: "Cloud infrastructure enumeration — AWS S3 buckets, Azure blob storage, GCP buckets, cloud metadata endpoints, IAM misconfigurations, CDN origin detection."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "cloud recon, S3 bucket, Azure blob, GCP bucket, cloud enum, CDN origin, bucket discovery, cloud infrastructure, serverless, container registry"
  tags: cloud, aws, azure, gcp, s3-bucket, cdn, serverless
  mitre_attack: T1580, T1538
---

# Cloud Infrastructure Reconnaissance Knowledge Base

Cloud reconnaissance identifies cloud-hosted assets, misconfigured storage, exposed services, and cloud-specific attack surfaces. Modern organizations run hybrid infrastructure — cloud recon is essential for complete attack surface mapping.

## 1. Cloud Provider Detection

### Fingerprinting via DNS/Headers

See `references/cloud-ip-ranges.md` for the full CNAME → provider mapping table and response header fingerprinting. See `references/cloud-naming-patterns.md` for bucket/resource naming dictionaries.

```bash
# Check CNAME records for cloud indicators
dig <target> CNAME +short

# Common cloud CNAME patterns:
# AWS:       *.amazonaws.com, *.cloudfront.net, *.elasticbeanstalk.com
# Azure:     *.azurewebsites.net, *.blob.core.windows.net, *.azure-api.net
# GCP:       *.googleapis.com, *.appspot.com, *.run.app, *.cloudfunctions.net
# Cloudflare: *.cdn.cloudflare.net

# Check IP ranges (AWS)
curl -s https://ip-ranges.amazonaws.com/ip-ranges.json | python3 -c "
import sys, json, ipaddress
data = json.load(sys.stdin)
target = ipaddress.ip_address('<TARGET_IP>')
for prefix in data['prefixes']:
    if target in ipaddress.ip_network(prefix['ip_prefix']):
        print(f\"AWS Region: {prefix['region']}, Service: {prefix['service']}\")
"
```

### Cloud Service Indicators
| Indicator | Provider | Service |
|-----------|----------|---------|
| `s3.amazonaws.com` CNAME | AWS | S3 Storage |
| `X-Amz-*` headers | AWS | Various |
| `X-Ms-*` headers | Azure | Various |
| `X-Cloud-Trace-Context` header | GCP | Cloud Run/Functions |
| `*.elasticbeanstalk.com` CNAME | AWS | Elastic Beanstalk |
| `*.azurewebsites.net` CNAME | Azure | App Service |
| `*.appspot.com` CNAME | GCP | App Engine |

## 2. AWS Enumeration

### S3 Bucket Discovery
```bash
# Common naming patterns
for prefix in <target> <target>-backup <target>-dev <target>-staging \
    <target>-prod <target>-assets <target>-uploads <target>-logs \
    <target>-data <target>-media www.<target> cdn.<target>; do
    # Check if bucket exists
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://$prefix.s3.amazonaws.com/")
    echo "$code $prefix.s3.amazonaws.com"
done

# Check bucket ACL (if accessible)
curl -s "https://<bucket>.s3.amazonaws.com/?acl"

# List bucket contents (if public)
curl -s "https://<bucket>.s3.amazonaws.com/?list-type=2&max-keys=20"
```

### S3 Bucket Takeover Detection
```bash
# If a subdomain CNAMEs to S3 but bucket doesn't exist:
# Response: "NoSuchBucket" → Takeover candidate
curl -s "https://assets.example.com/" | grep -i "NoSuchBucket"
```

### AWS Service Enumeration
```bash
# Check for exposed EC2 metadata (SSRF target)
# Internal: http://169.254.169.254/latest/meta-data/
# IMDSv2 requires token — check if v1 is still enabled

# Elastic Beanstalk environment discovery
dig <target>.elasticbeanstalk.com +short

# CloudFront origin detection
curl -sI "https://<target>" | grep -i "x-amz\|x-cache\|via.*cloudfront"

# API Gateway detection
curl -s "https://<api-id>.execute-api.<region>.amazonaws.com/prod/"
```

## 3. Azure Enumeration

### Azure Blob Storage
```bash
# Common storage account patterns
for name in <target> <target>storage <target>data <target>backup \
    <target>dev <target>prod; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://$name.blob.core.windows.net/")
    echo "$code $name.blob.core.windows.net"
done

# Enumerate containers (if listing enabled)
curl -s "https://<account>.blob.core.windows.net/<container>?restype=container&comp=list"

# Check for anonymous access
curl -s "https://<account>.blob.core.windows.net/\$web/index.html"
```

### Azure Service Discovery
```bash
# Azure App Service
dig <target>.azurewebsites.net +short

# Azure Functions
curl -s "https://<target>.azurewebsites.net/api/<function>"

# Azure API Management
dig <target>.azure-api.net +short

# Azure DevOps (public projects)
curl -s "https://dev.azure.com/<org>/_apis/projects?api-version=7.0"
```

### Azure Subdomain Patterns
```
*.azurewebsites.net       → App Service
*.blob.core.windows.net   → Blob Storage
*.table.core.windows.net  → Table Storage
*.queue.core.windows.net  → Queue Storage
*.file.core.windows.net   → File Storage
*.database.windows.net    → SQL Database
*.redis.cache.windows.net → Redis Cache
*.vault.azure.net         → Key Vault
*.azure-api.net           → API Management
*.azureedge.net           → CDN
```

## 4. GCP Enumeration

### GCP Storage Buckets
```bash
# Common GCP bucket names
for name in <target> <target>-bucket <target>-backup <target>-data \
    <target>.appspot.com <target>-uploads; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://storage.googleapis.com/$name/")
    echo "$code storage.googleapis.com/$name"
done

# List bucket contents (if public)
curl -s "https://storage.googleapis.com/<bucket>/"
```

### GCP Service Discovery
```bash
# App Engine
dig <project>.appspot.com +short

# Cloud Run
dig <service>-<hash>-<region>.a.run.app +short

# Cloud Functions
curl -s "https://<region>-<project>.cloudfunctions.net/<function>"

# Firebase
curl -s "https://<project>.firebaseio.com/.json"
```

## 5. Multi-Cloud Tools

### cloud_enum (Automated Discovery)
```bash
# Enumerate across all major cloud providers
cloud_enum -k <target> -l cloud_enum_<target>.txt

# With mutation file
cloud_enum -k <target> -m mutations.txt -l cloud_enum_<target>.txt
```

### Manual Multi-Cloud Checklist
```bash
# Run for each target keyword
TARGET="example"

echo "=== AWS ==="
curl -s -o /dev/null -w "%{http_code} " "https://$TARGET.s3.amazonaws.com/" && echo "S3"

echo "=== Azure ==="
curl -s -o /dev/null -w "%{http_code} " "https://$TARGET.blob.core.windows.net/" && echo "Blob"

echo "=== GCP ==="
curl -s -o /dev/null -w "%{http_code} " "https://storage.googleapis.com/$TARGET/" && echo "GCS"

echo "=== Firebase ==="
curl -s -o /dev/null -w "%{http_code} " "https://$TARGET.firebaseio.com/.json" && echo "Firebase"
```

## 6. CDN & Origin Detection

### Finding Origin IPs Behind CDN
```bash
# Check historical DNS records (via SecurityTrails, etc.)
# Check for direct IP disclosure in:
# - Email headers (Received: from)
# - SSL certificate Subject Alternative Names
# - Shodan/Censys searches for the same TLS cert

# Direct IP test
curl -sI -H "Host: <target>" https://<suspected_origin_ip>/ | head -20
```

## 7. Serverless & Container Enumeration

### Lambda/Functions URL Patterns
```bash
# AWS Lambda function URLs
curl -s "https://<id>.lambda-url.<region>.on.aws/"

# Azure Functions
curl -s "https://<app>.azurewebsites.net/api/<func>?code=<key>"

# GCP Cloud Functions
curl -s "https://<region>-<project>.cloudfunctions.net/<func>"
```

### Container Registry Exposure
```bash
# Docker Hub
curl -s "https://hub.docker.com/v2/repositories/<org>/" | python3 -m json.tool

# AWS ECR (if misconfigured)
# Azure ACR
curl -s "https://<registry>.azurecr.io/v2/_catalog"

# GCP GCR
curl -s "https://gcr.io/v2/<project>/tags/list"
```

## 8. Workflow: Cloud Recon Sequence

1. **Cloud Detection** → DNS CNAMEs, response headers, IP range lookups
2. **Storage Enumeration** → S3/Blob/GCS bucket discovery with naming patterns
3. **Service Discovery** → App services, functions, API gateways
4. **Access Testing** → Check for public listing, anonymous read/write
5. **Takeover Check** → Dangling CNAMEs to unclaimed cloud resources
6. **Origin Detection** → Find real IPs behind CDN
7. **Container/Registry** → Check for exposed container registries
8. **Document** → Add all cloud findings to main report with provider tags

## 9. Output Files
```
./
├── cloud_enum_<target>.txt           # cloud_enum results
├── s3_buckets_<target>.txt           # AWS S3 discovery
├── azure_storage_<target>.txt        # Azure blob discovery
├── gcp_buckets_<target>.txt          # GCP storage discovery
├── cloud_services_<target>.txt       # Discovered cloud services
└── cloud_recon_<target>_summary.md   # Consolidated cloud findings
```
