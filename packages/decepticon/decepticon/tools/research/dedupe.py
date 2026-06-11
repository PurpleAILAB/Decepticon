"""Semantic deduplication for knowledge-graph finding/vulnerability nodes.

Decepticon's graph dedups writes by deterministic node ID (SHA1 of kind +
canonical key — see :mod:`decepticon_core.types.kg`). That collapses
*byte-identical* writes, but the multi-agent design (recon / exploit /
analyst / vulnresearch each running with fresh context) structurally
produces SEPARATE nodes for the SAME underlying vulnerability when it is
reached via different routes or described with different wording. Those
near-duplicates survive ID-based dedup and surface as repeated entries in
reports.

This module adds a second, *semantic* layer on top of ID dedup. It is:

- **Pure**: :func:`find_duplicate` takes the candidate, the existing nodes,
  and an INJECTED ``judge`` callable. No LLM client is imported here, so
  the decision logic is fully testable with a stubbed judge.
- **Cheap-first**: a deterministic :func:`prefilter` (same
  :class:`~decepticon_core.types.kg.NodeKind` plus normalized host /
  endpoint / CWE overlap) runs BEFORE the judge, so obvious non-candidates
  are rejected without ever invoking it.
- **Report-only**: the :func:`kg_dedupe_findings` tool clusters likely
  duplicates and returns a JSON summary. It never deletes or mutates graph
  nodes — merging is a deliberate follow-up.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, graph_transaction
from decepticon_core.types.kg import SEVERITY_SCORE, KnowledgeGraph, Node, NodeKind, Severity

Judge = Callable[[Node, Node], dict[str, Any]]

_FINDING_KINDS: frozenset[NodeKind] = frozenset({NodeKind.FINDING, NodeKind.VULNERABILITY})

_HOST_PROP_KEYS: tuple[str, ...] = ("host", "hostname", "target", "ip")
_ENDPOINT_PROP_KEYS: tuple[str, ...] = ("endpoint", "url", "matched_at", "message", "file")

_CWE_RE = re.compile(r"cwe[-_ ]?(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class DuplicateVerdict:
    """Outcome of a duplicate check.

    Attributes:
        is_duplicate: True when ``candidate`` is judged the same underlying
            finding as some already-known node.
        canonical_id: The id of the matched canonical node when
            ``is_duplicate`` is True, else ``None``.
        reason: Short human-readable explanation (prefilter miss, judge
            verdict, etc.).
    """

    is_duplicate: bool
    canonical_id: str | None
    reason: str


@dataclass(frozen=True)
class _Signature:
    """Normalized, comparable signal extracted from a finding node."""

    kind: NodeKind
    host: str
    endpoint: str
    cwes: frozenset[str]


def _first_str_prop(node: Node, keys: Sequence[str]) -> str:
    """Return the first non-empty string prop among ``keys`` (lowered)."""
    for key in keys:
        value = node.props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _normalize_host(raw: str) -> str:
    """Reduce a host-ish string to a bare, comparable hostname.

    Strips a URL scheme, any ``user@`` prefix, a path/query tail, and a
    trailing ``:port`` so ``https://API.example.com:443/x`` and
    ``api.example.com`` collapse to the same token.
    """
    if not raw:
        return ""
    value = raw.strip().lower()
    value = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", value)
    value = value.split("@", 1)[-1]
    value = value.split("/", 1)[0]
    value = value.split("?", 1)[0]
    if value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value.rstrip(".")


def _normalize_endpoint(raw: str) -> str:
    """Reduce an endpoint-ish string to ``host/path`` without scheme/port/query.

    Query strings and fragments are dropped (different agents word the same
    endpoint with different parameter values) so the path identity is what
    drives overlap.
    """
    if not raw:
        return ""
    value = raw.strip().lower()
    value = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", value)
    value = value.split("@", 1)[-1]
    value = value.split("?", 1)[0]
    value = value.split("#", 1)[0]
    if "/" in value:
        authority, _, path = value.partition("/")
        if authority.count(":") == 1:
            authority = authority.split(":", 1)[0]
        value = f"{authority}/{path}"
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value.rstrip("/")


def _extract_cwes(node: Node) -> frozenset[str]:
    """Collect CWE identifiers from props and label as ``CWE-<n>`` tokens."""
    found: set[str] = set()

    raw = node.props.get("cwe")
    candidates: list[str] = []
    if isinstance(raw, str):
        candidates.append(raw)
    elif isinstance(raw, (list, tuple)):
        candidates.extend(str(item) for item in raw)  # pyright: ignore[reportUnknownArgumentType]

    haystack = " ".join([*candidates, node.label or "", str(node.props.get("message") or "")])
    for match in _CWE_RE.finditer(haystack):
        found.add(f"CWE-{int(match.group(1))}")
    return frozenset(found)


def _signature(node: Node) -> _Signature:
    """Build the normalized comparison signature for a node."""
    host = _normalize_host(_first_str_prop(node, _HOST_PROP_KEYS))
    endpoint = _normalize_endpoint(_first_str_prop(node, _ENDPOINT_PROP_KEYS))
    if not host and endpoint:
        host = _normalize_host(endpoint)
    return _Signature(kind=node.kind, host=host, endpoint=endpoint, cwes=_extract_cwes(node))


def prefilter(candidate: Node, other: Node) -> bool:
    """Cheap deterministic gate: could these be the same finding?

    Returns True only when both nodes share a finding-like
    :class:`NodeKind` AND have at least one locational signal in common:
    overlapping CWE, the same normalized host, or the same normalized
    endpoint path. This runs BEFORE any judge so non-candidates never reach
    an LLM.
    """
    if candidate.id == other.id:
        return False
    sig_a = _signature(candidate)
    sig_b = _signature(other)
    if sig_a.kind != sig_b.kind:
        return False
    if sig_a.kind not in _FINDING_KINDS:
        return False
    if sig_a.cwes and sig_b.cwes and (sig_a.cwes & sig_b.cwes):
        return True
    if sig_a.host and sig_a.host == sig_b.host:
        return True
    if sig_a.endpoint and sig_a.endpoint == sig_b.endpoint:
        return True
    return False


def _judge_says_duplicate(verdict: dict[str, Any]) -> tuple[bool, str]:
    """Interpret a judge's raw dict into ``(is_duplicate, reason)``."""
    is_dup = bool(verdict.get("is_duplicate") or verdict.get("duplicate"))
    reason = verdict.get("reason")
    reason_text = reason.strip() if isinstance(reason, str) and reason.strip() else "judge verdict"
    return is_dup, reason_text


