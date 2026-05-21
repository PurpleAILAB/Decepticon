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

import os

from decepticon.backends.http_sandbox import HTTPSandbox


def build_sandbox_backend() -> HTTPSandbox:
    """Build the HTTP-transport sandbox backend.

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
    return HTTPSandbox(base_url=base_url, token=token)
