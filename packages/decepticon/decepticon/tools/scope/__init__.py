"""Scope coverage package — bug-bounty asset routing.

Classifies free-form in-scope asset descriptors into the canonical AssetType
taxonomy, resolves each type's wired Phase(s), and maps phases to the
specialist role(s) that own them, so the orchestrator achieves full asset
coverage: every in-scope asset routed to the right specialist, nothing missed.

- ``classify_asset`` — heuristic descriptor -> AssetType name
- ``plan_coverage``  -> ``CoverageReport`` routing every asset to specialists
- ``AssetCoverage`` / ``CoverageReport`` — typed routing results
"""

from __future__ import annotations

from decepticon.tools.scope.coverage import (
    AssetCoverage,
    CoverageReport,
    classify_asset,
    plan_coverage,
)

__all__ = [
    "AssetCoverage",
    "CoverageReport",
    "classify_asset",
    "plan_coverage",
]