def find_duplicate(
    candidate: Node,
    existing: Sequence[Node],
    judge: Judge,
) -> DuplicateVerdict:
    """Decide whether ``candidate`` duplicates any node in ``existing``.

    The deterministic :func:`prefilter` runs first; only nodes that survive
    it are passed to ``judge``. The first node the judge confirms as a
    duplicate wins and its id becomes the canonical id.

    Args:
        candidate: The newly-observed finding node under test.
        existing: Already-known finding nodes to compare against.
        judge: Injected ``(candidate, other) -> dict`` callable. The dict is
            interpreted via ``is_duplicate``/``duplicate`` (bool) and an
            optional ``reason`` (str). No LLM call happens inside this
            module — the caller supplies the judge.

    Returns:
        A :class:`DuplicateVerdict`. ``is_duplicate`` is False when nothing
        passes the prefilter or the judge rejects every candidate.
    """
    considered = 0
    for other in existing:
        if not prefilter(candidate, other):
            continue
        considered += 1
        is_dup, reason = _judge_says_duplicate(judge(candidate, other))
        if is_dup:
            return DuplicateVerdict(is_duplicate=True, canonical_id=other.id, reason=reason)

    if considered == 0:
        return DuplicateVerdict(
            is_duplicate=False,
            canonical_id=None,
            reason="no prefilter candidates",
        )
    return DuplicateVerdict(
        is_duplicate=False,
        canonical_id=None,
        reason="judge rejected all candidates",
    )


def _cluster_by_prefilter(nodes: Sequence[Node]) -> list[list[Node]]:
    """Group finding nodes into prefilter-connected clusters.

    Two nodes land in the same cluster when :func:`prefilter` links them
    (directly or transitively). Singletons are dropped — only clusters with
    a likely duplicate are interesting for a dedup report.
    """
    finding_nodes = [n for n in nodes if n.kind in _FINDING_KINDS]
    parent: dict[str, str] = {n.id: n.id for n in finding_nodes}

    def _find(node_id: str) -> str:
        root = node_id
        while parent[root] != root:
            root = parent[root]
        while parent[node_id] != root:
            parent[node_id], node_id = root, parent[node_id]
        return root

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for i, left in enumerate(finding_nodes):
        for right in finding_nodes[i + 1 :]:
            if prefilter(left, right):
                _union(left.id, right.id)

    grouped: dict[str, list[Node]] = {}
    for node in finding_nodes:
        grouped.setdefault(_find(node.id), []).append(node)

    return [members for members in grouped.values() if len(members) > 1]


