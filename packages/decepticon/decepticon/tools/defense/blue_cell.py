"""Blue Cell detection-coverage tool — the runtime that closes the loop.

The Offensive Vaccine pipeline documents a ``Defender`` that writes Sigma
rules, but nothing in the OSS ever ran those rules against the agent's own
activity (``docs/features/blue-cell.md``). ``blue_cell_scan`` is that missing
runtime: it replays the engagement's sandbox session logs through the shipped
:class:`~decepticon.blue_cell.tap.BlueCellTap` +
:class:`~decepticon.blue_cell.rule_match.RuleMatcher`, and records every rule
that fires as a ``DetectionFired`` node in the knowledge graph — linked
``-[:USES_RULE]->`` the ``DefenseAction`` (the rule artifact) and
``-[:DETECTED]->`` the offensive ``Finding`` / ``Technique`` it caught.

Recording is deterministic and idempotent (matching, not the LLM, decides
what fired), and detection timing is write-once so repeated scans never
inflate MTTD. The agent narrates the returned coverage summary — including
the **detection gaps** (Findings with no ``DETECTED`` edge) — into a Defense
Brief.
"""

from __future__ import annotations

import os
import statistics
import time
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from decepticon.blue_cell.rule_match import RuleMatcher, load_rules
from decepticon.blue_cell.tap import BlueCellTap
from decepticon.tools.research._state import _json, graph_transaction
from decepticon_core.types.kg import Edge, EdgeKind, KnowledgeGraph, Node, NodeKind

# Bundled baseline ruleset — schema reference + bootstrap coverage. Operators
# point ``rules_path`` at their Detector-produced ruleset for real engagements.
_BUNDLED_RULES: Path = Path(__file__).resolve().parents[2] / "blue_cell" / "sample_rules.jsonl"

# Node kinds whose technique tags a fired rule can be attributed to.
_ATTRIBUTABLE: tuple[NodeKind, ...] = (NodeKind.FINDING, NodeKind.TECHNIQUE)


def _resolve_workspace(workspace_path: str, config: RunnableConfig | None) -> str:
    """Explicit arg → runnable config → env → ``/workspace`` (bash-tool order)."""
    if workspace_path:
        return workspace_path
    configurable = (config or {}).get("configurable", {}) if config else {}
    from_config = configurable.get("workspace_path") if isinstance(configurable, dict) else None
    if from_config:
        return str(from_config)
    return os.environ.get("DECEPTICON_WORKSPACE_PATH", "/workspace")


def node_techniques(node: Node) -> set[str]:
    """MITRE technique IDs a node carries, across the prop spellings in use."""
    out: set[str] = set()
    for key in ("technique_id", "technique", "mitre", "mitre_techniques"):
        val = node.props.get(key)
        if isinstance(val, str):
            out.add(val)
        elif isinstance(val, (list, tuple)):
            out.update(str(v) for v in val)
    return out


def _attribution_targets(graph: KnowledgeGraph, technique: str) -> list[Node]:
    """Finding/Technique nodes a detection for ``technique`` should link to."""
    return [
        node
        for node in graph.nodes.values()
        if node.kind in _ATTRIBUTABLE and technique in node_techniques(node)
    ]


