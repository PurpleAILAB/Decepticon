"""Backend factory — HTTP-transport sandbox builder.

The agent code shouldn't know how the sandbox is deployed; it just asks
for a sandbox object. ``build_sandbox_backend()`` returns an
``HTTPSandbox`` that talks to a sandbox daemon over HTTP, which works in
every deployment target Decepticon supports today:

  - Dev / local-docker: sandbox container exposes the FastAPI daemon
    on ``http://sandbox:9999`` over the shared ``sandbox-net`` network.
  - GCE Spot VMs (SaaS silo plane): sandbox sibling container on the VM,
    daemon reachable on loopback.
  - Cloud Run (SaaS pool plane): sandbox runs as a sidecar in the same
    Cloud Run revision, reachable on ``localhost:9999`` via the shared
    network namespace.

There is no longer a docker-exec transport: the previous DockerSandbox
path required mounting ``/var/run/docker.sock`` into the langgraph
container, which is a host-escape vector for any prompt-injection-driven
RCE inside the agent process. HTTP-only consolidates on a single tested
code path and keeps the sandbox blast radius bounded by the container
boundary + the ``sandbox-net`` network.
"""

from __future__ import annotations

import functools
import os

from decepticon.backends.http_sandbox import HTTPSandbox


@functools.lru_cache(maxsize=8)
def _shared_sandbox(base_url: str, token: str | None) -> HTTPSandbox:
    return HTTPSandbox(base_url=base_url, token=token)


def build_sandbox_backend() -> HTTPSandbox:
    """Build the HTTP-transport sandbox backend.

    Returns the same ``HTTPSandbox`` instance for every call with the
    same ``(base_url, token)``. langgraph dev server invokes one factory
    per registered graph at startup; without a shared client each
    factory builds its own client + its own ``BackgroundJobTracker``,
    and the ``SandboxNotificationMiddleware`` instance held by each
    graph sees a different ``_jobs`` view than the bash tool actually
    registers against — completion notifications never reach the agent.
    Keying by ``(base_url, token)`` keeps tests that monkeypatch the env
    isolated and supports multi-tenant SaaS deployments where pools
    target distinct daemons.

    Returns:
        An ``HTTPSandbox`` instance pointed at the daemon URL.

    Env:
        SAAS_SANDBOX_URL
            Base URL of the sandbox daemon. Default
            ``http://localhost:9999`` (sibling-container / sidecar
            loopback). Compose sets this to ``http://sandbox:9999``.
        SAAS_SANDBOX_TOKEN
            Optional bearer token for daemon auth — recommended even on
            loopback as defence-in-depth.
    """
    base_url = os.environ.get("SAAS_SANDBOX_URL", "http://localhost:9999")
    token = os.environ.get("SAAS_SANDBOX_TOKEN") or None
    return _shared_sandbox(base_url, token)
