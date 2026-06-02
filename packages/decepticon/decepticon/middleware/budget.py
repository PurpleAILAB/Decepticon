"""BudgetEnforcementMiddleware — per-engagement and per-agent USD spend caps.

Decepticon engagements can spin for hours with multiple specialist sub-agents
running in parallel, each driving an expensive frontier model. The
LiteLLM-only timeout knob (``DECEPTICON_LLM__TIMEOUT``) is necessary but not
sufficient — a long-running engagement on ``claude-opus-4-7 → fallback →
fallback`` can quietly accrue hundreds of dollars in spend before a human
operator notices.

This middleware exposes a single financial guardrail::

    DECEPTICON_BUDGET__ENGAGEMENT_USD    hard cap for the whole engagement
    DECEPTICON_BUDGET__PER_AGENT_USD     hard cap per specialist agent
    DECEPTICON_BUDGET__SOFT_WARN_AT_PCT  emit a stream warning at this fraction
    DECEPTICON_BUDGET__POLL_SECONDS      how often to re-query LiteLLM

Spend numbers come from LiteLLM's ``spend_logs`` table — already populated
by the proxy on every completion. We query it lazily before each model call;
the lookup is one row per agent (cheap, indexed) and is cached for the poll
interval so we don't hammer Postgres on tight inference loops.

Enforcement
-----------
- ``soft_warn`` threshold (default 70%) → emit a ``budget_warning`` custom
  stream event so the operator UI shows a yellow banner, but the agent
  proceeds.
- ``hard_pause`` threshold (100%) → raise ``BudgetExceeded`` from
  ``wrap_model_call``, which bubbles up to the agent runtime and terminates
  the run with an explanatory message. The HITL gate (§2.2) will eventually
  catch this and offer the operator a "raise budget" prompt; until that
  lands, the engagement just stops.

Disabled by default
-------------------
A non-positive ``ENGAGEMENT_USD`` cap means the middleware is a no-op. This
preserves the current behavior for users who haven't opted in.

Architectural notes
-------------------
- LiteLLM virtual-key spend is the source of truth, NOT a local counter. A
  local counter would drift on crash/restart; LiteLLM persists every call.
- The middleware does NOT block tool calls — only LLM calls. The agent can
  finish whatever tool round-trip is in flight and emit a final synthesis
  message before the next inference fails.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import closing
from typing import Any, ClassVar

from langchain.agents.middleware import AgentMiddleware
from typing_extensions import override

log = logging.getLogger(__name__)


class BudgetExceeded(RuntimeError):
    """Raised when an engagement or per-agent budget has been hit."""

    def __init__(self, scope: str, spent_usd: float, cap_usd: float) -> None:
        self.scope = scope
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        super().__init__(
            f"Budget exceeded ({scope}): spent ${spent_usd:.4f} of ${cap_usd:.2f} cap. "
            "Raise the cap via DECEPTICON_BUDGET__* or end the engagement."
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("invalid float for %s=%r; falling back to %s", name, raw, default)
        return default


class _SpendCache:
    """Tiny TTL cache over (scope_key) → (spent_usd, fetched_at).

    Bounded at ``_MAX_ENTRIES`` so a runaway agent-id-explosion can't grow
    memory unbounded. Entries are evicted in insertion order (FIFO) on
    overflow — cache misses cost one extra LiteLLM SQL round-trip, not
    correctness, so FIFO is fine.
    """

    _MAX_ENTRIES: ClassVar[int] = 1024

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, float]] = {}

    def get(self, key: str) -> float | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, fetched_at = entry
        if (time.monotonic() - fetched_at) > self._ttl:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, value: float) -> None:
        self._entries[key] = (value, time.monotonic())
        if len(self._entries) > self._MAX_ENTRIES:
            first_key = next(iter(self._entries))
            self._entries.pop(first_key, None)


def _emit_warning_event(scope: str, spent: float, cap: float, frac: float) -> None:
    """Emit a ``budget_warning`` custom stream event for the dashboard."""
    try:
        from langgraph.config import get_stream_writer  # noqa: PLC0415

        writer = get_stream_writer()
    except Exception:  # noqa: BLE001
        return
    if writer is None:
        return
    try:
        writer(
            {
                "type": "budget_warning",
                "scope": scope,
                "spent_usd": round(spent, 4),
                "cap_usd": cap,
                "used_pct": round(frac * 100, 1),
            }
        )
    except Exception as e:  # noqa: BLE001
        log.warning("failed to emit budget_warning stream event: %s", e)


class BudgetEnforcementMiddleware(AgentMiddleware):
    """Hard-pause when engagement or per-agent USD spend caps are hit.

    Construct once per engagement (or globally — the middleware reads scope
    from request metadata each call). Spend numbers are pulled from the
    injected ``spend_provider`` callable, which is expected to return the
    cumulative USD spend for a given scope key. The default provider
    queries LiteLLM Postgres via the connection string in
    ``DATABASE_URL``; injecting a stub provider makes this trivially
    unit-testable.
    """

    def __init__(
        self,
        *,
        engagement_cap_usd: float | None = None,
        per_agent_cap_usd: float | None = None,
        soft_warn_at_pct: float | None = None,
        poll_seconds: float | None = None,
        spend_provider: Any = None,
    ) -> None:
        super().__init__()
        self._engagement_cap = (
            engagement_cap_usd
            if engagement_cap_usd is not None
            else _env_float("DECEPTICON_BUDGET__ENGAGEMENT_USD", 0.0)
        )
        self._per_agent_cap = (
            per_agent_cap_usd
            if per_agent_cap_usd is not None
            else _env_float("DECEPTICON_BUDGET__PER_AGENT_USD", 0.0)
        )
        self._soft_warn = (
            soft_warn_at_pct
            if soft_warn_at_pct is not None
            else _env_float("DECEPTICON_BUDGET__SOFT_WARN_AT_PCT", 0.7)
        )
        poll = (
            poll_seconds
            if poll_seconds is not None
            else _env_float("DECEPTICON_BUDGET__POLL_SECONDS", 5.0)
        )
        self._cache = _SpendCache(ttl_seconds=poll)
        self._spend_provider = spend_provider or _default_litellm_spend_provider
        self._warned_scopes: set[str] = set()

    def _enabled(self) -> bool:
        return self._engagement_cap > 0 or self._per_agent_cap > 0

    def _scope_keys(self, request: Any) -> tuple[str, str]:
        """Pull engagement_id and agent_id from request state; fall back to env."""
        state = getattr(request, "state", None) or {}
        get = state.get if hasattr(state, "get") else (lambda _k, _d=None: None)
        engagement = (
            get("engagement_name")
            or get("engagement_id")
            or os.environ.get("DECEPTICON_ENGAGEMENT_ID", "")
            or "default-engagement"
        )
        agent_name = ""
        runtime = getattr(request, "runtime", None)
        if runtime is not None:
            agent_name = getattr(runtime, "agent_name", "") or ""
        agent_name = agent_name or "default-agent"
        return engagement, agent_name

    def _check_one(self, scope_kind: str, scope_key: str, cap_usd: float) -> None:
        if cap_usd <= 0:
            return
        cached = self._cache.get(scope_key)
        if cached is None:
            try:
                cached = float(self._spend_provider(scope_key))
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "spend provider failed for scope=%s: %s; not enforcing this turn",
                    scope_key,
                    exc,
                )
                return
            self._cache.set(scope_key, cached)
        frac = cached / cap_usd if cap_usd else 0.0
        if frac >= 1.0:
            raise BudgetExceeded(scope_kind, cached, cap_usd)
        warn_key = f"{scope_kind}:{scope_key}"
        if frac >= self._soft_warn and warn_key not in self._warned_scopes:
            self._warned_scopes.add(warn_key)
            log.warning(
                "budget soft-warn: scope=%s spent=$%.4f of $%.2f (%.0f%%)",
                scope_kind,
                cached,
                cap_usd,
                frac * 100,
            )
            _emit_warning_event(scope_kind, cached, cap_usd, frac)

    def _enforce(self, request: Any) -> None:
        if not self._enabled():
            return
        engagement, agent = self._scope_keys(request)
        self._check_one("engagement", f"engagement:{engagement}", self._engagement_cap)
        self._check_one("agent", f"agent:{engagement}:{agent}", self._per_agent_cap)

    @override
    def wrap_model_call(self, request, handler):
        self._enforce(request)
        return handler(request)

    @override
    async def awrap_model_call(self, request, handler):
        self._enforce(request)
        return await handler(request)


def _default_litellm_spend_provider(scope_key: str) -> float:
    """Default spend provider: query LiteLLM's Postgres ``spend_logs`` table.

    ``scope_key`` looks like ``engagement:<slug>`` or ``agent:<slug>:<agent>``.
    The convention is that LiteLLM virtual keys created by the launcher
    carry these scope keys as metadata, so a single SQL ``SUM(spend)``
    grouped by ``request_id->metadata`` yields the answer.

    Returns 0.0 on any failure — the middleware treats provider exceptions
    as "no data this turn, don't enforce" rather than as a hard error,
    so a transient Postgres blip can't terminate an active engagement.

    Requires ``DATABASE_URL`` to be set; absent that, returns 0.0.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return 0.0
    try:
        import psycopg2  # noqa: PLC0415
    except ImportError:
        log.warning("psycopg2 unavailable — install psycopg2-binary to enable budget enforcement")
        return 0.0
    try:
        with closing(psycopg2.connect(db_url)) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(spend), 0)::float
                    FROM "LiteLLM_SpendLogs"
                    WHERE metadata->>'scope_key' = %s
                    """,
                    (scope_key,),
                )
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
    except Exception as exc:  # noqa: BLE001
        log.warning("LiteLLM spend query failed for scope=%s: %s", scope_key, exc)
        return 0.0
