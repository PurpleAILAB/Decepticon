"""Batch exporter — queue Tier-A events and ship them to the gateway.

Design constraints:

* **Never break the agent.** Every failure (offline, gateway down, bad URL) is
  swallowed; telemetry degrades to a silent no-op, mirroring how the event log
  and budget middleware swallow I/O errors.
* **Batched + offline-tolerant.** Events accumulate and flush on size or a timer
  from a background daemon thread; a failed flush drops that batch rather than
  retrying forever or blocking the run.
* **No new dependency.** Uses stdlib ``urllib``. The HTTP POST is injectable so
  tests never touch the network.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

log = logging.getLogger("decepticon.telemetry.exporter")

# (url, json_body) -> None. Raises on failure; the exporter swallows it. The
# body is the raw JSON envelope (gzip is a future optimization, kept off so the
# wire format matches the gateway's plain application/json ingest).
Transport = Callable[[str, bytes], None]

# A named User-Agent. The stdlib default (``Python-urllib/x.y``) is blocked with
# 403 by Cloudflare's bot protection in front of the workers.dev gateway, which
# would silently drop every batch — so we identify as ourselves.
_USER_AGENT = "decepticon-telemetry/1.0"


def _http_post(url: str, body: bytes) -> None:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json", "user-agent": _USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — url is operator-configured
        if resp.status >= 300:
            raise urllib.error.HTTPError(url, resp.status, "telemetry rejected", resp.headers, None)


class BatchExporter:
    """Thread-safe Tier-A event buffer with size/timer-triggered flushing."""

    def __init__(
        self,
        *,
        endpoint: str,
        envelope: Callable[[list[dict[str, Any]]], dict[str, Any]],
        batch_size: int = 50,
        flush_interval_s: float = 30.0,
        max_queue: int = 1000,
        transport: Transport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._envelope = envelope
        self._batch_size = batch_size
        self._max_queue = max_queue
        self._transport = transport or _http_post
        self._buf: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._closed = False
        self._timer: threading.Timer | None = None
        self._flush_interval_s = flush_interval_s
        self._arm_timer()

    def _arm_timer(self) -> None:
        if self._closed or self._flush_interval_s <= 0:
            return
        self._timer = threading.Timer(self._flush_interval_s, self._on_timer)
        self._timer.daemon = True
        self._timer.start()

    def _on_timer(self) -> None:
        self.flush()
        with self._lock:
            if not self._closed:
                self._arm_timer()

    def record(self, event: dict[str, Any]) -> None:
        """Enqueue one Tier-A event; flush inline when the batch is full."""
        with self._lock:
            if self._closed:
                return
            if len(self._buf) >= self._max_queue:
                self._buf.pop(0)  # bounded buffer — drop oldest, never grow unbounded
            self._buf.append(event)
            full = len(self._buf) >= self._batch_size
        if full:
            self.flush()

    def flush(self) -> None:
        """Ship the current buffer. Swallows all errors (offline-tolerant)."""
        with self._lock:
            if not self._buf:
                return
            batch = self._buf
            self._buf = []
        try:
            body = json.dumps(self._envelope(batch), separators=(",", ":")).encode("utf-8")
            self._transport(self._endpoint, body)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Drop the batch — telemetry is best-effort, never a run blocker.
            log.debug("telemetry flush failed (%s events dropped): %s", len(batch), exc)

    def close(self) -> None:
        """Final flush and stop the timer."""
        with self._lock:
            self._closed = True
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()
        self.flush()
