"""Pure-pydantic types for the Decepticon contract layer.

Four submodules:

  * ``engagement`` — red-team planning documents (RoE, ConOps, OPPLAN,
    Finding, Objective, OpsecLevel, C2Tier, MITREPhase, ...). Was
    ``decepticon/core/schemas.py``.
  * ``llm`` — model selection types (Tier, AuthMethod, ModelProfile,
    ModelAssignment, ModelRouter, Credentials, LLMModelMapping,
    ProxyConfig). Was ``decepticon/llm/models.py``.
  * ``kg`` — knowledge-graph node / edge types and helpers. Was
    ``decepticon/tools/research/graph.py``.
  * ``roe`` — machine-readable Rules-of-Engagement *enforcement* schema
    (``EnforcementMode``, ``ScopeRule``, ``MachineEnforcement``,
    ``Decision``, ``evaluate_target``, ``evaluate_command``). The
    evaluation layer that decides allow/deny for a target or command;
    consumed by the framework's RoE-enforcement middleware. Distinct from
    ``engagement.RoE`` (the planning document).

These modules import only ``pydantic`` + stdlib + ``typing_extensions`` —
no ``langchain`` / ``langgraph`` / ``deepagents`` / ``httpx`` /
``fastapi``. Suitable to import from any context.
"""

from __future__ import annotations

from decepticon_core.types import asset_types, engagement, kg, llm, roe

__all__ = ["asset_types", "engagement", "llm", "kg", "roe"]
