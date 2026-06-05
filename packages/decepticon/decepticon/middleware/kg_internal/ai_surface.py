"""AI-attack-surface classification for recon ingest (ADR-0007).

The ``llm-redteam`` plugin can attack an exposed Ollama / framework
endpoint, but recon historically had no way to *recognize* one — an open
``11434`` landed as a ``Service`` with ``service=unknown``. This maps the
port the scanner already saw to a typed ``Technology`` node so the plugin
and the chain planner can route on it.

Port detection is the cheapest, most deterministic signal; the header /
banner / title classifiers (separate ingest passes) corroborate it and
add provenance. Two confidence tiers:

  * ``dedicated=True``  — a single-purpose AI default port (Ollama's
    11434). Recorded as a first-class detection.
  * ``dedicated=False`` — AI-associated but shared with generic services
    (Gradio / Ray dashboards also host non-AI apps). Recorded with
    ``guess=True`` so it cannot, on its own, drive an exploit chain
    (ADR-0007 corroborating-only rule).

The catalog is intentionally conservative — only ports whose AI default
is well documented — to keep precision high; banner/header passes widen
recall.
"""

from __future__ import annotations

from typing import Any

from decepticon_core.types.kg import TechnologyCategory, technology_key

DETECTED_BY_PORT = "port-catalog"

# port -> (category, product, dedicated)
_AI_PORT_CATALOG: dict[int, tuple[TechnologyCategory, str, bool]] = {
    11434: (TechnologyCategory.AI_RUNTIME, "ollama", True),
    7860: (TechnologyCategory.AI_FRAMEWORK, "gradio", False),
    8265: (TechnologyCategory.AI_FRAMEWORK, "ray", False),
}


def technology_for_port(port: int, source: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify a service port as an AI Technology.

    Returns ``(technology_node_observation, runs_edge)`` to append to the
    ingest batch — the edge belongs on the owning ``Service`` node's
    ``edges_out`` so it MERGEs as ``(Service)-[:RUNS]->(Technology)``.
    Returns ``None`` for any port not in the catalog.
    """
    entry = _AI_PORT_CATALOG.get(port)
    if entry is None:
        return None
    category, product, dedicated = entry
    key = technology_key(category, product)
    props: dict[str, Any] = {
        "name": product,
        "category": category.value,
        "detected_by": DETECTED_BY_PORT,
        "source": source,
    }
    if not dedicated:
        props["guess"] = True
    node = {"kind": "Technology", "key": key, "label": product, "props": props}
    edge = {"to_key": key, "kind": "RUNS", "props": {"detected_by": DETECTED_BY_PORT}}
    return node, edge
