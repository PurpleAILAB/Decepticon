from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research import cve as cve_mod
from decepticon.tools.research._state import _json, _load, _save
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    Node,
    NodeKind,
)
from decepticon.tools.research.kgtools._helpers import (
    _parse_dependencies,
    _severity_from_score,
)

# ── CVE intelligence ────────────────────────────────────────────────────


@tool
async def cve_lookup(cve_ids: str) -> str:
    """Look up CVEs against NVD + EPSS with real-world exploitability scoring.

    WHEN TO USE: Whenever you find a service version (nmap -sV),
    dependency (package.json, requirements.txt, Cargo.lock), or CVE ID
    from any source. Returns a ranked list: CVEs with high CVSS *and*
    high EPSS (or KEV listing) bubble to the top.

    The composite ``score`` blends:
    - CVSS base (0-10)
    - EPSS probability (log-scaled)
    - CISA KEV membership (floors score at 9.0)

    Args:
        cve_ids: Comma-separated CVE IDs, e.g. ``"CVE-2024-12345,CVE-2023-99999"``.

    Returns:
        JSON list of exploitability records, highest score first.
    """
    ids = [c.strip() for c in cve_ids.split(",") if c.strip()]
    if not ids:
        return _json({"error": "no CVE IDs provided"})
    records = await cve_mod.lookup_cves(ids)
    return _json([r.to_dict() for r in records])


@tool
async def cve_by_package(package: str, version: str, ecosystem: str = "PyPI") -> str:
    """Query OSV for CVEs affecting ``package@version`` in an ecosystem.

    WHEN TO USE: After reading a manifest file (requirements.txt,
    package.json, go.sum, Cargo.lock). Pair with ``cve_lookup`` to score
    the results and prioritise bounty-worthy targets.

    Args:
        package: Package name (exact, case-sensitive).
        version: Installed version string.
        ecosystem: One of PyPI, npm, crates.io, Go, Maven, RubyGems,
            NuGet, Packagist, Pub, Hex.

    Returns:
        JSON list of vulnerability IDs (CVE/GHSA). Empty if the package
        version is clean (or the OSV API was unreachable).
    """
    ids = await cve_mod.lookup_package(package, version, ecosystem)
    return _json({"package": package, "version": version, "ecosystem": ecosystem, "ids": ids})


@tool
async def cve_enrich_dependencies(path: str, limit: int = 100, min_score: float = 7.0) -> str:
    """Parse a lockfile/manifest and enrich the graph with ranked CVE findings.

    Supported files:
      - requirements.txt
      - package-lock.json
      - go.sum
      - Cargo.lock
    """
    dep_path = Path(path)
    if not dep_path.exists():
        return _json({"error": f"file not found: {path}"})

    try:
        deps = _parse_dependencies(dep_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return _json({"error": f"dependency parse failed: {e}"})

    # Deduplicate and cap work for bounded runtime.
    dedup: dict[tuple[str, str, str], None] = {}
    for dep in deps:
        dedup[dep] = None
    planned = list(dedup.keys())[: max(limit, 1)]
    if not planned:
        return _json({"error": f"unsupported or empty dependency file: {dep_path.name}"})

    graph, out_path = _load()
    added = 0
    kept: list[dict[str, Any]] = []

    semaphore = asyncio.Semaphore(8)

    async def _lookup(
        dep: tuple[str, str, str],
    ) -> tuple[tuple[str, str, str], list[dict[str, Any]]]:
        name, version, ecosystem = dep
        async with semaphore:
            vuln_ids = await cve_mod.lookup_package(name, version, ecosystem)
        cve_ids = sorted(
            {vid for vid in vuln_ids if isinstance(vid, str) and vid.startswith("CVE-")}
        )
        if not cve_ids:
            return dep, []
        records = await cve_mod.lookup_cves(cve_ids, concurrency=6)
        return dep, [r.to_dict() for r in records if r.score >= min_score]

    results = await asyncio.gather(*[_lookup(dep) for dep in planned])

    for dep, records in results:
        name, version, ecosystem = dep
        dep_node = graph.upsert_node(
            Node.make(
                NodeKind.SERVICE,
                f"{name}@{version}",
                key=f"dependency::{ecosystem}::{name}@{version}",
                component_type="dependency",
                package=name,
                version=version,
                ecosystem=ecosystem,
                source="dependency-enricher",
            )
        )

        for rec in records:
            cve_id = str(rec.get("cve_id") or "")
            if not cve_id.startswith("CVE-"):
                continue
            score = float(rec.get("score") or 0.0)
            severity = _severity_from_score(score)
            cve_node = graph.upsert_node(
                Node.make(
                    NodeKind.CVE,
                    cve_id,
                    key=f"cve::{cve_id}",
                    cvss=rec.get("cvss"),
                    epss=rec.get("epss"),
                    kev=rec.get("kev"),
                    score=score,
                    source="nvd+epss+osv",
                )
            )
            vuln = graph.upsert_node(
                Node.make(
                    NodeKind.VULNERABILITY,
                    f"{name}@{version} affected by {cve_id}",
                    key=f"dep-vuln::{ecosystem}::{name}@{version}::{cve_id}",
                    package=name,
                    version=version,
                    ecosystem=ecosystem,
                    cve_id=cve_id,
                    severity=severity.value,
                    cvss=rec.get("cvss"),
                    cvss_vector=rec.get("cvss_vector"),
                    epss=rec.get("epss"),
                    epss_percentile=rec.get("epss_percentile"),
                    kev=rec.get("kev"),
                    score=score,
                    summary=rec.get("summary", ""),
                    references=rec.get("references", []),
                    source="dependency-enricher",
                )
            )
            graph.upsert_edge(Edge.make(dep_node.id, cve_node.id, EdgeKind.AFFECTS, weight=0.5))
            graph.upsert_edge(Edge.make(dep_node.id, vuln.id, EdgeKind.HAS_VULN, weight=0.5))
            graph.upsert_edge(Edge.make(vuln.id, cve_node.id, EdgeKind.MAPS_TO, weight=0.5))
            kept.append(
                {
                    "dependency": f"{name}@{version}",
                    "ecosystem": ecosystem,
                    "cve": cve_id,
                    "score": score,
                    "severity": severity.value,
                    "kev": bool(rec.get("kev")),
                }
            )
            added += 1

    _save(graph, out_path)
    kept.sort(key=lambda x: x["score"], reverse=True)
    return _json(
        {
            "dependency_file": str(dep_path),
            "dependencies_scanned": len(planned),
            "high_signal_records": added,
            "results": kept[:100],
            "stats": graph.stats(),
        }
    )
