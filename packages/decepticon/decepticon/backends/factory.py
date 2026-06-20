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

_DEFAULT_SANDBOX_URL = "http://localhost:9999"


# maxsize is sized for the multi-tenant case: a single shared langgraph
# process can serve many concurrent engagements, each routed to its own
# per-engagement sandbox (distinct base_url/token). Each must keep its own
# HTTPSandbox so the SandboxNotificationMiddleware ``_jobs`` view stays
# consistent within a run; under-sizing this would evict a live run's client
# mid-flight. 128 covers realistic per-process concurrency with headroom.
@functools.lru_cache(maxsize=128)
def _shared_sandbox(base_url: str, token: str | None) -> HTTPSandbox:
    return HTTPSandbox(base_url=base_url, token=token)


def _resolve_endpoint() -> tuple[str, str | None]:
    """Resolve the sandbox ``(base_url, token)``, preferring per-run config.

    A SHARED langgraph process serving many engagements cannot reach a
    *per-engagement* sandbox through a single process-wide env var. So we first
    consult the current run's LangGraph config — ``configurable.sandbox_url`` /
    ``configurable.sandbox_token``, which the caller sets per invocation — and
    fall back to the ``SAAS_SANDBOX_*`` env vars. The env path still covers the
    single-tenant / silo / dev deployments (one sandbox per process) and
    module-import-time construction, where there is no active run context.

    The config keys are deployment-agnostic; nothing here is SaaS-specific.
    """
    url: str | None = None
    token: str | None = None
    try:
        # get_config() exposes the current run's RunnableConfig via contextvars
        # while a graph node executes. It raises RuntimeError outside a runnable
        # context (e.g. import-time agent construction) — fall back to env then.
        from langgraph.config import get_config

        configurable = (get_config() or {}).get("configurable") or {}
        raw_url = configurable.get("sandbox_url")
        raw_token = configurable.get("sandbox_token")
        url = raw_url if isinstance(raw_url, str) and raw_url else None
        token = raw_token if isinstance(raw_token, str) and raw_token else None
    except Exception:
        # No active run context, or langgraph config unavailable — use env.
        pass

    if url is None:
        url = os.environ.get("SAAS_SANDBOX_URL", _DEFAULT_SANDBOX_URL)
    if token is None:
        token = os.environ.get("SAAS_SANDBOX_TOKEN") or None
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
    isolated and supports multi-tenant SaaS deployments where a shared
    process routes each run to a distinct per-engagement daemon.

    Endpoint resolution (see ``_resolve_endpoint``): the current run's
    LangGraph ``configurable.sandbox_url`` / ``sandbox_token`` win when
    present, so a shared process can fan out to per-engagement sandboxes;
    otherwise the ``SAAS_SANDBOX_*`` env vars apply (single-tenant / silo
    / dev).

    Returns:
        An ``HTTPSandbox`` instance pointed at the resolved daemon URL.

    Env:
        SAAS_SANDBOX_URL
            Base URL of the sandbox daemon. Default
            ``http://localhost:9999`` (sibling-container / sidecar
            loopback). Compose sets this to ``http://sandbox:9999``.
        SAAS_SANDBOX_TOKEN
            Optional bearer token for daemon auth — recommended even on
            loopback as defence-in-depth.
    """
    base_url, token = _resolve_endpoint()
    return _shared_sandbox(base_url, token)
