"""LangChain @tool wrappers for the reporting package."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.reporting.bugcrowd import render_bugcrowd_csv
from decepticon.tools.reporting.executive import render_executive_summary
from decepticon.tools.reporting.findings_export import (
    write_finding_pack,
    write_findings_index,
)
from decepticon.tools.reporting.hackerone import render_hackerone_markdown
from decepticon.tools.reporting.timeline import extract_timeline
from decepticon.tools.research._state import _load
from decepticon.tools.research.attack.navigator import build_navigator_layer


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def report_hackerone(finding_id: str) -> str:
    """Render a HackerOne-style markdown report for a finding or vulnerability node."""
    graph, _ = _load()
    node = graph.nodes.get(finding_id)
    if node is None:
        return _json({"error": f"no node {finding_id} in graph"})
    md = render_hackerone_markdown(node, graph=graph)
    return _json({"id": finding_id, "markdown": md})


@tool
def report_bugcrowd_csv(min_severity: str = "medium") -> str:
    """Render the current graph as a Bugcrowd CSV submission bundle."""
    graph, _ = _load()
    csv = render_bugcrowd_csv(graph, min_severity=min_severity)
    return _json({"rows": csv.count("\n") - 1, "csv": csv})


@tool
def report_executive(engagement_name: str = "Engagement") -> str:
    """Produce an engagement-level executive summary from the graph."""
    graph, _ = _load()
    md = render_executive_summary(graph, engagement_name=engagement_name)
    return _json({"markdown": md})


@tool
def report_timeline() -> str:
    """Extract a chronological timeline of graph events."""
    graph, _ = _load()
    events = extract_timeline(graph)
    return _json({"count": len(events), "events": [e.to_dict() for e in events]})


def _findings_root(engagement_path: str | None = None) -> Path:
    """Resolve the directory under which finding packs are written.

    Priority: explicit ``engagement_path`` arg → ``DECEPTICON_FINDINGS_ROOT`` env
    → ``/workspace/findings`` (the in-sandbox engagement convention).
    """
    if engagement_path:
        return Path(engagement_path) / "findings"
    env = os.environ.get("DECEPTICON_FINDINGS_ROOT")
    if env:
        return Path(env)
    return Path("/workspace/findings")


@tool
def export_finding_pack(
    finding_id: str,
    engagement_path: str = "",
    overwrite: bool = False,
) -> str:
    """Export a single finding to a Strix-style portable pack on disk.

    Writes ``<engagement>/findings/<slug>-<digest>/`` with README.md,
    repro.md, poc.<ext>, manifest.json, evidence/. The receiving team can
    rerun the PoC without the Decepticon graph backend.

    Args:
        finding_id: Node ID in the active knowledge graph.
        engagement_path: Optional engagement root override. Defaults to
            ``$DECEPTICON_FINDINGS_ROOT`` or ``/workspace/findings``.
        overwrite: When True, replaces an existing pack directory.
    """
    graph, _ = _load()
    node = graph.nodes.get(finding_id)
    if node is None:
        return _json({"error": f"no node {finding_id} in graph"})
    pack = write_finding_pack(
        node.model_dump(mode="json"),
        output_root=_findings_root(engagement_path or None),
        finding_id=finding_id,
        overwrite=overwrite,
    )
    return _json(pack.to_dict())


@tool
def export_all_findings(engagement_path: str = "", min_severity: str = "low") -> str:
    """Export every Finding/Vulnerability node in the graph as packs + index.

    Iterates the knowledge graph, writes one pack per finding-shaped node,
    and regenerates the ``findings/INDEX.md`` summary. Returns a JSON
    summary of pack count + index path.

    Args:
        engagement_path: Optional engagement root override.
        min_severity: Skip findings whose ``props.severity`` is below this
            threshold (low/medium/high/critical). Default ``low`` exports
            everything.
    """
    severity_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    threshold = severity_order.get(min_severity.lower(), 0)
    graph, _ = _load()
    out_root = _findings_root(engagement_path or None)
    out_root.mkdir(parents=True, exist_ok=True)
    packs = []
    for node in graph.nodes.values():
        kind = getattr(node.kind, "value", str(node.kind)).lower()
        if kind not in {"finding", "vulnerability", "vuln"}:
            continue
        sev = str(node.props.get("severity", "")).lower()
        if severity_order.get(sev, 0) < threshold:
            continue
        pack = write_finding_pack(
            node.model_dump(mode="json"),
            output_root=out_root,
            finding_id=node.id,
            overwrite=True,
        )
        packs.append(pack)
    index = write_findings_index(packs, output_root=out_root)
    return _json(
        {
            "exported": len(packs),
            "index": str(index),
            "root": str(out_root),
            "packs": [p.to_dict() for p in packs],
        }
    )


@tool
def export_attack_navigator(engagement_name: str = "Engagement") -> str:
    """Export a MITRE ATT&CK Navigator layer of this engagement's coverage.

    Every technique a finding maps to becomes a colored cell — green where
    the blue team detected the activity, red for a detection gap. Write the
    returned JSON to ``report/attack-navigator.json`` and open it at
    https://mitre-attack.github.io/attack-navigator/ to view the heatmap.

    Args:
        engagement_name: Engagement name, used as the layer title.

    Returns:
        The ATT&CK Navigator v4.5 layer as JSON — write it verbatim to a
        ``.json`` file.
    """
    graph, _ = _load()
    layer = build_navigator_layer(graph, engagement_name)
    return _json(layer)


REPORTING_TOOLS = [
    report_hackerone,
    report_bugcrowd_csv,
    report_executive,
    report_timeline,
    export_finding_pack,
    export_all_findings,
    export_attack_navigator,
]
