# Decepticon: KG Middleware Redesign — Design Spec

- **Date:** 2026-06-03
- **Status:** Drafted, pending review
- **Related research:** [`docs/design/neo4j-research-notes.md`](../../design/neo4j-research-notes.md) (13 topics, 5 high-impact recommendations)
- **Related schema:** [`docs/design/attack-graph-schema.md`](../../design/attack-graph-schema.md) (node labels + relationships — unchanged by this spec)
- **Prep work (already landed on this branch):** narrow KG tool surface to analyst + AD/Contract specialists; move engagement scope helper to `decepticon_core.utils`
- **Branch:** continue on `chore/kg-removal-1-engagement-scope-evacuation` (suggest rename to `refactor/kg-narrow-and-research` before push) — implementation work will land on a follow-up branch `feat/kg-middleware`
- **Audience:** an engineering session that opens `/home/catow/GIT/decepticon_new/` *with no prior context* and is asked "execute this spec." Self-contained on purpose.

---

## 1. TL;DR

Replace Decepticon's broken standalone `kg_*` `@tool` decorators with a **`KGMiddleware`** class that owns the Neo4j store, builds the agent-facing tool surface, and handles the lifecycle. The middleware mirrors the existing `OPPLANMiddleware` pattern:

```python
class KGMiddleware(AgentMiddleware):
    state_schema = KGState

    def __init__(self, *, store: Neo4jStore | None = None,
                 enabled_tools: set[str] = DEFAULT_KG_TOOLS) -> None:
        super().__init__()
        self._store = store or Neo4jStore.from_env()
        self.tools = build_kg_tools(self._store, enabled_tools)

    def before_agent(self, state, runtime) -> dict | None: ...
    def wrap_model_call(self, request, handler): ...
    def wrap_tool_call(self, request, handler): ...
```

Agents opt in by adding `KGMiddleware()` to their middleware stack (or via a new `KG` slot in `SLOTS_PER_ROLE`). The current `analyst`, `ad_operator`, and `contract_auditor` agents (the post-narrow KG users) reacquire the surface through this slot; the other 14 agents keep their dead-weight-free state.

The middleware replaces the broken `graph_transaction()` pattern with per-operation `Neo4jStore.execute_write` / `execute_read` calls (research note §1, §2), enforces engagement-scope in the query builder (§4), and collapses the 12 `kg_ingest_*` tools into a single `kg_ingest(scanner_kind, path)` dispatcher.

Pre-1.0 status means the OSS plugin contract surface (`decepticon_core.contracts.slots`) is allowed to change: a new `MiddlewareSlot.KG` slot is added so plugin authors can override / disable the KG middleware the same way they override OPPLAN.

---

## 2. Background

### 2.1 Where we are after the narrow (commits 09401584..9fc7c958)

| | |
|---|---|
| KG-using agents | `analyst`, `ad_operator` (AD_TOOLS only), `contract_auditor` (CONTRACT_TOOLS only). 14 others have zero KG surface. |
| Tool implementation | Standalone `@tool` functions in `packages/decepticon/decepticon/tools/research/tools.py` (2,386 LOC, 34 @tool). All write paths wrap `with graph_transaction()`. |
| Backend | `Neo4jStore` (`packages/decepticon/decepticon/tools/research/neo4j_store.py`, 787 LOC). Has correct per-op `upsert_node`, `upsert_edge`, `batch_upsert_*`, `load_graph`, `query_custom`. Currently called only by `chain.py` and indirectly via the broken `graph_transaction()` wrapper in `_state.py`. |
| Engagement scope | `decepticon_core.utils.engagement_scope` (post-evacuation). Contextvar + label validator. Honored only on `load_graph()`; **not enforced** on `query_custom()`. |
| Middleware surface | No KG middleware. `engagement.py` sets the active-engagement contextvar via `set_active_engagement`. |
| CART contract | `runtime/cart.py` docstring promises `AttackGraphProtocol` (line 36) — **no class exists**. Vaporware. |
| Web dashboard | `clients/web/src/app/api/engagements/[id]/graph/route.ts` reads Neo4j directly via `neo4j-driver`. Will keep working as long as analyst writes findings (which it does via the same broken shim — to be replaced). |
| Tests | 17 test files under `packages/decepticon/tests/unit/research/` exercise the broken behavior and pass against it. |
| Skillogy | Separate concern — uses a separate Neo4j database (`neo4j_backend.py` in `decepticon/skillogy/server/`). Not in scope. |

### 2.2 The five high-impact problems (from research notes)

Cited so the redesign decisions are traceable:

1. **`graph_transaction()` round-trip** — every `kg_*` tool call does `load_graph` (two MATCH queries returning all nodes + all edges) → in-memory mutate → `batch_upsert_nodes + batch_upsert_edges` over the entire loaded graph. O(graph_size) per call.
2. **`_GRAPH_LOCK` global serialization** — Python-level `threading.Lock` serializes all KG traffic across 16 designed-to-be-concurrent agents. Neo4j MVCC + driver's `execute_write` retry already handles concurrent MERGE; the Python lock just adds latency.
3. **No engagement-scoped indexes** — Every engagement-scoped read does a full label scan. `(engagement, explored)` / `(engagement, severity)` / `(engagement, status)` composite range indexes are missing.
4. **`query_custom()` is unscoped** — Documented as "caller owns the Cypher." Multi-tenant data leak risk.
5. **`promote_chain()` not atomic** — Issues `1 + N_steps` separate `query_custom()` calls outside any transaction. Partial failure orphans the AttackPath node.

