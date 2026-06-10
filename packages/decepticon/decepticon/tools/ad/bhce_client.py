"""Thin Python client for the BloodHound Community Edition v9.2.2 REST API.

ADR: docs/adr/0005-bloodhound-via-bhce-rest-client.md

This module exists so the agent surface (``decepticon.tools.ad.bh_*``)
can call the real BHCE instead of the in-house ingest + post-process
pipeline being deprecated under ADR-0005.

Every authoritative behaviour cites BHCE v9.2.2 source.  The community
wrapper (mwnickerson/bloodhound_mcp) is **not** a source of truth — it
is at most an interface-shape hint for the tool surface that calls into
this client.

Signature scheme (HMAC 3-chain, ``cmd/api/src/api/signature.go:97-145``):

    OperationKey = HMAC_SHA256(token_secret,            METHOD || URI_PATH)
    DateKey      = HMAC_SHA256(OperationKey,            RFC3339[:13])
    BodyKey      = HMAC_SHA256(DateKey,                 body_bytes)
    Signature    = base64.standard_b64encode(BodyKey)

Where:

- ``METHOD`` is the upper-case HTTP verb (``GET``/``POST``/...).
- ``URI_PATH`` is the **full Request-URI** including the query string
  when present (i.e. ``path?query`` when ``query`` is non-empty, else
  just ``path``).  BHCE's server-side verifier feeds
  ``request.RequestURI`` into the signature (``cmd/api/src/api/auth.go:355``),
  while its Go client signs only ``request.URL.Path``
  (``signature.go:160``) — an internal asymmetry that doesn't matter
  for query-less requests but breaks every signed GET that carries
  query parameters (e.g. paginated ``/api/v2/file-upload``).  We
  match the **server** side because that is what determines accept /
  reject.
- ``RFC3339[:13]`` is the first 13 characters of the RFC3339 datetime,
  i.e. truncated to the hour (e.g. ``2026-06-05T07``).  The header
  ``RequestDate`` carries the **full** RFC3339 datetime; only the
  signature input is hour-truncated.
- Empty body still runs the third HMAC (writing zero bytes), so the
  algorithm is uniform across GET and POST.

Authentication headers (``signature.go:169-171``):

- ``Authorization: bhesignature <TOKEN_ID>``
- ``RequestDate:   <full RFC3339 datetime>``
- ``Signature:     <base64 of BodyKey, standard padding>``

Clock skew is enforced at ``±1 hour`` on the server
(``cmd/api/src/api/auth.go:276-296``), so the docs' "2 hour" paraphrase
is incorrect — keep client + server clocks within an hour.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)


_AUTH_SCHEME = "bhesignature"
"""Matches BHCE's ``AuthorizationSchemeBHESignature`` constant."""


