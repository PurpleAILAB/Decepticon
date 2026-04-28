"""Model router — resolves role to model name(s).

Thin layer over LLMModelMapping that provides convenience methods
for primary-only and primary+fallback resolution.
"""

from __future__ import annotations

from decepticon.llm.models import LLMModelMapping, ModelAssignment


class ModelRouter:
    """Resolves agent roles to model names."""

    def __init__(self, mapping: LLMModelMapping | None = None):
        self.mapping = mapping or LLMModelMapping()

    def resolve(self, role: str) -> str:
        """Return the primary model name for a role."""
        return self.get_assignment(role).primary

    def resolve_with_fallback(self, role: str) -> list[str]:
        """Return the full ordered chain: ``[primary, *fallbacks]``.

        The chain mirrors the user's credentials priority list as
        resolved at the agent's tier. ``ModelFallbackMiddleware``
        consumes this directly: primary first, each fallback tried
        in turn on failure.
        """
        assignment = self.get_assignment(role)
        return [assignment.primary, *assignment.fallbacks]

    def get_assignment(self, role: str) -> ModelAssignment:
        """Return full ModelAssignment for a role."""
        return self.mapping.get_assignment(role)
