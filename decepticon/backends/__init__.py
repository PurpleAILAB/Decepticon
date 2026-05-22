import importlib.resources

from deepagents.backends import CompositeBackend, FilesystemBackend

from .factory import build_sandbox_backend
from .http_sandbox import HTTPSandbox

# Skills ship as package data under ``decepticon/skills/`` and are read
# in-process by a local ``FilesystemBackend`` (not the sandbox container).
# Resolving via ``importlib.resources`` yields the correct on-disk location
# for every install shape — wheel (site-packages), editable (repo checkout),
# and the langgraph Docker image (``/app/decepticon/skills``) — so no
# container-specific path is hardcoded.
SKILLS_LOCAL_PATH = str(importlib.resources.files("decepticon") / "skills")


def make_agent_backend(sandbox):
    """Compose the runtime backend for a Decepticon agent.

    Routes ``/skills/`` to a local ``FilesystemBackend`` reading the
    package's ``decepticon/skills`` tree in-process, and routes everything
    else (notably ``/workspace/``) through the sandbox transport
    (``HTTPSandbox``). Returning a ``CompositeBackend`` lets
    ``SkillsMiddleware`` and ``FilesystemMiddleware`` share the same
    backend object while reading from different physical storage:

      /skills/...   ->  decepticon/skills/... read in-process (~5ms)
      /workspace/.. ->  sandbox container via HTTP (isolated, persistent)

    This replaces the previous pattern where every middleware used a raw
    sandbox for both paths, which forced an HTTP round-trip per skill
    read, and required the brittle ``_unwrap_backend()`` band-aid in
    ``decepticon.tools.skills`` to undo engagement-path mangling for
    ``/skills/`` lookups.
    """
    return CompositeBackend(
        default=sandbox,
        routes={
            "/skills/": FilesystemBackend(
                root_dir=SKILLS_LOCAL_PATH,
                virtual_mode=True,
            ),
        },
    )


__all__ = [
    "HTTPSandbox",
    "SKILLS_LOCAL_PATH",
    "build_sandbox_backend",
    "make_agent_backend",
]
