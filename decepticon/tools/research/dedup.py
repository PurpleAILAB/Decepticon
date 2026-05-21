"""Finding deduplication — collapse semantically equivalent FINDING nodes.

MDASH's "Dedup stage": two findings the same patch would fix are one bug.
Decepticon's vulnresearch pipeline can mint multiple FINDING nodes for the
same underlying vulnerability — a different PoC for the same root cause,
the same bug re-discovered across objectives — which wastes Patcher and
Exploiter effort and inflates the report.

This runs as a deterministic stage between the Verifier (stage 3) and the
Patcher (stage 4):

  Tier A (always)  cluster by a structural signature —
                   (CWE, root-cause class, normalized code location).
  Tier B (opt-in)  also merge clusters whose proposed patches touch the
                   same code (only useful once the Patcher has run).

One canonical finding is kept per cluster; the rest get a ``DUPLICATE_OF``
edge and ``superseded`` props. No node is deleted — the audit trail stays
intact. The Patcher consumes only findings where ``superseded`` is unset.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from os.path import basename

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, _load, _save
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
)

# ── CWE → coarse root-cause class ────────────────────────────────────
# A coarse bucket stabilises the signature across scanners that tag the
# same bug with slightly different (but related) CWE ids.

_CWE_CLASSES: dict[str, tuple[str, ...]] = {
    "injection": ("89", "78", "79", "94", "90", "91", "917", "943", "1336"),
    "memory": (
        "119",
        "120",
        "121",
        "122",
        "124",
        "125",
        "126",
        "127",
        "787",
        "415",
        "416",
        "476",
        "190",
        "191",
    ),
    "auth": ("287", "285", "306", "862", "863", "639", "522"),
    "disclosure": ("200", "209", "532", "538", "215"),
    "traversal": ("22", "23", "36", "98", "73"),
    "ssrf": ("918",),
    "xxe": ("611", "776"),
    "crypto": ("327", "328", "326", "916", "330"),
    "deserialization": ("502",),
}


def _cwe_primary(vuln: Node) -> str:
    """First CWE id on a vuln node, normalized to ``CWE-<n>`` (or '')."""
    raw = vuln.props.get("cwe")
    if isinstance(raw, list) and raw:
        first = str(raw[0])
    elif isinstance(raw, str) and raw:
        first = raw.split(",")[0]
    else:
        return ""
    digits = re.sub(r"\D", "", first)
    return f"CWE-{digits}" if digits else ""


def _root_cause_class(vuln: Node) -> str:
    """Coarse root-cause bucket for a vuln node, derived from its CWE."""
    cwe = _cwe_primary(vuln)
    digits = cwe.removeprefix("CWE-")
    for klass, ids in _CWE_CLASSES.items():
        if digits in ids:
            return klass
    return "other"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:60]


def _normalized_location(vuln: Node) -> str:
    """A location string for a vuln node, line-bucketed to collapse
    near-duplicate reports.

    Precedence: file:line(/5) → affected component → package@major →
    vuln label slug.
    """
    file = vuln.props.get("file")
    line = vuln.props.get("line")
    if file:
        base = basename(str(file))
        if isinstance(line, int):
            return f"{base}:{line // 5}"
        return base
    component = vuln.props.get("affected_component") or vuln.props.get("component")
    if component:
        return _slug(str(component).split("?")[0].rstrip("/"))
    package = vuln.props.get("package")
    if package:
        version = str(vuln.props.get("version") or "")
        major = version.split(".")[0] if version else ""
        return f"{_slug(str(package))}@{major}"
    return _slug(vuln.label)


def _validates_vuln(graph: KnowledgeGraph, finding: Node) -> Node | None:
    """Resolve the VULNERABILITY a FINDING validates.

    Uses the ``vuln_id`` prop first (always written by ``_persist_result``),
    falling back to the ``VALIDATES`` edge.
    """
    vuln_id = finding.props.get("vuln_id")
    if vuln_id and vuln_id in graph.nodes:
        return graph.nodes[vuln_id]
    for edge, nbr in graph.neighbors(finding.id, EdgeKind.VALIDATES, direction="out"):
        if nbr.kind == NodeKind.VULNERABILITY:
            return nbr
    return None


def finding_signature(graph: KnowledgeGraph, finding: Node) -> tuple[str, str, str]:
    """Structural signature ``(cwe, root_cause_class, location)``.

    Falls back to the finding's own label when no vulnerability can be
    resolved, so a dangling finding clusters only with itself.
    """
    vuln = _validates_vuln(graph, finding)
    if vuln is None:
        return ("", "", f"finding:{_slug(finding.label)}")
    return (_cwe_primary(vuln), _root_cause_class(vuln), _normalized_location(vuln))


def _cluster_key(signature: tuple[str, str, str]) -> str:
    return hashlib.sha1("::".join(signature).encode(), usedforsecurity=False).hexdigest()[:16]


def cluster_findings(graph: KnowledgeGraph) -> dict[str, list[Node]]:
    """Group validated FINDING nodes by structural signature (Tier A)."""
    clusters: dict[str, list[Node]] = defaultdict(list)
    for finding in graph.by_kind(NodeKind.FINDING):
        if finding.props.get("validated") is not True:
            continue
        clusters[_cluster_key(finding_signature(graph, finding))].append(finding)
    return dict(clusters)


# ── Tier B — patch-based grouping ────────────────────────────────────

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_RE = re.compile(r"^\+\+\+ [ab]/(.+)$")


def diff_signature(patch: Node) -> set[tuple[str, int, int]]:
    """Parse a PATCH node's unified diff into ``(file, start, end)`` hunks."""
    diff = str(patch.props.get("diff") or "")
    hunks: set[tuple[str, int, int]] = set()
    current_file = ""
    for line in diff.splitlines():
        fm = _FILE_RE.match(line)
        if fm:
            current_file = fm.group(1).strip()
            continue
        hm = _HUNK_RE.match(line)
        if hm:
            start = int(hm.group(1))
            length = int(hm.group(2)) if hm.group(2) else 1
            hunks.add((current_file, start, start + max(length, 1)))
    return hunks


