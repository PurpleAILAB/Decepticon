"""ops-control sidecar — the single lifecycle surface for compose-defined
domain services.

ADR: docs/adr/0006-agent-driven-container-lifecycle.md

This is the *only* container in the management plane that touches the
Docker socket.  It exposes a tiny HTTP API on ``decepticon-net``:

    GET  /v1/health                    - liveness, no auth, no logic
    GET  /v1/profiles                  - allowlist + per-profile state
    POST /v1/profiles/{name}/start     - docker compose --profile <name> up -d
    POST /v1/profiles/{name}/stop      - docker compose --profile <name> stop

``{name}`` must appear in the server-side allowlist driven by the
``OPS_PROFILE_ALLOWLIST`` env var (comma-separated).  Anything else
returns 400 without touching docker.  No raw ``docker run`` / image
pull / volume / network APIs are exposed — those code paths simply
do not exist in this binary.

Implementation choice: shell out to ``docker compose`` rather than
linking the docker SDK.  Two reasons.  First, the compose runtime
that interprets profiles + service dependencies (the very feature we
rely on) lives in the CLI plugin, not in the engine API; using the
SDK would mean re-implementing profile resolution.  Second, the CLI
binary is small, audited, and version-pinned in the container image,
so the lifecycle surface stays small.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException

log = logging.getLogger("ops-control")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


# ── Configuration (env, validated once at boot) ──────────────────────


def _parse_allowlist(raw: str) -> set[str]:
    """Parse the comma-separated allowlist; defensively reject anything
    that isn't ``[a-z0-9-]{1,63}`` since these values flow into the
    ``docker compose --profile`` argument and must not be able to
    break out into a separate flag."""
    items: set[str] = set()
    for token in raw.split(","):
        candidate = token.strip()
        if not candidate:
            continue
        if not re.fullmatch(r"[a-z0-9-]{1,63}", candidate):
            log.warning("ops-control: dropping invalid allowlist entry %r", candidate)
            continue
        items.add(candidate)
    return items


_ALLOWLIST: set[str] = _parse_allowlist(os.environ.get("OPS_PROFILE_ALLOWLIST", ""))
_COMPOSE_PROJECT: str = os.environ.get("OPS_COMPOSE_PROJECT", "decepticon")
_COMPOSE_FILE: str = os.environ.get("OPS_COMPOSE_FILE", "/host/docker-compose.yml")
_DOCKER_BIN: str = os.environ.get("OPS_DOCKER_BIN", "docker")

if not _ALLOWLIST:
    log.warning(
        "ops-control: OPS_PROFILE_ALLOWLIST is empty — every start/stop call "
        "will be rejected.  Set it on the ops-control service (e.g. "
        "OPS_PROFILE_ALLOWLIST=ad,c2-sliver,reversing) before issuing tools."
    )

log.info(
    "ops-control ready: project=%s compose_file=%s allowlist=%s",
    _COMPOSE_PROJECT,
    _COMPOSE_FILE,
    sorted(_ALLOWLIST),
)


# ── Compose invocation ──────────────────────────────────────────────


_COMPOSE_TIMEOUT_SECONDS = 180.0
"""Hard ceiling on a single docker compose invocation.  Profile-up on a
cold BHCE stack takes ~30s; 180s is generous head-room."""


def _compose(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [_DOCKER_BIN, "compose", "-p", _COMPOSE_PROJECT, "-f", _COMPOSE_FILE, *args]
    log.info("ops-control: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=_COMPOSE_TIMEOUT_SECONDS,
    )


def _require_allowlisted(name: str) -> None:
    if name not in _ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail=f"profile {name!r} is not in OPS_PROFILE_ALLOWLIST",
        )


# ── HTTP surface ────────────────────────────────────────────────────


app = FastAPI(title="decepticon-ops-control", version="0.1.0")


@app.get("/v1/health")
def health() -> dict[str, Any]:
    """Liveness — no compose invocation, used by Docker healthcheck."""
    return {
        "ok": True,
        "project": _COMPOSE_PROJECT,
        "allowlist_size": len(_ALLOWLIST),
        "now": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.get("/v1/profiles")
def list_profiles() -> dict[str, Any]:
    """Return the allowlist plus the running-container count for each
    profile so callers can tell ``ad`` from ``ad+spinning-up``."""
    result = _compose(["ps", "--all", "--format", "json"])
    profile_state: dict[str, list[str]] = {name: [] for name in _ALLOWLIST}
    if result.returncode == 0:
        import json

        for raw in result.stdout.splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            container_profiles = row.get("Profiles") or ""
            for profile in container_profiles.split(","):
                profile = profile.strip()
                if profile and profile in profile_state:
                    profile_state[profile].append(f"{row.get('Service')}={row.get('State')}")
    return {
        "allowlist": sorted(_ALLOWLIST),
        "running": {k: v for k, v in profile_state.items() if v},
    }


@app.post("/v1/profiles/{name}/start", status_code=202)
def start_profile(name: str) -> dict[str, Any]:
    _require_allowlisted(name)
    result = _compose(["--profile", name, "up", "-d"])
    if result.returncode != 0:
        log.error(
            "ops-control start %s failed (rc=%s): %s",
            name,
            result.returncode,
            result.stderr.strip(),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "profile": name,
                "returncode": result.returncode,
                "stderr": result.stderr.strip().splitlines()[-5:],
            },
        )
    return {
        "profile": name,
        "action": "started",
        "stdout_tail": result.stdout.strip().splitlines()[-5:],
    }


@app.post("/v1/profiles/{name}/stop", status_code=202)
def stop_profile(name: str) -> dict[str, Any]:
    _require_allowlisted(name)
    result = _compose(["--profile", name, "stop"])
    if result.returncode != 0:
        log.error(
            "ops-control stop %s failed (rc=%s): %s",
            name,
            result.returncode,
            result.stderr.strip(),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "profile": name,
                "returncode": result.returncode,
                "stderr": result.stderr.strip().splitlines()[-5:],
            },
        )
    return {
        "profile": name,
        "action": "stopped",
        "stdout_tail": result.stdout.strip().splitlines()[-5:],
    }