def _rfc3339_now() -> str:
    """RFC3339 timestamp matching Go's ``time.Format(time.RFC3339)``.

    Go's RFC3339 format is ``2006-01-02T15:04:05Z07:00`` — second-resolution
    with a numeric timezone offset.  Python's ``datetime.isoformat`` emits
    microseconds and a ``+00:00`` offset.  We strip microseconds and
    canonicalise the offset to ``+HH:MM``; UTC stays as ``+00:00`` (Go
    emits ``Z`` only when the location is exactly ``UTC``, but BHCE's
    server-side validator accepts both per ``time.Parse(time.RFC3339, …)``).
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sign_request(
    token_id: str,
    token_secret: str,
    method: str,
    url: str,
    body: bytes = b"",
    *,
    request_date: str | None = None,
) -> dict[str, str]:
    """Return the BHCE auth headers for the given HTTP request.

    Args:
        token_id: BHCE API token ID (the public half — also called
            "Token ID" in the BHCE UI's ``Admin → Manage Users``).
        token_secret: BHCE API token secret (the private half).
        method: Upper-case HTTP verb.
        url: Fully-qualified request URL.  The path and query string
            are fed into the signature (matching the server-side
            ``request.RequestURI`` per ``auth.go:355``); scheme and
            host are ignored.
        body: Request body bytes.  Use ``b""`` for empty.
        request_date: Optional RFC3339 datetime override (used by tests
            for deterministic signatures).  Defaults to ``_rfc3339_now()``.

    Returns:
        A ``dict`` of HTTP headers to attach to the outgoing request:
        ``Authorization``, ``RequestDate``, ``Signature``.
    """
    datetime_str = request_date or _rfc3339_now()
    parts = urlsplit(url)
    request_uri = parts.path or "/"
    if parts.query:
        request_uri = f"{request_uri}?{parts.query}"

    op_key = hmac.new(
        token_secret.encode("utf-8"),
        (method.upper() + request_uri).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    date_key = hmac.new(op_key, datetime_str[:13].encode("utf-8"), hashlib.sha256).digest()
    body_key = hmac.new(date_key, body, hashlib.sha256).digest()

    return {
        "Authorization": f"{_AUTH_SCHEME} {token_id}",
        "RequestDate": datetime_str,
        "Signature": base64.standard_b64encode(body_key).decode("ascii"),
    }


class BHCEConfigError(RuntimeError):
    """Raised when required BHCE configuration is missing."""


class BHCEHTTPError(RuntimeError):
    """Raised when BHCE returns a non-success status.

    Carries ``status_code`` and the parsed BHCE error envelope when
    available (BHCE v9.2.2 emits ``{http_status, timestamp, request_id,
    errors:[{context, message}]}``).
    """

    def __init__(self, status_code: int, body: Any, message: str | None = None) -> None:
        super().__init__(message or f"BHCE returned HTTP {status_code}: {body!r}")
        self.status_code = status_code
        self.body = body


class BHCEClient:
    """Synchronous BHCE v9.2.2 REST client.

    Constructed with ``BHCEClient.from_env()`` in production.  The env
    surface mirrors the BHCE example compose:

    - ``BHCE_URL``         — base URL (e.g. ``http://bhce:8080``).
    - ``BHCE_TOKEN_ID``    — HMAC token ID.
    - ``BHCE_TOKEN_KEY``   — HMAC token secret.
    - ``BHCE_TIMEOUT``     — request timeout in seconds (default 30).

    The 11 methods below each map to **one** documented BHCE endpoint;
    aggregate "composite" tools live in the LangChain @tool layer above
    this client, not here.
    """

    def __init__(
        self,
        base_url: str,
        token_id: str | None = None,
        token_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token_id = token_id
        self._token_key = token_key
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    @classmethod
    def from_env(cls) -> BHCEClient:
        base = os.environ.get("BHCE_URL", "").strip()
        if not base:
            raise BHCEConfigError("BHCE_URL is required to construct BHCEClient")
        token_id = os.environ.get("BHCE_TOKEN_ID") or None
        token_key = os.environ.get("BHCE_TOKEN_KEY") or None
        timeout_str = os.environ.get("BHCE_TIMEOUT", "30").strip() or "30"
        try:
            timeout = float(timeout_str)
        except ValueError as exc:
            raise BHCEConfigError(f"BHCE_TIMEOUT must be a number, got {timeout_str!r}") from exc
        return cls(base, token_id, token_key, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> BHCEClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        signed: bool = True,
    ) -> httpx.Response:
        url = f"{self._base}{path}"
        payload = body or b""
        headers: dict[str, str] = {}
        if payload or content_type != "application/json":
            headers["Content-Type"] = content_type
        if signed:
            if not self._token_id or not self._token_key:
                raise BHCEConfigError(
                    "BHCE_TOKEN_ID and BHCE_TOKEN_KEY are required for signed requests"
                )
            headers.update(
                sign_request(
                    self._token_id,
                    self._token_key,
                    method,
                    url,
                    payload,
                )
            )
        resp = self._client.request(method, url, content=payload, headers=headers)
        if resp.status_code >= 400:
            try:
                body_parsed: Any = resp.json()
            except Exception:
                body_parsed = resp.text
            raise BHCEHTTPError(resp.status_code, body_parsed)
        return resp

    # ── Public endpoint methods (1:1 with BHCE v9.2.2 routes) ───────

    def get_version(self) -> dict[str, Any]:
        """``GET /api/version`` — authenticated.

        Despite living under ``/api/version`` (no ``v2`` prefix), this
        endpoint enforces auth in v9.2.2.  Only ``GET /api/v2/spec`` is
        ``security: []`` per the in-repo OpenAPI spec.
        """
        return self._request("GET", "/api/version").json()

    def get_spec(self) -> str:
        """``GET /api/v2/spec`` — OpenAPI 3.0.3 (text/x-yaml).  No auth."""
        return self._request("GET", "/api/v2/spec", signed=False).text

    def get_self(self) -> dict[str, Any]:
        """``GET /api/v2/self`` — the principal behind the credentials."""
        return self._request("GET", "/api/v2/self").json()

    def run_cypher(self, query: str, *, include_properties: bool = True) -> dict[str, Any]:
        """``POST /api/v2/graphs/cypher``.

        BHCE's ``cypherquery.go`` handler enforces read-only by default
        (mutations require ``bhe_enable_cypher_mutations=true`` on the
        server).  Returns ``{data: UnifiedGraph}``.
        """
        import json

        payload = json.dumps({"query": query, "include_properties": include_properties}).encode(
            "utf-8"
        )
        return self._request("POST", "/api/v2/graphs/cypher", body=payload).json()

    def start_upload_job(self) -> int:
        """``POST /api/v2/file-upload/start`` — returns the new ``job_id``."""
        resp = self._request("POST", "/api/v2/file-upload/start").json()
        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict) or "id" not in data:
            raise BHCEHTTPError(200, resp, message="BHCE start_upload_job: missing data.id")
        return int(data["id"])

    def upload_chunk(
        self,
        job_id: int,
        payload: bytes,
        *,
        content_type: str = "application/json",
        filename: str | None = None,
    ) -> None:
        """``POST /api/v2/file-upload/{job_id}``.

        Accepted ``content_type`` per
        ``packages/go/openapi/src/paths/collection-uploads.file-upload.id.yaml``:
        ``application/json``, ``application/zip``, ``application/zip-compressed``,
        ``application/x-zip-compressed``.
        """
        path = f"/api/v2/file-upload/{job_id}"
        resp = self._request("POST", path, body=payload, content_type=content_type)
        # 202 No Content per spec; we just confirm success.
        if filename and resp.headers.get("X-File-Upload-Name"):
            log.debug("BHCE chunk accepted: %s", resp.headers.get("X-File-Upload-Name"))

    def end_upload_job(self, job_id: int) -> None:
        """``POST /api/v2/file-upload/{job_id}/end`` — close the job."""
        self._request("POST", f"/api/v2/file-upload/{job_id}/end")

    def get_upload_job(self, job_id: int) -> dict[str, Any]:
        """Return the FileUploadJob payload for ``job_id``.

        BHCE v9.2.2 only exposes ``GET /api/v2/file-upload`` (paginated
        list) and ``GET /api/v2/file-upload/{id}/completed-tasks`` —
        there is **no** ``GET /api/v2/file-upload/{id}`` route
        (``cmd/api/src/api/registration/v2.go`` shows only POST on the
        ``/{id}`` and ``/{id}/end`` paths).  We page through the list
        until we find the matching id, then return the wrapped object
        in a ``{data: …}`` envelope so callers can treat single-job
        and list responses uniformly.
        """
        skip = 0
        page_size = 100
        while True:
            page = self._request(
                "GET",
                f"/api/v2/file-upload?skip={skip}&limit={page_size}",
            ).json()
            items = page.get("data") if isinstance(page, dict) else None
            if not isinstance(items, list) or not items:
                return {"data": None}
            for item in items:
                if isinstance(item, dict) and item.get("id") == job_id:
                    return {"data": item}
            if len(items) < page_size:
                return {"data": None}
            skip += page_size

    def get_domain(self, object_id: str) -> dict[str, Any]:
        """``GET /api/v2/domains/{object_id}``."""
        return self._request("GET", f"/api/v2/domains/{object_id}").json()

    def get_user(self, object_id: str) -> dict[str, Any]:
        """``GET /api/v2/users/{object_id}``."""
        return self._request("GET", f"/api/v2/users/{object_id}").json()

    def get_computer(self, object_id: str) -> dict[str, Any]:
        """``GET /api/v2/computers/{object_id}``."""
        return self._request("GET", f"/api/v2/computers/{object_id}").json()
