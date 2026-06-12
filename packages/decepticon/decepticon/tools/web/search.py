"""RoE-gated open-web search (ADR-0008, closes #593 Tier-1).

DuckDuckGo HTML backend via ``httpx``. Per-result URLs are filtered
against the engagement's ``plan/roe.json`` ``machine_enforcement``
block; out-of-scope hosts are dropped and recorded as
``web_search.result_filtered`` in the RoE audit ledger. The search
provider itself is OSINT-exempt from target gating (the middleware
still audits + throttles the call). No new runtime dependencies.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from langchain_core.tools import tool

from decepticon.middleware._audit_sink import RoEAuditSink
from decepticon_core.types.roe import evaluate_target

log = logging.getLogger(__name__)


DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "Decepticon-RedTeam/1.0"
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_MAX_RESULTS = 10

# DDG HTML wraps each hit in `result__a` + sibling `result__snippet`.
_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str = "duckduckgo"


def _strip(raw: str) -> str:
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def _unwrap_ddg_href(href: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlsplit(href)
    except ValueError:
        return href
    if parsed.netloc not in {"duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com"}:
        return href
    qs = parse_qs(parsed.query)
    inner = qs.get("uddg") or qs.get("u")
    if inner:
        return unquote(inner[0])
    return href


def _parse_ddg_html(body: str, limit: int = 50) -> list[WebSearchResult]:
    out: list[WebSearchResult] = []
    for match in _RESULT_RE.finditer(body):
        href = _unwrap_ddg_href(match.group("href"))
        if not href.startswith(("http://", "https://")):
            continue
        out.append(
            WebSearchResult(
                title=_strip(match.group("title")),
                url=href,
                snippet=_strip(match.group("snippet")),
            )
        )
        if len(out) >= limit:
            break
    return out


_MAX_RESPONSE_BYTES = 512 * 1024  # 512 KiB


async def _fetch_ddg(query: str, *, timeout_s: float) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_s,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        async with client.stream("POST", DDG_HTML_ENDPOINT, data={"q": query}) as response:
            response.raise_for_status()
            chunks = []
            bytes_read = 0
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                bytes_read += len(chunk)
                if bytes_read >= _MAX_RESPONSE_BYTES:
                    break
            body = b"".join(chunks)[:_MAX_RESPONSE_BYTES]
            return body.decode(response.encoding or "utf-8", errors="replace")


def _audit_event(sink: RoEAuditSink | None, payload: dict[str, Any]) -> None:
    if sink is None:
        return
    try:
        sink.append({"ts": time.time(), **payload})
    except Exception as exc:  # noqa: BLE001 - audit must never break tool execution
        log.error("web_search: audit sink write failed: %s", exc)


def _default_sink(workspace_path: str | None) -> RoEAuditSink | None:
    env_path = os.environ.get("DECEPTICON_ROE_AUDIT_PATH")
    if env_path:
        return RoEAuditSink(path=Path(env_path))
    if not workspace_path:
        return None
    return RoEAuditSink(path=Path(workspace_path) / "audit" / "roe-decisions.jsonl")


def _filter_by_roe(
    results: list[WebSearchResult],
    *,
    workspace_path: str | None,
    sink: RoEAuditSink | None,
    engagement: str,
    objective: str,
    query: str,
) -> list[WebSearchResult]:
    from decepticon.middleware.roe import _load_rules_for_workspace

    rules = _load_rules_for_workspace(workspace_path)
    # NB: do NOT short-circuit when in_scope/out_of_scope are empty.
    # evaluate_target still enforces the always-on forbidden destinations
    # (cloud-metadata / IMDS endpoints) and the default-deny sensitive TLDs,
    # so a result pointing at e.g. 169.254.169.254 must never be handed to
    # the agent just because the engagement left its scope lists empty.
    kept: list[WebSearchResult] = []
    for r in results:
        try:
            host = urlsplit(r.url).hostname or ""
        except ValueError:
            host = ""
        if host:
            decision = evaluate_target(host, rules)
            if decision.allow:
                kept.append(r)
                continue
            reason_code = decision.reason_code
        else:
            # Unparseable / hostless URL: we cannot prove it is in scope,
            # so default-deny rather than leak an opaque URL to the agent.
            reason_code = "UNPARSEABLE_HOST"
        _audit_event(
            sink,
            {
                "event": "web_search.result_filtered",
                "engagement": engagement,
                "objective_id": objective,
                "tool": "web_search",
                "decision": "refuse",
                "reason_code": reason_code,
                "host": host,
                "url": r.url,
                "query": query[:256],
            },
        )
    return kept


async def run_web_search(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    workspace_path: str | None = None,
    engagement: str = "unknown-engagement",
    objective: str = "",
    sink: RoEAuditSink | None = None,
) -> dict[str, Any]:
    if not query or not query.strip():
        return {"query": query, "results": [], "error": "empty query"}
    limit = max(1, min(int(max_results), DEFAULT_MAX_RESULTS))
    sink = sink or _default_sink(workspace_path)
    try:
        body = await _fetch_ddg(query, timeout_s=timeout_s)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        _audit_event(
            sink,
            {
                "event": "web_search.error",
                "engagement": engagement,
                "objective_id": objective,
                "tool": "web_search",
                "query": query[:256],
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return {"query": query, "results": [], "error": f"{type(exc).__name__}: {exc}"}
    raw = _parse_ddg_html(body, limit=50)
    kept_all = _filter_by_roe(
        raw,
        workspace_path=workspace_path,
        sink=sink,
        engagement=engagement,
        objective=objective,
        query=query,
    )
    kept = kept_all[:limit]
    _audit_event(
        sink,
        {
            "event": "web_search.query",
            "engagement": engagement,
            "objective_id": objective,
            "tool": "web_search",
            "query": query[:256],
            "result_count": len(kept),
            "filtered_count": len(raw) - len(kept_all),
        },
    )
    return {
        "query": query,
        "results": [asdict(r) for r in kept],
        "filtered_count": len(raw) - len(kept_all),
    }


def _resolve_engagement_state() -> tuple[str | None, str, str]:
    workspace = os.environ.get("DECEPTICON_WORKSPACE") or None
    engagement = os.environ.get("DECEPTICON_ENGAGEMENT") or "unknown-engagement"
    objective = os.environ.get("DECEPTICON_OBJECTIVE_ID") or ""
    return workspace, engagement, objective


@tool
async def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """OSINT search across the open web (DuckDuckGo HTML backend).

    Args:
        query: Free-text search query (e.g. ``"site:acme.com login"``).
        max_results: Cap on returned hits (1-10, default 10).

    Returns:
        JSON string ``{"query", "results": [{title,url,snippet,source}, ...],
        "filtered_count"}``. Result URLs whose host fails the engagement's
        RoE check (``in_scope``/``out_of_scope``, plus the always-on
        forbidden destinations and default-deny sensitive TLDs) are dropped
        *before* the agent sees them and logged as ``web_search.result_filtered`` in
        the RoE audit ledger. Network errors collapse to
        ``{"results": [], "error": ...}`` — the tool never raises.
    """
    workspace, engagement, objective = _resolve_engagement_state()
    payload = await run_web_search(
        query,
        max_results=max_results,
        workspace_path=workspace,
        engagement=engagement,
        objective=objective,
    )
    return json.dumps(payload, ensure_ascii=False)
