"""Bugcrowd CSV submission writer.

Bugcrowd accepts bulk finding imports as CSV with columns:
``title,severity,cwe,url,description,recommendation,poc``.

This renderer writes a valid CSV to disk from a list of vulnerability
nodes so an engagement's entire finding set can be submitted in one
upload.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable

from decepticon.tools.research.graph import KnowledgeGraph, NodeKind

_HEADER: tuple[str, ...] = (
    "title",
    "severity",
    "cwe",
    "url",
    "description",
    "recommendation",
    "poc",
    "cvss_vector",
    "cvss_score",
)


def render_bugcrowd_csv(
    graph: KnowledgeGraph,
    *,
    include_kinds: Iterable[NodeKind] = (NodeKind.VULNERABILITY, NodeKind.FINDING),
    min_severity: str | None = None,
) -> str:
    """Render a Bugcrowd CSV from all matching graph nodes."""
    severity_order = ["info", "low", "medium", "high", "critical"]
    min_rank = severity_order.index(min_severity) if min_severity in severity_order else 0

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_HEADER)

    include_set = set(include_kinds)
    for node in sorted(graph.nodes.values(), key=lambda n: n.created_at):
        if node.kind not in include_set:
            continue
        sev = node.props.get("severity", "info")
        if sev not in severity_order or severity_order.index(sev) < min_rank:
            continue
        cwe_list = node.props.get("cwe") or []
        if isinstance(cwe_list, list):
            cwe = ",".join(cwe_list)
        else:
            cwe = str(cwe_list)
        writer.writerow(
            [
                node.label[:240],
                sev,
                cwe,
                node.props.get("url") or node.props.get("file") or "",
                (node.props.get("description") or node.props.get("summary") or "")[:2000],
                node.props.get("recommendation") or "",
                (node.props.get("poc_command") or node.props.get("stdout_excerpt") or "")[:2000],
                node.props.get("cvss_vector") or "",
                node.props.get("cvss_score") or "",
            ]
        )

    return buf.getvalue()
