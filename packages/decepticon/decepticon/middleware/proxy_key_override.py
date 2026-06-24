"""Per-run LiteLLM virtual-key override — multi-tenant cost attribution.

In a SHARED langgraph serving many orgs, the baked-in model authenticates to
the LiteLLM proxy with the env master key (``DECEPTICON_LLM__PROXY_API_KEY``),
so ALL spend lands on the master key and can't be split per customer. The SaaS
launch flow mints a virtual key per engagement (the key's ``team_id`` is the
org) and threads it in as ``config.configurable.proxy_api_key``. This middleware
reads that key and rebinds the model for the wrapped call to authenticate with
it, so LiteLLM attributes the spend to that key's team (= the org) — the basis
for per-customer billing + budget enforcement (``/team/info`` spend per org).

Slot placement: ``PROXY_KEY_OVERRIDE`` sits AFTER ``MODEL_FALLBACK`` in the
canonical slot order, i.e. inner-most relative to model selection. So it
re-keys whatever model is actually about to be called — including a fallback
model the fallback middleware swapped in, and any model the model-override
middleware selected. Keep that ordering or fallbacks mis-attribute.

Resolution order (mirrors ``model_override``):

  1. ``request.runtime.context.proxy_api_key`` (Runtime context)
  2. ``request.state["proxy_api_key"]`` (input state)

When neither is set the wrapped handler runs with the original env-keyed model
untouched — so single-tenant / OSS deployments (no per-run key) are unaffected.

The key value is never logged here, and ``event_logging`` already redacts
``api_key`` fields, so the virtual key does not leak into event streams.
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

log = get_logger("middleware.proxy_key_override")


def _read_proxy_key(request: Any) -> str:
    """Pull the per-run virtual key out of runtime context or input state.

    Returns the empty string when nothing is set so the caller can
    short-circuit with a single truthiness check.
    """
    runtime = getattr(request, "runtime", None)
    if runtime is not None:
        ctx = getattr(runtime, "context", None) or {}
        if isinstance(ctx, dict):
            value = ctx.get("proxy_api_key", "")
            if isinstance(value, str) and value.strip():
                return value.strip()
    state = getattr(request, "state", None) or {}
    get = state.get if hasattr(state, "get") else (lambda _k, _d=None: None)
    value = get("proxy_api_key", "") or ""
    return value.strip() if isinstance(value, str) else ""


def _rekey_model(original: BaseChatModel, api_key: str) -> BaseChatModel:
    """Rebuild ``original`` against the LiteLLM proxy, authenticating with
    ``api_key`` instead of the env master key.

    Rebuild rather than ``model_copy`` because the OpenAI client binds the API
    key at ``__init__`` — a shallow copy would keep the old client (old key).
    Model id, base url, timeout, retries, and the temperature gate mirror the
    baked-in primary (same as ``model_override._build_proxied_llm``) so
    streaming / tool calling / fallback semantics are unchanged; only the
    Authorization key differs.
    """
    proxy = LLMFactory._resolve_proxy_config()
    model_id = getattr(original, "model_name", None) or getattr(original, "model", None)
    if not model_id:
        raise ValueError("cannot resolve model id from current model for re-key")
    kwargs: dict[str, Any] = {
        "model": model_id,
        "base_url": proxy.url,
        "api_key": SecretStr(api_key),
        "timeout": proxy.timeout,
        "max_retries": proxy.max_retries,
    }
    if not _model_drops_temperature(str(model_id)):
        temperature = getattr(original, "temperature", None)
        if temperature is not None:
            kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


class ProxyKeyOverrideMiddleware(AgentMiddleware):
    """Per-invocation LiteLLM key swap driven by Runtime context / input state.

    No-op when no per-run key is present, so OSS / single-tenant deployments
    behave exactly as before.
    """

    @override
    def wrap_model_call(self, request, handler):
        key = _read_proxy_key(request)
        if not key:
            return handler(request)
        try:
            new_llm = _rekey_model(request.model, key)
        except Exception as exc:
            log.warning("proxy_key_override failed to bind: %s", exc)
            return handler(request)
        log.info("proxy_key_override active (per-run virtual key)")
        return handler(request.override(model=new_llm))

    @override
    async def awrap_model_call(self, request, handler):
        key = _read_proxy_key(request)
        if not key:
            return await handler(request)
        try:
            new_llm = _rekey_model(request.model, key)
        except Exception as exc:
            log.warning("proxy_key_override failed to bind: %s", exc)
            return await handler(request)
        log.info("proxy_key_override active (per-run virtual key)")
        return await handler(request.override(model=new_llm))


__all__ = ["ProxyKeyOverrideMiddleware"]