### 2.3 What the narrow already gave us

The five commits on this branch are the **necessary prep**, not the redesign itself:
- Dead-weight surface in 14 agents is gone — no more 30+ broken tools costing context tokens with zero use.
- Engagement scope helper is in a stable location that survives any further refactor of `tools/research/`.
- Research notes pin the redesign direction so subsequent design choices have evidence.
- 5 atomic commits → clean git history that bisects across the prep / redesign boundary.

The redesign now starts from a smaller, well-understood blast radius (3 KG-using agents + 1 backend + 1 unused vaporware contract).

---

## 3. Goals & non-goals

### Goals

1. **G1 — Single-owner KG**: `KGMiddleware` is the sole owner of the Neo4j store handle, the engagement-scoped query layer, the lifecycle hooks, and the agent-facing tool surface. Agents do not import `Neo4jStore` or `kg_*` symbols directly.
2. **G2 — Correct concurrency**: Replace `graph_transaction()` with per-op `execute_write` / `execute_read`. Remove `_GRAPH_LOCK`. Rely on Neo4j MVCC + driver retry (research note §1).
3. **G3 — Engagement-scope safety**: Every read AND every write is engagement-scoped by the query-builder layer. `query_custom()` either disappears or grows a mandatory `scoped: bool = True` parameter that injects the filter automatically (research note §4).
4. **G4 — Tool surface consolidation**: 12 `kg_ingest_*` tools → 1 `kg_ingest(scanner_kind, path)` with internal dispatch and a registry plugin authors can extend. Total agent-facing KG tool count drops from ~30 to ~6.
5. **G5 — Plugin slot**: Add `MiddlewareSlot.KG` to `decepticon_core.contracts.slots`. Plugin bundles can replace / disable the middleware (e.g. an enterprise plugin substituting a vector-augmented variant).
6. **G6 — Fill the `AttackGraphProtocol` vaporware**: Define the protocol the middleware emits SnapshotDelta against so `runtime/cart.py` can subscribe.
7. **G7 — Composite range indexes**: Three new indexes shipped via a migration file (research note §3): `(engagement, explored)`, `(engagement, severity)`, `(engagement, status)`.
8. **G8 — Backwards-compatible read for the web dashboard**: `clients/web/src/app/api/engagements/[id]/graph/route.ts` continues to work without changes (it reads via `neo4j-driver` directly; we keep its query shape stable).
9. **G9 — No regression for analyst end-to-end**: `analyst` agent's `RESEARCH_TOOLS` workflow (ENUMERATE → GROUND → HUNT → PERSIST → CHAIN → VALIDATE → REPORT) keeps working with the new tool surface. `chain.py`'s good-pattern code path stays intact and is merged into the middleware-owned implementation.
10. **G10 — Skillogy unaffected**: Skillogy's separate Neo4j database wiring is untouched.

### Non-goals (explicit)

- **NG1 — Vector index integration**: Research note §4 establishes that Neo4j 5.13+ vector index could absorb skillogy's separate store, but skillogy phase 1b is paused and that consolidation is a follow-up spec.
- **NG2 — Multi-database multi-tenancy** (Neo4j Enterprise): Keep label-property scoping. Reassess when a multi-tenant deployment requires it.
- **NG3 — Migrating AD_TOOLS / CONTRACT_TOOLS internals**: `bh_ingest_zip`, `slither_ingest`, etc. still call the broken shim. They will be migrated in a follow-up PR after KGMiddleware lands; this spec covers only the generic KG surface that analyst uses.
- **NG4 — `auto`-ingestion from SUMMARY.md / findings**: Agents continue to call `kg_*` tools explicitly. The middleware does NOT silently parse workspace files. (Confirmed direction — see `project_kg_middleware_design.md` in user memory.)
- **NG5 — Memgraph / Kuzu migration**: Research note §13 concludes the bottleneck is `graph_transaction()`, not Neo4j. Re-profile post-refactor; defer the database swap.
- **NG6 — Removing `tools/research/` entirely**: Pre-existing `chain.py` (good-pattern path planner) and `neo4j_store.py` (Cypher infrastructure) are reused by the middleware. `tools.py` and `_state.py` get retired piecewise as the middleware absorbs their callers.

---

## 4. The KGMiddleware design

### 4.1 Module layout

```
packages/decepticon/decepticon/middleware/
  kg.py                      ← new. KGMiddleware + KGState + tool factory
  kg_internal/
    __init__.py
    store.py                 ← thin wrapper that replaces _state.get_store(),
                               adds execute_write/read helpers and engagement-
                               scoped query builder
    tools.py                 ← @tool factory functions (read/write surface)
    ingest.py                ← scanner-kind dispatch for kg_ingest
    summary.py               ← KG summary block builder (system-prompt injection)
```

Why `kg_internal/` and not `tools/research/`:
- The middleware's tool factory is *not* a public plugin surface (it is mediated by `KGMiddleware`).
- Tools imported from `kg_internal` should NEVER be imported by an agent directly — only constructed via the middleware. The `_internal` naming makes that explicit.

