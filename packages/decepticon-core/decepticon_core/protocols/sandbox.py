"""Sandbox transport protocol — matches the ``HTTPSandbox`` shape.

The framework's bash execution + filesystem operations all route
through a sandbox transport (today, ``decepticon.backends.HTTPSandbox``
talking to the sandbox container's FastAPI daemon). Plugin authors
implementing alternative transports — local subprocess, remote SSH,
or a different containerization runtime — conform to this Protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SandboxProtocol(Protocol):
    """Contract for a sandbox command-execution transport.

    Mandatory method:
        ``execute_command`` — run a shell command in the sandbox and
        return its output. Concrete signature varies per backend (sync
        vs async, blocking vs background); plugin authors should match
        the existing ``HTTPSandbox`` shape until a more formalized
        signature lands in a later phase.

    Additional methods commonly present on transports — ``read_file``,
    ``write_file``, ``list_directory`` — are exposed via the
    ``BackendProtocol`` instead so single-port adapters can satisfy
    either Protocol independently.
    """

    def execute_command(self, command: str, **kwargs: Any) -> Any: ...
