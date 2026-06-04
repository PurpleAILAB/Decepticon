"""LangChain ``@tool`` surface for the real BHCE v9.2.2 backend.

These are the *new* AD attack-graph tools per ADR-0005, replacing the
in-house ingest + ESC* post-process pipeline behind ``bh_ingest_zip``,
``adcs_post_process``, ``dcsync_check``, etc.  They call the official
BHCE REST API via :mod:`decepticon.tools.ad.bhce_client`.

Until PR #6 of the migration lands (which flips the legacy ``bh_*``
names to deprecation aliases pointing at this module), the new tools
live under the ``bhce_*`` prefix.  Once the cutover completes, the
``bh_*`` names will route here and the in-house tools move to
``decepticon.compat``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.ad.bhce_client import (
    BHCEClient,
    BHCEConfigError,
    BHCEHTTPError,
)

log = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _make_client() -> BHCEClient | None:
    """Construct a client from env vars or return ``None`` with an error
    payload-friendly diagnostic logged.  The caller emits the structured
    error string so the agent sees an actionable message."""
    try:
        return BHCEClient.from_env()
    except BHCEConfigError as exc:
        log.warning("BHCE client unavailable: %s", exc)
        return None


def _config_error(message: str) -> str:
    return _json(
        {
            "error": message,
            "hint": (
                "Set BHCE_URL, BHCE_TOKEN_ID, BHCE_TOKEN_KEY in the "
                "environment.  Provision the token via the BHCE UI "
                "(Admin → My Profile → API Keys) or via "
                "POST /api/v2/tokens with a JWT session."
            ),
        }
    )


# ── bhce_status ───────────────────────────────────────────────────


@tool
def bhce_status() -> str:
    """Probe the BHCE sidecar — verifies version, auth, and self.

    Returns a JSON blob with the BHCE server version and the principal
    behind the configured HMAC token.  Use this when the agent needs to
    confirm the BHCE plane is healthy before issuing queries.
    """
    client = _make_client()
    if client is None:
        return _config_error("BHCE client could not be constructed from env")
    try:
        with client:
            version = client.get_version()
            try:
                me = client.get_self()
            except BHCEHTTPError as exc:
                return _json(
                    {
                        "version": version,
                        "self_error": {
                            "status_code": exc.status_code,
                            "body": exc.body,
                        },
                    }
                )
            return _json({"version": version, "self": me})
    except BHCEHTTPError as exc:
        return _json({"error": "BHCE HTTP error", "status_code": exc.status_code, "body": exc.body})


# ── bhce_cypher ───────────────────────────────────────────────────


@tool
def bhce_cypher(query: str, include_properties: bool = True) -> str:
    """Run a Cypher query against the BHCE graph.

    Passthrough to ``POST /api/v2/graphs/cypher``.  BHCE enforces
    read-only by default; mutation requires
    ``bhe_enable_cypher_mutations=true`` on the server side (off in
    our compose by design — see ADR-0005).

    Args:
        query: Cypher query string.
        include_properties: Include node + edge property bags in the
            response (default True).
    """
    if not query or not query.strip():
        return _json({"error": "query is required"})
    client = _make_client()
    if client is None:
        return _config_error("BHCE client could not be constructed from env")
    try:
        with client:
            return _json(client.run_cypher(query, include_properties=include_properties))
    except BHCEHTTPError as exc:
        return _json(
            {
                "error": "BHCE returned an error for the Cypher query",
                "status_code": exc.status_code,
                "body": exc.body,
            }
        )


# ── bhce_ingest_zip ───────────────────────────────────────────────


_UPLOAD_POLL_INTERVAL_SECONDS = 2.0
_UPLOAD_POLL_TIMEOUT_SECONDS = 600.0


@tool
def bhce_ingest_zip(path: str) -> str:
    """Ingest a SharpHound collection ZIP via BHCE's file-upload flow.

    Runs the official 3-step BHCE v9.2.2 ingest pipeline:

      1. ``POST /api/v2/file-upload/start``      (creates a job)
      2. ``POST /api/v2/file-upload/{job_id}``   (uploads the ZIP body)
      3. ``POST /api/v2/file-upload/{job_id}/end`` (closes the job)
      4. Polls ``GET /api/v2/file-upload/{job_id}`` until BHCE reports
         a terminal status or the timeout elapses.

    Args:
        path: Filesystem path to a SharpHound-generated ZIP.

    Returns:
        JSON: ``{job_id, terminal_status, last_payload, elapsed_seconds}``
        on success, or ``{error, ...}`` with diagnostic context on
        failure.  BHCE's parsing + analysis runs *inside* the BHCE
        server; we do not interpret the resulting graph here.
    """
    zip_path = Path(path)
    if not zip_path.is_file():
        return _json({"error": f"not a file: {path}"})
    try:
        payload = zip_path.read_bytes()
    except OSError as exc:
        return _json({"error": f"failed to read {path}: {exc}"})

    client = _make_client()
    if client is None:
        return _config_error("BHCE client could not be constructed from env")

    started = time.monotonic()
    try:
        with client:
            job_id = client.start_upload_job()
            client.upload_chunk(
                job_id,
                payload,
                content_type="application/zip",
                filename=zip_path.name,
            )
            client.end_upload_job(job_id)

            last: dict[str, Any] = {}
            deadline = started + _UPLOAD_POLL_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                last = client.get_upload_job(job_id)
                status = _extract_status(last)
                if status is not None and _is_terminal(status):
                    return _json(
                        {
                            "job_id": job_id,
                            "terminal_status": status,
                            "last_payload": last,
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                        }
                    )
                time.sleep(_UPLOAD_POLL_INTERVAL_SECONDS)
            return _json(
                {
                    "error": "BHCE ingest poll timed out",
                    "job_id": job_id,
                    "last_payload": last,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
            )
    except BHCEHTTPError as exc:
        return _json(
            {
                "error": "BHCE returned an error during ingest",
                "status_code": exc.status_code,
                "body": exc.body,
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        )


_TERMINAL_STATUSES = {"Complete", "Failed", "Cancelled", "PartiallyComplete"}
"""BHCE v9.2.2 ``FileUploadJob.status`` enum terminal values.

Source: ``packages/go/openapi/src/schemas/model.file-upload-job.yaml`` and
``cmd/api/src/services/upload/jobs.go``.  Non-terminal: ``Created``,
``Running``, ``Ingesting``, ``Analyzing``.
"""


def _extract_status(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    status = data.get("status_message") or data.get("status")
    return status if isinstance(status, str) else None


def _is_terminal(status: str) -> bool:
    return status in _TERMINAL_STATUSES


BHCE_TOOLS = [bhce_status, bhce_cypher, bhce_ingest_zip]
"""LangChain tool list — wire into the agent toolbox alongside the
existing AD_TOOLS surface.  This list will absorb the legacy ``bh_*``
names in PR #6 of the ADR-0005 migration."""
