"""FilesystemMiddleware variant that omits the `execute` tool.

Decepticon ships its own `bash` tool (see `decepticon/tools/bash/bash.py`) with
tmux session continuity, large-output offload to /workspace/.scratch/, ANSI
strip, and a 5M-char size watchdog. The upstream FilesystemMiddleware bundles
its own `execute` tool that funnels into the same DockerSandbox backend but
without those features.

Exposing both to an agent gives the LLM two ways to run shell commands. We
filter out `execute` so every agent has a single, well-engineered shell entry
point — `bash`. The dynamic system prompt FilesystemMiddleware generates is
based on `self.tools`, so removing `execute` here also drops the corresponding
prompt section automatically (no orphan reference).
"""

from __future__ import annotations

from deepagents.middleware.filesystem import FilesystemMiddleware


class FilesystemMiddlewareNoExecute(FilesystemMiddleware):
    """FilesystemMiddleware without the `execute` tool."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.tools = [t for t in self.tools if t.name != "execute"]
