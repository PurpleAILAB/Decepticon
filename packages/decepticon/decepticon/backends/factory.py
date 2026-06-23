"""Backend factory — HTTP-transport sandbox builder.

The agent code shouldn't know how the sandbox is deployed; it just asks
for a sandbox object. ``build_sandbox_backend()`` returns an
``HTTPSandbox`` that talks to a sandbox daemon over HTTP, which works in
every deployment target Decepticon supports today:

  - Dev / local-docker: sandbox container exposes the FastAPI daemon
    on ``http://sandbox:9999`` over the shared ``sandbox-net`` network.
  - Per-VM silo plane: sandbox sibling container on the VM, daemon
    reachable on loopback.
  - Cloud Run pool plane: sandbox runs as a sidecar in the same
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

_DEFAULT_SANDBOX_URL = "http://localhost:9999"


# Sized for the multi-tenant case: a single SHARED langgraph process can serve
# many concurrent engagements, each routed (via the bash tool's per-run
# ``configurable.sandbox_url`` — see ``tools/bash/bash.py:_sandbox_from_config``)
# to its OWN per-engagement sandbox. Each must keep its own client so the
# ``SandboxNotificationMiddleware._jobs`` view stays consistent within a run;
# under-sizing would evict a live engagement's client mid-flight. 128 covers
# realistic per-process concurrency with headroom.
@functools.lru_cache(maxsize=128)
def _shared_sandbox(base_url: str, token: str | None) -> HTTPSandbox:
    return HTTPSandbox(base_url=base_url, token=token)


def _resolve_endpoint() -> tuple[str, str | None]:
    """Resolve the sandbox ``(base_url, token)``, preferring per-run config.

    A shared langgraph process serving many engagements cannot reach a
    per-engagement sandbox through one process-wide env var. So we first consult
    the current run's LangGraph config — ``configurable.sandbox_url`` /
    ``configurable.sandbox_token``, set by the caller per invocation — then fall
    back to ``SANDBOX_URL`` / ``SANDBOX_TOKEN``. The env path still covers
    single-tenant, sidecar, local-docker, and import-time construction where
    there is no active run context.
    """
    url: str | None = None
    token: str | None = None
    try:
        # get_config() exposes the current run's RunnableConfig via contextvars
        # while a graph node executes. It raises RuntimeError outside a runnable
        # context (for example, import-time agent construction), so fall back to
        # env in that case.
        from langgraph.config import get_config

        configurable = (get_config() or {}).get("configurable") or {}
        raw_url = configurable.get("sandbox_url")
        raw_token = configurable.get("sandbox_token")
        url = raw_url if isinstance(raw_url, str) and raw_url else None
        token = raw_token if isinstance(raw_token, str) and raw_token else None
    except Exception:
        pass

    if url is None:
        url = os.environ.get("SANDBOX_URL", _DEFAULT_SANDBOX_URL)
    if token is None:
        token = os.environ.get("SANDBOX_TOKEN") or None
    return url, token


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
    isolated and supports multi-tenant deployments where a shared process routes
    each run to a distinct per-engagement daemon.

    Endpoint resolution (see ``_resolve_endpoint``): the current run's
    LangGraph ``configurable.sandbox_url`` / ``sandbox_token`` win when
    present; otherwise ``SANDBOX_URL`` / ``SANDBOX_TOKEN`` apply.

    Returns:
        An ``HTTPSandbox`` instance pointed at the daemon URL.

    Env:
        SANDBOX_URL
            Base URL of the sandbox daemon. Default
            ``http://localhost:9999`` (sibling-container / sidecar
            loopback). Compose sets this to ``http://sandbox:9999``.
        SANDBOX_TOKEN
            Optional bearer token for daemon auth — recommended even on
            loopback as defence-in-depth.
    """
    base_url, token = _resolve_endpoint()
    return _shared_sandbox(base_url, token)