`packages/decepticon/decepticon/tools/research/`:
- `chain.py` and `neo4j_store.py` are *moved* under `middleware/kg_internal/` to consolidate ownership. Imports from outside the middleware are forbidden by a new linter rule (or at minimum a CONTRIBUTING note).
- `tools.py` is *retired in three slices* (see §6.2). Each slice removes a category of broken tools as the middleware absorbs them.
- `_state.py`, `_engagement_scope.py` (re-export shim), `bounty.py`, `dedupe.py`, `patch.py`, `scanner_tools.py`, `sarif.py`, `sarif_export.py`, `fuzz.py`, `cve.py`, `poc.py`, `health.py`, `graph.py` — assessed individually in §6.3.

### 4.2 `KGState` schema

```python
from typing import Annotated, NotRequired
from langchain.agents import AgentState

class KGState(AgentState):
    """State extension owned by KGMiddleware."""

    # Hydrated by before_agent from engagement_name (already in state).
    # Distinct field so middleware can detect first-turn vs continuation.
    kg_engagement: NotRequired[Annotated[str, "Engagement label scoped onto every KG op."]]

    # Snapshot id and (optional) summary text. Updated by after_model when
    # a write tool ran. Reused by wrap_model_call to skip re-rendering the
    # summary block when revision is unchanged (prompt-cache hit on the
    # static system prefix).
    kg_revision: NotRequired[Annotated[str, "Opaque revision token from Neo4jStore.revision()."]]
    kg_summary: NotRequired[Annotated[str, "Cached rendered KG summary for system-prompt injection."]]
```

State fields are `NotRequired` so they coexist with the existing `EngagementContextState`, `OPPLANState`, etc.

### 4.3 Public class interface

```python
from collections.abc import Iterable
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

from decepticon.middleware.kg_internal.store import KGStore
from decepticon.middleware.kg_internal.tools import build_kg_tools
from decepticon_core.utils.engagement_scope import set_active_engagement


DEFAULT_KG_TOOLS = frozenset({
    "kg_query", "kg_neighbors", "kg_stats",
    "kg_add_node", "kg_add_edge",
    "kg_ingest",
    "kg_plan_chains", "kg_promote_chain",
})


class KGMiddleware(AgentMiddleware):
    """Owns the Neo4j store, the kg_* tool surface, and KG lifecycle.

    Mirrors OPPLANMiddleware in shape (state_schema, tools-on-init,
    wrap_model_call summary injection, scoped tool execution).
    """

    state_schema = KGState

    def __init__(
        self,
        *,
        store: KGStore | None = None,
        enabled_tools: Iterable[str] = DEFAULT_KG_TOOLS,
        summary_top_k: int = 10,
    ) -> None:
        super().__init__()
        self._store = store or KGStore.from_env()
        self._summary_top_k = summary_top_k
        self.tools: list[BaseTool] = build_kg_tools(self._store, set(enabled_tools))

    @override
    def before_agent(self, state, runtime) -> dict | None:
        """Hydrate kg_engagement from engagement_name; warm summary cache."""
        ...

    @override
    def wrap_model_call(self, request, handler):
        """Inject KG summary block into the system message (cached prefix)."""
        ...

    @override
    def wrap_tool_call(self, request, handler):
        """Enforce engagement scope on kg_* calls; reject if engagement unset."""
        ...

    @override
    def after_model(self, state, runtime):
        """If a kg_* write tool ran, bump kg_revision so summary re-renders next turn."""
        ...
```

### 4.4 Lifecycle hooks — full behavior

#### `before_agent`

1. Read `engagement_name` from state (already hydrated by `EngagementContextMiddleware`).
2. Copy into `kg_engagement` (the KG-side name; lets the KG be opted-out per agent independently of engagement scope).
3. Call `set_active_engagement(engagement_name)` so any path that still uses the contextvar fallback gets the right label.
4. Read `self._store.revision()` (Neo4j `MATCH (n) RETURN max(n.updated_at)` scoped by engagement). If state.kg_revision differs OR is unset, recompute summary via `build_summary(store, engagement, top_k=self._summary_top_k)` and stash in state.

#### `wrap_model_call`

Inject TWO system-message content blocks (same caching strategy as OPPLAN — see opplan.py:350-393):

- **Static block** — `KG_SYSTEM_PROMPT` (constant: "the knowledge graph is your memory across iterations; here's the schema; prefer batched `kg_ingest` over individual `kg_add_*` for scanner output"). Tagged `cache_control: ephemeral`.
- **Dynamic block** — formatted summary table (top-N high-severity vulns, unexplored entrypoints, current crown jewel set, current chain count). NO cache marker.

#### `wrap_tool_call`

Engagement-scope enforcement at the routing layer (defense-in-depth on top of query-builder scoping):

```python
def wrap_tool_call(self, request, handler):
    if request.tool and request.tool.name in self._kg_tool_names:
        engagement = request.state.get("kg_engagement")
        if not engagement:
            return ToolMessage(
                content=json.dumps({
                    "error": "kg_engagement unset; KG tools refuse to run without an engagement scope.",
                }),
                tool_call_id=request.tool_call.id,
                name=request.tool.name,
            )
    return handler(request)
```

#### `after_model`

