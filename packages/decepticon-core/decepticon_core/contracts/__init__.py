"""Plugin contracts — the surface plugin authors implement against.

Submodules:

  * ``slots`` — middleware slot enum and per-role applicability mapping.
    Was ``decepticon.agents.middleware_slots``; framework keeps the
    default factory helpers (which need langchain runtime) and imports
    the enum/constants from here.

Future Phase 1 commits will add ``contributions`` (ToolContribution,
MiddlewareContribution, PromptContribution, SubAgentContribution,
SafetyDeclaration) and ``PluginBundle`` proper (currently lives at
``decepticon_core.plugin_loader`` after Phase 1.B).
"""

from __future__ import annotations

from decepticon_core.contracts import contributions, slots
from decepticon_core.contracts.contributions import (
    MiddlewareContribution,
    PromptContribution,
    SafetyDeclaration,
    SubAgentContribution,
    ToolContribution,
)

__all__ = [
    "MiddlewareContribution",
    "PromptContribution",
    "SafetyDeclaration",
    "SubAgentContribution",
    "ToolContribution",
    "contributions",
    "slots",
]
