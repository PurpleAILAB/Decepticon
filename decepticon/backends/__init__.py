from deepagents.backends import CompositeBackend, FilesystemBackend

from .factory import build_sandbox_backend
from .http_sandbox import HTTPSandbox

# Container-local path where the langgraph image bakes the skills tree
# (see ``containers/langgraph.Dockerfile``). Skills are READ-ONLY knowledge
# and live INSIDE the langgraph container — not the sandbox container —
# so reads happen as fast in-process ``FilesystemBackend`` calls instead
# of cross-container HTTP round-trips. This is the architectural reason
# the sandbox image no longer bakes skills: skills don't belong in an
# isolated execution environment, they belong next to the agent process
# that consumes them.
SKILLS_LOCAL_PATH = "/app/skills"


def make_agent_backend(sandbox):
    """Compose the runtime backend for a Decepticon agent.

    Routes ``/skills/`` to a local ``FilesystemBackend`` reading from the
    baked skill tree inside the langgraph container, and routes everything
    else (notably ``/workspace/``) through the sandbox transport
    (``HTTPSandbox``). Returning a ``CompositeBackend`` lets
    ``SkillsMiddleware`` and ``FilesystemMiddleware`` share the same
    backend object while reading from different physical storage:

      /skills/...   ->  /app/skills/... in the langgraph container (~5ms)
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
