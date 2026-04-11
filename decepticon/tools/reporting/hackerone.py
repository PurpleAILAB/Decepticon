"""HackerOne-style markdown report renderer.

Produces a single-file markdown document following the H1 convention:
Title, Summary, Steps to Reproduce, Impact, Proof of Concept, Remediation,
References, CVSS vector + score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from decepticon.tools.research.graph import KnowledgeGraph, Node


@dataclass
class HackerOneReport:
    """In-memory representation before markdown rendering."""

    title: str
    severity: str
    cvss_vector: str = ""
    cvss_score: float | None = None
    summary: str = ""
    steps: list[str] = field(default_factory=list)
    impact: str = ""
    poc: str = ""
    remediation: str = ""
    references: list[str] = field(default_factory=list)
    chain_id: str | None = None

    def to_markdown(self) -> str:
        out: list[str] = []
        out.append(f"# {self.title}")
        out.append("")
        out.append(f"**Severity:** {self.severity.upper()}")
        if self.cvss_score is not None:
            out.append(f"**CVSS:** {self.cvss_score} ({self.cvss_vector})")
        out.append("")

        out.append("## Summary")
        out.append(self.summary or "_(pending)_")
        out.append("")

        out.append("## Steps to Reproduce")
        if self.steps:
            for i, step in enumerate(self.steps, 1):
                out.append(f"{i}. {step}")
        else:
            out.append("_(no steps recorded)_")
        out.append("")

        out.append("## Impact")
        out.append(self.impact or "_(pending)_")
        out.append("")

        out.append("## Proof of Concept")
        out.append("```")
        out.append(self.poc or "(attach PoC script or request)")
        out.append("```")
        out.append("")

        out.append("## Remediation")
        out.append(self.remediation or "_(pending)_")
        out.append("")

        if self.references:
            out.append("## References")
            for ref in self.references:
                out.append(f"- {ref}")
            out.append("")

        if self.chain_id:
            out.append(f"_Chain ID: {self.chain_id}_")

        return "\n".join(out).rstrip() + "\n"


def render_hackerone_markdown(finding_node: Node, *, graph: KnowledgeGraph) -> str:
    """Compose a HackerOne markdown report from a finding (or vulnerability) node.

    Pulls context from neighbouring nodes: file/line, CVSS, chain.
    """
    props = finding_node.props
    title = props.get("title") or finding_node.label
    severity = props.get("severity", "medium")
    cvss_vector = props.get("cvss_vector") or ""
    cvss_score = props.get("cvss_score")
    summary = props.get("summary") or props.get("description") or ""
    poc = props.get("poc_command") or props.get("stdout_excerpt") or ""
    impact = props.get("impact") or ""
    remediation = props.get("remediation") or ""
    references: list[Any] = list(props.get("references") or [])

    # Auto-build step list when none provided
    steps: list[str] = list(props.get("steps") or [])
    if not steps and poc:
        steps = [f"Run the PoC: ``{poc.strip().splitlines()[0] if poc else ''}``"]
        steps.append("Observe the response matches the success patterns described above.")

    # Derive impact from severity if missing
    if not impact:
        impact = {
            "critical": "Unauthenticated remote compromise of affected component.",
            "high": "Significant unauthorised access or integrity impact.",
            "medium": "Limited unauthorised access / information disclosure.",
            "low": "Minor information disclosure or denial of service.",
            "info": "Informational; no direct security impact.",
        }.get(severity, "See details.")

    # Locate chain node if any
    chain_id = None
    for edge in graph.edges.values():
        if edge.dst == finding_node.id and graph.nodes.get(edge.src, None) is not None:
            src_node = graph.nodes[edge.src]
            if src_node.kind.value == "chain":
                chain_id = src_node.id
                break

    report = HackerOneReport(
        title=title,
        severity=severity,
        cvss_vector=cvss_vector,
        cvss_score=cvss_score if isinstance(cvss_score, (int, float)) else None,
        summary=summary,
        steps=steps,
        impact=impact,
        poc=poc,
        remediation=remediation,
        references=[str(r) for r in references],
        chain_id=chain_id,
    )
    return report.to_markdown()
