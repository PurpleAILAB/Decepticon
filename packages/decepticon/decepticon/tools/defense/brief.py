"""Defense Brief — the customer-facing detection-coverage deliverable.

Reads the engagement knowledge graph that Blue Cell (``DetectionFired`` /
``DETECTED``) and the Defender (``DefenseAction``) populated, and renders the
proven-coverage report documented in ``docs/features/blue-cell.md``: coverage
%, MTTD stats, the detected-technique table (slowest first), the detection-gap
list (Findings nothing caught), and the deployed-rule inventory — plus an
ATT&CK Navigator layer the customer's SOC can open directly.

The numbers are computed deterministically from the graph; the Blue Cell agent
adds the judgement layer (no-rule vs rule-too-strict, proposed improvements).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.defense.blue_cell import node_techniques
from decepticon.tools.research._state import _json, _load
from decepticon_core.types.kg import EdgeKind, KnowledgeGraph, NodeKind

# ATT&CK Navigator layer colours: detection fired vs detection gap.
_NAV_DETECTED = "#2ecc71"
_NAV_GAP = "#e74c3c"


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0, 1]). Empty → 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = q * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)


def _is_detected(graph: KnowledgeGraph, finding_id: str) -> bool:
    return bool(graph.neighbors(finding_id, edge_kind=EdgeKind.DETECTED, direction="in"))


def build_defense_brief(
    graph: KnowledgeGraph, *, engagement_name: str = "Engagement"
) -> dict[str, Any]:
    """Compute the structured detection-coverage brief from the graph."""
    findings = graph.by_kind(NodeKind.FINDING)
    detected_ids = {f.id for f in findings if _is_detected(graph, f.id)}
    detected_findings = [f for f in findings if f.id in detected_ids]
    gap_findings = [f for f in findings if f.id not in detected_ids]

    # Detected techniques: from the rules that actually fired. Keep the
    # fastest (min MTTD) detection per technique.
    detected_tech: dict[str, dict[str, Any]] = {}
    mttds: list[float] = []
    event_ts: list[float] = []
    for fired in graph.by_kind(NodeKind.DETECTION_FIRED):
        mttd = float(fired.props.get("mttd_seconds", 0.0) or 0.0)
        mttds.append(mttd)
        if "event_ts" in fired.props:
            event_ts.append(float(fired.props["event_ts"]))
        rule_id = str(fired.props.get("rule_id", ""))
        for technique in fired.props.get("mitre", []) or []:
            technique = str(technique)
            current = detected_tech.get(technique)
            if current is None or mttd < current["mttd_seconds"]:
                detected_tech[technique] = {
                    "technique": technique,
                    "mttd_seconds": round(mttd, 2),
                    "rule_id": rule_id,
                }

    gap_techniques: set[str] = set()
    for finding in gap_findings:
        gap_techniques |= node_techniques(finding)
    gap_techniques -= set(detected_tech)

    observed = len(findings)
    return {
        "engagement": engagement_name,
        "window": ({"start": min(event_ts), "end": max(event_ts)} if event_ts else None),
        "coverage": {
            "findings_observed": observed,
            "findings_detected": len(detected_findings),
            "findings_missed": len(gap_findings),
            "detected_pct": round(len(detected_findings) / observed * 100, 1) if observed else 0.0,
        },
        "mttd": {
            "median_seconds": round(statistics.median(mttds), 2) if mttds else None,
            "p95_seconds": round(_percentile(mttds, 0.95), 2) if mttds else None,
            "max_seconds": round(max(mttds), 2) if mttds else None,
        },
        "detected_techniques": sorted(
            detected_tech.values(), key=lambda d: d["mttd_seconds"], reverse=True
        ),
        "missed_techniques": sorted(gap_techniques),
        "detection_gaps": [
            {
                "finding": f.label,
                "techniques": sorted(node_techniques(f)),
                "severity": str(f.props.get("severity", "")),
            }
            for f in gap_findings
        ],
        "deployed_rules": [
            {
                "rule_id": str(a.props.get("rule_id", "")),
                "title": a.label,
                "mitre": [str(t) for t in (a.props.get("mitre", []) or [])],
                "siem_target": str(a.props.get("siem_target", "")),
                "status": str(a.props.get("status", "")),
            }
            for a in graph.by_kind(NodeKind.DEFENSE_ACTION)
        ],
    }


def render_brief_markdown(brief: dict[str, Any]) -> str:
    """Render the brief in the text form from docs/features/blue-cell.md."""
    cov, mttd = brief["coverage"], brief["mttd"]
    lines = [f"Engagement: {brief['engagement']}"]
    if brief["window"]:
        lines.append(f"Time window: {brief['window']['start']} -> {brief['window']['end']}")
    lines += [
        "",
        "Detection coverage:",
        f"   {cov['findings_observed']} findings observed",
        f"   {cov['findings_detected']} detected ({cov['detected_pct']}%)",
        f"   {cov['findings_missed']} missed",
    ]
    if mttd["median_seconds"] is not None:
        lines += [
            f"   median MTTD: {mttd['median_seconds']}s",
            f"   p95 MTTD: {mttd['p95_seconds']}s",
        ]

    lines += ["", "Detected techniques (slowest first):"]
    lines += [
        f"   {d['technique']} — fired in {d['mttd_seconds']}s (rule {d['rule_id']})"
        for d in brief["detected_techniques"]
    ] or ["   (none)"]

    lines += ["", "Detection gaps:"]
    lines += [
        f"   {g['finding']} [{', '.join(g['techniques']) or 'no technique mapped'}] — no detection fired"
        for g in brief["detection_gaps"]
    ] or ["   (none — full coverage)"]

    if brief["deployed_rules"]:
        lines += ["", "Deployed detections:"]
        lines += [
            f"   {r['rule_id']} -> {r['siem_target'] or 'unsent'} ({r['status'] or '?'})"
            for r in brief["deployed_rules"]
        ]
    return "\n".join(lines)


def build_navigator_layer(brief: dict[str, Any]) -> dict[str, Any]:
    """Build an ATT&CK Navigator layer: detected techniques green, gaps red."""
    techniques = [
        {
            "techniqueID": d["technique"],
            "score": 100,
            "color": _NAV_DETECTED,
            "comment": f"detected in {d['mttd_seconds']}s by {d['rule_id']}",
            "enabled": True,
        }
        for d in brief["detected_techniques"]
    ] + [
        {
            "techniqueID": technique,
            "score": 0,
            "color": _NAV_GAP,
            "comment": "detection gap — no rule fired",
            "enabled": True,
        }
        for technique in brief["missed_techniques"]
    ]
    return {
        "name": f"Decepticon Detection Coverage — {brief['engagement']}",
        "versions": {"layer": "4.5", "navigator": "4.9.5", "attack": "15"},
        "domain": "enterprise-attack",
        "description": (
            "Proven detection coverage from the Decepticon Offensive Vaccine loop. "
            "Green = a detection rule fired on this technique during the engagement; "
            "red = the technique ran but nothing detected it."
        ),
        "techniques": techniques,
        "legendItems": [
            {"label": "detection fired", "color": _NAV_DETECTED},
            {"label": "detection gap", "color": _NAV_GAP},
        ],
    }


@tool
def defense_brief(engagement_name: str = "Engagement") -> str:
    """Render the engagement's proven detection-coverage brief from the graph.

    Reads the DetectionFired / DETECTED / DefenseAction state Blue Cell and the
    Defender wrote, and returns the coverage %, MTTD stats, detected-technique
    table, detection-gap list, and deployed-rule inventory — both as structured
    fields and as a ready-to-paste markdown brief.

    WHEN TO USE: at engagement out-brief, after ``blue_cell_scan`` has recorded
    coverage, to produce the customer's Detection Coverage deliverable.

    Args:
        engagement_name: Name shown in the brief header.

    Returns:
        JSON with ``markdown`` plus ``coverage`` / ``mttd`` /
        ``detected_techniques`` / ``detection_gaps`` / ``deployed_rules``.
    """
    graph, _ = _load()
    brief = build_defense_brief(graph, engagement_name=engagement_name)
    return _json({**brief, "markdown": render_brief_markdown(brief)})


@tool
def export_attack_navigator(output_path: str, engagement_name: str = "Engagement") -> str:
    """Write an ATT&CK Navigator layer of the engagement's detection coverage.

    Produces a Navigator-importable JSON layer (detected techniques green,
    detection gaps red) so the customer's SOC can see exactly what the kill
    chain exercised and what their detections caught. Writes UTF-8 to
    ``output_path`` (parent dirs created).

    Args:
        output_path: Destination ``.json`` path for the layer.
        engagement_name: Name shown in the layer title.

    Returns:
        JSON summary: written path, technique count, and byte size.
    """
    graph, _ = _load()
    layer = build_navigator_layer(build_defense_brief(graph, engagement_name=engagement_name))
    payload = json.dumps(layer, indent=2, ensure_ascii=False)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return _json(
        {"path": str(path), "techniques": len(layer["techniques"]), "bytes": len(payload.encode())}
    )


DEFENSE_BRIEF_TOOLS = [defense_brief, export_attack_navigator]

__all__ = [
    "DEFENSE_BRIEF_TOOLS",
    "build_defense_brief",
    "build_navigator_layer",
    "defense_brief",
    "export_attack_navigator",
    "render_brief_markdown",
]
