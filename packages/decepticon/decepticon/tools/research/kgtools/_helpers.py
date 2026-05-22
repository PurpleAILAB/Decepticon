from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from decepticon.tools.research._state import _json, _load
from decepticon.tools.research.graph import (
    SEVERITY_SCORE,
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)


def _open_ingest_file(path: str) -> tuple[KnowledgeGraph, Path, Path] | str:
    """Load the graph and validate that *path* exists on disk.

    Returns ``(graph, file_path, compat_out_path)`` on success,
    or a JSON error string that the caller should return immediately.
    """
    graph, out_path = _load()
    p = Path(path)
    if not p.exists():
        return _json({"error": f"file not found: {path}"})
    return graph, p, out_path


def _parse_props(props_json: str) -> dict[str, Any]:
    if not props_json:
        return {}
    try:
        parsed = json.loads(props_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"props must be valid JSON: {e}") from None
    if not isinstance(parsed, dict):
        raise ValueError("props must be a JSON object")
    return parsed


def _severity_from_score(score: float) -> Severity:
    if score >= 9.0:
        return Severity.CRITICAL
    if score >= 7.0:
        return Severity.HIGH
    if score >= 4.0:
        return Severity.MEDIUM
    if score > 0.0:
        return Severity.LOW
    return Severity.INFO


def _severity_from_string(value: str | None) -> Severity:
    if not value:
        return Severity.MEDIUM
    normalized = value.strip().lower()
    mapping = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
        "info": Severity.INFO,
        "informational": Severity.INFO,
    }
    return mapping.get(normalized, Severity.MEDIUM)


def _is_web_port(port: int) -> bool:
    return port in {80, 81, 443, 3000, 5000, 7001, 8000, 8008, 8080, 8443, 8888}


def _severity_threshold(sev: Severity) -> float:
    return SEVERITY_SCORE.get(sev, 0.0)


def _jwt_finding_severity(finding: str) -> Severity:
    text = finding.lower()
    if "alg=none" in text:
        return Severity.CRITICAL
    if "key confusion" in text or "path traversal" in text:
        return Severity.HIGH
    if "no exp" in text or "expired" in text:
        return Severity.MEDIUM
    return Severity.LOW


def _cookie_finding_severity(finding: str) -> Severity:
    text = finding.lower()
    if "predictable session" in text:
        return Severity.HIGH
    if "httponly not set" in text or "samesite" in text:
        return Severity.MEDIUM
    if "secure flag not set" in text:
        return Severity.MEDIUM
    return Severity.LOW


def _ensure_host_node(
    graph: KnowledgeGraph,
    *,
    label: str,
    key: str,
    **props: Any,
) -> Node:
    return graph.upsert_node(Node.make(NodeKind.HOST, label, key=key, **props))


def _ensure_service_node(
    graph: KnowledgeGraph,
    *,
    host: Node,
    host_label: str,
    port: int,
    proto: str,
    **props: Any,
) -> Node:
    label = f"{host_label}:{port}/{proto}"
    service = graph.upsert_node(
        Node.make(
            NodeKind.SERVICE,
            label,
            key=f"service::{host_label}:{port}/{proto}",
            host=host_label,
            port=port,
            protocol=proto,
            **props,
        )
    )
    graph.upsert_edge(Edge.make(host.id, service.id, EdgeKind.EXPOSES, weight=0.6))
    graph.upsert_edge(Edge.make(service.id, host.id, EdgeKind.HOSTS, weight=0.6))
    return service


def _ensure_entrypoint_node(
    graph: KnowledgeGraph,
    *,
    host_label: str,
    port: int,
    source: str,
) -> Node:
    scheme = "https" if port in {443, 8443} else "http"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    endpoint = f"{scheme}://{host_label}/" if default_port else f"{scheme}://{host_label}:{port}/"
    return graph.upsert_node(
        Node.make(
            NodeKind.ENTRYPOINT,
            endpoint,
            key=f"entrypoint::{endpoint}",
            source=source,
            host=host_label,
            port=port,
            scheme=scheme,
        )
    )


def _iter_requirements(path: Path) -> list[tuple[str, str, str]]:
    deps: list[tuple[str, str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()
        line = line.split("#", 1)[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-+]+)$", line)
        if m:
            deps.append((m.group(1), m.group(2), "PyPI"))
    return deps


def _iter_package_lock(path: Path) -> list[tuple[str, str, str]]:
    deps: list[tuple[str, str, str]] = []
    payload = json.loads(path.read_text(encoding="utf-8"))

    packages = payload.get("packages")
    if isinstance(packages, dict):
        for pkg_path, meta in packages.items():
            if not pkg_path.startswith("node_modules/"):
                continue
            if not isinstance(meta, dict):
                continue
            name = meta.get("name") or pkg_path.rsplit("node_modules/", 1)[-1]
            version = meta.get("version")
            if isinstance(name, str) and isinstance(version, str):
                deps.append((name, version, "npm"))
        return deps

    # npm lockfile v1 fallback
    stack = [payload.get("dependencies", {})]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        for name, meta in cur.items():
            if not isinstance(meta, dict):
                continue
            version = meta.get("version")
            if isinstance(name, str) and isinstance(version, str):
                deps.append((name, version, "npm"))
            nested = meta.get("dependencies")
            if isinstance(nested, dict):
                stack.append(nested)
    return deps


def _iter_go_sum(path: Path) -> list[tuple[str, str, str]]:
    deps: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        module = parts[0]
        version = parts[1]
        if module.endswith("/go.mod"):
            module = module[: -len("/go.mod")]
        if version.endswith("/go.mod"):
            version = version[: -len("/go.mod")]
        key = (module, version)
        if key in seen:
            continue
        seen.add(key)
        deps.append((module, version, "Go"))
    return deps


def _iter_cargo_lock(path: Path) -> list[tuple[str, str, str]]:
    deps: list[tuple[str, str, str]] = []
    # Cargo.lock is TOML-like; avoid external deps with a tiny parser.
    current_name: str | None = None
    current_ver: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "[[package]]":
            if current_name and current_ver:
                deps.append((current_name, current_ver, "crates.io"))
            current_name = None
            current_ver = None
            continue
        if line.startswith("name = "):
            current_name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version = "):
            current_ver = line.split("=", 1)[1].strip().strip('"')
    if current_name and current_ver:
        deps.append((current_name, current_ver, "crates.io"))
    return deps


def _parse_dependencies(path: Path) -> list[tuple[str, str, str]]:
    name = path.name.lower()
    if name == "requirements.txt":
        return _iter_requirements(path)
    if name == "package-lock.json":
        return _iter_package_lock(path)
    if name == "go.sum":
        return _iter_go_sum(path)
    if name == "cargo.lock":
        return _iter_cargo_lock(path)
    return []
