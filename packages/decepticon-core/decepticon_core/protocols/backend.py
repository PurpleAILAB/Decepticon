"""Filesystem backend protocol — matches the deepagents Backend shape.

The Decepticon framework composes a ``CompositeBackend`` per agent
(``decepticon.backends.make_agent_backend``) that routes ``/skills/``
to in-process file reads and everything else to the sandbox transport.
Plugin authors implementing custom backends conform to this Protocol.

Phase 1 minimum surface — extended in subsequent commits as the
framework retrofit (Phase 2) wires plugins to backend routes via
``make_agent_backend(extra_routes=)``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BackendProtocol(Protocol):
    """Duck-type contract for a Decepticon filesystem backend.

    Implementations mediate read/write/list operations against the
    storage layer of their choice — local filesystem, remote sandbox,
    object store, etc. The framework's middleware (``SkillsMiddleware``,
    ``FilesystemMiddleware``) talks to backends via these methods.

    All methods are async-capable in the deepagents superset; sync
    implementations satisfy the Protocol too, since Protocol checks
    are signature-based and Python's duck typing tolerates both.
    """

    def read(self, path: str) -> str | bytes: ...

    def write(self, path: str, content: str | bytes) -> None: ...

    def list(self, path: str) -> list[str]: ...

    def exists(self, path: str) -> bool: ...
