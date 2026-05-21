"""Model router — resolves role to model name(s).

Thin layer over LLMModelMapping that provides convenience methods
for primary-only, primary+fallback, and ensemble resolution.
"""

from __future__ import annotations

from decepticon.llm.ensemble import EnsembleAssignment, resolve_ensemble
from decepticon.llm.models import Credentials, LLMModelMapping, ModelAssignment


class ModelRouter:
    """Resolves agent roles to model names."""

    def __init__(
        self,
        mapping: LLMModelMapping | None = None,
        *,
        credentials: Credentials | None = None,
    ):
        self.mapping = mapping or LLMModelMapping()
        # Kept so ensemble resolution can resolve a fresh LOW-tier chain
        # for the debater. ``None`` when the router was built from an
        # explicit mapping with no credential context — ensemble
        # resolution then degrades to chain-derived selection only.
        self.credentials = credentials

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

    def resolve_ensemble(self, role: str, *, default_role: str | None = None) -> EnsembleAssignment:
        """Return the role's :class:`EnsembleAssignment`.

        Carries the primary reasoner plus a family-aware counterpoint and
        debater. Used by the adversarial-debate validation path to pick an
        independent cross-family skeptic model.
        """
        return resolve_ensemble(
            role,
            mapping=self.mapping,
            credentials=self.credentials,
            default_role=default_role,
        )

    def get_assignment(self, role: str, *, default_role: str | None = None) -> ModelAssignment:
        """Return full ModelAssignment for a role.

        ``default_role`` lets plugin orchestrators inherit an OSS role's
        assignment when their own role is not in ``AGENT_TIERS`` —
        see ``LLMModelMapping.get_assignment`` for the contract.
        """
        return self.mapping.get_assignment(role, default_role=default_role)
