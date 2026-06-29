"""Vaccine State Middleware — injects live vaccine context into every agent turn.

At the start of each LLM invocation the middleware queries the engagement
knowledge graph for:

1. **Unmitigated Findings** — nodes with no ``vaccine_status`` or
   ``vaccine_status == "unmitigated"``; these are the agent's work queue.
2. **Active DefenseActions** — deployed but not yet verified controls,
   giving the agent awareness of in-flight remediations.
3. **Verification history** — recent ``VerificationResult`` nodes with
   their dispositions, so the agent can reason about retry strategy.

The assembled state is serialised as a compact JSON block and prepended to
the message list as a ``SystemMessage`` with ``name="vaccine_state"``.  This
keeps the agent's context window grounded in the graph rather than relying
on the LLM to remember prior tool outputs across many turns.

Slot: ``vaccine_state`` — inserted before the default middleware stack so
the system prompt (which references the state) always has data to work with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import SystemMessage

from decepticon_core.types.kg import EdgeKind, KnowledgeGraph, NodeKind


@dataclass(slots=True)
class VaccineStateMiddleware:
    """Middleware that injects vaccine-loop situational awareness.

    Attributes:
        backend: the deepagents filesystem backend used to load the KG.
        max_findings: cap on unmitigated findings injected per turn to
            avoid blowing the context window on large engagements.
        max_history: cap on recent verification results shown.
    """

    backend: Any
    max_findings: int = 20
    max_history: int = 10

    def _load_graph(self) -> KnowledgeGraph | None:
        """Load the engagement knowledge graph from the backend."""
        try:
            return self.backend.load_knowledge_graph()
        except Exception:
            return None

    def _unmitigated_findings(self, graph: KnowledgeGraph) -> list[dict[str, Any]]:
        """Return findings that still need vaccine remediation."""
        results: list[dict[str, Any]] = []
        for node in graph.nodes(kind=NodeKind.FINDING):
            status = node.properties.get("vaccine_status")
            if status in (None, "unmitigated"):
                results.append({
                    "id": node.id,
                    "title": node.properties.get("title", node.id),
                    "severity": node.properties.get("severity", "unknown"),
                    "techniques": [
                        t.properties.get("name", t.id)
                        for t in graph.neighbors(
                            node.id,
                            edge_kind=EdgeKind.USES_TECHNIQUE,
                            direction="out",
                        )
                    ],
                })
                if len(results) >= self.max_findings:
                    break
        return results

    def _active_defense_actions(self, graph: KnowledgeGraph) -> list[dict[str, Any]]:
        """Return deployed but unverified defense actions."""
        results: list[dict[str, Any]] = []
        for node in graph.nodes(kind=NodeKind.DEFENSE_ACTION):
            if node.properties.get("status") == "deployed":
                results.append({
                    "id": node.id,
                    "action_type": node.properties.get("action_type", "unknown"),
                    "description": node.properties.get("description", ""),
                    "finding_id": node.properties.get("finding_id", ""),
                    "deployed_at": node.properties.get("deployed_at", ""),
                })
        return results

    def _recent_verifications(self, graph: KnowledgeGraph) -> list[dict[str, Any]]:
        """Return recent verification results, newest first."""
        results: list[dict[str, Any]] = []
        for node in graph.nodes(kind=NodeKind.VERIFICATION_RESULT):
            results.append({
                "id": node.id,
                "disposition": node.properties.get("disposition", "pending"),
                "finding_id": node.properties.get("finding_id", ""),
                "defense_action_id": node.properties.get("defense_action_id", ""),
                "verified_at": node.properties.get("verified_at", ""),
            })
        # Sort newest-first and cap.
        results.sort(key=lambda r: r.get("verified_at", ""), reverse=True)
        return results[: self.max_history]

    def __call__(self, messages: list[Any], **kwargs: Any) -> list[Any]:
        """Inject vaccine state as a leading system message.

        Args:
            messages: the current message list being sent to the LLM.
            **kwargs: forwarded unchanged.

        Returns:
            Updated message list with the vaccine state prepended.
        """
        graph = self._load_graph()
        if graph is None:
            return messages

        import json

        state: dict[str, Any] = {
            "unmitigated_findings": self._unmitigated_findings(graph),
            "active_defense_actions": self._active_defense_actions(graph),
            "recent_verifications": self._recent_verifications(graph),
        }

        total_unmitigated = sum(
            1
            for n in graph.nodes(kind=NodeKind.FINDING)
            if n.properties.get("vaccine_status") in (None, "unmitigated")
        )
        total_mitigated = sum(
            1
            for n in graph.nodes(kind=NodeKind.FINDING)
            if n.properties.get("vaccine_status") == "mitigated"
        )
        state["summary"] = {
            "total_findings": total_unmitigated + total_mitigated,
            "unmitigated": total_unmitigated,
            "mitigated": total_mitigated,
            "coverage_pct": (
                round(total_mitigated / (total_unmitigated + total_mitigated) * 100, 1)
                if (total_unmitigated + total_mitigated) > 0
                else 0.0
            ),
        }

        state_text = (
            "## Vaccine State (auto-injected)\n\n"
            f"```json\n{json.dumps(state, indent=2)}\n```"
        )
        vaccine_msg = SystemMessage(content=state_text, name="vaccine_state")
        return [vaccine_msg, *messages]
