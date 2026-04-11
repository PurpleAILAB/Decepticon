"""Slither JSON → KnowledgeGraph ingestion.

Slither (https://github.com/crytic/slither) is the de-facto Solidity
static analyser. Its ``--json -`` output contains a ``results.detectors``
array of structured findings that we lift into the graph alongside
pattern-scanner output and SARIF from other tools.

This module is pure parsing — the agent calls Slither via bash, saves
JSON to the sandbox, then invokes ``ingest_slither_json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decepticon.core.logging import get_logger
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)

log = get_logger("contracts.slither")

_IMPACT_TO_SEVERITY: dict[str, Severity] = {
    "High": Severity.HIGH,
    "Medium": Severity.MEDIUM,
    "Low": Severity.LOW,
    "Informational": Severity.INFO,
    "Optimization": Severity.INFO,
}


def ingest_slither_json(data: str | dict[str, Any], graph: KnowledgeGraph) -> int:
    """Merge a Slither JSON output into ``graph``.

    ``data`` may be a JSON string or a pre-parsed dict. Returns the count
    of ingested detector results.
    """
    if isinstance(data, str):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            log.warning("slither json parse failed: %s", e)
            return 0
    else:
        payload = data

    results = (
        payload.get("results", {}).get("detectors")
        if isinstance(payload.get("results"), dict)
        else None
    )
    if not results:
        return 0

    count = 0
    for det in results:
        check = det.get("check") or "unknown"
        impact = det.get("impact", "Medium")
        confidence = det.get("confidence", "Medium")
        description = det.get("description") or ""
        markdown = det.get("markdown") or ""
        severity = _IMPACT_TO_SEVERITY.get(impact, Severity.MEDIUM)

        # Walk elements to extract (file, line) tuples
        elements = det.get("elements") or []
        file_path: str | None = None
        line: int | None = None
        for el in elements:
            src = el.get("source_mapping") or {}
            if src.get("filename_relative") or src.get("filename_absolute"):
                file_path = src.get("filename_relative") or src.get("filename_absolute")
                lines = src.get("lines") or []
                if lines:
                    line = lines[0]
                break

        key = f"slither::{check}::{file_path}::{line}"
        label = f"[slither:{check}] {description.strip().splitlines()[0][:80] if description else check}"
        vuln_props: dict[str, Any] = {
            "key": key,
            "scanner": "slither",
            "rule_id": check,
            "severity": severity.value,
            "confidence": confidence,
            "description": description,
            "markdown": markdown[:2000],
            "file": file_path,
            "line": line,
        }
        vuln = Node.make(NodeKind.VULNERABILITY, label, **vuln_props)
        graph.upsert_node(vuln)

        if file_path:
            loc_label = f"{file_path}:{line}" if line else file_path
            loc = Node.make(
                NodeKind.CODE_LOCATION,
                loc_label,
                key=f"{file_path}::{line}",
                file=file_path,
                start_line=line,
            )
            graph.upsert_node(loc)
            graph.upsert_edge(Edge.make(vuln.id, loc.id, EdgeKind.DEFINED_IN))
            file_node = Node.make(NodeKind.SOURCE_FILE, file_path, key=file_path)
            graph.upsert_node(file_node)
            graph.upsert_edge(Edge.make(loc.id, file_node.id, EdgeKind.DEFINED_IN))

        count += 1

    return count


def ingest_slither_file(path: str | Path, graph: KnowledgeGraph) -> int:
    """Convenience wrapper: read JSON from disk and ingest."""
    p = Path(path)
    try:
        data = p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("slither file read failed: %s", e)
        return 0
    return ingest_slither_json(data, graph)
