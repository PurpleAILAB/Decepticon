from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research.chain import critical_path_score, plan_chains, promote_chain
from decepticon.tools.research.graph import NodeKind
from decepticon.tools.research._state import _json, _load, _save


# ── Chain planner ──────────────────────────────────────────────────────


@tool
def plan_attack_chains(
    max_depth: int = 8, max_cost: float = 20.0, top_k: int = 10, promote: bool = False
) -> str:
    """Enumerate multi-hop exploit chains from entrypoints to crown jewels.

    WHEN TO USE: After you've added ENTRYPOINT nodes (exposed public
    surfaces) and CROWN_JEWEL nodes (bounty-worthy targets) and connected
    vulns between them with ``enables``/``leaks``/``grants`` edges. The
    planner walks the graph with Dijkstra and returns the cheapest
    complete paths.

    COST MODEL: lower is better. Critical vulns shrink cost (0.4x),
    validated PoCs shrink further (0.5x), high edge weight grows it.

    Args:
        max_depth: Max hops per chain (default 8).
        max_cost: Discard paths exceeding this total cost (default 20).
        top_k: Return the top-K cheapest chains (default 10).
        promote: If true, persist each computed chain as a ``chain`` node
            in the graph so future queries can reference it.

    Returns:
        JSON list of chains with entrypoint, crown jewel, hop sequence,
        and total cost.
    """
    chains = plan_chains(max_depth=max_depth, max_cost=max_cost, top_k=top_k)
    promoted_ids: list[str] = []
    if promote:
        for chain in chains:
            promoted_ids.append(promote_chain(chain))
    return _json(
        {
            "count": len(chains),
            "promoted": promoted_ids if promote else [],
            "chains": [c.to_dict() for c in chains],
        }
    )


@tool
def suggest_objectives_from_chains(
    top_k: int = 5,
    max_depth: int = 8,
    max_cost: float = 20.0,
) -> str:
    """Convert top-ranked attack chains into OPPLAN-ready objective drafts.

    This does not mutate OPPLAN; it returns draft payloads for the
    orchestrator's `add_objective` tool.
    """
    chains = plan_chains(top_k=max(top_k, 1), max_depth=max_depth, max_cost=max_cost)
    if not chains:
        return _json({"count": 0, "objectives": []})

    ranked = sorted(chains, key=critical_path_score, reverse=True)
    drafts: list[dict[str, Any]] = []

    for idx, chain in enumerate(ranked[:top_k], start=1):
        chain_score = critical_path_score(chain)

        phase = "initial-access"
        if any(step.node_kind in {NodeKind.CREDENTIAL, NodeKind.SECRET} for step in chain.steps):
            phase = "post-exploit"
        elif (
            "admin" in chain.crown_jewel_label.lower()
            or "domain" in chain.crown_jewel_label.lower()
        ):
            phase = "post-exploit"

        title = f"Exploit chain {idx}: {chain.entrypoint_label} -> {chain.crown_jewel_label}"
        acceptance = [
            f"Demonstrate path from {chain.entrypoint_label} to {chain.crown_jewel_label}.",
            "Capture evidence for each hop (commands, outputs, and impacted asset IDs).",
            "Validate the highest-risk step with PoC evidence or explain why blocked.",
        ]
        drafts.append(
            {
                "priority": idx,
                "phase": phase,
                "title": title,
                "description": chain.summary(),
                "acceptance_criteria": acceptance,
                "mitre": [],
                "opsec": "standard",
                "notes": {
                    "chain_total_cost": chain.total_cost,
                    "chain_score": chain_score,
                    "path": chain.path_labels,
                },
            }
        )

    return _json({"count": len(drafts), "objectives": drafts})


# ── PoC validation ─────────────────────────────────────────────────────


@tool
async def validate_finding(
    vuln_id: str,
    poc_command: str,
    success_patterns: str,
    negative_command: str = "",
    negative_patterns: str = "",
    cvss_vector: str = "",
) -> str:
    """Run a PoC inside the sandbox and mark the vuln validated on hit.

    WHEN TO USE: After identifying a vulnerability, craft a minimal
    reproducer and run it here. The validator applies ZFP (zero false
    positives) by requiring a negative control: if the same request
    without the payload *also* fires the success pattern, the result is
    demoted.

    SUCCESS PATTERNS are Python regexes (DOTALL + IGNORECASE). Use simple
    substrings when you don't need regex power.

    CVSS_VECTOR example: ``"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"``
    If provided, the base score is computed and written back onto the
    vuln node.

    Args:
        vuln_id: Graph id of the vulnerability node to validate.
        poc_command: Bash command that exercises the vulnerability.
        success_patterns: Comma-separated list of regexes to match in stdout.
        negative_command: Optional baseline command (same request without payload).
        negative_patterns: Comma-separated regexes expected in the baseline.
        cvss_vector: Optional CVSS v3.1 vector string.

    Returns:
        JSON validation record including success signals, negative
        control hits, stdout excerpt, and CVSS score if provided.
    """
    from decepticon.tools.bash.bash import get_sandbox
    from decepticon.tools.research.poc import (
        AC,
        AV,
        PR,
        UI,
        CVSSVector,
        Impact,
        Scope,
        sandbox_runner,
        validate_poc,
    )

    sandbox = get_sandbox()
    if sandbox is None:
        return _json({"error": "HTTPSandbox not initialized"})

    def _split(s: str) -> list[str]:
        return [p.strip() for p in s.split(",") if p.strip()]

    cvss: CVSSVector | None = None
    if cvss_vector:
        try:
            parts = {kv.split(":")[0]: kv.split(":")[1] for kv in cvss_vector.split("/")[1:]}
            cvss = CVSSVector(
                av=AV(parts.get("AV", "N")),
                ac=AC(parts.get("AC", "L")),
                pr=PR(parts.get("PR", "N")),
                ui=UI(parts.get("UI", "N")),
                scope=Scope(parts.get("S", "U")),
                c=Impact(parts.get("C", "H")),
                i=Impact(parts.get("I", "H")),
                a=Impact(parts.get("A", "H")),
            )
        except (ValueError, KeyError, IndexError) as e:
            return _json({"error": f"bad CVSS vector: {e}"})

    graph, path = _load()
    runner = sandbox_runner(sandbox)
    result = await validate_poc(
        vuln_id=vuln_id,
        poc_command=poc_command,
        success_patterns=_split(success_patterns),
        runner=runner,
        negative_command=negative_command or None,
        negative_patterns=_split(negative_patterns) if negative_patterns else None,
        cvss=cvss,
        graph=graph,
    )
    _save(graph, path)
    return _json(result.to_dict())
