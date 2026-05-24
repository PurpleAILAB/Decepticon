"""Pure-pydantic types for the Decepticon contract layer.

Three submodules:

  * ``engagement`` — red-team planning documents (RoE, ConOps, OPPLAN,
    Finding, Objective, OpsecLevel, C2Tier, MITREPhase, ...). Was
    ``decepticon/core/schemas.py``.
  * ``llm`` — model selection types (Tier, AuthMethod, ModelProfile,
    ModelAssignment, ModelRouter, Credentials, LLMModelMapping,
    ProxyConfig). Was ``decepticon/llm/models.py``.
  * ``kg`` — knowledge-graph node / edge types and helpers. Was
    ``decepticon/tools/research/graph.py``.

These modules import only ``pydantic`` + stdlib + ``typing_extensions`` —
no ``langchain`` / ``langgraph`` / ``deepagents`` / ``httpx`` /
``fastapi``. Suitable to import from any context.
"""

from __future__ import annotations

from decepticon_core.types import engagement, kg, llm

__all__ = ["engagement", "llm", "kg"]
