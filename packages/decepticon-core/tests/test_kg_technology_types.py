"""Regression tests for the Technology KG vocabulary (ADR-0007).

AI-surface and tech-detection recon classifiers (HTTP header, port
catalog, nmap banner, frontend title) write detected products as
``Technology`` nodes linked ``(Service)-[:RUNS]->(Technology)``.

``NodeKind`` values are Neo4j labels and ``EdgeKind`` values are Neo4j
relationship types (1:1, per the ``kg`` module docstring), and the
``technology_key`` format is the ``(key, engagement)`` MERGE contract the
V004 migration's uniqueness constraint enforces. Pin the exact strings
here so a rename can't silently break the classifier ingest or the
chain-planner queries that read these nodes.
"""

from __future__ import annotations

import pytest

from decepticon_core.types.kg import (
    EdgeKind,
    Node,
    NodeKind,
    TechnologyCategory,
    technology_key,
)


def test_technology_node_kind_has_neo4j_label() -> None:
    assert NodeKind.TECHNOLOGY == "Technology"


def test_runs_edge_kind_has_neo4j_relationship_type() -> None:
    assert EdgeKind.RUNS == "RUNS"


def test_technology_categories_are_the_closed_vocabulary() -> None:
    # The AI-surface cluster ADR-0007 exists to make queryable.
    assert TechnologyCategory.AI_RUNTIME == "ai-runtime"
    assert TechnologyCategory.AI_PROXY == "ai-proxy"
    assert TechnologyCategory.AI_FRAMEWORK == "ai-framework"
    assert TechnologyCategory.AI_SDK_CLIENT == "ai-sdk-client"


def test_technology_key_is_category_prefixed_and_normalized() -> None:
    assert technology_key(TechnologyCategory.AI_RUNTIME, "Ollama") == "ai-runtime:ollama"
    # Whitespace collapses so banner "vLLM  server" and header "vLLM server"
    # MERGE onto one node.
    assert (
        technology_key(TechnologyCategory.AI_RUNTIME, "  vLLM  server ") == "ai-runtime:vllm-server"
    )


def test_technology_key_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        technology_key(TechnologyCategory.AI_RUNTIME, "   ")


def test_two_classifiers_same_product_dedup_to_one_node() -> None:
    key = technology_key(TechnologyCategory.AI_RUNTIME, "ollama")
    from_header = Node.make(NodeKind.TECHNOLOGY, "ollama", key=key, detected_by="httpx-ai-header")
    from_banner = Node.make(NodeKind.TECHNOLOGY, "ollama", key=key, detected_by="nmap-banner")
    # Same (kind, key) → same deterministic id → one node after merge.
    assert from_header.id == from_banner.id


def test_distinct_categories_are_distinct_nodes() -> None:
    runtime = Node.make(
        NodeKind.TECHNOLOGY,
        "ollama",
        key=technology_key(TechnologyCategory.AI_RUNTIME, "ollama"),
    )
    proxy = Node.make(
        NodeKind.TECHNOLOGY,
        "ollama",
        key=technology_key(TechnologyCategory.AI_PROXY, "ollama"),
    )
    assert runtime.id != proxy.id