If the just-executed tool calls included a write tool (`kg_add_node`, `kg_add_edge`, `kg_ingest`, `kg_promote_chain`), set `kg_revision` to a placeholder (`"dirty"`) so next-turn `before_agent` re-fetches the actual revision and re-renders the summary. Reads do not invalidate.

### 4.5 Tool surface (post-redesign)

| Tool | Read/Write | Replaces | Notes |
|---|---|---|---|
| `kg_query(kind, min_severity, limit)` | R | `kg_query` (broken) | Uses `KGStore.find_nodes` with engagement filter injected. |
| `kg_neighbors(node_id, direction, edge_kind)` | R | `kg_neighbors` (broken) | One-hop walk via Cypher MATCH. |
| `kg_stats()` | R | `kg_stats` + `kg_backend_health` | Stats + driver connectivity in one call. |
| `kg_add_node(kind, label, props)` | W | `kg_add_node` (broken) | Single `store.upsert_node` MERGE; engagement auto-tagged. |
| `kg_add_edge(src, dst, kind, weight)` | W | `kg_add_edge` (broken) | Single `store.upsert_edge` MERGE. |
| `kg_ingest(scanner_kind, path)` | W | 12 `kg_ingest_*` tools | Dispatch via `ingest.py` adapter registry. Scanner kinds: `nmap_xml`, `nuclei_jsonl`, `subfinder`, `httpx_jsonl`, `dnsx`, `katana`, `masscan`, `ffuf`, `testssl`, `crackmapexec`, `asrep_hashes`, `sarif`. Plugin authors register new adapters via `decepticon.kg.ingesters` entry-point. |
| `kg_plan_chains(max_depth, max_cost, top_k)` | R | `plan_attack_chains` | Wraps `chain.py:plan_chains`. APOC dijkstra with shortestPath fallback (unchanged — already correct). |
| `kg_promote_chain(chain_dict)` | W | `plan_attack_chains(promote=True)` half | Single atomic `CALL { ... }` subquery (research note §5). |

**Retired** (no longer surfaced; their job migrates to `kg_ingest` or away from KG entirely):
- `kg_analyze_jwt`, `kg_analyze_oauth_callback`, `kg_analyze_cookie_value` — analysis logic stays in `tools/web/`, just stops writing to KG. Their findings come back to the agent in JSON and the agent decides whether to `kg_add_node` them.
- `kg_scan_solidity`, `kg_ingest_slither`, `kg_triage_binary` — same treatment. Analysis tools return JSON; agent decides what to persist.
- `kg_dedupe_findings` — moved to a maintenance script under `scripts/kg/`. Not a per-turn agent action.
- `validate_finding` — moved out of KG surface; PoC validation becomes a `tools/validation/` package. Whether or not it writes back to the graph is the agent's choice (via `kg_add_node`).
- `suggest_objectives_from_chains` — OPPLAN concern, moves under OPPLAN middleware.
- `cve_lookup`, `cve_by_package`, `cve_enrich_dependencies` — moved to a new `tools/intel/` package (clean, no KG dependency). `kg_add_node` is called explicitly by the agent if it wants the result persisted.
- `fuzz_classify`, `fuzz_harness`, `fuzz_record_crash` — moved to `tools/fuzz/`. Same pattern.
- `bounty_scope_check`, `format_bounty_report` — moved to `tools/bounty/`. Same pattern.

This is the consolidation that takes the agent's KG surface from ~30 tools to **8**.

### 4.6 `KGStore` — the wrapper that replaces `_state.get_store()` + `graph_transaction()`

```python
class KGStore:
    """Engagement-scoped wrapper around Neo4j driver.

    Replaces decepticon.tools.research._state.{get_store, graph_transaction}
    and decepticon.tools.research.neo4j_store.Neo4jStore.{load_graph,
    batch_upsert_*, query_custom}.

    Every public method takes an explicit `engagement` parameter; the
    middleware injects it from kg_engagement state. No contextvar fallback
    — the contextvar in decepticon_core.utils is kept only for legacy
    paths during the migration window.
    """

    def __init__(self, driver: neo4j.Driver, database: str = "neo4j") -> None: ...

    @classmethod
    def from_env(cls) -> "KGStore": ...

    def revision(self, *, engagement: str) -> str: ...
    def find_nodes(self, *, engagement: str, kind: str | None = None,
                   min_severity: str | None = None, limit: int = 25) -> list[dict]: ...
    def neighbors(self, *, engagement: str, node_id: str,
                  direction: str, edge_kind: str | None = None) -> list[dict]: ...
    def stats(self, *, engagement: str) -> dict: ...
    def upsert_node(self, node: Node, *, engagement: str) -> Node: ...
    def upsert_edge(self, edge: Edge, *, engagement: str) -> Edge: ...
    def execute_write(self, cypher: str, params: dict, *, engagement: str) -> list[dict]: ...
    def execute_read(self, cypher: str, params: dict, *, engagement: str) -> list[dict]: ...
```

Notes:
- `execute_write` / `execute_read` use the driver's transaction functions (`session.execute_write(lambda tx: tx.run(cypher, **params).data())`). Driver auto-retries `Neo.TransientError.Transaction.DeadlockDetected` (research note §1).
- The `engagement` parameter is **always** injected into `params` and used in the WHERE clause. There is no unscoped path.
- `execute_write` / `execute_read` replace the broken `query_custom()`. The migration window keeps `query_custom()` as a thin wrapper that raises `DeprecationWarning` for one minor release cycle.

