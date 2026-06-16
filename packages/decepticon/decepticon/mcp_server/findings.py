"""Read persisted engagement findings and summarise them as SARIF.

The orchestrator persists its KnowledgeGraph to a conventional workspace
location. This module reads that graph back and reduces it to a compact,
agent-friendly summary (counts + optional full SARIF), reusing the same
exporter the headless CLI uses so the MCP surface and CI agree on findings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from decepticon.mcp_server.models import FindingsResult
from decepticon_core.utils.engagement_scope import is_valid_engagement_label
from decepticon_core.utils.logging import get_logger

if TYPE_CHECKING:
    from decepticon_core.types.kg import KnowledgeGraph

log = get_logger("mcp_server.findings")


def engagement_workspace(engagement_name: str) -> Path:
    """Resolve the workspace directory for an engagement.

    Mirrors ``decepticon.cli.scan._load_findings_graph`` so the MCP bridge and
    the headless CLI resolve the same path (``DECEPTICON_ENGAGEMENT_WORKSPACE``
    override, else ``~/.decepticon/workspace/<slug>``).

    ``engagement_name`` arrives from a remote MCP caller, so it is validated
    against the engagement-label contract before it is ever joined onto a
    filesystem path. Without this guard a value like ``../../etc`` or an
    absolute ``/root/.ssh`` would escape the workspace root (pathlib discards
    the left operand of ``/`` when the right side is absolute), turning the
    findings/status tools into an arbitrary-file read + existence oracle.
    """
    if not is_valid_engagement_label(engagement_name):
        raise ValueError(
            f"invalid engagement name {engagement_name!r}; must match "
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127} (no path separators or '..')"
        )
    override = os.environ.get("DECEPTICON_ENGAGEMENT_WORKSPACE")
    if override:
        return Path(override)
    return Path.home() / ".decepticon" / "workspace" / engagement_name


def load_findings_graph(engagement_name: str) -> KnowledgeGraph | None:
    """Load the engagement KnowledgeGraph, or ``None`` when none was persisted.

    An unsafe ``engagement_name`` is treated as "no findings" (returns ``None``)
    rather than reading an attacker-chosen path, so the findings tool never
    surfaces an out-of-tree file or distinguishes "rejected" from "absent".
    """
    if not is_valid_engagement_label(engagement_name):
        log.warning("rejecting unsafe engagement name %r for findings load", engagement_name)
        return None
    graph_path = engagement_workspace(engagement_name) / "graph.json"
    if not graph_path.exists():
        log.info("no graph.json at %s; treating as zero findings", graph_path)
        return None
    from decepticon_core.types.kg import KnowledgeGraph

    # KnowledgeGraph.from_json is a runtime classmethod pyright can't resolve
    # through the compat re-export; same call is used in decepticon.cli.scan.
    return KnowledgeGraph.from_json(graph_path.read_text(encoding="utf-8"))  # pyright: ignore[reportAttributeAccessIssue]


def _count_levels(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        level = str(result.get("level") or "none")
        counts[level] = counts.get(level, 0) + 1
    return counts


def summarize_findings(
    graph: KnowledgeGraph | None,
    *,
    engagement_name: str,
    include_sarif: bool,
) -> FindingsResult:
    """Reduce a (possibly absent) KnowledgeGraph to a :class:`FindingsResult`."""
    if graph is None:
        return FindingsResult(
            engagement_name=engagement_name,
            available=False,
            result_count=0,
            level_counts={},
            sarif=None,
        )
    from decepticon.tools.research.sarif_export import export_findings_to_sarif

    doc = export_findings_to_sarif(graph, engagement_name=engagement_name)
    runs = doc.get("runs") or [{}]
    results = runs[0].get("results", [])
    return FindingsResult(
        engagement_name=engagement_name,
        available=True,
        result_count=len(results),
        level_counts=_count_levels(results),
        sarif=doc if include_sarif else None,
    )
