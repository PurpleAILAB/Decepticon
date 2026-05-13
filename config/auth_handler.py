"""Auth provider dispatcher for ``auth/`` model slugs.

Routes incoming requests to the correct subscription handler based on the
slug after ``auth/``:

  - ``auth/claude-*``  → claude_code_handler  (Claude Code OAuth)

Adding a new ``auth/<prefix>-*`` subscription is one line in
``_PREFIX_HANDLERS``.

Note: ChatGPT Codex (user-facing ``auth/gpt-*``) does NOT go through this
dispatcher. ``litellm_dynamic_config.py`` aliases it to the dedicated
``codex-oauth/oauth-gpt-*`` route — the ``oauth-`` sentinel is required to
dodge LiteLLM's ``main.py:2561`` ``open_ai_chat_completion_models``
short-circuit, which would otherwise route bare ``gpt-*`` slugs to
api.openai.com. The dispatcher remains the multiplex point for any future
``auth/<prefix>-*`` namespace whose slugs do not collide.

This module is mounted into the LiteLLM container alongside the per-provider
handler files. It replaces the inline ``_select_auth_handler`` /
``_AuthDispatcher`` previously living at the top of ``litellm_startup.py``,
so the dispatch table is now testable in isolation and grows without
touching startup glue.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import litellm
from claude_code_handler import claude_code_handler_instance
from litellm import CustomLLM, ModelResponse

# Prefix → handler. Order matters only for documentation; lookup is exact.
_PREFIX_HANDLERS: list[tuple[str, CustomLLM]] = [
    ("claude-", claude_code_handler_instance),
]


def _select_auth_handler(model: str) -> CustomLLM:
    """Resolve a ``auth/<slug>`` model name to its subscription handler."""
    slug = model.split("/", 1)[-1] if "/" in model else model
    slug_lower = slug.lower()
    for prefix, handler in _PREFIX_HANDLERS:
        if slug_lower.startswith(prefix):
            return handler
    supported = ", ".join(f"{p}*" for p, _ in _PREFIX_HANDLERS)
    raise litellm.BadRequestError(
        message=(
            f"auth/ provider: model slug {slug!r} did not match any known "
            f"subscription handler. Supported prefixes: {supported}."
        ),
        model=model,
        llm_provider="auth",
    )


def _model_arg(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extract the ``model`` argument from a CustomLLM dispatch call.

    LiteLLM passes the model either positionally (first arg) or by keyword
    depending on the call site. The dispatcher needs the model to choose a
    handler, so it accepts both shapes.
    """
    return kwargs.get("model") or (args[0] if args else "")


class AuthDispatcher(CustomLLM):
    """Dispatch ``auth/`` requests to the right per-provider handler."""

    def completion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return _select_auth_handler(_model_arg(args, kwargs)).completion(*args, **kwargs)

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return await _select_auth_handler(_model_arg(args, kwargs)).acompletion(*args, **kwargs)

    def streaming(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        handler = _select_auth_handler(_model_arg(args, kwargs))
        result: Callable[..., Iterator[dict[str, Any]]] = handler.streaming
        return result(*args, **kwargs)

    async def astreaming(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        handler = _select_auth_handler(_model_arg(args, kwargs))
        async for chunk in handler.astreaming(*args, **kwargs):
            yield chunk


auth_handler_instance = AuthDispatcher()


__all__ = [
    "AuthDispatcher",
    "auth_handler_instance",
]
