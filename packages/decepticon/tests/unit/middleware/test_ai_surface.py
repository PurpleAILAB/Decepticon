"""Unit tests for the AI-surface port classifier (ADR-0007).

``technology_for_port`` turns a scanned port into a typed ``Technology``
node + a ``RUNS`` edge the owning service carries, so the ``llm-redteam``
plugin can find an exposed AI runtime recon already saw.
"""

from __future__ import annotations

from decepticon.middleware.kg_internal.ai_surface import (
    DETECTED_BY_PORT,
    technology_for_port,
)
from decepticon_core.types.kg import TechnologyCategory, technology_key


def test_dedicated_port_is_confident_technology() -> None:
    result = technology_for_port(11434, "nmap")
    assert result is not None
    node, edge = result
    assert node["kind"] == "Technology"
    assert (
        node["key"]
        == technology_key(TechnologyCategory.AI_RUNTIME, "ollama")
        == "ai-runtime:ollama"
    )
    assert node["props"]["detected_by"] == DETECTED_BY_PORT
    # Dedicated ports are NOT guesses — they can anchor an exploit chain.
    assert "guess" not in node["props"]
    assert edge == {
        "to_key": "ai-runtime:ollama",
        "kind": "RUNS",
        "props": {"detected_by": DETECTED_BY_PORT},
    }


def test_shared_port_is_corroborating_guess_only() -> None:
    result = technology_for_port(7860, "nmap")
    assert result is not None
    node, _edge = result
    # Shared ports are flagged guess=True so they cannot drive a chain alone.
    assert node["props"]["guess"] is True
    assert node["key"] == "ai-framework:gradio"


def test_unknown_port_is_not_classified() -> None:
    assert technology_for_port(22, "nmap") is None
    assert technology_for_port(443, "nmap") is None


def test_edge_to_key_matches_node_key() -> None:
    node, edge = technology_for_port(11434, "nmap")  # type: ignore[misc]
    assert edge["to_key"] == node["key"]
