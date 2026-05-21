"""ATT&CK Navigator layer export — per-engagement coverage heatmap.

Builds a MITRE ATT&CK Navigator v4.5 layer from the knowledge graph:
every technique a finding or vulnerability ``MAPS_TO`` becomes a colored
cell. Colour encodes the blue team's detection result, turning the layer
into a purple-team detection-gap map.
"""

from __future__ import annotations

from decepticon.tools.research.attack.catalog import load_attack_catalog
from decepticon.tools.research.graph import EdgeKind, KnowledgeGraph, NodeKind

# Detection-status colours.
_COLOR_DETECTED = "#4caf50"  # green — blue team caught it
_COLOR_GAP = "#fc3b3b"  # red — detection gap
_COLOR_UNKNOWN = "#b3b3b3"  # grey — detection not assessed

_SEVERITY_SCORE: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "informational": 1,
    "info": 1,
}

# Node kinds that carry severity + detection and map to techniques.
_EXERCISED_KINDS = (NodeKind.FINDING, NodeKind.VULNERABILITY)


def _severity_score(raw: object) -> int:
    """Map a node's ``severity`` prop to a 1-4 Navigator score."""
    return _SEVERITY_SCORE.get(str(raw or "").strip().lower(), 1)


def _attack_version() -> str:
    """Bundled ATT&CK dataset version, best-effort."""
    try:
        return load_attack_catalog().version
    except Exception:
        return "unknown"


def build_navigator_layer(
    graph: KnowledgeGraph,
    engagement_name: str,
    attack_version: str | None = None,
) -> dict:
    """Build a MITRE ATT&CK Navigator v4.5 layer from the knowledge graph.

    Every technique reached by a ``MAPS_TO`` edge from a finding or
    vulnerability becomes a technique entry. ``score`` is the maximum
    severity among mapping nodes; ``color`` encodes detection status
    (green = detected, red = gap, grey = unknown).
    """
    agg: dict[str, dict] = {}
    for kind in _EXERCISED_KINDS:
        for node in graph.by_kind(kind):
            for _edge, tech in graph.neighbors(node.id, EdgeKind.MAPS_TO, direction="out"):
                if tech.kind != NodeKind.TECHNIQUE:
                    continue
                tid = tech.props.get("key") or tech.label
                entry = agg.setdefault(tid, {"findings": [], "scores": [], "detected": []})
                entry["findings"].append(node.props.get("key") or node.label)
                entry["scores"].append(_severity_score(node.props.get("severity")))
                entry["detected"].append(node.props.get("detected"))

    techniques: list[dict] = []
    for tid in sorted(agg):
        entry = agg[tid]
        detected = entry["detected"]
        if any(d is True for d in detected):
            color, status = _COLOR_DETECTED, "detected"
        elif any(d is False for d in detected):
            color, status = _COLOR_GAP, "not-detected"
        else:
            color, status = _COLOR_UNKNOWN, "unknown"
        findings = entry["findings"]
        techniques.append(
            {
                "techniqueID": tid,
                "score": max(entry["scores"]),
                "color": color,
                "comment": f"{len(findings)} finding(s): {', '.join(findings)}",
                "enabled": True,
                "metadata": [
                    {"name": "detection", "value": status},
                    {"name": "findings", "value": str(len(findings))},
                ],
            }
        )

    return {
        "name": f"Decepticon — {engagement_name}",
        "versions": {
            "attack": attack_version or _attack_version(),
            "navigator": "4.9.5",
            "layer": "4.5",
        },
        "domain": "enterprise-attack",
        "description": (
            "Decepticon ATT&CK coverage. Green = detected by blue team; "
            "red = detection gap; grey = detection not assessed."
        ),
        "techniques": techniques,
        "gradient": {
            "colors": ["#ffe766", "#ffaf66", "#ff6666"],
            "minValue": 1,
            "maxValue": 4,
        },
        "legendItems": [
            {"label": "Detected by blue team", "color": _COLOR_DETECTED},
            {"label": "Detection gap", "color": _COLOR_GAP},
            {"label": "Detection not assessed", "color": _COLOR_UNKNOWN},
        ],
        "sorting": 3,
        "hideDisabled": False,
        "showTacticRowBackground": False,
        "selectTechniquesAcrossTactics": True,
    }


__all__ = ["build_navigator_layer"]
