"""Runtime model override — power for the CLI ``/model`` command.

Reads ``model_override`` from the agent runtime context (set by the CLI
client via ``config.configurable.model_override``) and rebinds the LLM
for the wrapped invocation. The override is per-call, not per-process,
so flipping the model in the REPL takes effect on the next ``submit()``
without restarting the agent or rebuilding the langgraph stack.

Resolution order, in priority:

  1. ``request.runtime.context.model_override`` (set by Runtime context)
  2. ``request.state["model_override"]`` (set by input state field)

When neither is set, the wrapped handler is called with the original
LLM untouched (the ``factory.get_model("decepticon")`` baked in at
agent construction).

The override value can be:
  - A LiteLLM model id like ``anthropic/claude-opus-4-7`` or
    ``groq/llama-3.3-70b-versatile`` — gets routed through the same
    LiteLLM proxy the rest of the stack uses.
  - An empty string or None — equivalent to no override.

Failure modes:
  - Unknown / malformed model id surfaces at the next provider call
    as a 404 wrapped through ``_reraise_with_actionable_message``;
    middleware does not pre-validate (kept dumb so the operator can
    experiment with brand-new model ids without a release).
"""

from __future__ import annotations

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from typing_extensions import Annotated, NotRequired, override

from decepticon.llm.factory import LLMFactory, _model_drops_temperature
from decepticon.middleware.state_reducers import reduce_converging_value
from decepticon_core.utils.logging import get_logger

log = get_logger("middleware.model_override")


def _read_override(request: Any, role: str | None = None) -> str:
    """Pull the override id out of runtime context or input state.

    Two shapes are honoured, in priority order:

      1. ``model_overrides`` — a ``{role: model_id}`` MAP. When ``role`` is
         present in the map, that per-agent model wins. This is the
         PER-AGENT policy surface — a multi-tenant host (e.g. the SaaS)
         threads one map per run so ``soundwave`` and ``exploit`` can run
         a different model than the rest WITHOUT an OSS release. Set once
         on the run (Runtime context or the ``model_overrides`` state
         channel, which propagates to sub-agents like ``proxy_api_key``).
      2. ``model_override`` — a single model id applied to EVERY agent
         (the CLI ``/model`` command). Fallback when the map has no entry
         for this role.

    Returns the empty string when nothing is set so the caller can
    short-circuit with a single truthiness check.
    """

    def _pick(container: Any) -> str:
        if not isinstance(container, dict):
            return ""
        if role:
            overrides = container.get("model_overrides")
            if isinstance(overrides, dict):
                value = overrides.get(role, "")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        value = container.get("model_override", "")
        return value.strip() if isinstance(value, str) and value.strip() else ""

    runtime = getattr(request, "runtime", None)
    if runtime is not None:
        ctx = getattr(runtime, "context", None) or {}
        picked = _pick(ctx if isinstance(ctx, dict) else {})
        if picked:
            return picked
    state = getattr(request, "state", None) or {}
    if hasattr(state, "get"):
        picked = _pick(
            {
                "model_overrides": state.get("model_overrides"),
                "model_override": state.get("model_override", ""),
            }
        )
        if picked:
            return picked
    return ""


def _build_proxied_llm(model_id: str, original: BaseChatModel) -> BaseChatModel:
    """Construct a ChatOpenAI bound to the LiteLLM proxy for ``model_id``.

    Mirrors the configuration the LLMFactory uses for the baked-in
    primary so streaming, tool calling, and fallback semantics match.
    Resolves the proxy config via :meth:`LLMFactory._resolve_proxy_config`
    so we honour ``DECEPTICON_LLM__PROXY_URL`` (e.g. ``http://litellm:4000``
    inside the langgraph container) instead of falling back to the bare
    pydantic defaults — which point at ``http://localhost:4000`` and
    bind to the langgraph container itself, where nothing listens. See
    issue #186.

    Temperature inherits from the original model when present, except
    for models the factory marks as dropping ``temperature`` (Opus 4.x
    family) — those would 400 at the upstream API even when the proxy
    masks the param. Same gate the factory's ``_create_chat_model``
    uses for the baked-in primary.
    """
    proxy = LLMFactory._resolve_proxy_config()
    if _model_drops_temperature(model_id):
        temperature = None
    else:
        temperature = getattr(original, "temperature", None)
    kwargs: dict[str, Any] = {
        "model": model_id,
        "base_url": proxy.url,
        "api_key": SecretStr(proxy.api_key),
        "timeout": proxy.timeout,
        "max_retries": proxy.max_retries,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


class ModelOverridesState(AgentState):
    """Declares a ``model_overrides`` channel on the orchestrator graph.

    Mirrors ``ProxyKeyState`` (see ``proxy_key_override``). The Platform
    DROPS an undeclared key from run ``input``, so without this channel a
    SaaS caller threading a per-role model map via run ``input`` could
    never reach ``request.state`` (the middleware's reachable read path;
    ``runtime.context`` needs a top-level ``context`` field the Platform
    forbids alongside ``config.configurable``). Set once on the kickoff
    run, persisted to the checkpoint, read on every model call.

    Reducer — ``reduce_converging_value`` (NOT the default LastValue):
    the orchestrator dispatches sub-agents in the SAME super-step and
    deepagents copies parent state (incl. ``model_overrides``) into each,
    so every sub-agent writes the map back to the parent in one tick. A
    LastValue channel rejects >1 write per step; a converging reducer
    keeps the (identical) non-None write. Same treatment ``proxy_api_key``
    and the launcher-set context channels already use.
    """

    model_overrides: NotRequired[Annotated[dict, reduce_converging_value]]


class ModelOverrideMiddleware(AgentMiddleware):
    """Per-invocation model swap driven by Runtime context / input state.

    Wired into every agent's middleware stack ahead of
    ``ModelFallbackMiddleware`` so the override picks the new primary
    and the existing fallback chain still applies on its failure.

    ``role`` is the agent this instance is attached to (the slot factory
    passes it). It lets a per-role ``model_overrides`` map target this
    agent specifically; without it only the global ``model_override``
    (CLI ``/model``) applies.
    """

    state_schema = ModelOverridesState

    def __init__(self, role: str | None = None) -> None:
        super().__init__()
        self._role = role

    @override
    def wrap_model_call(self, request, handler):
        override_id = _read_override(request, self._role)
        if not override_id:
            return handler(request)
        try:
            new_llm = _build_proxied_llm(override_id, request.model)
        except Exception as exc:
            log.warning("model_override %s failed to bind: %s", override_id, exc)
            return handler(request)
        log.info("model_override active: %s", override_id)
        return handler(request.override(model=new_llm))

    @override
    async def awrap_model_call(self, request, handler):
        override_id = _read_override(request, self._role)
        if not override_id:
            return await handler(request)
        try:
            new_llm = _build_proxied_llm(override_id, request.model)
        except Exception as exc:
            log.warning("model_override %s failed to bind: %s", override_id, exc)
            return await handler(request)
        log.info("model_override active: %s", override_id)
        return await handler(request.override(model=new_llm))


__all__ = ["ModelOverrideMiddleware"]