def _cluster_summary(members: Sequence[Node]) -> dict[str, Any]:
    """Build a compact, stable JSON summary for one duplicate cluster.

    The lowest node id is chosen as the canonical anchor purely so the
    report is deterministic; this tool does not persist that choice.
    """
    ordered = sorted(members, key=lambda n: n.id)
    canonical = ordered[0]
    sig = _signature(canonical)
    return {
        "canonical_id": canonical.id,
        "kind": canonical.kind.value,
        "host": sig.host,
        "endpoint": sig.endpoint,
        "cwes": sorted(sig.cwes),
        "size": len(ordered),
        "members": [
            {
                "id": n.id,
                "kind": n.kind.value,
                "label": n.label,
                "severity": n.props.get("severity"),
            }
            for n in ordered
        ],
    }


@tool
def kg_dedupe_findings(min_cluster_size: int = 2) -> str:
    """Report likely-duplicate finding/vulnerability clusters (read-only).

    WHEN TO USE: Before writing a report, to surface findings that describe
    the SAME underlying bug but were recorded as separate nodes by
    different agents (recon / exploit / analyst / vulnresearch). Decepticon
    already dedups byte-identical writes by node id; this catches semantic
    duplicates — same host/endpoint/CWE, different wording.

    HOW IT WORKS: walks Finding and Vulnerability nodes and groups them with
    a cheap deterministic pre-filter (same kind plus overlapping CWE,
    normalized host, or normalized endpoint). It is REPORT-ONLY: no nodes
    are deleted or mutated. Merging duplicates is a deliberate follow-up.

    Args:
        min_cluster_size: Minimum members for a cluster to be reported
            (default 2; values below 2 are clamped to 2).

    Returns:
        JSON with the number of finding nodes scanned, the duplicate
        clusters found, and how many nodes are involved in duplicates.
    """
    threshold = max(min_cluster_size, 2)
    with graph_transaction() as graph:
        return _json(_dedupe_report(graph, threshold))


def _dedupe_report(graph: KnowledgeGraph, threshold: int) -> dict[str, Any]:
    """Compute the report-only duplicate summary for ``graph``.

    Split out from the tool wrapper so it stays a pure function over a
    :class:`KnowledgeGraph` (no graph mutation, easy to unit test).
    """
    finding_nodes = [n for n in graph.nodes.values() if n.kind in _FINDING_KINDS]
    clusters = [c for c in _cluster_by_prefilter(finding_nodes) if len(c) >= threshold]
    summaries = sorted(
        (_cluster_summary(c) for c in clusters),
        key=lambda s: (-s["size"], s["canonical_id"]),
    )
    duplicate_nodes = sum(s["size"] for s in summaries)
    return {
        "scanned_findings": len(finding_nodes),
        "duplicate_clusters": len(summaries),
        "duplicate_nodes": duplicate_nodes,
        "clusters": summaries,
    }


# ── Auto-dedup on insertion ─────────────────────────────────────────────
#
# The report-only path above leaves merging to a human/LLM follow-up. The
# helpers below close that loop for the write path (``kg_add_node``): a
# deterministic judge confirms duplicates without an LLM, and
# :func:`integrate_node` merges a candidate into its canonical twin instead
# of creating a second near-identical node.

_DESCRIPTION_KEYS: tuple[str, ...] = ("description", "message")
_MERGE_SKIP_KEYS: frozenset[str] = frozenset(
    {"severity", "description", "message", "validated", "false-positive", "key"}
)
_EMPTY_VALUES: tuple[Any, ...] = (None, "", [], {}, ())


