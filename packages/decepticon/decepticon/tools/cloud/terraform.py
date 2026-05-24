"""Terraform state + plan analyser.

Terraform state files (``terraform.tfstate``) are the single highest-
value artifact in cloud engagements: they store plaintext outputs,
resource IDs, and, historically, plain-text secret values for many
providers. Most organisations leave them with overly broad S3 bucket
permissions.

This module parses the JSON and:

- Extracts every ``sensitive = true`` output value (leaked if the state
  isn't encrypted)
- Flags resources whose attributes contain keys/tokens/passwords
- Surfaces the backend config (which bucket/region holds state → a
  secondary target)
- Counts provider accounts + IAM principals for lateral hints
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "private_key",
    "aws_secret_access_key",
    "client_secret",
    "connection_string",
    "jwt_secret",
    "db_password",
    "master_password",
}


@dataclass
class TFStateFinding:
    kind: str
    resource: str
    detail: str
    severity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "resource": self.resource,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class TFStateReport:
    version: int | None = None
    terraform_version: str | None = None
    backend: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    sensitive_outputs: list[str] = field(default_factory=list)
    secrets: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # resource, key, value snippet
    resources: int = 0
    providers: set[str] = field(default_factory=set)
    findings: list[TFStateFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "terraform_version": self.terraform_version,
            "backend": self.backend,
            "resources": self.resources,
            "providers": sorted(self.providers),
            "outputs": list(self.outputs.keys()),
            "sensitive_outputs": list(self.sensitive_outputs),
            "secrets_found": len(self.secrets),
            "findings": [f.to_dict() for f in self.findings],
        }


def _walk_secrets(obj: Any, resource: str, report: TFStateReport, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{path}.{k}" if path else k
            key_lower = k.lower()
            if key_lower in _SECRET_KEYS and isinstance(v, str) and v:
                report.secrets.append((resource, key_path, v[:80]))
                report.findings.append(
                    TFStateFinding(
                        kind="plaintext_secret",
                        resource=resource,
                        detail=f"{key_path} contains a plaintext value",
                        severity="high",
                    )
                )
            _walk_secrets(v, resource, report, key_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_secrets(item, resource, report, f"{path}[{i}]")


def analyze_tfstate(data: str | dict[str, Any]) -> TFStateReport:
    """Parse and audit a Terraform state file payload."""
    if isinstance(data, str):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            r = TFStateReport()
            r.findings.append(
                TFStateFinding(kind="parse-error", resource="-", detail="Invalid JSON")
            )
            return r
    else:
        payload = data

    report = TFStateReport(
        version=payload.get("version"),
        terraform_version=payload.get("terraform_version"),
        backend=(payload.get("backend") or {}).get("type"),
    )

    outputs = payload.get("outputs") or {}
    for name, meta in outputs.items():
        report.outputs[name] = meta.get("value")
        if meta.get("sensitive"):
            report.sensitive_outputs.append(name)
            report.findings.append(
                TFStateFinding(
                    kind="sensitive_output",
                    resource=f"output.{name}",
                    detail="Output marked sensitive — value stored in cleartext in state.",
                    severity="high",
                )
            )

    resources = payload.get("resources") or []
    for r in resources:
        provider = r.get("provider", "")
        if provider:
            report.providers.add(provider)
        name = f"{r.get('mode', '?')}.{r.get('type', '?')}.{r.get('name', '?')}"
        report.resources += 1
        for inst in r.get("instances") or []:
            attrs = inst.get("attributes") or {}
            _walk_secrets(attrs, name, report)

    return report
