"""LLM protocol — minimum bound-language-model surface.

The framework's ``LLMFactory`` produces bound langchain chat models;
this Protocol documents the surface plugin authors and library
consumers can rely on when accepting an LLM. Concrete langchain
``BaseChatModel`` instances naturally conform.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProtocol(Protocol):
    """Contract for bound language models the framework can drive.

    Mandatory method:
        ``invoke`` — synchronous call accepting a langchain-style
        messages list (or ``ChatPromptTemplate`` rendered output) and
        returning the model's response.

    ``ainvoke`` (async) is also expected on real instances; the
    Protocol intentionally only mandates the sync entry so plugin
    authors writing fake LLMs for tests don't need to implement both.
    """

    def invoke(self, input: Any, *, config: Any | None = None, **kwargs: Any) -> Any: ...