def _is_truthy(value: Any) -> bool:
    """Loose truthiness for status flags stored as bool/str/number."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "validated"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _severity_score(value: Any) -> float:
    """Map a severity string to its numeric rank; unknown/absent → -1."""
    if not isinstance(value, str):
        return -1.0
    try:
        sev = Severity(value.strip().lower())
    except ValueError:
        return -1.0
    return SEVERITY_SCORE.get(sev, -1.0)


def deterministic_judge(candidate: Node, other: Node) -> dict[str, Any]:
    """LLM-free judge used by the write path.

    Confirms a duplicate only on a *strong* deterministic signal so the
    auto-merge never collapses two genuinely distinct findings that merely
    share a host. The :func:`prefilter` has already established that the two
    nodes share at least one of host / endpoint / CWE; this tightens that
    into a merge decision:

    - Conflicting CWE classes (both sides classified, no overlap) → NOT a
      duplicate (e.g. XSS vs SQLi on the same URL stay separate).
    - Same normalized endpoint path with compatible CWE → duplicate.
    - Overlapping CWE on the same normalized host → duplicate.
    - Otherwise (e.g. same host only) → NOT a duplicate.
    """
    sig_a = _signature(candidate)
    sig_b = _signature(other)
    cwe_overlap = bool(sig_a.cwes & sig_b.cwes)
    cwe_conflict = bool(sig_a.cwes and sig_b.cwes and not cwe_overlap)
    if cwe_conflict:
        return {"is_duplicate": False, "reason": "different CWE classes"}
    if sig_a.endpoint and sig_a.endpoint == sig_b.endpoint:
        return {"is_duplicate": True, "reason": "same endpoint, compatible CWE"}
    if cwe_overlap and sig_a.host and sig_a.host == sig_b.host:
        return {"is_duplicate": True, "reason": "shared CWE on same host"}
    return {"is_duplicate": False, "reason": "insufficient signal overlap"}


def merge_nodes(canonical: Node, candidate: Node) -> Node:
    """Fold ``candidate`` into ``canonical`` in place, keeping the richer signal.

    Merge policy (canonical keeps its id and ``created_at``):

    - **severity**: keep whichever ranks higher on the CVSS scale.
    - **description / message**: keep the longer string.
    - **validated**: sticky — if either side is validated the merged node is
      ``validated: true`` and any ``false-positive`` flag is cleared.
    - **false-positive**: OR'd together only when the result is not validated.
    - **label**: keep the longer (more descriptive) label.
    - other props: candidate fills any key the canonical node is missing or
      has empty, but never clobbers an existing non-empty value.
    """
    cand_sev = candidate.props.get("severity")
    if _severity_score(cand_sev) > _severity_score(canonical.props.get("severity")):
        canonical.props["severity"] = cand_sev

    for key in _DESCRIPTION_KEYS:
        new_val = candidate.props.get(key)
        if not isinstance(new_val, str):
            continue
        cur_val = canonical.props.get(key)
        cur_len = len(cur_val) if isinstance(cur_val, str) else -1
        if len(new_val) > cur_len:
            canonical.props[key] = new_val

    validated = _is_truthy(canonical.props.get("validated")) or _is_truthy(
        candidate.props.get("validated")
    )
    false_positive = _is_truthy(canonical.props.get("false-positive")) or _is_truthy(
        candidate.props.get("false-positive")
    )
    if validated:
        canonical.props["validated"] = True
        if "false-positive" in canonical.props or "false-positive" in candidate.props:
            canonical.props["false-positive"] = False
    else:
        if "validated" in canonical.props or "validated" in candidate.props:
            canonical.props["validated"] = False
        if false_positive:
            canonical.props["false-positive"] = True

    if len(candidate.label) > len(canonical.label):
        canonical.label = candidate.label

    for key, value in candidate.props.items():
        if key in _MERGE_SKIP_KEYS:
            continue
        if canonical.props.get(key) in _EMPTY_VALUES and value not in _EMPTY_VALUES:
            canonical.props[key] = value

    canonical.updated_at = time.time()
    return canonical


def integrate_node(
    graph: KnowledgeGraph,
    candidate: Node,
    judge: Judge = deterministic_judge,
) -> tuple[Node, bool]:
    """Insert ``candidate`` into ``graph``, merging semantic duplicates.

    For finding/vulnerability kinds this runs the :func:`prefilter` +
    ``judge`` pipeline against existing finding nodes. On a confirmed
    duplicate it merges the candidate's props into the canonical node via
    :func:`merge_nodes` and returns ``(canonical, True)`` — no new node is
    created. Otherwise (or for non-finding kinds, or an exact id match that
    ordinary id-dedup already handles) it upserts normally and returns
    ``(node, False)``.
    """
    if candidate.kind not in _FINDING_KINDS or candidate.id in graph.nodes:
        return graph.upsert_node(candidate), False

    existing = [n for n in graph.nodes.values() if n.kind in _FINDING_KINDS]
    verdict = find_duplicate(candidate, existing, judge)
    if verdict.is_duplicate and verdict.canonical_id in graph.nodes:
        canonical = graph.nodes[verdict.canonical_id]
        merge_nodes(canonical, candidate)
        return canonical, True

    return graph.upsert_node(candidate), False
