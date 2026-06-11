"""LangChain @tool wrappers for the smart contract audit package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.contracts.foundry import (
    generate_access_control_test,
    generate_flashloan_test,
    generate_reentrancy_test,
)
from decepticon.tools.contracts.patterns import scan_solidity_source
from decepticon.tools.contracts.slither import (
    ingest_slither_json as _ingest_slither_json_impl,
)
from decepticon.tools.research._engagement_scope import _LEGACY_ENGAGEMENT_LABEL
from decepticon_core.utils.engagement_scope import get_active_engagement


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _resolve_engagement() -> str:
    """Engagement label for Slither ingest writes.

    Falls back to the shared ``_LEGACY_ENGAGEMENT_LABEL`` when the
    ``EngagementContextMiddleware`` contextvar is unset — matches the
    convention used by the AD ingest path.
    """
    return get_active_engagement() or _LEGACY_ENGAGEMENT_LABEL


@tool
def solidity_scan(source: str) -> str:
    """Run offline Solidity pattern scanner.

    Returns findings for: reentrancy, tx.origin, delegatecall, bad randomness,
    unchecked ecrecover, proxy init, missing access control, unchecked casts,
    flash-loan callbacks, oracle abuse.

    Args:
        source: Raw Solidity source code to scan.
    """
    findings = scan_solidity_source(source)
    return _json([f.to_dict() for f in findings])


@tool
def solidity_scan_file(path: str) -> str:
    """Read a .sol file from disk and run the pattern scanner."""
    try:
        src = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return _json({"error": str(e)})
    findings = scan_solidity_source(src)
    return _json(
        {"file": path, "count": len(findings), "findings": [f.to_dict() for f in findings]}
    )


@tool
def slither_ingest(path: str) -> str:
    """Ingest a Slither ``--json -`` output file into the engagement KG.

    Writes flow directly through ``KGStore.record_observations`` — a
    single atomic batch per file. Workflow: run ``slither . --json
    out.json`` then call this tool with the path to ``out.json``.
    """
    try:
        data = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return _json({"error": str(e)})
    engagement = _resolve_engagement()
    try:
        count = _ingest_slither_json_impl(data, engagement=engagement)
    except ValueError as exc:
        return _json({"error": str(exc)})
    return _json({"ingested": count})


@tool
def foundry_reentrancy_test(target: str, function: str, target_path: str = "src/Target.sol") -> str:
    """Generate a Foundry reentrancy PoC test for target.function."""
    h = generate_reentrancy_test(target, function, target_path)
    return _json({"path": h.path, "source": h.source})


@tool
def foundry_access_test(target: str, function: str, target_path: str = "src/Target.sol") -> str:
    """Generate a Foundry access-control bypass test for target.function."""
    h = generate_access_control_test(target, function, target_path)
    return _json({"path": h.path, "source": h.source})


@tool
def foundry_flashloan_test(target: str, target_path: str = "src/Target.sol") -> str:
    """Generate a Foundry flash-loan callback auth test for target."""
    h = generate_flashloan_test(target, target_path)
    return _json({"path": h.path, "source": h.source})


CONTRACT_TOOLS = [
    solidity_scan,
    solidity_scan_file,
    slither_ingest,
    foundry_reentrancy_test,
    foundry_access_test,
    foundry_flashloan_test,
]
