"""AWS-focused analysers: IAM policies, S3 buckets, EC2 user-data.

IAM privilege escalation detection follows the canonical Rhino
Security Labs 21 privesc paths — we don't replicate the whole matrix,
but we flag the high-value primitives:

- ``iam:CreateAccessKey``
- ``iam:PassRole`` combined with ``lambda:CreateFunction``
- ``iam:PutUserPolicy`` / ``iam:AttachUserPolicy``
- ``iam:UpdateLoginProfile``
- ``sts:AssumeRole`` on wildcard
- ``*`` on Resource with a write action

S3 bucket name extraction feeds the bucket takeover check (any
reference to a bucket we don't know exists is worth testing).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class IAMFinding:
    id: str
    severity: str
    title: str
    detail: str
    action: str | None = None
    resource: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
            "resource": self.resource,
        }


# Privesc primitive → (severity, title, explanation) mapping
_PRIVESC_PRIMITIVES: dict[str, tuple[str, str, str]] = {
    "iam:createaccesskey": (
        "critical",
        "IAM CreateAccessKey privilege escalation",
        "Grants the ability to mint access keys for any user, including admins.",
    ),
    "iam:updateloginprofile": (
        "critical",
        "IAM UpdateLoginProfile privilege escalation",
        "Grants password reset for any user including admins — console takeover.",
    ),
    "iam:putuserpolicy": (
        "critical",
        "IAM PutUserPolicy privilege escalation",
        "Can attach inline policies to any user, granting arbitrary permissions.",
    ),
    "iam:attachuserpolicy": (
        "critical",
        "IAM AttachUserPolicy privilege escalation",
        "Can attach managed policies to any user, including AdministratorAccess.",
    ),
    "iam:attachrolepolicy": (
        "critical",
        "IAM AttachRolePolicy privilege escalation",
        "Can attach managed policies to any role, enabling role takeover.",
    ),
    "iam:putrolepolicy": (
        "critical",
        "IAM PutRolePolicy privilege escalation",
        "Can attach inline policies to any role — arbitrary permission grant.",
    ),
    "iam:createpolicyversion": (
        "high",
        "IAM CreatePolicyVersion with SetAsDefault",
        "Can replace any managed policy version with an attacker-crafted one.",
    ),
    "iam:passrole": (
        "high",
        "iam:PassRole primitive",
        "Dangerous when combined with compute services (lambda/ec2/ecs) to assume any role.",
    ),
    "sts:assumerole": (
        "medium",
        "sts:AssumeRole grant",
        "Direct role takeover if the trust policy allows the caller.",
    ),
    "lambda:createfunction": (
        "high",
        "lambda:CreateFunction primitive",
        "Dangerous paired with iam:PassRole — create a Lambda with any execution role.",
    ),
    "lambda:updatefunctioncode": (
        "high",
        "lambda:UpdateFunctionCode primitive",
        "Replace a trusted Lambda's code — persistence + lateral movement.",
    ),
    "ec2:runinstances": (
        "high",
        "ec2:RunInstances primitive",
        "Launch EC2 with an instance profile → role takeover via metadata.",
    ),
}


def _as_list(val: Any) -> list[Any]:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def analyze_iam_policy(policy: str | dict[str, Any]) -> list[IAMFinding]:
    """Return a list of privilege escalation findings for an IAM policy."""
    if isinstance(policy, str):
        try:
            data = json.loads(policy)
        except json.JSONDecodeError:
            return [
                IAMFinding(id="iam.parse-error", severity="info", title="Not valid JSON", detail="")
            ]
    else:
        data = policy

    findings: list[IAMFinding] = []
    idx = 0
    for stmt in _as_list(data.get("Statement")):
        effect = (stmt.get("Effect") or "Allow").lower()
        if effect != "allow":
            continue
        for action in _as_list(stmt.get("Action") or stmt.get("NotAction") or "*"):
            act = str(action).lower()
            for resource in _as_list(stmt.get("Resource") or "*"):
                res = str(resource)
                if act == "*" and res == "*":
                    idx += 1
                    findings.append(
                        IAMFinding(
                            id=f"iam-{idx:04d}",
                            severity="critical",
                            title="Wildcard Action on Wildcard Resource",
                            detail="Effect=Allow, Action=*, Resource=* — account takeover.",
                            action=act,
                            resource=res,
                        )
                    )
                    continue
                # Wildcarded action families
                if act.endswith(":*") and res == "*":
                    idx += 1
                    findings.append(
                        IAMFinding(
                            id=f"iam-{idx:04d}",
                            severity="high",
                            title=f"Wildcard {act} on all resources",
                            detail=f"All {act.split(':')[0]} actions allowed account-wide.",
                            action=act,
                            resource=res,
                        )
                    )
                # Known privesc primitives
                matched = _PRIVESC_PRIMITIVES.get(act.strip("*"))
                if matched:
                    sev, title, detail = matched
                    idx += 1
                    findings.append(
                        IAMFinding(
                            id=f"iam-{idx:04d}",
                            severity=sev,
                            title=title,
                            detail=detail,
                            action=act,
                            resource=res,
                        )
                    )
    return findings


# ── S3 helpers ──────────────────────────────────────────────────────────


# Three forms of bucket reference:
#   1. s3://bucket-name[/key]                       — SDK / awscli
#   2. bucket-name.s3[-region].amazonaws.com/...    — virtual-hosted style
#   3. s3[-region].amazonaws.com/bucket-name/...    — path style
_BUCKET_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"s3://([a-z0-9][a-z0-9.\-]{1,61}[a-z0-9])(?:/|$)", re.IGNORECASE),
    re.compile(
        r"(?<![A-Za-z0-9.-])([a-z0-9][a-z0-9.\-]{1,61}[a-z0-9])\.s3(?:[-.][a-z0-9-]+)?\.amazonaws\.com",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9.-])s3(?:[-.][a-z0-9-]+)?\.amazonaws\.com/([a-z0-9][a-z0-9.\-]{1,61}[a-z0-9])(?:/|$)",
        re.IGNORECASE,
    ),
)


def scan_bucket_names(text: str) -> list[str]:
    """Pull every S3 bucket name referenced in ``text``."""
    names: list[str] = []
    for pat in _BUCKET_RES:
        for m in pat.finditer(text):
            name = m.group(1).lower().rstrip(".")
            if name and name not in names and name != "s3":
                names.append(name)
    return names


# ── User data secret scanner ───────────────────────────────────────────


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_key", re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40}(?![A-Za-z0-9+/])")),
    ("ssh_private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("password_literal", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[^\s\"']{6,}")),
)


def scan_user_data(text: str) -> list[tuple[str, str]]:
    """Scan EC2/Cloud-Init user-data for embedded secrets.

    Returns a list of ``(kind, snippet)`` tuples.
    """
    results: list[tuple[str, str]] = []
    for kind, pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            # Truncate noise
            snippet = m.group(0)[:80]
            results.append((kind, snippet))
    return results
