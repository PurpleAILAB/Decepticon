"""Cloud exploitation package.

Offline analysers for the cloud artifact formats an agent typically
encounters mid-engagement:

- ``aws``        — IAM policy analyser (privilege escalation paths), S3
                   bucket-name takeover checks, CloudFormation template
                   audit, user-data secret scanner
- ``k8s``        — Kubernetes manifest analyser for RBAC, host mounts,
                   privileged containers, exposed dashboards, secret refs
- ``terraform``  — Terraform state JSON scanner for plaintext secrets
                   and dangerous IAM statements
- ``metadata``   — cloud metadata endpoint catalogue with headers /
                   tokens / response shapes (used by SSRF playbook)

All scanners are pure-Python and operate on JSON / YAML / HCL strings
the agent pastes in. Network exploitation (actual signing, credential
use) stays in the bash lane — this package flags *what* to test, not
*does* it.
"""

from __future__ import annotations

from decepticon.tools.cloud.aws import (
    IAMFinding,
    analyze_iam_policy,
    scan_bucket_names,
    scan_user_data,
)
from decepticon.tools.cloud.k8s import K8sFinding, analyze_k8s_manifest
from decepticon.tools.cloud.metadata import METADATA_ENDPOINTS, MetadataEndpoint
from decepticon.tools.cloud.terraform import analyze_tfstate

__all__ = [
    "IAMFinding",
    "K8sFinding",
    "METADATA_ENDPOINTS",
    "MetadataEndpoint",
    "analyze_iam_policy",
    "analyze_k8s_manifest",
    "analyze_tfstate",
    "scan_bucket_names",
    "scan_user_data",
]
