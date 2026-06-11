---
name: cloud-metadata-exfiltration
description: End-to-end chain abusing a cloud Instance Metadata Service — SSRF entry, IMDSv1/v2 token extraction, IAM role credential exfiltration, and privilege escalation through the stolen role.
metadata:
  phase: credential-access
  tags:
    - cloud
    - ssrf
    - imds
    - aws
    - iam
    - credential-exfiltration
  steps:
    - skill: exploit-ssrf
      goal: Find and confirm a server-side request forgery primitive on a cloud-hosted target and prove it reaches link-local addresses.
      phase: web-exploitation
    - skill: imds-pivot
      goal: Drive the SSRF at the Instance Metadata Service, defeat IMDSv2 token gating where possible, and pull the IAM role security credentials.
      phase: credential-access
    - skill: aws-iam-enum
      goal: Authenticate with the exfiltrated role credentials and enumerate its effective permissions and reachable resources.
      phase: discovery
    - skill: aws-iam-passrole-chain
      goal: Escalate from the role by chaining iam:PassRole / privilege-bearing actions into a higher-privileged identity.
      phase: privilege-escalation
---

# Cloud Instance Metadata Exfiltration

A repeatable chain that turns a single SSRF foothold on a cloud-hosted
workload into stolen IAM role credentials and, where the role allows it,
full account compromise. This is the Capital One 2019 pattern generalised
across AWS, GCP, and Azure.

The four steps map onto the linked skills — each step references a skill
the operator already has. Run them in order; stop at the first hard
boundary (e.g. enforced IMDSv2 with a GET-only SSRF) and pivot.

## Objective

Exfiltrate the IAM role credentials bound to a cloud instance and use
them to move laterally / escalate. Success = `sts get-caller-identity`
returning the stolen role and at least one action that the bound role can
perform against a crown-jewel asset.

## Preconditions

- A cloud-hosted target (AWS / GCP / Azure / other) — confirm via IP
  range, response headers, or asset metadata.
- A server-side fetch surface: "import from URL", webhook tester, PDF/SSR
  renderer, image proxy, link-preview, or any RCE that lets you `curl`
  from the box.
- Authorisation to test the target and to use any credentials recovered
  (in-scope engagement / lab / CTF only).

## Step 1 — Establish the SSRF primitive (`exploit-ssrf`)

Locate a parameter the server fetches and confirm it will reach an
attacker-chosen host, then point it at the link-local metadata address.

- Enumerate fetch surfaces; confirm out-of-band callback to your
  collaborator host.
- Test reachability of `169.254.169.254` (AWS/Azure/Alibaba/DO) and
  `metadata.google.internal` (GCP).
- If the app blocks local IPs, apply the bypass catalog (decimal/hex/octal
  IP encodings, DNS rebinding, open-redirect chaining, parser quirks).

Boundary: a fully filtered fetch with no bypass = no SSRF; document and
pivot to another entry vector.

## Step 2 — Extract role credentials from IMDS (`imds-pivot`)

With the SSRF reaching the metadata endpoint, pull the credentials.

- Fingerprint the provider, then request the credential path:
  - **AWS** `iam/security-credentials/<role>` (IMDSv1 directly; IMDSv2
    needs a `PUT` for the token first).
  - **GCP** `instance/service-accounts/default/token`
    (header `Metadata-Flavor: Google`).
  - **Azure** `identity/oauth2/token` (header `Metadata: true`).
- Capture `AccessKeyId` / `SecretAccessKey` / `Token` (the session token
  is mandatory for `ASIA…` keys), or the OAuth bearer for GCP/Azure.
- Also pull user-data / custom metadata — boot scripts routinely leak
  static secrets.

Boundary: IMDSv2 enforced **and** SSRF is GET-only → cannot mint the PUT
token. Try to chain SSRF→RCE so you `curl` locally; otherwise document the
boundary.

OPSEC: the metadata read itself is kernel-local and **not** logged
(CloudTrail/GCP/Azure). Every subsequent API call with the stolen
credentials **is** logged — plan usage before you spend the creds.

## Step 3 — Enumerate the stolen identity (`aws-iam-enum`)

Load the credentials and map what the role can actually do.

```bash
export AWS_ACCESS_KEY_ID=...; export AWS_SECRET_ACCESS_KEY=...; export AWS_SESSION_TOKEN=...
aws sts get-caller-identity
```

- Resolve the role's attached/inline policies and effective permissions.
- Inventory reachable resources (S3, Secrets Manager, KMS, EC2, Lambda).
- Flag privilege-escalation primitives: `iam:PassRole`,
  `iam:CreatePolicyVersion`, `iam:AttachRolePolicy`, `lambda:*`,
  `sts:AssumeRole`, wildcard actions.

(GCP/Azure: enumerate the service-account / managed-identity scopes with
the bearer token via the respective APIs.)

## Step 4 — Escalate via the role (`aws-iam-passrole-chain`)

Convert the enumerated escalation primitive into a higher-privileged
identity.

- Chain `iam:PassRole` with a compute service (Lambda/EC2/Glue/CodeBuild)
  to run as a more privileged role.
- Or rewrite a policy version / attach an admin policy if the role allows
  it, then re-`AssumeRole`.
- Re-run `sts get-caller-identity` to confirm the elevated principal.

## Promote findings

```
kg_add_node(kind="credential", label="<role>:<ASIA-prefix>",
            props={"source":"cloud-metadata-exfiltration","cloud":"aws"})
kg_add_edge(src=<ssrf-vuln>, dst=<cred>, kind="extracts")
kg_add_edge(src=<cred>, dst=<crown_jewel:aws-account>, kind="grants-access")
```

## Impact & remediation

- **Impact**: SSRF + IMDSv1 + over-privileged role is a clean path to
  account compromise — `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` (10.0).
- **Remediation**:
  - Enforce IMDSv2 fleet-wide (`ec2:MetadataHttpTokens = required`) and set
    the response hop-limit to 1 so containers cannot mint the token.
  - Scope IAM roles to least privilege — no wildcard actions, no
    unnecessary `iam:PassRole`.
  - Block `169.254.169.254` from workloads that do not need cloud APIs
    (host firewall / network policy).
  - Validate and allowlist outbound fetch targets at the application layer.

## Known exemplars

- Capital One 2019: WAF → SSRF → IMDS → IAM creds → ~100M PII records.
- Numerous PortSwigger SSRF labs solve to this exact chain.
- Pattern signature: any "fetch a URL" feature on an unhardened cloud
  instance with IMDSv1 reachable.
