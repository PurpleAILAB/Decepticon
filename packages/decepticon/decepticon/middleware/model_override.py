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

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from typing_extensions import override

from decepticon.llm.factory import LLMFactory, _model_drops_temperature
from decepticon_core.utils.logging import get_logger

log = get_logger("middleware.model_override")


def _read_override(request: Any) -> str:
    """Pull the override id out of runtime context or input state.

    Returns the empty string when nothing is set so the caller can
    short-circuit with a single truthiness check.
    """
    runtime = getattr(request, "runtime", None)
    if runtime is not None:
        ctx = getattr(runtime, "context", None) or {}
        if isinstance(ctx, dict):
            value = ctx.get("model_override", "")
            if isinstance(value, str) and value.strip():
                return value.strip()
    state = getattr(request, "state", None) or {}
    get = state.get if hasattr(state, "get") else (lambda _k, _d=None: None)
    value = get("model_override", "") or ""
    return value.strip() if isinstance(value, str) else ""


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


class ModelOverrideMiddleware(AgentMiddleware):
    """Per-invocation model swap driven by Runtime context / input state.

    Wired into every agent's middleware stack ahead of
    ``ModelFallbackMiddleware`` so the override picks the new primary
    and the existing fallback chain still applies on its failure.
    """

    @override
    def wrap_model_call(self, request, handler):
        override_id = _read_override(request)
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
        override_id = _read_override(request)
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
