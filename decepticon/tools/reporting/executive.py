"""Executive summary writer.

Produces a high-level markdown digest that a CISO / program owner can
read in 90 seconds. Focuses on:

- Headline finding counts by severity
- Top-N critical chains with brief impact statements
- CVE exposure (top 5 ranked by composite score)
- Coverage gaps (assets with zero findings might be unscanned)
"""

from __future__ import annotations

from collections import Counter

from decepticon.tools.research.graph import KnowledgeGraph, NodeKind


def _count_by_severity(graph: KnowledgeGraph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for node in graph.by_kind(NodeKind.VULNERABILITY):
        counts[node.props.get("severity", "info")] += 1
    return dict(counts)


def _top_chains(graph: KnowledgeGraph, limit: int = 5) -> list[tuple[str, float, int]]:
    out: list[tuple[str, float, int]] = []
    for node in graph.by_kind(NodeKind.ATTACK_PATH):
        cost = float(node.props.get("total_cost", 99.0))
        length = int(node.props.get("length", 0))
        out.append((node.label, cost, length))
    out.sort(key=lambda t: t[1])
    return out[:limit]


def _top_cves(graph: KnowledgeGraph, limit: int = 5) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for node in graph.by_kind(NodeKind.CVE):
        score = float(node.props.get("score", 0.0))
        rows.append((node.label, score))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:limit]


def render_executive_summary(
    graph: KnowledgeGraph,
    *,
    engagement_name: str = "Engagement",
) -> str:
    """Build the markdown summary for the current graph state."""
    severity_counts = _count_by_severity(graph)
    severity_order = ["critical", "high", "medium", "low", "info"]
    total_findings = sum(severity_counts.values())

    lines: list[str] = []
    lines.append(f"# {engagement_name} — Executive Summary")
    lines.append("")
    lines.append("## Headline")
    if total_findings == 0:
        lines.append("No findings recorded in the knowledge graph yet.")
    else:
        lines.append(f"{total_findings} total findings across the engagement:")
        for sev in severity_order:
            n = severity_counts.get(sev, 0)
            if n:
                lines.append(f"- **{sev.upper()}**: {n}")
    lines.append("")

    chains = _top_chains(graph)
    if chains:
        lines.append("## Top Critical Chains")
        for label, cost, length in chains:
            lines.append(f"- `{label}` — cost {cost:.2f}, {length} hops")
        lines.append("")

    cves = _top_cves(graph)
    if cves:
        lines.append("## Top CVE Exposure")
        for label, score in cves:
            lines.append(f"- {label} (score {score:.2f})")
        lines.append("")

    validated = [n for n in graph.by_kind(NodeKind.VULNERABILITY) if n.props.get("validated")]
    if validated:
        lines.append(f"## Validated Findings ({len(validated)})")
        for node in validated[:15]:
            lines.append(f"- [{node.props.get('severity', '?').upper()}] {node.label}")
        lines.append("")

    lines.append("## Graph Stats")
    for k, v in sorted(graph.stats().items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    return "\n".join(lines)
