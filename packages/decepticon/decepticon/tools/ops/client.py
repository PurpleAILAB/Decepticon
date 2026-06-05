"""HTTP client for the ops-control sidecar.

ADR-0006.  The ops-control sidecar exposes:

    GET  /v1/health                    - liveness
    GET  /v1/profiles                  - allowlist + per-profile state
    POST /v1/profiles/{name}/start     - docker compose --profile <name> up -d
    POST /v1/profiles/{name}/stop     - docker compose --profile <name> stop

This client is the single integration point the LangChain @tool
layer (``tools/ops/tools.py``) talks through.  No docker socket
access, no subprocess — strictly HTTP against ops-control.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class OpsControlConfigError(RuntimeError):
    """Raised when required configuration is missing."""


class OpsControlHTTPError(RuntimeError):
    """Raised when ops-control returns a non-success status."""

    def __init__(self, status_code: int, body: Any) -> None:
        super().__init__(f"ops-control returned HTTP {status_code}: {body!r}")
        self.status_code = status_code
        self.body = body


class OpsControlClient:
    """Synchronous HTTP client for the ops-control sidecar."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    @classmethod
    def from_env(cls) -> OpsControlClient:
        base = os.environ.get("OPS_CONTROL_URL", "").strip()
        if not base:
            raise OpsControlConfigError("OPS_CONTROL_URL is required to construct OpsControlClient")
        timeout_str = os.environ.get("OPS_CONTROL_TIMEOUT", "60").strip() or "60"
        try:
            timeout = float(timeout_str)
        except ValueError as exc:
            raise OpsControlConfigError(
                f"OPS_CONTROL_TIMEOUT must be a number, got {timeout_str!r}"
            ) from exc
        return cls(base, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpsControlClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, path: str) -> dict[str, Any]:
        resp = self._client.request(method, f"{self._base}{path}")
        if resp.status_code >= 400:
            try:
                body: Any = resp.json()
            except Exception:
                body = resp.text
            raise OpsControlHTTPError(resp.status_code, body)
        return resp.json()

    # ── Endpoints (1:1 with ops-control routes) ─────────────────────

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health")

    def list_profiles(self) -> dict[str, Any]:
        return self._request("GET", "/v1/profiles")

    def start_profile(self, name: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/profiles/{name}/start")

    def stop_profile(self, name: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/profiles/{name}/stop")
