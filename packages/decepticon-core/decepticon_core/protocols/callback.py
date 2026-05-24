"""Callback protocol — matches the langchain ``BaseCallbackHandler`` shape.

Plugin-shipped callback handlers register via the ``decepticon.callbacks``
entry-point group; the framework wires them into every agent
construction. Implementations get called at well-known lifecycle
points (LLM start/end, tool start/end, chain start/end) for
observability or side-effect plumbing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CallbackProtocol(Protocol):
    """Contract for plugin-contributed callback handlers.

    Every callback hook is optional; the framework calls each only if
    it is defined on the implementation. The Protocol declares the
    canonical set; concrete handlers typically subclass langchain's
    ``BaseCallbackHandler`` which automatically conforms.
    """

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None: ...

    def on_llm_end(self, *args: Any, **kwargs: Any) -> None: ...

    def on_tool_start(self, *args: Any, **kwargs: Any) -> None: ...

    def on_tool_end(self, *args: Any, **kwargs: Any) -> None: ...
