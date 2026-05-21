"""HTTP proxy session — Strix-style record/replay/tamper for the agent.

Decepticon's existing :mod:`decepticon.tools.web.http` already records
every outgoing request. This module wraps that history into a higher-
level proxy abstraction the agent can drive turn-by-turn:

  * **record** — capture a request (manual or auto-instrumented) into a
    named history slot
  * **replay** — re-issue a recorded request optionally rewriting
    headers / body / params
  * **tamper** — produce a mutation (header injection, parameter
    pollution, content-type confusion, body fuzzing) for a recorded
    request without sending it
  * **diff** — side-by-side compare two responses

This is the lightweight equivalent of Caido / Burp Repeater: enough to
test for IDOR, header injection, parameter trust issues, and
authentication bypasses without standing up an external proxy. The
backend uses ``httpx`` (already a project dep) so there's no extra
container required and the tests run hermetically.

Pairs with the new :mod:`decepticon.tools.web.browser` module which
provides Playwright-driven browser automation for the multi-tab XSS /
auth-flow side of the Strix toolkit.
"""

from __future__ import annotations

import copy
import difflib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)


@dataclass
class ProxyEntry:
    """One recorded request + (optionally) its captured response."""

    name: str
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: str = ""
    response_status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    elapsed_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "url": self.url,
            "headers": dict(self.headers),
            "params": dict(self.params),
            "body": self.body,
            "response_status": self.response_status,
            "response_headers": dict(self.response_headers),
            "response_body": self.response_body,
            "elapsed_ms": self.elapsed_ms,
        }

    def clone(self, **overrides: Any) -> ProxyEntry:
        """Return a deep-copied entry with selected fields replaced."""
        new = copy.deepcopy(self)
        for k, v in overrides.items():
            if not hasattr(new, k):
                raise AttributeError(f"ProxyEntry has no field {k!r}")
            setattr(new, k, v)
        return new


# Type alias for the optional injectable HTTP transport (used in tests
# to bypass real network I/O without monkeypatching httpx).
_Sender = Callable[[httpx.Request], httpx.Response]


