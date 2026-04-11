"""LangChain @tool wrappers for the cloud exploitation package."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.cloud.aws import (
    analyze_iam_policy,
    scan_bucket_names,
    scan_user_data,
)
from decepticon.tools.cloud.k8s import analyze_k8s_manifest
from decepticon.tools.cloud.metadata import METADATA_ENDPOINTS
from decepticon.tools.cloud.terraform import analyze_tfstate


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def iam_policy_audit(policy_json: str) -> str:
    """Audit an AWS IAM policy JSON for privilege escalation primitives.

    Flags the Rhino Security Labs canonical privesc paths plus wildcard
    action/resource pairs.
    """
    findings = analyze_iam_policy(policy_json)
    return _json([f.to_dict() for f in findings])


@tool
def s3_buckets_from_text(text: str) -> str:
    """Extract S3 bucket names referenced anywhere in ``text``.

    Covers ``s3://bucket``, ``bucket.s3.amazonaws.com`` virtual-hosted,
    and ``s3.amazonaws.com/bucket`` path-style. Agent follow-up:
    enumerate each for public listing / dangling CNAME / misconfig.
    """
    buckets = scan_bucket_names(text)
    return _json({"count": len(buckets), "buckets": buckets})


@tool
def user_data_secrets(text: str) -> str:
    """Scan EC2 user-data (or any cloud-init) for embedded secrets."""
    hits = scan_user_data(text)
    return _json({"count": len(hits), "hits": [{"kind": k, "snippet": s} for k, s in hits]})


@tool
def k8s_audit(manifest_json: str) -> str:
    """Audit a Kubernetes manifest (pre-parsed JSON) for escape primitives.

    Flags: hostNetwork/PID/IPC, hostPath to / or docker.sock, privileged
    containers, dangerous caps (SYS_ADMIN, NET_ADMIN, ...), wildcard RBAC
    rules, plaintext env secrets.
    """
    findings = analyze_k8s_manifest(manifest_json)
    return _json([f.to_dict() for f in findings])


@tool
def tfstate_audit(tfstate_json: str) -> str:
    """Audit a Terraform state file for plaintext secrets and sensitive outputs."""
    report = analyze_tfstate(tfstate_json)
    return _json(report.to_dict())


@tool
def metadata_endpoints(provider: str = "") -> str:
    """Return the canonical cloud metadata endpoint catalogue.

    Pass a provider filter (aws / gcp / azure / oracle / alibaba /
    digitalocean / kubernetes) to narrow the list.
    """
    items = [e.to_dict() for e in METADATA_ENDPOINTS if not provider or e.provider == provider]
    return _json({"count": len(items), "endpoints": items})


CLOUD_TOOLS = [
    iam_policy_audit,
    s3_buckets_from_text,
    user_data_secrets,
    k8s_audit,
    tfstate_audit,
    metadata_endpoints,
]
