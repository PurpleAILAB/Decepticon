"""BudgetEnforcementMiddleware — per-engagement and per-agent USD spend caps.

Decepticon engagements can spin for hours with multiple specialist sub-agents
running in parallel, each driving an expensive frontier model. The
LiteLLM-only timeout knob (``DECEPTICON_LLM__TIMEOUT``) is necessary but not
sufficient — a long-running engagement on ``claude-opus-4-8 → fallback →
fallback`` can quietly accrue hundreds of dollars in spend before a human
operator notices.

This middleware exposes a single financial guardrail::

    DECEPTICON_BUDGET__ENGAGEMENT_USD    hard cap for the whole engagement
    DECEPTICON_BUDGET__PER_AGENT_USD     hard cap per specialist agent
    DECEPTICON_BUDGET__SOFT_WARN_AT_PCT  emit a stream warning at this fraction
    DECEPTICON_BUDGET__POLL_SECONDS      how often to re-query LiteLLM

Spend numbers come from the LiteLLM proxy's ``/spend/tags`` API. The
middleware tags every outbound completion with its scope keys
(``engagement:<slug>`` and ``agent:<slug>:<agent>`` via request
``metadata.tags``), the proxy records them in its spend logs, and
``/spend/tags`` returns the cumulative USD total per tag. We query it
lazily before each model call and cache for the poll interval so we
don't hammer the proxy on tight inference loops.

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
- LiteLLM proxy spend is the source of truth, NOT a local counter. A
  local counter would drift on crash/restart; LiteLLM persists every call.
- Spend attribution rides the documented proxy API (``metadata.tags`` in,
  ``/spend/tags`` out) rather than SQL against LiteLLM's internal Prisma
  tables, so proxy upgrades can't break enforcement on a schema change.
- The middleware does NOT block tool calls — only LLM calls. The agent can
  finish whatever tool round-trip is in flight and emit a final synthesis
  message before the next inference fails.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
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
    overflow — cache misses cost one extra LiteLLM proxy round-trip, not
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
    queries the LiteLLM proxy ``/spend/tags`` API using the same proxy
    URL/key the LLM factory resolves; injecting a stub provider makes
    this trivially unit-testable.
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
        # awrap_model_call runs _enforce in a thread-pool executor, so two
        # concurrent agents sharing an engagement can enter _check_one on
        # different threads. This lock keeps the cache-miss→fetch→set window
        # and the soft-warn check-then-add on _warned_scopes atomic, so the
        # "at most one HTTP fetch per poll interval" and "soft-warn fires once
        # per scope" invariants hold under concurrency. It only serializes
        # budget-enforce threads — the event loop itself is never blocked
        # (enforcement runs off-loop via asyncio.to_thread).
        self._lock = threading.Lock()

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
        # Hold the lock across the whole check so a cache miss serializes
        # concurrent agents onto a single fetch (the loser sees the warm
        # cache), and so the soft-warn check-then-add can't double-fire.
        with self._lock:
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
            already_warned = warn_key in self._warned_scopes
            if frac >= self._soft_warn and not already_warned:
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

    def _tag_request(self, request: Any) -> Any:
        """Attach scope tags to the outbound completion via ``metadata.tags``.

        The LiteLLM proxy records these tags on every spend-log row, which
        is what makes the ``/spend/tags`` lookup in the default provider
        work. Tags are merged non-destructively: existing ``model_settings``
        keys (e.g. an ``extra_body.thinking`` block) and pre-existing tags
        are preserved.
        """
        if not self._enabled():
            return request
        engagement, agent = self._scope_keys(request)
        scope_tags = [f"engagement:{engagement}", f"agent:{engagement}:{agent}"]
        settings = dict(getattr(request, "model_settings", None) or {})
        extra_body = dict(settings.get("extra_body") or {})
        metadata = dict(extra_body.get("metadata") or {})
        tags = list(metadata.get("tags") or [])
        tags.extend(t for t in scope_tags if t not in tags)
        metadata["tags"] = tags
        extra_body["metadata"] = metadata
        settings["extra_body"] = extra_body
        return request.override(model_settings=settings)

    @override
    def wrap_model_call(self, request, handler):
        self._enforce(request)
        return handler(self._tag_request(request))

    @override
    async def awrap_model_call(self, request, handler):
        # The default spend provider does a blocking HTTP round-trip to the
        # LiteLLM proxy (at most once per poll interval, per scope); run it
        # off the event loop so concurrent agents aren't stalled behind it.
        await asyncio.to_thread(self._enforce, request)
        return await handler(self._tag_request(request))


def _default_litellm_spend_provider(scope_key: str) -> float:
    """Default spend provider: query the LiteLLM proxy ``/spend/tags`` API.

    ``scope_key`` looks like ``engagement:<slug>`` or ``agent:<slug>:<agent>``
    and matches the tags ``_tag_request`` attaches to every completion this
    middleware wraps. ``/spend/tags`` aggregates ``SUM(spend)`` per distinct
    tag proxy-side, so the response is one row per tag — bounded by tag
    cardinality, not log volume.

    Proxy URL and key come from the same ``DecepticonConfig`` source the LLM
    factory uses (``DECEPTICON_LLM__PROXY_URL`` / ``__PROXY_API_KEY``), so
    any environment that can run an agent can also enforce its budget.

    Returns 0.0 on any failure — the middleware treats provider exceptions
    as "no data this turn, don't enforce" rather than as a hard error,
    so a transient proxy blip can't terminate an active engagement. A
    scope tag with no recorded spend also yields 0.0.
    """
    try:
        from decepticon_core.utils.config import load_config  # noqa: PLC0415

        config = load_config()
        base_url = config.llm.proxy_url.rstrip("/")
        api_key = config.llm.proxy_api_key
    except Exception as exc:  # noqa: BLE001
        log.warning("cannot resolve LiteLLM proxy config for budget query: %s", exc)
        return 0.0
    try:
        import httpx  # noqa: PLC0415

        resp = httpx.get(
            f"{base_url}/spend/tags",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        for row in resp.json():
            if row.get("individual_request_tag") == scope_key:
                return float(row.get("total_spend") or 0.0)
        return 0.0
    except Exception as exc:  # noqa: BLE001
        log.warning("LiteLLM spend query failed for scope=%s: %s", scope_key, exc)
        return 0.0
