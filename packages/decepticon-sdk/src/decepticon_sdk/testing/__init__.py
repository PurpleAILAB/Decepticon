"""Test fakes for hermetic plugin tests.

Each fake satisfies the corresponding ``decepticon_core.protocols``
Protocol so plugin tests can ``isinstance(fake, BackendProtocol)`` and
``isinstance(fake, LLMProtocol)`` without spinning up a live framework.

Plugin authors:

    from decepticon_sdk.testing import FakeBackend, FakeLLM, FakeSandbox

    def test_my_middleware():
        backend = FakeBackend({"/skills/recon/index.md": "..."})
        llm = FakeLLM(responses=["mocked llm output"])
        # ... wire into your middleware-under-test

Phase 3 ships the in-memory fakes that cover ~80% of plugin test
scenarios. Future commits add ``make_test_engagement`` /
``make_test_opplan`` for richer engagement-level fixtures.
"""

from __future__ import annotations

from typing import Any


class FakeBackend:
    """In-memory ``BackendProtocol`` implementation for plugin tests.

    Backs every operation by a Python dict so plugin code under test
    sees a working filesystem with no IO. Satisfies the
    ``BackendProtocol`` duck-type contract — passes
    ``isinstance(fake, BackendProtocol)`` at runtime.
    """

    def __init__(self, files: dict[str, str | bytes] | None = None) -> None:
        self._files: dict[str, str | bytes] = dict(files or {})

    def read(self, path: str, **kwargs: Any) -> str | bytes:
        # Accept deepagents' ``offset`` / ``limit`` kwargs (passed through
        # by CompositeBackend.read) so the fake composes cleanly with the
        # real router. Slicing semantics mirror the canonical backend's
        # contract: offset is char/byte count from the start, limit caps
        # the returned slice.
        content = self._files[path]
        offset = kwargs.get("offset")
        limit = kwargs.get("limit")
        if offset is not None:
            content = content[offset:]
        if limit is not None:
            content = content[:limit]
        return content

    def write(self, path: str, content: str | bytes, **_: Any) -> None:
        self._files[path] = content

    def list(self, path: str, **_: Any) -> list[str]:
        prefix = path if path.endswith("/") else path + "/"
        return sorted(p for p in self._files if p.startswith(prefix))

    def exists(self, path: str, **_: Any) -> bool:
        return path in self._files


class FakeLLM:
    """Scripted ``LLMProtocol`` implementation for plugin tests.

    Returns each entry from ``responses`` in order on successive
    ``invoke()`` calls. After exhaustion, raises ``IndexError`` so
    over-invocations don't silently succeed.
    """

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses: list[Any] = list(responses or [])
        self._index: int = 0
        self.calls: list[Any] = []

    def invoke(self, input: Any, *, config: Any | None = None, **kwargs: Any) -> Any:
        del config, kwargs  # unused — fakes preserve only the signature
        self.calls.append(input)
        if self._index >= len(self._responses):
            raise IndexError(
                f"FakeLLM exhausted after {self._index} invocations; "
                f"add more responses or stop calling."
            )
        response = self._responses[self._index]
        self._index += 1
        return response


class FakeSandbox:
    """No-op ``SandboxProtocol`` implementation for plugin tests.

    Records every ``execute_command()`` call into ``self.commands`` and
    returns ``stdout`` from the constructor's response queue. Plugin
    tests inspect ``commands`` to assert command-construction logic
    without standing up a sandbox container.
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses: list[str] = list(responses or [])
        self._index: int = 0
        self.commands: list[str] = []

    def execute_command(self, command: str, **kwargs: Any) -> Any:
        del kwargs  # unused
        self.commands.append(command)
        if self._index >= len(self._responses):
            return ""  # default to empty stdout when queue exhausted
        response = self._responses[self._index]
        self._index += 1
        return response


__all__ = ["FakeBackend", "FakeLLM", "FakeSandbox"]
