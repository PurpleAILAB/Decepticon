"""LangChain @tool wrappers for the reporting package."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.reporting.bugcrowd import render_bugcrowd_csv
from decepticon.tools.reporting.executive import render_executive_summary
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
    export_attack_navigator,
]