### 4.7 `AttackGraphProtocol` — the runtime/cart.py contract

Fills the docstring vaporware:

```python
# packages/decepticon/decepticon/runtime/cart.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class AttackGraphProtocol(Protocol):
    """What CART expects of any attack-graph backend.

    Implemented by KGMiddleware-owned KGStore. CART consumes only this
    surface so a future plugin (e.g. an enterprise variant with extra
    fields) can be substituted without touching cart.py internals.
    """

    def revision(self, *, engagement: str) -> str: ...
    def snapshot(self, *, engagement: str) -> EngagementSnapshot: ...
    def subscribe(self, callback: Callable[[SnapshotDelta], None]) -> SubscriptionToken: ...
```

`KGStore` implements `revision`, `snapshot` (returns a frozen `EngagementSnapshot` built from a single Cypher MATCH), and `subscribe` (optional — initial version polls; a follow-up can use Neo4j 5.x change data capture).

### 4.8 Composite range indexes

Ship via a new migration file `packages/decepticon/decepticon/middleware/kg_internal/migrations/V002__engagement_composite_indexes.cypher` (V001 = the existing schema in `Neo4jStore.ensure_schema`):

```cypher
CREATE RANGE INDEX engagement_host_explored IF NOT EXISTS
  FOR (h:Host) ON (h.engagement, h.explored);
CREATE RANGE INDEX engagement_vuln_severity IF NOT EXISTS
  FOR (v:Vulnerability) ON (v.engagement, v.severity);
CREATE RANGE INDEX engagement_finding_status IF NOT EXISTS
  FOR (f:Finding) ON (f.engagement, f.status);
```

These three cover the agent's top read patterns per research note §3 + §7.

### 4.9 Adapter registry for `kg_ingest`

```python
# kg_internal/ingest.py
from collections.abc import Callable
from typing import Any

ScannerAdapter = Callable[[Path, KGStore, str], dict[str, Any]]
#                ^^^^^   ^^^^^^^  ^^^^^^^^
#                path    store    engagement → result dict

_REGISTRY: dict[str, ScannerAdapter] = {}

def register_adapter(scanner_kind: str, adapter: ScannerAdapter) -> None: ...

def ingest(scanner_kind: str, path: str, store: KGStore, engagement: str) -> dict: ...

# Built-ins registered at import time:
register_adapter("nmap_xml", _nmap_adapter)
register_adapter("nuclei_jsonl", _nuclei_adapter)
# ...11 more
```

Plugin authors extend via the `decepticon.kg.ingesters` entry-point group (one of the entry-point groups documented in §5).

### 4.10 Plugin surface — `MiddlewareSlot.KG`

Adds one enum entry to `decepticon_core.contracts.slots.MiddlewareSlot`:

```python
class MiddlewareSlot(StrEnum):
    ENGAGEMENT_CONTEXT = "ENGAGEMENT_CONTEXT"
    SKILLS             = "SKILLS"
    OPPLAN             = "OPPLAN"
    KG                 = "KG"          # ← new
    HITL               = "HITL"
    # ...existing slots
```

Plugin bundles can replace the slot (e.g. a downstream plugin providing `EnterpriseKGMiddleware` with vector search) or disable it (an OSS-only agent with no Neo4j).

`SLOTS_PER_ROLE` updates:
- `analyst` gains `KG` (in the same position as `OPPLAN` for orchestrators).
- `ad_operator` gains `KG`.
- `contract_auditor` gains `KG`.
- The other 14 agents do not gain it.

Agents stop importing `RESEARCH_TOOLS`, `BOUNTY_TOOLS`, `REPORTING_TOOLS`, etc. from `tools/research/`. Those imports were already removed for the 14 non-KG agents in the prep work; the 3 KG-using agents lose them when the slot adoption lands.

---

## 5. Plugin contract additions

The post-1.0 plugin contract needs to absorb the changes:

| Entry-point group | Status | Purpose |
|---|---|---|
| `decepticon.kg.ingesters` | **new** | Plugin authors register scanner adapters. Loaded by `kg_internal.ingest.register_adapter` during framework boot. |
| `decepticon.middleware` | existing | Plugin authors can ship their own `KGMiddleware` subclass and have it picked up via the slot system. |
| `decepticon.bundles` | existing | Bundle authors compose middleware sets including / excluding KG. |

Documentation goes in `packages/decepticon-sdk/decepticon_sdk/scaffold/templates/kg_ingester/` — a `decepticon-sdk plugin new --kind=kg-ingester` template ships in the SDK.

---

## 6. Migration plan

### 6.1 Phased execution (4 PRs after this spec lands)

**PR-A — Foundations (no behavior change for agents).** Adds `KGStore`, `AttackGraphProtocol`, composite range indexes (migration file + invocation at boot), and the `decepticon.kg.ingesters` entry-point group. `tools/research/` is untouched.

