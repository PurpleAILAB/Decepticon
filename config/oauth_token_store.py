"""Shared OAuth token store helpers for LiteLLM custom handlers.

Mounted into the LiteLLM container alongside the per-provider handler
modules (claude_code_handler, codex_chatgpt_handler, copilot_handler, ...).
Centralizes credential I/O so a refresh on the host (e.g. ``codex login``
rotating ``~/.codex/auth.json`` or Claude Code rotating
``~/.claude/.credentials.json``) is picked up by the running container
without a restart.

Design:
  - File reads are mtime+size cached. When the host writes a new token,
    the next container call sees a fresh stat and reloads automatically.
  - Writes go through atomic ``temp + rename`` so a refresh that races
    with a host-side write never produces a partial file. Permissions are
    forced to 0o600.
  - JWT and timestamp expiry checks both live here so all handlers share
    the same skew / buffer convention.
  - 401 retry is a generic wrapper: handlers pass in a ``send`` closure
    that takes a ``force_refresh`` flag; the wrapper calls once normally,
    once with force_refresh on 401.

This module is self-contained — it does NOT import the ``decepticon``
package because LiteLLM mounts only the handler files into ``/app``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import litellm
from http_client import post as _http_post

log = logging.getLogger(__name__)

DEFAULT_REFRESH_BUFFER_SECONDS = 5 * 60
DEFAULT_JWT_SKEW_SECONDS = 60


# ── File I/O ─────────────────────────────────────────────────────────────


def read_json_file(path: Path) -> dict[str, Any] | None:
    """Read and parse a JSON file. Returns None on any I/O error.

    Caller raises ``litellm.AuthenticationError`` when None is returned and
    credentials are required — this helper stays error-neutral so the same
    call works for "best-effort load" semantics.
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("oauth_token_store: read failed for %s: %s", path, exc)
        return None
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("oauth_token_store: invalid JSON in %s: %s", path, exc)
        return None
    return result if isinstance(result, dict) else None


def write_json_atomic(
    path: Path,
    data: dict[str, Any],
    mode: int = 0o600,
) -> bool:
    """Write JSON to ``path`` atomically (temp + rename). Returns False on failure.

    Many credential mounts are bind-mounted from the host. A rename within
    the same directory is atomic on POSIX, so a host-side reader never
    sees a half-written file. ``:ro`` mounts cause ``write_text`` /
    ``replace`` to fail; we log once at WARNING and let the in-process
    cache hold the refreshed token for the rest of the container's life.

    Sensitive-data note: this helper persists OAuth refresh / access
    tokens unencrypted, mirroring how the upstream CLIs (Claude Code's
    ``~/.claude/.credentials.json``, Codex's ``~/.codex/auth.json``)
    already store them. Decepticon's value-add is *sharing* those exact
    files between host CLI and the LiteLLM container so a refresh on
    either side flows to the other. Encrypting at this layer would break
    that contract and gain nothing — the file mode is restricted to
    0o600 so only the owning user can read the bytes. CodeQL flags the
    plain-text write; the suppression below documents the trade-off.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("oauth_token_store: mkdir failed for %s: %s", path.parent, exc)
        return False
    payload = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    # Unique temp file in the same directory. Two LiteLLM workers may refresh
    # the same OAuth credential file concurrently; a SHARED temp path makes
    # their writes collide and corrupt / lose a token. ``mkstemp`` allocates a
    # process-unique name and opens it with ``O_CREAT | O_EXCL``, which also
    # closes the symlink-replacement TOCTOU window (no need for O_NOFOLLOW).
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
    except OSError as exc:
        log.warning("oauth_token_store: mkstemp failed for %s: %s", path, exc)
        return False
    tmp = Path(tmp_name)
    try:
        # mkstemp creates with 0o600; widen/narrow only to honor ``mode``.
        os.chmod(tmp, mode)
        os.write(fd, payload)
        os.fsync(fd)
    except OSError as exc:
        log.warning("oauth_token_store: write failed for %s: %s", path, exc)
        try:
            os.close(fd)
        except OSError:
            # Already closed or invalid descriptor — nothing actionable.
            pass
        try:
            tmp.unlink()
        except OSError:
            # Cleanup is best-effort: the temp file may already be gone
            # (concurrent reaper, tmpfs eviction) or sit on a read-only mount.
            pass
        return False
    try:
        os.close(fd)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("oauth_token_store: replace failed for %s: %s", path, exc)
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


# ── mtime+size aware caching ────────────────────────────────────────────


class FileBackedCache:
    """In-process cache keyed by ``(mtime, size)`` of the underlying file.

    Handlers call ``get()`` per request without paying disk I/O. When the
    host CLI rewrites the file, the next ``get()`` sees a new stat tuple
    and triggers a fresh ``loader(path)`` call.

    ``mtime`` alone is insufficient on filesystems with 1-second resolution
    (ext4 on some configurations, FAT-derived volumes). Pairing it with
    ``size`` catches in-second rewrites where the body length differs.

    Thread-safe — async / sync handler paths can share one cache.
    """

    def __init__(
        self,
        path: Path,
        loader: Callable[[Path], dict[str, Any] | None],
    ) -> None:
        self._path = path
        self._loader = loader
        self._cached: dict[str, Any] | None = None
        self._cache_key: tuple[float, int] | None = None
        self._lock = threading.Lock()

    def _stat_key(self) -> tuple[float, int] | None:
        try:
            st = self._path.stat()
        except OSError:
            return None
        return (st.st_mtime, st.st_size)

    def get(self) -> dict[str, Any] | None:
        with self._lock:
            key = self._stat_key()
            if key is None:
                # Missing file: clear cache and let loader decide what to
                # return (None, or raise via the caller).
                self._cached = None
                self._cache_key = None
                return self._loader(self._path)
            if self._cache_key != key or self._cached is None:
                self._cached = self._loader(self._path)
                self._cache_key = key if self._cached is not None else None
            return self._cached

    def invalidate(self) -> None:
        """Force the next ``get()`` to re-read from disk."""
        with self._lock:
            self._cached = None
            self._cache_key = None

    def replace(self, data: dict[str, Any]) -> None:
        """Update cache after an in-process refresh that wrote ``data`` to disk.

        Stamps the cache key with the current file stat so the post-write
        ``get()`` does not re-read the file we just wrote.
        """
        with self._lock:
            self._cached = data
            self._cache_key = self._stat_key()


# ── JWT + timestamp helpers ─────────────────────────────────────────────


def decode_jwt_payload(token: str | None) -> dict[str, Any]:
    """Best-effort base64-decode of a JWT's middle segment. ``{}`` on malformed."""
    if not isinstance(token, str):
        return {}
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
        result = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) else {}


