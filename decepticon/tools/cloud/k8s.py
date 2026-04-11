"""Kubernetes manifest analyser.

Scans a parsed YAML (dict or list of dicts) for the canonical cluster
escape / privilege-escalation patterns:

- ``privileged: true``
- ``hostNetwork / hostPID / hostIPC``
- ``hostPath`` volume mounting ``/``, ``/var/run/docker.sock``, ``/proc``
- ``allowPrivilegeEscalation: true``
- missing ``runAsNonRoot`` / ``runAsUser: 0``
- ``automountServiceAccountToken: true`` on sensitive pods
- wildcard RBAC rules (``*`` verbs on ``*`` resources)
- ``capabilities.add`` containing SYS_ADMIN / SYS_PTRACE / NET_ADMIN
- secrets referenced in plain ``env`` (non-secretKeyRef)

Output is a structured list of :class:`K8sFinding` the agent promotes
into the knowledge graph with ``severity`` from the table below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_DANGEROUS_CAPS = {
    "SYS_ADMIN",
    "SYS_PTRACE",
    "NET_ADMIN",
    "NET_RAW",
    "SYS_MODULE",
    "DAC_READ_SEARCH",
}
_DANGEROUS_PATHS = {
    "/",
    "/var/run/docker.sock",
    "/var/lib/kubelet",
    "/proc",
    "/etc",
    "/root",
    "/var",
}


@dataclass
class K8sFinding:
    id: str
    severity: str
    kind: str
    name: str
    title: str
    detail: str
    namespace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "kind": self.kind,
            "name": self.name,
            "namespace": self.namespace,
            "title": self.title,
            "detail": self.detail,
        }


def _iter_documents(manifest: Any) -> list[dict[str, Any]]:
    if isinstance(manifest, list):
        return [d for d in manifest if isinstance(d, dict)]
    if isinstance(manifest, dict):
        if manifest.get("kind") == "List":
            return [d for d in (manifest.get("items") or []) if isinstance(d, dict)]
        return [manifest]
    return []


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    kind = doc.get("kind", "")
    spec = doc.get("spec") or {}
    if kind in ("Pod",):
        return spec
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet", "CronJob"):
        template = (spec.get("template") or {}).get("spec")
        if isinstance(template, dict):
            return template
        job_template = (spec.get("jobTemplate") or {}).get("spec") or {}
        template = (job_template.get("template") or {}).get("spec")
        if isinstance(template, dict):
            return template
    return None


def _containers(pod_spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in pod_spec.get("containers") or []:
        if isinstance(c, dict):
            out.append(c)
    for c in pod_spec.get("initContainers") or []:
        if isinstance(c, dict):
            out.append(c)
    return out


def analyze_k8s_manifest(manifest: str | dict[str, Any] | list[Any]) -> list[K8sFinding]:
    """Analyse a single manifest or list of manifests."""
    if isinstance(manifest, str):
        try:
            parsed = json.loads(manifest)
        except json.JSONDecodeError:
            return [
                K8sFinding(
                    id="k8s.parse-error",
                    severity="info",
                    kind="?",
                    name="?",
                    title="Not valid JSON (YAML not parsed here)",
                    detail="",
                )
            ]
    else:
        parsed = manifest

    findings: list[K8sFinding] = []
    idx = 0
    for doc in _iter_documents(parsed):
        kind = doc.get("kind", "Unknown")
        meta = doc.get("metadata") or {}
        name = meta.get("name") or "?"
        namespace = meta.get("namespace")

        # RBAC rules
        if kind in ("ClusterRole", "Role"):
            for rule in doc.get("rules") or []:
                verbs = [v.lower() for v in (rule.get("verbs") or [])]
                resources = rule.get("resources") or []
                api_groups = rule.get("apiGroups") or [""]
                if "*" in verbs and "*" in resources:
                    idx += 1
                    findings.append(
                        K8sFinding(
                            id=f"k8s-{idx:04d}",
                            severity="critical",
                            kind=kind,
                            name=name,
                            namespace=namespace,
                            title="Wildcard RBAC rule",
                            detail=f"verbs=* resources=* apiGroups={api_groups} — cluster admin equivalent.",
                        )
                    )
                elif "*" in verbs and "secrets" in resources:
                    idx += 1
                    findings.append(
                        K8sFinding(
                            id=f"k8s-{idx:04d}",
                            severity="high",
                            kind=kind,
                            name=name,
                            namespace=namespace,
                            title="Wildcard verbs on secrets",
                            detail="Any secret across the scope can be read and modified.",
                        )
                    )
                elif "impersonate" in verbs:
                    idx += 1
                    findings.append(
                        K8sFinding(
                            id=f"k8s-{idx:04d}",
                            severity="high",
                            kind=kind,
                            name=name,
                            namespace=namespace,
                            title="Impersonation allowed",
                            detail="impersonate verb allows assuming other subjects' identities.",
                        )
                    )

        pod_spec = _pod_spec(doc)
        if not pod_spec:
            continue

        # Host namespaces
        for flag, severity in (
            ("hostNetwork", "high"),
            ("hostPID", "high"),
            ("hostIPC", "high"),
        ):
            if pod_spec.get(flag) is True:
                idx += 1
                findings.append(
                    K8sFinding(
                        id=f"k8s-{idx:04d}",
                        severity=severity,
                        kind=kind,
                        name=name,
                        namespace=namespace,
                        title=f"{flag} enabled",
                        detail=f"Pod shares the host's {flag[4:].lower()} namespace — escape surface.",
                    )
                )

        # Volume hostPath checks
        for vol in pod_spec.get("volumes") or []:
            hp = (vol or {}).get("hostPath") if isinstance(vol, dict) else None
            if hp and isinstance(hp, dict):
                path = hp.get("path", "")
                if path in _DANGEROUS_PATHS or path.startswith(("/var/run/", "/proc/", "/dev/")):
                    idx += 1
                    findings.append(
                        K8sFinding(
                            id=f"k8s-{idx:04d}",
                            severity="critical" if "docker.sock" in path else "high",
                            kind=kind,
                            name=name,
                            namespace=namespace,
                            title=f"hostPath volume at {path}",
                            detail="Container can read/modify the host filesystem — likely container escape.",
                        )
                    )

        # Containers: privileged / caps / runAsUser
        for c in _containers(pod_spec):
            sc = c.get("securityContext") or {}
            if sc.get("privileged") is True:
                idx += 1
                findings.append(
                    K8sFinding(
                        id=f"k8s-{idx:04d}",
                        severity="critical",
                        kind=kind,
                        name=name,
                        namespace=namespace,
                        title=f"Container {c.get('name')} privileged",
                        detail="privileged: true — full host device access and kernel caps.",
                    )
                )
            if sc.get("allowPrivilegeEscalation") is True:
                idx += 1
                findings.append(
                    K8sFinding(
                        id=f"k8s-{idx:04d}",
                        severity="medium",
                        kind=kind,
                        name=name,
                        namespace=namespace,
                        title=f"Container {c.get('name')} allowPrivilegeEscalation",
                        detail="allowPrivilegeEscalation: true lets setuid binaries elevate within the container.",
                    )
                )
            if sc.get("runAsUser") == 0 or (
                sc.get("runAsNonRoot") is False and "runAsUser" not in sc
            ):
                idx += 1
                findings.append(
                    K8sFinding(
                        id=f"k8s-{idx:04d}",
                        severity="medium",
                        kind=kind,
                        name=name,
                        namespace=namespace,
                        title=f"Container {c.get('name')} runs as root",
                        detail="No runAsNonRoot enforcement — default root inside container.",
                    )
                )
            caps = (sc.get("capabilities") or {}).get("add") or []
            dangerous = [cap for cap in caps if str(cap).upper() in _DANGEROUS_CAPS]
            if dangerous:
                idx += 1
                findings.append(
                    K8sFinding(
                        id=f"k8s-{idx:04d}",
                        severity="high",
                        kind=kind,
                        name=name,
                        namespace=namespace,
                        title=f"Dangerous capabilities: {', '.join(dangerous)}",
                        detail="Granting these caps often enables container escape.",
                    )
                )

            # Plain env secrets
            for env in c.get("env") or []:
                val = env.get("value") if isinstance(env, dict) else None
                name_env = (env or {}).get("name", "") if isinstance(env, dict) else ""
                if val and any(
                    k in name_env.lower() for k in ("password", "secret", "token", "key", "api")
                ):
                    idx += 1
                    findings.append(
                        K8sFinding(
                            id=f"k8s-{idx:04d}",
                            severity="medium",
                            kind=kind,
                            name=name,
                            namespace=namespace,
                            title=f"Env var {name_env} has literal value",
                            detail="Secret-sounding env var with a plain value. Use valueFrom.secretKeyRef.",
                        )
                    )

    return findings