def _record_hit(graph: KnowledgeGraph, source: str, detection: Any) -> float:
    """Upsert the DefenseAction + DetectionFired pair and edges for one hit.

    Detection timing is write-once: a re-scan of the same logged event
    preserves the first-seen ``detection_ts`` / ``mttd_seconds`` so periodic
    scanning never inflates MTTD. Returns the recorded MTTD in seconds.
    """
    rule = detection.rule
    action = graph.upsert_node(
        Node.make(
            NodeKind.DEFENSE_ACTION,
            rule.title,
            key=f"rule::{rule.id}",
            rule_id=rule.id,
            level=rule.level,
            mitre=list(rule.mitre),
        )
    )
    fired = Node.make(
        NodeKind.DETECTION_FIRED,
        rule.title,
        key=f"detection::{rule.id}::{detection.event_ts}",
        rule_id=rule.id,
        rule_title=rule.title,
        rule_level=rule.level,
        mitre=list(rule.mitre),
        matched_fields=dict(detection.matched_fields),
        event_ts=detection.event_ts,
        detection_ts=detection.detection_ts,
        mttd_seconds=detection.mttd_seconds,
        source=source,
    )
    prior = graph.nodes.get(fired.id)
    if prior is not None and "detection_ts" in prior.props:
        fired.props["detection_ts"] = prior.props["detection_ts"]
        fired.props["mttd_seconds"] = prior.props["mttd_seconds"]
    fired = graph.upsert_node(fired)
    graph.upsert_edge(Edge.make(fired.id, action.id, EdgeKind.USES_RULE))
    for technique in rule.mitre:
        for target in _attribution_targets(graph, technique):
            graph.upsert_edge(Edge.make(fired.id, target.id, EdgeKind.DETECTED, key=technique))
    return float(fired.props["mttd_seconds"])


def _scan_and_record(
    graph: KnowledgeGraph, *, workspace_path: str, rules_path: str, now_ts: float
) -> dict[str, Any]:
    """Replay the tap, evaluate rules, record detections, return coverage."""
    rules_path = rules_path or str(_BUNDLED_RULES)
    rules = load_rules(rules_path)
    matcher = RuleMatcher(rules)
    events = BlueCellTap(workspace_path).read_batch()

    detections = 0
    techniques: set[str] = set()
    mttds: list[float] = []
    for event in events:
        payload = event.to_dict()
        for hit in matcher.match(payload, now_ts=now_ts):
            mttds.append(_record_hit(graph, str(payload["source"]), hit))
            techniques.update(hit.rule.mitre)
            detections += 1

    findings = graph.by_kind(NodeKind.FINDING)
    gaps = [
        f.label
        for f in findings
        if not graph.neighbors(f.id, edge_kind=EdgeKind.DETECTED, direction="in")
    ]
    return {
        "rules_loaded": len(rules),
        "rules_path": rules_path,
        "events_scanned": len(events),
        "detections": detections,
        "techniques_detected": sorted(techniques),
        "median_mttd_seconds": round(statistics.median(mttds), 2) if mttds else None,
        "findings_total": len(findings),
        "findings_detected": len(findings) - len(gaps),
        "detection_gaps": gaps,
    }


@tool
def blue_cell_scan(
    workspace_path: str = "",
    rules_path: str = "",
    config: RunnableConfig | None = None,
) -> str:
    """Score detection rules against Red Cell's own activity and record coverage.

    Replays the engagement's sandbox session logs, evaluates every detection
    rule against them, and writes a ``DetectionFired`` node per hit (linked to
    the rule and to the offensive Finding/Technique it caught). Re-running is
    safe and idempotent — detection timing is preserved from first sighting.

    WHEN TO USE: after offensive activity has run, to produce the engagement's
    proven detection-coverage picture (what fired, how fast, and — most
    importantly — which Findings nothing detected).

    Args:
        workspace_path: Engagement workspace root holding ``.sessions/``.
            Defaults to the runnable config / ``DECEPTICON_WORKSPACE_PATH`` /
            ``/workspace``.
        rules_path: JSONL file or directory of detection rules. Defaults to
            the bundled baseline ruleset; point this at the Detector's output
            for a real engagement.

    Returns:
        JSON coverage summary: rules loaded, events scanned, detections,
        techniques detected, median MTTD, and the detection-gap Finding list.
    """
    resolved_workspace = _resolve_workspace(workspace_path, config)
    with graph_transaction() as graph:
        return _json(
            _scan_and_record(
                graph,
                workspace_path=resolved_workspace,
                rules_path=rules_path,
                now_ts=time.time(),
            )
        )


BLUE_CELL_TOOLS = [blue_cell_scan]

__all__ = ["BLUE_CELL_TOOLS", "blue_cell_scan"]