**PR-B — Middleware introduction.** Adds `KGMiddleware`, `KGState`, `kg_internal/` package, the 8-tool surface, the `kg_ingest` adapter registry with 12 built-in adapters. The middleware is **not yet wired into any agent** — opt-in is by direct construction for the integration tests only. `analyst`, `ad_operator`, `contract_auditor` continue to import the broken `RESEARCH_TOOLS` etc.

Acceptance: a new test file `tests/integration/kg_middleware/test_analyst_e2e.py` exercises the middleware against a live Neo4j (compose-managed) and confirms the 8 tools work end-to-end. The broken pathway also still works.

**PR-C — Agent cutover.** `MiddlewareSlot.KG` lands. `SLOTS_PER_ROLE` for analyst / ad_operator / contract_auditor gains `KG`. The 3 agent factories drop their direct `RESEARCH_TOOLS` etc. imports. `tools/research/tools.py` reduces to a thin shim that emits `DeprecationWarning` for the slated-for-removal symbols (one minor cycle).

Acceptance: `analyst` end-to-end via `make benchmark ARGS="--ids XBEN-095-24"` produces the same trace shape as before; analyst-side tool calls show `kg_*` routing through `KGMiddleware` (visible in LangSmith trace).

**PR-D — Cleanup.** `tools/research/{_state.py, bounty.py, dedupe.py, patch.py, scanner_tools.py, sarif.py, sarif_export.py, fuzz.py, cve.py, poc.py, health.py, graph.py}` retire or relocate (see §6.3). `chain.py` and `neo4j_store.py` get moved under `middleware/kg_internal/` (or stay where they are if importers still need the path; either way the implementation owner is the middleware). Web dashboard route unchanged (it speaks Cypher directly).

### 6.2 File-by-file migration table (`tools/research/`)