class ProxySession:
    """Record / replay / tamper a small library of HTTP requests.

    The session is in-memory and per-engagement — agents are expected to
    run one ``ProxySession`` per attack chain. Persisting beyond the run
    is the agent author's responsibility (write the JSON to the
    workspace via :meth:`to_dict`).
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        sender: _Sender | None = None,
        max_entries: int = 256,
    ) -> None:
        """Initialise the session.

        Args:
            client: Custom httpx client (e.g. with TLS opts, proxies).
            sender: Optional callable that turns a Request into a Response.
                Overrides ``client``. Useful for unit tests / dry-runs
                where you want to assert on the produced request without
                sending it.
            max_entries: Hard cap to prevent runaway memory usage on a
                long-running session.
        """
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=False)
        self._sender = sender
        self._max = max_entries
        self._entries: dict[str, ProxyEntry] = {}

    # ── lifecycle helpers ────────────────────────────────────────

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass

    def __enter__(self) -> ProxySession:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ── record / list / get ──────────────────────────────────────

    def record(
        self,
        name: str,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        body: str = "",
        send: bool = True,
    ) -> ProxyEntry:
        """Persist a request into the session and (optionally) send it.

        When ``send=False`` the request is recorded as a template the
        agent can mutate later with :meth:`tamper` and then re-issue
        with :meth:`replay`. When ``send=True`` (default) the request
        is sent immediately and the captured response is attached.
        """
        if not name:
            raise ValueError("record name is required")
        if name in self._entries:
            raise ValueError(f"entry {name!r} already exists; use a unique name or tamper()")
        if len(self._entries) >= self._max:
            raise RuntimeError(f"proxy session full ({self._max} entries)")
        entry = ProxyEntry(
            name=name,
            method=method.upper(),
            url=url,
            headers=dict(headers or {}),
            params=dict(params or {}),
            body=body,
        )
        if send:
            self._dispatch(entry)
        self._entries[name] = entry
        return entry

    def list(self) -> list[str]:
        """Return ordered names of every recorded entry."""
        return list(self._entries.keys())

    def get(self, name: str) -> ProxyEntry:
        try:
            return self._entries[name]
        except KeyError:
            raise KeyError(f"no proxy entry named {name!r}") from None

    # ── replay / tamper ─────────────────────────────────────────

    def replay(
        self,
        name: str,
        *,
        as_name: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        body: str | None = None,
        url: str | None = None,
        method: str | None = None,
    ) -> ProxyEntry:
        """Re-issue a recorded request with optional field overrides.

        The replayed request is recorded under ``as_name`` (or
        ``"<name>-replay-N"`` if omitted) so callers can keep the
        original entry pristine for further mutation.
        """
        base = self.get(name)
        replayed = base.clone(
            name=as_name or self._next_replay_name(base.name),
            method=(method or base.method).upper(),
            url=url or base.url,
            headers={**base.headers, **(headers or {})},
            params={**base.params, **(params or {})},
            body=body if body is not None else base.body,
            response_status=None,
            response_headers={},
            response_body="",
            elapsed_ms=None,
        )
        if replayed.name in self._entries:
            raise ValueError(f"entry {replayed.name!r} already exists")
        self._dispatch(replayed)
        self._entries[replayed.name] = replayed
        return replayed

    def tamper(
        self,
        name: str,
        *,
        as_name: str | None = None,
        header_overrides: dict[str, str] | None = None,
        param_overrides: dict[str, str] | None = None,
        body_overrides: str | None = None,
        send: bool = False,
    ) -> ProxyEntry:
        """Produce a mutated copy of a recorded entry.

        Defaults to ``send=False`` so the agent can stage multiple
        mutations and inspect them before firing. Set ``send=True`` to
        also dispatch the mutated request immediately.
        """
        base = self.get(name)
        new_name = as_name or f"{base.name}-tampered-{self._tamper_seq(base.name)}"
        if new_name in self._entries:
            raise ValueError(f"entry {new_name!r} already exists")
        mutated = base.clone(
            name=new_name,
            headers={**base.headers, **(header_overrides or {})},
            params={**base.params, **(param_overrides or {})},
            body=body_overrides if body_overrides is not None else base.body,
            response_status=None,
            response_headers={},
            response_body="",
            elapsed_ms=None,
        )
        if send:
            self._dispatch(mutated)
        self._entries[new_name] = mutated
        return mutated

    # ── diff helpers ─────────────────────────────────────────────

    def diff(self, name_a: str, name_b: str, *, max_lines: int = 80) -> str:
        """Return a unified diff of two recorded responses (body only)."""
        a = self.get(name_a)
        b = self.get(name_b)
        body_a = (a.response_body or "").splitlines()
        body_b = (b.response_body or "").splitlines()
        diff = difflib.unified_diff(body_a, body_b, fromfile=name_a, tofile=name_b, lineterm="")
        out = list(diff)
        if not out:
            return f"(no difference between {name_a!r} and {name_b!r})"
        if len(out) > max_lines:
            out = out[:max_lines] + [f"... (+{len(out) - max_lines} lines truncated)"]
        return "\n".join(out)

    # ── internals ───────────────────────────────────────────────

    def _next_replay_name(self, base_name: str) -> str:
        n = 1
        while f"{base_name}-replay-{n}" in self._entries:
            n += 1
        return f"{base_name}-replay-{n}"

    def _tamper_seq(self, base_name: str) -> int:
        n = 1
        while f"{base_name}-tampered-{n}" in self._entries:
            n += 1
        return n

    def _dispatch(self, entry: ProxyEntry) -> None:
        """Build an httpx Request from the entry and capture the response."""
        request = self._client.build_request(
            entry.method,
            entry.url,
            params=entry.params or None,
            headers=entry.headers or None,
            content=entry.body.encode("utf-8") if entry.body else None,
        )
        if self._sender is not None:
            response = self._sender(request)
        else:
            response = self._client.send(request)
        entry.response_status = response.status_code
        entry.response_headers = dict(response.headers)
        try:
            entry.response_body = response.text
        except Exception as exc:  # noqa: BLE001 — non-text bodies handled below
            log.debug("non-text response body for %s (%s)", entry.url, exc)
            entry.response_body = ""
        try:
            # ``.elapsed`` is only populated when the response actually
            # transited a transport — synthetic responses (injected via
            # ``sender`` in tests/dry-runs) raise RuntimeError here.
            entry.elapsed_ms = response.elapsed.total_seconds() * 1000.0
        except RuntimeError:
            entry.elapsed_ms = None

    # ── serialisation ───────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self._entries.values()]}


__all__ = ["ProxyEntry", "ProxySession"]
