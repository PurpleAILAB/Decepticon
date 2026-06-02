---
name: cloud-overview
description: Cloud exploitation lane — AWS IAM privesc, S3 takeover, k8s RBAC abuse, Terraform state leaks, cloud metadata pivoting.
metadata:
  subdomain: cloud
  when_to_use: "cloud aws gcp azure iam s3 kubernetes k8s terraform metadata imds privesc lane overview routing"
  mitre_attack:
    - T1078.004
    - T1530
    - T1552.005
    - T1552.007
    - T1610
    - T1611
---

# Cloud Hunter Skill Catalog

## Playbooks
| Skill | Use for |
|---|---|
| `/skills/standard/cloud/aws-iam-enum/SKILL.md`      | IAM enumeration + privesc |
| `/skills/standard/cloud/s3-takeover/SKILL.md`       | Dangling bucket / subdomain takeover |
| `/skills/standard/cloud/k8s-pivot/SKILL.md`         | Pod escape, RBAC abuse, hostPath |
| `/skills/standard/cloud/terraform-state-leak/SKILL.md` | Exposed state file exploitation |
| `/skills/standard/cloud/imds-pivot/SKILL.md`        | SSRF → metadata → IAM role |

## Workflow (authenticated engagement)
1. `bash("aws sts get-caller-identity")`
2. `bash("aws iam list-attached-user-policies --user-name <me>")`
3. For each attached policy: fetch JSON and `iam_policy_audit`
4. Feed Terraform state via `bash("aws s3 cp s3://bucket/terraform.tfstate -")` → `tfstate_audit`
5. `bash("kubectl get pods -A -o json")` → `k8s_audit`
6. Every privesc primitive → kg_add_node + chain edges

## Workflow (post-SSRF)
1. `metadata_endpoints("aws")` for the target cloud
2. Pivot URL one at a time via the SSRF vector
3. Confirmed creds → `credential` node + `leaks` edge from the SSRF vuln
4. `plan_attack_chains(promote=True)` to see the full path