def is_jwt_expired(token: str, skew_seconds: int = DEFAULT_JWT_SKEW_SECONDS) -> bool:
    """True if the JWT's ``exp`` is within ``skew_seconds`` of now or missing."""
    exp = decode_jwt_payload(token).get("exp")
    if not isinstance(exp, (int, float)):
        return True
    return time.time() >= float(exp) - skew_seconds


def is_timestamp_expired(
    expires_at: float | int | None,
    buffer_seconds: int = DEFAULT_REFRESH_BUFFER_SECONDS,
) -> bool:
    """Generic expiry check for non-JWT formats.

    Accepts seconds or milliseconds (auto-detected when value > 1e12).
    Returns ``False`` when ``expires_at`` is 0 / None — caller treats that
    as "never expires" (e.g. the ``ANTHROPIC_OAUTH_TOKEN`` env override).
    """
    if not expires_at:
        return False
    expires_at_f = float(expires_at)
    if expires_at_f > 1e12:
        expires_at_f /= 1000.0
    return time.time() + buffer_seconds >= expires_at_f


# ── Generic OAuth refresh ───────────────────────────────────────────────


def oauth_refresh_request(
    token_url: str,
    payload: dict[str, Any],
    *,
    json_body: bool = True,
    timeout: float = 30.0,
    provider_label: str = "auth",
) -> dict[str, Any]:
    """POST to an OAuth token endpoint and return the parsed JSON response.

    Raises ``litellm.AuthenticationError`` on failure with a message that
    surfaces the underlying response body — actionable for "rerun the CLI
    login" recovery.
    """
    try:
        if json_body:
            resp = _http_post(token_url, json=payload, timeout=timeout)
        else:
            resp = _http_post(token_url, data=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise litellm.AuthenticationError(
            message=(
                f"OAuth token refresh failed for {provider_label}. Underlying: {exc.response.text}"
            ),
            model=provider_label,
            llm_provider=provider_label,
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise litellm.AuthenticationError(
            message=f"OAuth token refresh request failed for {provider_label}: {exc}",
            model=provider_label,
            llm_provider=provider_label,
        ) from exc
    if not isinstance(data, dict):
        raise litellm.AuthenticationError(
            message=f"OAuth refresh response for {provider_label} was not an object.",
            model=provider_label,
            llm_provider=provider_label,
        )
    return data


# ── 401 retry wrapper ───────────────────────────────────────────────────


def with_retry_on_401(
    send: Callable[[bool], httpx.Response],
    *,
    max_attempts: int = 2,
) -> httpx.Response:
    """Call ``send(force_refresh: bool)`` up to ``max_attempts`` times.

    Handlers fetch their token via a closure that respects ``force_refresh``.
    The first attempt uses the cached token; on 401 the wrapper replays
    once with ``force_refresh=True``. Non-401 errors return immediately so
    the caller can build a typed exception with model / llm_provider
    context. After ``max_attempts`` 401s the last response is returned for
    the caller to surface.
    """
    resp: httpx.Response | None = None
    for attempt in range(max_attempts):
        resp = send(attempt > 0)
        if resp.status_code != 401:
            return resp
    assert resp is not None  # max_attempts >= 1 always sets resp
    return resp


__all__ = [
    "DEFAULT_JWT_SKEW_SECONDS",
    "DEFAULT_REFRESH_BUFFER_SECONDS",
    "FileBackedCache",
    "decode_jwt_payload",
    "is_jwt_expired",
    "is_timestamp_expired",
    "oauth_refresh_request",
    "read_json_file",
    "with_retry_on_401",
    "write_json_atomic",
]
