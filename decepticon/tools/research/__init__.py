"""Vulnerability research package.

High-value capabilities for 0-day discovery and exploit chain construction:

- ``graph``  — KnowledgeGraph: persistent JSON graph of assets, vulns, creds, chains
- ``cve``    — CVE/OSV/EPSS intelligence lookup with EPSS-weighted scoring
- ``sarif``  — SARIF ingestion (semgrep, bandit, gitleaks, trivy, nuclei)
- ``chain``  — Attack path planner (multi-hop graph search)
- ``poc``    — PoC reproducer validator with CVSS estimation
- ``fuzz``   — Fuzzing orchestration (libFuzzer, AFL++, jazzer, boofuzz)
- ``tools``  — LangChain @tool wrappers exposing all of the above to agents

State defaults to /workspace/kg.json (sandbox-bound JSON graph), with an
optional Neo4j backend via DECEPTICON_KG_BACKEND=neo4j for larger
multi-agent workloads.
"""

from __future__ import annotations

from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
    load_graph,
    save_graph,
)

__all__ = [
    "Edge",
    "EdgeKind",
    "KnowledgeGraph",
    "Node",
    "NodeKind",
    "Severity",
    "load_graph",
    "save_graph",
]
