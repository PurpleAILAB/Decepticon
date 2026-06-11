# `web_search` — RoE-gated open-web search

> Implements ADR-0008 (Tier-1 open-web reach, OSS roadmap issue #593).

`web_search` gives the agent its first piece of open-web reach. It is
an OSINT-grade query against DuckDuckGo's HTML endpoint, with every
returned URL checked against the engagement's `plan/roe.json`
`machine_enforcement` block before the agent ever sees it.

## Tool signature

```python
@tool
async def web_search(query: str, max_results: int = 10) -> str
```

Returns a JSON string of the form:

```json
{
  "query": "site:example.com test",
  "results": [
    {"title": "...", "url": "https://example.com/...", "snippet": "...", "source": "duckduckgo"}
  ],
  "filtered_count": 0
}
```

`filtered_count` counts results dropped by the RoE gate (see below).
Network errors collapse to `{"results": [], "error": "<exc>"}` — the
tool never raises.

## Backend

DuckDuckGo HTML endpoint (`https://html.duckduckgo.com/html/`) via
`httpx.AsyncClient`. Keyless. Fixed 5 s timeout, fixed user-agent
`Decepticon-RedTeam/1.0`, hard cap of 10 results per call.

Swapping in a second backend (Scrapling / Brave / SerpAPI, per
ADR-0008) is deferred until the second provider is actually wired —
per K3 we do not introduce a provider abstraction for a single
backend.

## RoE behaviour

| Layer | Behaviour |
|-------|-----------|
| Middleware (`RoEEnforcementMiddleware`) | `web_search` is in `GATED_TOOL_NAMES`. The middleware audits the call, applies the engagement's time-window / throttle rules, and (per ADR-0008) treats the search provider itself as OSINT — the network target extractor returns `[]`. |
| Tool (`run_web_search`) | After parsing the DDG HTML, each result URL's host is run through `evaluate_target(host, rules)`. Hosts that fail (out-of-scope, sensitive-TLD, cloud-metadata, etc.) are dropped from the returned set and a `web_search.result_filtered` event is appended to the RoE audit ledger (`<workspace>/audit/roe-decisions.jsonl`). |

If `roe.json` has no `in_scope` / `out_of_scope` rules the gate is a
no-op (audit-only mode) and every parsed result is returned.

## Audit events

| Event | Emitted when |
|-------|--------------|
| `web_search.query` | One per successful query — carries `query`, `result_count`, `filtered_count`. |
| `web_search.result_filtered` | One per dropped result — carries `host`, `url`, `reason_code`, `query`. |
| `web_search.error` | One per network failure — carries `error`. |

## Usage example

```python
from decepticon.tools.web import web_search

raw = await web_search.ainvoke({"query": "site:acme.com login", "max_results": 5})
```

Inside the agent the tool is selected automatically from `WEB_TOOLS`;
operators do not need to wire it up.

## Dry-run reproducer

```bash
uv run pytest packages/decepticon/tests/unit/tools/web/test_web_search.py -v
```

The tests use a hand-rolled HTML fixture — no live network. See
`run_web_search()` in `decepticon/tools/web/search.py` if you want to
call the library entry point directly from a script.
