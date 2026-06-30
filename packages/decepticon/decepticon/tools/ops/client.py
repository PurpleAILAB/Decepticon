"""HTTP-over-Unix-socket client for the opscontrol daemon.

ADR-0006 §1' / §6: the daemon listens on a Unix domain socket bind-
mounted into the langgraph container at ``/var/run/decepticon-ops.sock``.
The socket file is the capability grant — no TCP, no network member-
ship, no service discovery.

``httpx.HTTPTransport(uds=...)`` is the supported transport since
httpx 0.18 and matches what other projects (Docker SDK, Vercel
Sandbox SDK) use for UDS-only control planes.
"""

from __future__ import annotations

import os
import socket as _socket
from typing import Any

import httpx

DEFAULT_SOCKET_PATH = "/var/run/decepticon-ops.sock"
SOCKET_PATH_ENV = "DECEPTICON_OPSCONTROL_SOCK"


def resolve_socket_path() -> str:
    """The opscontrol socket path for this process (env override → default)."""
    return os.environ.get(SOCKET_PATH_ENV, DEFAULT_SOCKET_PATH)


def ops_available() -> bool:
    """True when the opscontrol daemon is actually REACHABLE.

    The socket is the ADR-0006 capability grant: a live daemon listens on it
    only when the stack was brought up via ``decepticon start`` (the daemon
    bind-mounts it into the langgraph container). Daemon-less topologies —
    ``make dev`` / ``make smoke``, and hosted deployments that manage workload
    teardown externally (no opscontrol on the runtime) — have no live daemon,
    so the ``ops_*`` tools have nothing to talk to. Registering them there only
    lets the orchestrator call a tool that returns ``opscontrol_unreachable``;
    gating registration on this check keeps the toolset honest per topology.

    A bare ``os.path.exists`` is NOT enough: a stale/leftover socket inode (or a
    path that exists for an unrelated reason in a hosted container) passes the
    file check while no daemon answers, so the tools get registered and then
    fail at call time. We require an actual UDS *connect* to succeed — only a
    live, accepting daemon flips this True.
    """
    path = resolve_socket_path()
    if not os.path.exists(path):
        return False
    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(path)
        return True
    except OSError:
        return False


class OpsControlError(RuntimeError):
    """Daemon returned a non-2xx HTTP response."""

    def __init__(self, status_code: int, body: dict[str, Any] | str) -> None:
        super().__init__(f"opscontrol {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class OpsControlUnreachableError(RuntimeError):
    """Daemon is not reachable.

    Surfaced when the socket file does not exist or the connection is
    refused. Translates to the agent-visible diagnostic "opscontrol
    daemon not reachable" — usually means the launcher was not used to
    bring up the stack (``make dev`` / ``make smoke`` are daemon-less
    by design per :mod:`docker-compose.opscontrol.yml`).
    """


class OpsControlClient:
    """Thin httpx client around the opscontrol HTTP API.

    The client is stateless — each call opens a fresh UDS connection
    and closes it. The daemon side handles concurrency.
    """

    def __init__(self, socket_path: str | None = None, timeout: float = 30.0) -> None:
        self._socket_path = socket_path or os.environ.get(SOCKET_PATH_ENV, DEFAULT_SOCKET_PATH)
        self._timeout = timeout

    @property
    def socket_path(self) -> str:
        return self._socket_path

    def _client(self) -> httpx.Client:
        # base_url must use a placeholder host because the UDS
        # transport routes by socket, not by hostname. "http://opscontrol"
        # is convention from the docker SDK and shows up cleanly in logs.
        return httpx.Client(
            base_url="http://opscontrol",
            transport=httpx.HTTPTransport(uds=self._socket_path),
            timeout=self._timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with self._client() as client:
                resp = client.request(method, path, **kwargs)
        except (FileNotFoundError, httpx.ConnectError) as exc:
            raise OpsControlUnreachableError(
                f"opscontrol daemon not reachable at {self._socket_path}: {exc}. "
                "Was the stack brought up via `decepticon start`? "
                "`make dev` / `make smoke` are daemon-less by design."
            ) from exc
        body: dict[str, Any]
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        if resp.status_code >= 400:
            raise OpsControlError(resp.status_code, body)
        return body

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health")

    def list_profiles(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/v1/profiles")
        return result if isinstance(result, list) else []

    def start(self, workload: str, engagement_id: str | None = None) -> dict[str, Any]:
        params = {"engagement": engagement_id} if engagement_id else None
        return self._request(
            "POST",
            f"/v1/profiles/{workload}/start",
            params=params,
        )

    def stop(self, workload: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/profiles/{workload}/stop")

    def cleanup_engagement(self, engagement_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/engagements/{engagement_id}/cleanup")