| File | LOC | Disposition in PR-D |
|---|---:|---|
| `__init__.py` | 37 | Slim down to re-export from `decepticon_core.types.kg` only. |
| `_state.py` | 89 | Delete. `_load` / `_save` / `graph_transaction` are no longer called by anything inside the framework. |
| `_engagement_scope.py` | 50 | Delete (it is already a re-export shim post-evacuation). |
| `_apoc_safety.py` | 145 | Move under `kg_internal/`. Used by the chain planner for Cypher injection defense. |
| `bounty.py` | 343 | Move under `tools/bounty/`. Replace `_load` / `_save` calls with `KGStore.execute_*`. Tools become available via a new (small) `BountyMiddleware` or remain agent-facing if the team prefers; decide during PR-D. |
| `chain.py` | 422 | Move under `kg_internal/chain.py`. Already good-pattern; just imports update. |
| `cve.py` | 480 | Move under `tools/intel/cve.py`. No graph dependency. |
| `dedupe.py` | 342 | Move under `kg_internal/dedupe.py`. Becomes an internal helper invoked by `KGMiddleware` (or by the `scripts/kg/dedupe.py` maintenance command). |
| `fuzz.py` | 357 | Move under `tools/fuzz/`. No graph dependency for the harness/classify pieces; the `record_crash` helper takes a `KGStore` arg. |
| `graph.py` | 36 | Delete. Already a deprecated re-export shim for `core/types/kg.py`. |
| `health.py` | 49 | Move under `kg_internal/health.py`. Used by `kg_stats`. |
| `neo4j_store.py` | 787 | Move under `kg_internal/store.py` (rename to `Neo4jKGStore` if we keep `KGStore` as the interface name) OR be wrapped by `KGStore`. Decided in PR-A. |
| `patch.py` | 298 | Move under `tools/patch/`. Same treatment as `bounty.py`. |
| `poc.py` | 381 | Move under `tools/validation/poc.py`. Pure logic; `validate_poc` takes the store as arg. |
| `sarif.py` | 240 | Move under `kg_internal/ingest/sarif.py`. Becomes one of the 12 built-in adapters for `kg_ingest`. |
| `sarif_export.py` | 261 | Move under `tools/reporting/` (it's an output formatter, not an ingester). |
| `scanner_tools.py` | 601 | Split. `scan_shard` / `rank_candidates` move under `tools/scanner/` (clean). `kg_add_candidate` migrates to use `KGStore` directly. |
| `tools.py` | 2,386 | Retire piecewise. Each @tool either (a) becomes a method in `kg_internal/tools.py` or (b) moves to its non-KG home (`tools/intel/`, `tools/fuzz/`, etc.). The file shrinks to zero. |

### 6.3 Test migration

- The 17 `tests/unit/research/` files keep their fixtures but change their imports to target `kg_internal/`. The contracts they assert (deterministic IDs, MERGE idempotence, severity weighting) are unchanged.
- New tests under `tests/unit/middleware/test_kg_middleware.py` cover: state hydration, summary injection, write-revision invalidation, engagement-scope enforcement (rejecting writes when `kg_engagement` is unset), and the `kg_ingest` adapter registry.
- New integration tests under `tests/integration/kg_middleware/` exercise the middleware against a compose-managed Neo4j (test fixture spins up the service or uses an existing one).

### 6.4 Downstream coordination

A downstream plugin package may import from `decepticon.tools.research`. A follow-up change there:
1. Replaces direct `kg_*` imports with `KGMiddleware`-mediated access (or whatever the downstream agents do).
2. Adds any downstream-specific KG ingesters via the `decepticon.kg.ingesters` entry-point.

Coordinated with this spec, not gated on it.

---

## 7. Acceptance criteria

For each PR:

### PR-A

- `KGStore` is importable from `decepticon.middleware.kg_internal.store`.
- `AttackGraphProtocol` is defined in `runtime/cart.py` and `KGStore` is checked via `isinstance(store, AttackGraphProtocol)` at boot.
- The three composite indexes are created on first boot against a fresh Neo4j volume; `EXPLAIN MATCH (h:Host {engagement: $e, explored: true}) RETURN h` shows index usage.
- `decepticon.kg.ingesters` entry-point group is wired (an empty implementation in the framework + a stub adapter registered).
- All existing tests pass.

### PR-B

- `KGMiddleware` is importable from `decepticon.middleware.kg`.
- `KGMiddleware().tools` returns 8 tools with names `kg_query`, `kg_neighbors`, `kg_stats`, `kg_add_node`, `kg_add_edge`, `kg_ingest`, `kg_plan_chains`, `kg_promote_chain`.
- Integration test against compose Neo4j: build an agent with `KGMiddleware()` only, call `kg_add_node` + `kg_query` + `kg_ingest("nmap_xml", ...)`, assert results.
- `kg_ingest` with each of the 12 built-in scanner kinds round-trips against a sample input file.
- Engagement-scope rejection: a call with unset `kg_engagement` returns the documented error and does NOT touch Neo4j.

### PR-C

- `MiddlewareSlot.KG` exists in `decepticon_core.contracts.slots`.
- `SLOTS_PER_ROLE["analyst"]`, `["ad_operator"]`, `["contract_auditor"]` include `KG`.
- `analyst.py` no longer imports `RESEARCH_TOOLS`, `BOUNTY_TOOLS`, `REPORTING_TOOLS`, `REFERENCES_TOOLS`. Its `_STANDARD_TOOLS` reduces to `*REFERENCES_TOOLS`, `*BASH_TOOLS` (the references and bash tools are still direct; KG tools come from the slot).
- `make benchmark ARGS="--ids XBEN-095-24"` (an analyst-heavy challenge) finishes with the same pass/fail shape as the pre-PR baseline. Tool-call latency in LangSmith is **lower** (target: 5× lower for `kg_*` calls vs the broken backend on a graph with 1K+ nodes).
- The web dashboard `engagements/[id]/graph` page still renders the engagement graph.

### PR-D

- `tools/research/` reduces to `__init__.py` + the chain.py / neo4j_store.py files (if not moved) or is empty (if all moved).
- No production code imports from `decepticon.tools.research.{_state,bounty,dedupe,patch,scanner_tools,sarif,sarif_export,fuzz,cve,poc,health,graph}`.
- `DeprecationWarning` from the migration shim is the only remaining trace; the shim ships for one minor version and is removed at the next minor.
- All tests pass; coverage of the new `middleware/kg.py` and `kg_internal/` is ≥ 85%.

### Global acceptance (across all PRs)

- A single benchmark run of `XBEN-095-24` (an analyst-leaning challenge) shows a per-`kg_*` call latency reduction of ≥ 80% measured at the LangSmith trace level.
- A multi-agent stress test (16-agent parallel writes) succeeds without the `_GRAPH_LOCK` (because there is no lock) and without any data corruption (verified by `kg_dedupe_findings` running clean post-test).
- `runtime/cart.py` can subscribe to KG snapshots via the new `AttackGraphProtocol` — proven by a small CART unit test that builds two snapshots and diffs them.

---

## 8. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| KGMiddleware breaks analyst's existing flow during PR-C cutover | Medium | High (analyst is the production KG user) | PR-B integration tests run analyst-shaped scenarios before PR-C lands. PR-C is reversible (revert restores `RESEARCH_TOOLS` imports). |
| AD_TOOLS / CONTRACT_TOOLS still use the broken shim after PR-C | High | Medium (they keep working, just slowly) | Out of scope for this spec by design (NG3). Track as follow-up. |
| Composite index creation collides with existing data (engagement property missing on legacy nodes) | Low | Medium | The existing `_LEGACY_ENGAGEMENT_LABEL` migration helper in `_engagement_scope.py` covers this. Run it before V002 migration. |
| Web dashboard query shape changes break the graph view | Low | High (visible to user) | Web route reads via direct `neo4j-driver`; it queries by label + engagement property. We preserve that contract. No web changes in this spec. |
| Plugin authors get broken imports during the deprecation window | Medium | Low | `DeprecationWarning` with explicit migration mapping in `decepticon.compat`. One minor cycle window. |
| `query_custom` removal breaks a downstream plugin | Medium | Medium | Coordinated migration in the downstream plugin package. |

---

## 9. Out-of-band items

- **`runtime/cart.py:AttackGraphProtocol` move**: spec resolves the docstring vaporware by fully defining the protocol in PR-A. Subscribers (CART itself) are wired in PR-B's integration test.
- **`untrusted_output.py:68-71`**: the four `kg_*` names in the untrusted-source list remain accurate (KG tool calls still return untrusted data). No edit needed.
- **`scripts/kg/`**: new directory for maintenance scripts (`dedupe`, `migrate`, `inspect`). Spec defers content to PR-D.
- **`docs/architecture.md`**: needs a one-paragraph update noting the KGMiddleware ownership. Defer to PR-C.

---

## 10. Appendix — example tool implementations

```python
# kg_internal/tools.py
from langchain_core.tools import tool

def build_kg_tools(store: KGStore, enabled: set[str]) -> list[BaseTool]:
    tools = []

    if "kg_query" in enabled:
        @tool
        def kg_query(
            kind: str = "",
            min_severity: str = "",
            limit: int = 25,
            *,
            engagement: Annotated[str, InjectedState("kg_engagement")],
        ) -> str:
            """Query the knowledge graph for nodes matching kind / severity.
            (docstring unchanged from the broken implementation; the WHEN / IMPORTANT
            sections stay so the analyst prompt's existing references still match)"""
            rows = store.find_nodes(
                engagement=engagement, kind=kind or None,
                min_severity=min_severity or None, limit=limit,
            )
            return json.dumps({
                "total": len(rows),
                "returned": min(len(rows), limit),
                "nodes": rows[:limit],
            })
        tools.append(kg_query)

    # ...kg_neighbors, kg_stats, kg_add_node, kg_add_edge, kg_ingest,
    #    kg_plan_chains, kg_promote_chain follow the same pattern

    return tools
```

Note `engagement` comes from state via `InjectedState`, not from the LLM. The model never sees an `engagement` parameter in the tool schema — the middleware injects it.

```python
# kg_internal/store.py — execute_write example
def upsert_node(self, node: Node, *, engagement: str) -> Node:
    props = dict(node.props) | {"engagement": engagement}
    cypher = """
    MERGE (n:{label} {id: $id})
    ON CREATE SET n.created_at = $now
    SET n.label = $label,
        n.kind = $kind,
        n.props = $props_json,
        n.engagement = $engagement,
        n.updated_at = $now
    RETURN n.id AS id
    """.replace("{label}", node.kind.value)
    with self._driver.session(database=self._database) as session:
        session.execute_write(
            lambda tx: tx.run(
                cypher,
                id=node.id, label=node.label, kind=node.kind.value,
                props_json=json.dumps(props), engagement=engagement,
                now=time.time(),
            ).consume()
        )
    return node
```

Note: only this MERGE runs, not the whole graph round-trip. Driver retries deadlocks. No Python-side lock.

```python
# kg_internal/ingest.py — adapter pattern
def _nmap_adapter(path: Path, store: KGStore, engagement: str) -> dict:
    """Adapter for kg_ingest('nmap_xml', path).

    Reads the same nmap XML the old kg_ingest_nmap_xml read, but writes
    via per-op store calls inside one transaction.
    """
    root = defusedxml.ElementTree.parse(path).getroot()
    nodes: list[Node] = []
    edges: list[Edge] = []
    for host_el in root.findall("host"):
        # ...build nodes / edges (logic copied from the old implementation)
        ...
    # Single transaction for the whole ingest:
    with store.driver.session(database=store.database) as session:
        session.execute_write(_batch_merge, nodes, edges, engagement)
    return {"hosts_added": ..., "services_added": ...}
```

---

## 11. Open questions

1. **Tool name `kg_ingest` vs preserving names**: Should we ship `kg_ingest("nmap_xml", path)` (one tool, dispatched) OR `kg_ingest_nmap_xml(path)` etc. as thin wrappers around the adapter for prompt-backwards-compat? The current analyst.md prompt cites `kg_ingest_sarif`, `kg_ingest_nmap_xml`, etc. by name. The single-tool form is cleaner but forces a one-time prompt rewrite. **Recommendation:** ship both — one canonical (`kg_ingest`) plus name-preserving wrappers as a transition aid, drop wrappers after one minor cycle.

2. **`InjectedState` requirement**: `langchain_core.tools.InjectedState` is the canonical pattern but it requires the tool function signature to declare it. Does our current langchain version support it cleanly with the middleware-owned `state_schema`? Verify in PR-A before committing to the pattern.

3. **`KGStore` as a `Neo4jStore` wrapper vs replacement**: Section 6.2 leaves this open. Wrapping preserves the existing `Neo4jStore` API (and its tests). Replacement is cleaner but doubles the migration surface. **Lean:** wrap in PR-A, replace in PR-D when no external caller is left.

4. **Per-engagement vs per-thread state**: `kg_summary` lives in agent state, which langgraph checkpoints per thread. Multi-engagement same-thread (which we do not currently support) would conflate summaries. Add a "summary keyed by engagement" caveat to PR-B's `KGState`.

5. **Vector index hook**: Should `KGMiddleware` expose a `kg_search_semantic(query, top_k)` tool that uses Neo4j 5.13's vector index? Research note §4 leaves this as a follow-up. **Decision deferred** to the next spec.

---

## 12. Sign-off checklist (pre-PR-A)

- [ ] User review of this spec, especially §3 (goals), §4.5 (tool surface), §6.2 (file disposition).
- [ ] Confirm `langchain_core.tools.InjectedState` support in the pinned langchain version.
- [ ] Confirm `Neo4j 5.24 community` supports the composite range index syntax used in §4.8.
- [ ] Decide the `tools/research/_state.py` removal timing (PR-D vs as soon as no caller is left).
- [ ] Decide the `KGStore` wrap-vs-replace question (§11 #3).
- [ ] Coordinate downstream on §6.4.
