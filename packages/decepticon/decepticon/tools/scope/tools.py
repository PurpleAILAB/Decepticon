"""LangChain @tool wrappers for the scope coverage engine."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.scope.coverage import plan_coverage


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _split_scope(scope: str) -> list[str]:
    """Split a newline-/comma-separated scope blob into clean descriptors."""
    parts = re.split(r"[,\n]+", scope)
    return [p.strip() for p in parts if p.strip()]


@tool
def plan_asset_coverage(scope: str) -> str:
    """Plan full specialist coverage for a bug-bounty program scope.

    Pass ``scope`` as a newline- and/or comma-separated list of in-scope asset
    descriptors: domains, wildcards (``*.example.com``), URLs, REST/GraphQL API
    hosts, mobile app links (App Store / Play Store URLs or ``.ipa``/``.apk``),
    source repos (GitHub/GitLab URLs, ``org/repo``, ``*.git``), firmware /
    ARM-TF project names, compiled binaries (``.so``/``.dll``/``.elf``),
    cryptographic library names, IPs/CIDRs, and smart-contract addresses.

    Returns JSON with, per asset, the classified asset type and the recommended
    specialist sub-agent role(s) to dispatch via ``task()`` so the asset is
    actually exercised — plus an ``uncovered`` list of assets that mapped to no
    specialist and must be handled manually (e.g. routed to ``analyst``). Use
    this first so every in-scope asset is covered and nothing is missed.
    """
    report = plan_coverage(_split_scope(scope))
    return _json(report.to_dict())


COVERAGE_TOOLS = [plan_asset_coverage]