def _patches_for_finding(graph: KnowledgeGraph, finding: Node) -> list[Node]:
    vuln_id = finding.props.get("vuln_id")
    out: list[Node] = []
    for patch in graph.by_kind(NodeKind.PATCH):
        if patch.props.get("finding_id") == finding.id:
            out.append(patch)
        elif vuln_id and patch.props.get("vuln_id") == vuln_id:
            out.append(patch)
    return out


def _hunks_overlap(a: tuple[str, int, int], b: tuple[str, int, int]) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def merge_clusters_by_patch(
    graph: KnowledgeGraph, clusters: dict[str, list[Node]]
) -> dict[str, list[Node]]:
    """Merge Tier-A clusters whose patches share a diff or overlap (Tier B)."""
    items = list(clusters.items())
    fingerprints: dict[str, tuple[set[str], set[tuple[str, int, int]]]] = {}
    for cid, findings in items:
        hashes: set[str] = set()
        hunks: set[tuple[str, int, int]] = set()
        for finding in findings:
            for patch in _patches_for_finding(graph, finding):
                dh = patch.props.get("diff_hash")
                if dh:
                    hashes.add(str(dh))
                hunks |= diff_signature(patch)
        fingerprints[cid] = (hashes, hunks)

    parent = {cid: cid for cid, _ in items}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][0], items[j][0]
            ha, hua = fingerprints[a]
            hb, hub = fingerprints[b]
            if not (ha or hua) or not (hb or hub):
                continue
            overlap = bool(ha & hb) or any(_hunks_overlap(x, y) for x in hua for y in hub)
            if overlap:
                parent[find(a)] = find(b)

    merged: dict[str, list[Node]] = defaultdict(list)
    for cid, findings in items:
        merged[find(cid)].extend(findings)
    return dict(merged)


# ── Canonical selection + application ────────────────────────────────


def select_canonical(cluster: list[Node]) -> Node:
    """Pick the canonical finding: highest CVSS → richest summary → oldest."""

    def rank(node: Node) -> tuple[float, int, float]:
        cvss = node.props.get("cvss_score")
        cvss_val = float(cvss) if isinstance(cvss, (int, float)) else 0.0
        summary_len = len(str(node.props.get("summary") or ""))
        return (cvss_val, summary_len, -node.created_at)

    return max(cluster, key=rank)


def apply_dedup(graph: KnowledgeGraph, *, use_patch_tier: bool = False) -> dict:
    """Cluster validated findings, mark duplicates, return a report."""
    clusters = cluster_findings(graph)
    if use_patch_tier:
        clusters = merge_clusters_by_patch(graph, clusters)

    total = sum(len(f) for f in clusters.values())
    clusters_with_dupes = 0
    duplicates_marked = 0

    for cluster_id, findings in clusters.items():
        for finding in findings:
            finding.props["cluster_id"] = cluster_id
        if len(findings) < 2:
            if findings:
                findings[0].props["canonical_id"] = findings[0].id
            continue
        clusters_with_dupes += 1
        canonical = select_canonical(findings)
        dup_ids: list[str] = []
        for finding in findings:
            finding.props["canonical_id"] = canonical.id
            if finding.id == canonical.id:
                continue
            finding.props["duplicate_of"] = canonical.id
            finding.props["superseded"] = True
            graph.upsert_edge(Edge.make(finding.id, canonical.id, EdgeKind.DUPLICATE_OF))
            dup_ids.append(finding.id)
            duplicates_marked += 1
        canonical.props["canonical"] = True
        canonical.props["duplicate_ids"] = dup_ids

    return {
        "total_findings": total,
        "clusters": len(clusters),
        "clusters_with_duplicates": clusters_with_dupes,
        "duplicates_marked": duplicates_marked,
        "patch_tier": use_patch_tier,
    }


@tool
def kg_dedup_findings(use_patch_signature: bool = False) -> str:
    """Collapse semantically equivalent FINDING nodes into clusters.

    WHEN TO USE: run once after the Verifier finishes and before
    dispatching the Patcher, so the Patcher and Exploiter only act on
    canonical findings. Findings sharing a structural signature (CWE +
    root-cause class + code location) are grouped; one canonical finding
    is kept per cluster and the rest get a ``DUPLICATE_OF`` edge plus a
    ``superseded`` prop.

    Args:
        use_patch_signature: also merge clusters whose proposed patches
            touch the same code (Tier B — only meaningful after the
            Patcher has proposed patches).

    Returns:
        JSON report: total findings, cluster count, clusters with
        duplicates, and how many findings were marked as duplicates.
    """
    graph, path = _load()
    report = apply_dedup(graph, use_patch_tier=use_patch_signature)
    _save(graph, path)
    return _json(report)


DEDUP_TOOLS = [kg_dedup_findings]
