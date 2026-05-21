"""Shared sandbox kernel — utilities used by BOTH the agent-side transport
backends and the in-container HTTP daemon.

Layering: this package is the lowest layer of the sandbox stack. It
contains the tmux session manager, the background-job tracker, and the
docker-less ``DaemonSandbox`` class. Everything else hangs off of it:

  ``decepticon.backends.docker_sandbox.DockerSandbox`` — agent-side,
      uses ``docker exec`` as transport. Imports ``TmuxSessionManager``
      from this package via the ``exec_prefix=["docker", "exec", ...]``
      configuration knob.

  ``decepticon.backends.http_sandbox.HTTPSandbox`` — agent-side,
      uses HTTP as transport. Imports ``BackgroundJob`` and
      ``BackgroundJobTracker`` from this package so the
      ``SandboxNotificationMiddleware`` mirror pattern works
      identically across the two backends.

  ``decepticon.sandbox_server.app`` — sandbox-side, FastAPI daemon.
      Imports ``DaemonSandbox`` from this package and exposes its
      methods over HTTP.

Why a separate package: the OSS sandbox container image is a *passive*
container (Kali Linux + red-team tools + tmux); historically it shipped
zero decepticon Python code. Adding the daemon to the same image
required *some* in-container Python, but the agent-side transport
classes (``DockerSandbox``, ``HTTPSandbox``, ``factory``) have no
business inside the sandbox. Splitting the shared utilities out keeps
the original "agent has everything, sandbox has nothing" boundary
intact: the sandbox image now ships only ``sandbox_kernel`` + ``sandbox_server``,
the agent (langgraph image) keeps ``backends`` + everything else.
"""

from decepticon.sandbox_kernel.jobs import BackgroundJob, BackgroundJobTracker
from decepticon.sandbox_kernel.tmux import (
    AUTO_BACKGROUND_SECONDS,
    MAX_OUTPUT_CHARS,
    POLL_INTERVAL,
    PS1_PATTERN,
    SIZE_WATCHDOG_CHARS,
    SIZE_WATCHDOG_INTERVAL,
    STALL_SECONDS,
    TmuxCommandError,
    TmuxSessionManager,
)

__all__ = [
    "AUTO_BACKGROUND_SECONDS",
    "BackgroundJob",
    "BackgroundJobTracker",
    "MAX_OUTPUT_CHARS",
    "POLL_INTERVAL",
    "PS1_PATTERN",
    "SIZE_WATCHDOG_CHARS",
    "SIZE_WATCHDOG_INTERVAL",
    "STALL_SECONDS",
    "TmuxCommandError",
    "TmuxSessionManager",
]
