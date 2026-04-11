"""SARIF → KnowledgeGraph ingestion.

SARIF (Static Analysis Results Interchange Format — OASIS standard) is the
common output format for modern scanners: semgrep, CodeQL, bandit, gitleaks,
trivy, snyk, nuclei (optional), grype. Rather than writing a bespoke parser
per tool, Decepticon ingests SARIF universally and lifts every ``result`` into
a Vulnerability/Finding pair in the knowledge graph.

Example flow
------------
    analyst agent: runs ``semgrep --sarif --config auto /workspace/src > out.sarif``
    then calls ingest_sarif_file("out.sarif") → graph gets ~N vuln nodes

Severity mapping
----------------
SARIF uses ``level`` (note/warning/error) and optional ``properties.security-severity``
(a 0-10 CVSS-like number). We map both into :class:`Severity`.
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

log = get_logger("research.sarif")


# ── Severity mapping ────────────────────────────────────────────────────

_LEVEL_TO_SEVERITY: dict[str, Severity] = {
    "none": Severity.INFO,
    "note": Severity.INFO,
    "warning": Severity.MEDIUM,
    "error": Severity.HIGH,
}


def _severity_from_score(score: float) -> Severity:
    """Map CVSS-like 0..10 score to qualitative severity."""
    if score >= 9.0:
        return Severity.CRITICAL
    if score >= 7.0:
        return Severity.HIGH
    if score >= 4.0:
        return Severity.MEDIUM
    if score >= 0.1:
        return Severity.LOW
    return Severity.INFO


def _result_severity(result: dict[str, Any], rule: dict[str, Any] | None) -> Severity:
    """Derive severity from SARIF result, preferring security-severity over level."""
    props = (result.get("properties") or {}) if result else {}
    rule_props = (rule.get("properties") or {}) if rule else {}

    # 1. Result-level security-severity
    sev_score = props.get("security-severity") or rule_props.get("security-severity")
    if sev_score is not None:
        try:
            return _severity_from_score(float(sev_score))
        except (TypeError, ValueError):
            pass

    # 2. Rule-level tags (semgrep puts "HIGH"/"CRITICAL" here)
    for tag in rule_props.get("tags") or []:
        tag_upper = tag.upper() if isinstance(tag, str) else ""
        if tag_upper in Severity.__members__:
            return Severity[tag_upper]

    # 3. SARIF level
    level = (result.get("level") or "warning").lower()
    return _LEVEL_TO_SEVERITY.get(level, Severity.MEDIUM)


# ── Rule index ──────────────────────────────────────────────────────────


def _build_rule_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a rule-id → rule-dict index from a SARIF ``run``."""
    tool = run.get("tool") or {}
    driver = tool.get("driver") or {}
    rules = driver.get("rules") or []
    extensions = tool.get("extensions") or []
    index: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rid = rule.get("id")
        if rid:
            index[rid] = rule
    # Extensions (e.g. semgrep packs) carry additional rule definitions
    for ext in extensions:
        for rule in ext.get("rules") or []:
            rid = rule.get("id")
            if rid and rid not in index:
                index[rid] = rule
    return index


def _result_location(result: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """Extract (file, start_line, end_line) from a SARIF result."""
    locs = result.get("locations") or []
    if not locs:
        return None, None, None
    phys = locs[0].get("physicalLocation") or {}
    artifact = phys.get("artifactLocation") or {}
    uri = artifact.get("uri")
    region = phys.get("region") or {}
    start = region.get("startLine")
    end = region.get("endLine") or start
    return uri, start, end


def _result_message(result: dict[str, Any]) -> str:
    """Extract a human-readable message from a SARIF result."""
    msg = result.get("message")
    if isinstance(msg, dict):
        return msg.get("text") or msg.get("markdown") or ""
    if isinstance(msg, str):
        return msg
    return ""


# ── Ingestion ───────────────────────────────────────────────────────────


def ingest_sarif(
    sarif: dict[str, Any],
    graph: KnowledgeGraph,
    *,
    scanner_hint: str | None = None,
) -> int:
    """Merge a parsed SARIF document into ``graph``.

    Returns the number of results ingested. Scanner identity is recorded on
    each vulnerability as ``props["scanner"]``. If ``scanner_hint`` is given
    it takes precedence over the SARIF driver name (useful when an agent
    already knows the tool but the SARIF is anonymised).
    """
    runs = sarif.get("runs") or []
    total = 0

    for run in runs:
        tool = run.get("tool") or {}
        driver = tool.get("driver") or {}
        scanner = scanner_hint or driver.get("name") or "unknown"
        rule_index = _build_rule_index(run)

        for result in run.get("results") or []:
            rule_id = result.get("ruleId") or "unknown-rule"
            rule = rule_index.get(rule_id)
            severity = _result_severity(result, rule)
            uri, start_line, end_line = _result_location(result)
            message = _result_message(result)

            # Build vulnerability node — dedup across scans by (scanner, rule, file, line)
            vuln_key = f"{scanner}::{rule_id}::{uri}::{start_line}"
            vuln_label = f"[{scanner}:{rule_id}] {message[:80]}"
            vuln_props: dict[str, Any] = {
                "key": vuln_key,
                "scanner": scanner,
                "rule_id": rule_id,
                "severity": severity.value,
                "message": message,
                "file": uri,
                "start_line": start_line,
                "end_line": end_line,
            }
            if rule is not None:
                short = (rule.get("shortDescription") or {}).get("text")
                full = (rule.get("fullDescription") or {}).get("text")
                help_ = (rule.get("help") or {}).get("text")
                if short:
                    vuln_props["short_description"] = short
                if full:
                    vuln_props["description"] = full
                if help_:
                    vuln_props["help"] = help_
                props = rule.get("properties") or {}
                tags = props.get("tags") or []
                if tags:
                    vuln_props["tags"] = tags
                # CWE from tags (semgrep uses "cwe:CWE-89" style)
                cwes = [
                    t.replace("cwe:", "").upper()
                    for t in tags
                    if isinstance(t, str) and t.lower().startswith("cwe:")
                ]
                if cwes:
                    vuln_props["cwe"] = cwes

            vuln_node = Node.make(NodeKind.VULNERABILITY, vuln_label, **vuln_props)
            graph.upsert_node(vuln_node)

            # Code location node — groups multiple vulns in the same span
            if uri:
                loc_label = f"{uri}:{start_line}" if start_line else uri
                loc_node = Node.make(
                    NodeKind.CODE_LOCATION,
                    loc_label,
                    key=f"{uri}::{start_line}",
                    file=uri,
                    start_line=start_line,
                    end_line=end_line,
                )
                graph.upsert_node(loc_node)
                graph.upsert_edge(Edge.make(vuln_node.id, loc_node.id, EdgeKind.DEFINED_IN))

                file_node = Node.make(NodeKind.SOURCE_FILE, uri, key=uri)
                graph.upsert_node(file_node)
                graph.upsert_edge(Edge.make(loc_node.id, file_node.id, EdgeKind.DEFINED_IN))

            total += 1

    return total


def ingest_sarif_file(
    path: str | Path,
    graph: KnowledgeGraph,
    *,
    scanner_hint: str | None = None,
) -> int:
    """Convenience wrapper: read SARIF JSON from disk and ingest it."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("failed to read SARIF %s: %s", p, e)
        return 0
    return ingest_sarif(data, graph, scanner_hint=scanner_hint)
