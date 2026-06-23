# KG Middleware Implementation Research

- **Date:** 2026-06-03
- **Status:** Phase 1 draft (skills + prior research). Phase 2 (external docs) appended after review.
- **Related:** [`docs/design/2026-06-03-kg-middleware-redesign.md`](./2026-06-03-kg-middleware-redesign.md) (spec), [`docs/design/neo4j-research-notes.md`](./neo4j-research-notes.md) (Neo4j 13-topic deep dive), [`docs/design/2026-06-03-external-docs-research.md`](./2026-06-03-external-docs-research.md) (external docs, in progress)
- **Branch:** `feat/kg-middleware`
- **Purpose:** Surface the *implementation* questions the spec leaves open, with evidence from the LangChain / LangGraph / DeepAgents / memory-systems / tool-design skills, and present concrete options for user review **before** any KG code is written.

---

## 1. TL;DR

The KG middleware redesign was specified before doing the agent-framework research. Three issues surfaced that justify a design check-in:

1. **A 2026 memory-systems benchmark calls the entire premise into question.** Letta's **filesystem-based agents scored 74% on LoCoMo**, beating Mem0's specialized memory tools at 68.5%. Decepticon's analyst already writes `findings/FIND-NNN.md`, `recon/SUMMARY.md`, `timeline.jsonl` — file-system memory it already produces. **Question: does a dedicated KG middleware enable new capability, or is it tooling for tooling's sake?**

2. **The tool-design skill's "Stop Constraining Reasoning" principle** argues against specialized tools when primitives suffice. Adding 8 KG tools may constrain the model instead of enabling it.

3. **The DeepAgents skill confirms** that DeepAgents already ships `MemoryMiddleware` + `Store` for cross-session memory. The OPPLAN pattern in `middleware/opplan.py` is the right shape for *workflow-state* middleware. But for *graph-shaped memory*, the LangGraph `BaseStore` interface is a poor fit (hierarchical key-value, no edge model) — confirming the `KGStore` direct-Cypher decision from the spec.

The recommendation is **NOT** to pick option A (spec-as-written) blindly. The three options in §6 are concrete trade-offs the user should pick from before any code lands.

---

## 2. Skills consulted (6) — what each contributed

| Skill | Key finding for KG middleware |
|---|---|
| `framework-selection` | Decepticon is **layered**: LangChain `create_agent` + LangGraph runtime + DeepAgents backend. Middleware = `langchain.agents.middleware.AgentMiddleware`. The spec's OPPLAN-mirror approach is correct in *kind*. |
| `langchain-middleware` | 5 hooks confirmed: `before_agent`, `before_model`, `wrap_model_call`, `wrap_tool_call`, `after_model`, `after_agent`. Tool-specific middleware (`tools=[...]` scoped to certain tools) is supported. HITL pattern (`interrupt_on={"kg_add_edge": True}`) is available if we want operator-approved chains. |
| `deep-agents-core` | DeepAgents' built-in `MemoryMiddleware` + `Store` is the canonical long-term memory pattern. Skills (SKILL.md) and subagent (`task` tool) middlewares already exist. **Custom middleware composes with the built-ins.** |
| `memory-systems` | LoCoMo benchmark: **Letta filesystem (74%) > Mem0 (68.5%)**. Zep/Graphiti's temporal bi-modeling shows 18.5% LongMemEval improvement + 90% latency reduction via subgraph retrieval. Anti-pattern: "over-engineering early." |
| `langgraph-persistence` | `Store` is key-value / hierarchical, not graph-native. Implementing `BaseStore` for Neo4j would force us to flatten edges into encoded keys — a degraded representation. Confirms **`KGStore` as a direct API** (spec §4.6), not a `BaseStore` impl. |
| `tool-design` | Consolidation principle ("if a human can't pick the tool, an agent can't") **supports** collapsing 12 `kg_ingest_*` into one. Architectural-reduction principle **questions** whether we need any KG tools at all. 10-20 tools per agent is the budget. |

---

## 3. Confirmed design decisions (no change from spec)

These are the spec items that survive the research check:

- **Class shape**: `class KGMiddleware(AgentMiddleware)` with `state_schema = KGState`. Mirrors OPPLAN.
- **Tool factory**: `self.tools = build_kg_tools(self._store, enabled)`. The `self.tools` attribute is the standard LangChain middleware mechanism for contributing tools to the agent's tool list (confirmed by 8+ usages in `decepticon/tools/opplan.py`).
- **Per-op `execute_write` / `execute_read`** replacing `graph_transaction()`. Removes the global `threading.Lock`. (Research notes §1–§2.)
- **`InjectedState` pattern** for engagement scoping at the tool layer — the model never sees an `engagement` parameter. Used 8+ times in `tools/opplan.py` already.
- **Engagement-scoped composite range indexes** (`(engagement, severity)` etc.) ship as a V002 migration. (Research notes §3, §7.)
- **`kg_ingest(scanner_kind, path)`** with adapter registry replaces 12 `kg_ingest_*` tools. Tool-design consolidation principle supports this.
- **`AttackGraphProtocol`** filled in (currently docstring-only vaporware at `runtime/cart.py:36`). The `revision()` + `snapshot()` polling model survives.
- **`KGStore` is a direct API, NOT a `BaseStore` implementation.** The langgraph-persistence skill makes clear the `Store` interface (put/get/search/delete by key) can't express edges without flattening into encoded keys. A separate API is correct.

---

## 4. Open questions the spec did not answer

These came up only after going through the skills. Each one needs a user decision.

### Q1 — Does a KG middleware enable new capability, or constrain the model?

The memory-systems and tool-design skills both surface the file-system pattern. Decepticon's analyst.md prompt already instructs the model to write `findings/FIND-NNN.md`, `recon/SUMMARY.md`, `timeline.jsonl`. Those files are durable, queryable with `grep`, human-readable, and survive any framework change.

What does Neo4j enable that files don't?

| Capability | File-system | Neo4j |
|---|---|---|
| Per-finding markdown report for operator | ✓ | ✗ (would render from graph) |
| `grep -r "SSRF" findings/` to recall | ✓ | Cypher MATCH (more powerful but more setup) |
| Multi-hop attack-path planning (`entrypoint → cred → admin`) | ✗ | ✓ (APOC dijkstra) |
| Cross-engagement correlation in a dashboard | ✗ | ✓ (already wired in `clients/web/`) |
| Deduplication of `Host` by IP across multiple agents | ✗ | ✓ (MERGE-on-key) |
| Vector search over finding descriptions | ✗ | ✓ (Neo4j 5.13+ vector index) |

**The Neo4j-unique capabilities are (a) multi-hop chain planning and (b) cross-agent dedup.** Files cover (c) recall and (d) reporting better.

**Implication for design**: the KG middleware does NOT need to expose `kg_query` and `kg_neighbors` as tools the LLM calls — the LLM can `grep findings/`. What the KG middleware DOES need is:
- A write surface so multi-agent writes land in Neo4j (for cross-agent dedup + path planning).
- A summary block injected into the system prompt (chain candidates, current crown-jewel set).
- Direct `cypher-shell` access via bash for the agent when it needs path-planner output.

This pushes toward **Option B (hybrid)** in §6 — read tools off, write tools on, summary in prompt.

### Q2 — Is "auto-ingest from files" really off the table?

The spec's NG4 (out-of-scope) says: "Agents continue to call `kg_*` tools explicitly. The middleware does NOT silently parse workspace files." This was confirmed by the user 2026-06-03: "미들웨어 통해서 자동 kg 기여가 아니라... KG 도구 자체를 KG 미들웨어로 만들어서 tool로 노출."

But the Q1 analysis changes the picture:
- If the LLM uses `grep findings/` for recall (instead of `kg_query`), the LLM is no longer the entity *writing* to KG — at least not for findings recall.
- A background `after_model` hook could ingest newly-written `findings/FIND-NNN.md` into KG nodes automatically.
- This is NOT "silent middleware doing the agent's work" — it's "middleware projecting the file the agent just wrote into the graph."

**Re-confirm with user**: did the 2026-06-03 directive rule out auto-ingest entirely, or only "auto-ingest in lieu of agent action"? File→KG projection after the agent writes a file is a different pattern.

### Q3 — How much of analyst's current prompt survives?

`analyst.md` is ~200 lines and heavily KG-centric (12 `kg_*` mentions, the `<KNOWLEDGE_GRAPH_DISCIPLINE>` block, 8 hunting lanes). If we narrow the tool surface to write-only + summary-injection, the prompt needs rewriting:
- Remove the "`kg_query(...)` → review highs/criticals" instructions (LLM uses `grep` instead).
- Remove the `KG_DISCIPLINE` block (or rewrite it as "the middleware shows you the chain candidates; if you want details, grep").
- Keep the explicit `kg_add_node` / `kg_ingest` calls for write-only.

This is a substantial prompt rewrite. Worth it if Option B saves the analyst from the broken backend.

### Q4 — Multi-engagement concurrency

`memory-systems` skill flagged: "Stateful subgraphs (`checkpointer=True`) do NOT support calling the same subgraph instance multiple times within a single node — namespace conflict." This is a langgraph constraint, but the analog for our KG is: **simultaneous writes from two agents in the same engagement.**

Neo4j's MVCC handles concurrent MERGE correctly — but two agents BOTH adding `Host {ip: "10.0.0.1"}` in the same transaction window can produce duplicate edges if `key` isn't deterministic. We already use deterministic IDs in `Node.make` (SHA1 of `kind+key`), so this is handled.

Confirm in PR-A: stress-test 16-agent parallel writes against compose Neo4j. If the deterministic key holds, we're done; if not, we need `apoc.lock.nodes` for cross-MERGE atomicity.

### Q5 — Vector index for analyst's "semantic recall"?

Skill `memory-systems` lists Zep/Graphiti's hybrid retrieval (semantic + keyword + graph) as the SOTA. Neo4j 5.13+ ships a native vector index. The spec marks vector integration as NG1 (out of scope), but **if we're already touching the schema in PR-A, adding a vector property + index to `Vulnerability` and `Finding` is cheap.**

Cost: an embedding API call per `kg_add_node(kind="vulnerability")` write. Could be opt-in via a `KGMiddleware(embed_findings=True)` flag.

Recommendation: ship vector schema (RANGE INDEX + vector property) in PR-A; defer the embed-on-write call and the `kg_search_semantic` tool to a follow-up. Keeps the schema future-proof without committing to the embed pipeline now.

---

## 5. Skill-confirmed anti-patterns to avoid

From the skills:

- **(tool-design)** "Pre-filtering context, constraining options, wrapping interactions in validation logic. These guardrails often become liabilities as models improve." → Do not wrap every Cypher call in a Pydantic validation layer. Trust the driver's parameter binding.
- **(memory-systems)** "Stuffing everything into context. Long inputs are expensive and degrade performance. Use just-in-time retrieval." → The KG summary block injected in `wrap_model_call` must be **small** (top-5 vulns + top-3 entrypoints + chain count). Not the whole graph.
- **(memory-systems)** "Ignoring temporal validity. Facts go stale." → A `Vulnerability` node with `validated_at` and `patched_at` is the right starting point. Don't go straight to bi-temporal (Graphiti-style) — but leave room for it.
- **(memory-systems)** "Over-engineering early. A filesystem agent can outperform complex memory tooling." → See Q1.
- **(memory-systems)** "No consolidation strategy. Unbounded memory growth degrades retrieval quality." → A `scripts/kg/dedupe.py` maintenance script (already in spec) is necessary. Pre-empt cluster expansion.
- **(langgraph-persistence)** "Never block the agent's response on a memory write." → KG writes must be best-effort. If Neo4j is unreachable, the analyst still finishes the engagement; the writes get queued or dropped (with a logged warning).
- **(langchain-middleware)** "Skip checkpointer requirement for HITL" is impossible. Engagement state hydration in `before_agent` must tolerate the case where there's no checkpointer (e.g. one-shot benchmarks).

---

## 6. Three options for user review

| Option | KG surface (what the LLM sees) | KGMiddleware does | Code surface | Risk |
|---|---|---|---|---|
| **A. Spec-as-written** | 8 tools (`kg_query`, `kg_neighbors`, `kg_stats`, `kg_add_node`, `kg_add_edge`, `kg_ingest`, `kg_plan_chains`, `kg_promote_chain`) | Own store, build_tools, before_agent summary, wrap_tool_call scope, after_model revision | ~2,500 LOC new + retire `tools/research/` per migration table | Medium. Familiar OPPLAN-mirror pattern but high tool count for the analyst. |
| **B. Hybrid (read-off, write-on, summary-in-prompt)** | 3 tools (`kg_add_node`, `kg_add_edge`, `kg_ingest`). No read tools — LLM uses `grep findings/` + `bash("cypher-shell ... 'MATCH path = ...'")` when it needs path planning. | Own store, summary block in `wrap_model_call`, optional `after_model` file→KG projection (re-confirm with user per Q2), wrap_tool_call scope. | ~1,500 LOC new. Smaller tool surface = simpler prompt rewrite. | Lower. Aligns with Letta-style file-system result. Loses LLM-driven path planning unless the summary block surfaces top-N chains. |
| **C. File-first, KG-as-projection** | 0 tools. LLM works only in files. Middleware silently reads new findings files and projects them into Neo4j after each turn. The web dashboard `engagements/[id]/graph` keeps working. | Own store. `after_model` parses any newly-written `findings/*.md` (front-matter or JSON sidecar). Summary block from KG in `wrap_model_call`. | ~800 LOC new. No tool factory at all. | Highest reframe but lowest tool-surface cost. Requires explicit user override of 2026-06-03 "no auto-ingest" directive (Q2). Web dashboard still gets data because the middleware writes; the LLM is unaware. |

### What each option means for the next 2-3 weeks of work

- **A**: PR-A (foundations) → PR-B (middleware) → PR-C (analyst cutover) → PR-D (cleanup). 4 PRs, all spec-as-written. Risk: analyst prompt has to keep its KG-centric procedure, but the broken backend is gone.
- **B**: PR-A (foundations same) → PR-B (smaller middleware, 3 tools + summary block) → PR-C (analyst prompt **substantial rewrite**: drop kg_query/kg_neighbors from prompt, add "use grep findings/" + "the chain block above shows current candidates"). Spec § 4.5 tool list reduced from 8 to 3. The 12-ingester dispatch still collapses into `kg_ingest`.
- **C**: PR-A (foundations same) → PR-B (KGMiddleware that reads files in `after_model` and writes nodes — front-matter or sidecar `.json` defines the node structure) → PR-C (analyst prompt **minimal change**: remove KG section entirely, the prompt only knows about files). LLM ground-truth becomes the files; KG is the "compiled" view for the web dashboard and CART.

---

## 7. What's still pending (external docs research)

Background agent is fetching the following and will append to `docs/design/2026-06-03-external-docs-research.md`:

1. LangChain `AgentMiddleware` latest API (verify `self.tools` attribute, hook signatures, tool-specific scoping).
2. LangGraph `BaseStore` shape — confirm graph-shape mismatch.
3. DeepAgents `MemoryMiddleware` + `Store` interplay — confirm `KGMiddleware` composes cleanly with the built-ins.
4. Neo4j Python driver `session.execute_write` + retry semantics. Verify `CREATE RANGE INDEX FOR (n:Label) ON (n.a, n.b)` for 5.24 (research notes claim it but no live verification yet).
5. BloodHound CE 2026 / Cartography sync / Graphiti / Cognee patterns — borrow what's borrowable.

When that lands, this doc will get a § 8 ("External docs findings") and may flip the recommendation in § 6.

---

## 8. Decision points for user review

Please pick one of A / B / C in §6 (or describe a D the research missed), then confirm or revise the Q1–Q5 answers in §4:

- **Q1**: Which KG-unique capabilities matter most (chain planning, dedup, cross-agent correlation, vector recall)?
- **Q2**: Is file→KG auto-projection (after the agent writes a file) different enough from "silent ingest" to allow?
- **Q3**: Willing to rewrite `analyst.md` substantially (Option B/C) vs. preserving it (Option A)?
- **Q4**: Run the 16-agent parallel-write stress test in PR-A?
- **Q5**: Ship the vector-index schema in PR-A even if we don't use it yet?

Once decided, this doc gets the § 9 ("Implementation plan, post-review") added and PR-A starts on `feat/kg-middleware`.

---

## 9. Post-decision minimal design (Option B confirmed, 2026-06-03)

User chose Option B. Directive: "꼭 필요한 기능/필수적인 기능, 도구만 포함." Re-applying the consolidation + architectural-reduction principles to push the tool surface to the absolute minimum.

### 9.1 Why 3 tools (the original Option B count) is still too many

`kg_add_node` and `kg_add_edge` as separate tools force the agent to chain 2-5 tool calls for a single observation. Example: "Host 10.0.0.1 runs nginx 1.18 on port 80":

| With `kg_add_node` + `kg_add_edge` separately | Cognitive cost |
|---|---|
| 1. `kg_add_node("host", "10.0.0.1", {...})` → returns `host_id` | 1 turn |
| 2. `kg_add_node("service", "10.0.0.1:80", {...})` → returns `svc_id` | 1 turn |
| 3. `kg_add_edge(host_id, svc_id, "HOSTS", 0.5)` | 1 turn |
| 4. (optionally repeat for Vulnerability) | 1 turn |

That's **3-4 turns to record one finding**. Each turn carries:
- Tool selection overhead (which of `kg_add_node` / `kg_add_edge` / `kg_ingest`).
- Round-trip to the model.
- Risk of mismatched IDs.

The tool-design skill calls this out directly: "Consolidation reduces token consumption … reduces tool selection complexity by shrinking the effective tool set."

### 9.2 The 2-tool minimum

**T1: `kg_record(observations: list[dict])`** — atomic batch write of nodes AND their outgoing edges in a single call.

```python
# Tool signature (shape; final types refined in PR-B)
@tool
def kg_record(observations: str) -> str:
    """Record one or more graph observations atomically.

    Each observation is one node, optionally with outgoing edges. The
    middleware injects the engagement scope; the deterministic key
    ensures dedup across multiple agents writing the same host /
    service / vuln. All observations in one call land in one Neo4j
    transaction — partial failure rolls back the batch.

    WHEN TO USE: every time you observe an asset, vulnerability, credential,
    entrypoint, or want to connect existing nodes. One call per logical
    observation (a host + its services + its vulns).

    OBSERVATION SHAPE (JSON):
      {
        "kind": "host" | "service" | "vulnerability" | "credential" | ...,
        "label": "10.0.0.1",
        "key": "host::10.0.0.1",        # deterministic dedup
        "props": {"ip": "10.0.0.1", "explored": false, ...},
        "edges_out": [
          {"to_key": "service::10.0.0.1:80", "kind": "HOSTS", "weight": 0.5}
        ]
      }

    BATCHING: send 1-10 observations per call. >10 → use kg_ingest with
    a scanner adapter.

    Returns: JSON {"created": N, "merged": M, "edges": E, "revision": "..."}.
    """
```

Why this shape:
- **Single tool for the write surface.** Aligns with consolidation principle (tool-design skill).
- **Atomic batch.** The "host + its services + its vulns" cluster lands in one transaction. Either all of it persists, or none — partial inserts on a transient Neo4j error are the worst kind of bug.
- **Forces deterministic key.** `props["key"]` is mandatory for dedup. Eliminates the broken-shim era's accidental duplicate-on-rescan.
- **Edges expressed inline.** No separate edge-call dance. The agent thinks "this host has these services" and writes that as the natural payload shape.
- **No node-id return.** The deterministic key IS the id. The agent never holds a transient node-id between calls.

**T2: `kg_ingest(scanner_kind: str, path: str)`** — scanner output dispatch.

```python
@tool
def kg_ingest(scanner_kind: str, path: str) -> str:
    """Ingest a scanner output file into the engagement graph.

    SUPPORTED scanner_kinds (registry-backed; plugins can add more
    via the decepticon.kg.ingesters entry-point group):
      nmap_xml, nuclei_jsonl, subfinder, httpx_jsonl, dnsx, katana,
      masscan, ffuf, testssl, crackmapexec, asrep_hashes, sarif.

    WHEN TO USE: after running any of the above scanners and saving
    output to a file. The adapter parses the structured output and
    merges nodes + edges in one transaction.

    Returns: JSON {"ingested": N, "scanner": "...", "revision": "..."}.
    """
```

Why this stays as a separate tool from `kg_record`:
- Different mental model (file path vs. inline observations).
- Different cost profile (one file → potentially hundreds of nodes).
- Different failure modes (file-not-found, parse error vs. validation error).

### 9.3 What we explicitly did NOT add

| Considered | Decision | Reason |
|---|---|---|
| `kg_add_node` + `kg_add_edge` as separate tools | ❌ Drop | Forces 3-4 turns per observation; `kg_record` does the same in 1 turn. |
| `kg_query` | ❌ Drop | Agent uses `grep findings/` for recall + summary block in prompt. Cypher details via `bash("cypher-shell ...")` if needed. |
| `kg_neighbors` | ❌ Drop | Same as above. Edge walks are bash + cypher-shell for analyst's rare deep-dive case. |
| `kg_stats` | ❌ Drop | The summary block (wrap_model_call) always shows stats. A tool that returns "current stats" duplicates that. |
| `kg_backend_health` | ❌ Drop | The middleware fails fast at boot if Neo4j is down. No reason for the agent to check. |
| `kg_plan_chains` | ❌ Drop | Pushed into the summary block — middleware computes top-3 chain candidates each turn and shows them. Agent NEVER calls a planner tool; the planner output is part of context. |
| `kg_promote_chain` | ❌ Drop | When the agent decides to act on a chain, it writes a `findings/CHAIN-NNN.md`. The middleware projects that file (Q2 = open question). If Q2 = no, then we add `kg_record` with a `kind="chain"` observation — but no new tool. |

**Tool count: 2.** Down from spec's 8, down from earlier Option B's 3.

### 9.4 What the middleware does (the actual workflow)

```
┌─────────────────────────────────────────────────────────────────┐
│  before_agent(state, runtime)                                   │
│    1. Hydrate engagement from state.engagement_name             │
│    2. Set kg_engagement state field                             │
│    3. Fetch store.revision(engagement=...) → cache              │
│    4. If revision changed since last turn OR first turn:        │
│       compute summary_block via summary.build(store, engagement)│
│       and stash in state.kg_summary                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  wrap_model_call(request, handler)                              │
│    Inject TWO content blocks into system message:               │
│                                                                 │
│    [static cache_control=ephemeral]                             │
│    KG_SYSTEM_PROMPT — "your graph memory is durable. write     │
│    findings to findings/FIND-NNN.md and call kg_record for     │
│    structured asset/vuln observations. the chain candidates    │
│    below are computed each turn from the current graph."       │
│                                                                 │
│    [dynamic]                                                    │
│    KG STATE (engagement=XYZ):                                   │
│    • Top vulns (3): SSTI in /search [CRITICAL] · SQLi … · …     │
│    • Open entrypoints (2): https://app.example.com:443/ · …    │
│    • Chain candidates (top 3): entry→vuln→creds→admin (cost 1.8)│
│    • Crown jewels: domain_admin (1 path), payments_db (0 paths) │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                       (LLM generates tool call)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  wrap_tool_call(request, handler)                               │
│    If tool.name in {"kg_record", "kg_ingest"}:                  │
│      Validate state.kg_engagement is set (refuse otherwise)     │
│      Otherwise: pass through unchanged                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  after_model(state, runtime)                                    │
│    If a kg_record / kg_ingest call ran this step:               │
│      mark state.kg_revision = "dirty"  (forces re-fetch next    │
│      turn → fresh summary block)                                │
└─────────────────────────────────────────────────────────────────┘
```

**Critical:** the summary block IS the read interface. The agent never calls a "read tool" — the graph state is always already in the system prompt, cached when unchanged, fresh when changed.

### 9.5 Summary block — what to include (minimal)

Per memory-systems anti-pattern "stuffing everything into context," the dynamic block has hard limits:

| Section | Max items | Source |
|---|---:|---|
| Top high-severity vulnerabilities | 5 | `MATCH (v:Vulnerability {engagement: $e}) WHERE v.severity IN ['critical','high'] RETURN v ORDER BY v.score DESC LIMIT 5` |
| Unexplored entrypoints | 3 | `MATCH (e:Entrypoint {engagement: $e}) WHERE NOT (e)-[:HAS_VULN]->() RETURN e LIMIT 3` |
| Chain candidates | 3 | `chain.plan_chains(...)` (existing good-pattern code in `chain.py`), top-3 by cost |
| Crown jewels with status | unlimited | One line each. `MATCH (c:CrownJewel {engagement: $e}) OPTIONAL MATCH p=(:Entrypoint)-->...->(c) RETURN c, count(p)` |
| Stats line | 1 | `nodes: N · edges: E · last_updated: ISO` |

Estimated dynamic block: **15-25 lines of markdown**. Compares to the broken backend's per-`kg_stats` call returning the whole node count tree.

### 9.6 PR plan (revised, 4 atomic commits per PR, 3 PRs total)

**PR-A — Foundations (~600 LOC)**

1. `feat(kg): add AttackGraphProtocol contract in runtime/cart` — Protocol + isinstance test
2. `feat(kg): add KGStore with per-op execute_write/read` — `middleware/kg_internal/store.py`. Methods: `revision`, `record_observations`, `ingest_via_adapter`, `find_vulns_by_severity`, `find_open_entrypoints`, `find_crown_jewels`, `count_paths_to`. All require explicit `engagement=` kwarg.
3. `feat(kg): composite range indexes + V002 migration + vector schema placeholder` — `kg_internal/migrations/V002__engagement_composite_indexes.cypher`. Schema for future vector index (Vulnerability.embedding property + vector index) lands now, no embed pipeline.
4. `test(kg): integration test for KGStore against compose Neo4j` — 16-agent parallel-write stress test in this same PR (Q4 = yes).

**PR-B — Middleware + 2 tools (~700 LOC)**

5. `feat(kg): KGState schema + summary block builder` — `kg_internal/summary.py`. Returns a static block + dynamic block (the 5-section table from §9.5).
6. `feat(kg): scanner adapter registry + 12 built-in adapters` — `kg_internal/ingest.py`. Plugin authors register via `decepticon.kg.ingesters` entry-point.
7. `feat(kg): kg_record + kg_ingest tools` — `kg_internal/tools.py`. `build_kg_tools(store)` factory.
8. `feat(kg): KGMiddleware wires state + tools + 4 lifecycle hooks` — `middleware/kg.py`. Mirrors `OPPLANMiddleware` shape.

**PR-C — Agent cutover + prompt rewrite (~400 LOC)**

9. `feat(kg): MiddlewareSlot.KG + SLOTS_PER_ROLE adoption` — `decepticon_core.contracts.slots`. Analyst gets the slot.
10. `refactor(kg): analyst.py drops direct RESEARCH_TOOLS imports` — middleware provides them.
11. `docs(prompts): analyst.md rewrites the KG_DISCIPLINE block` — drops `kg_query`/`kg_neighbors` references. Replaces with "the chain candidates above are computed each turn; call `kg_record` to observe; use `grep findings/` to recall older details; use `bash('cypher-shell ...')` for advanced graph queries."
12. `test(integration): analyst e2e against compose Neo4j` — full workflow: observe host → record → check summary block updates → record chain → verify web-dashboard read works.

**PR-D (post-cutover) — Retire `tools/research/` per the existing spec migration table.** Same as the original spec.

### 9.7 Pending external research

Background agent's findings (`docs/design/2026-06-03-external-docs-research.md`) will inform:

- Final `kg_record` signature shape (does `langchain_core.tools` 2026 prefer `Annotated[list[dict], InjectedState]` for observations, or stringified JSON like opplan?).
- Whether DeepAgents' `MemoryMiddleware` Store-mode could carry the engagement summary cache (or if KGMiddleware owns it).
- BloodHound CE 2026's writer-coordination pattern — informs the 16-agent stress test threshold.

The above is **PR-A's design**, not final implementation. PR-A may need minor adjustments after the external research lands.

### 9.8 Decision asks (need answers before PR-A code starts)

1. **Confirm 2-tool surface (`kg_record` + `kg_ingest`)** — anything missing that the analyst REALLY needs?
2. **Q2 (still open):** auto file→KG projection on `findings/FIND-NNN.md` write? If yes, `kg_record` becomes optional. If no, `kg_record` is the only structured-observation surface.
3. **Q5 vector schema** — confirm shipping `Vulnerability.embedding` property + Neo4j vector index in PR-A's V002 migration (cheap, no embed pipeline yet).
4. **Chain promotion path** — if a chain candidate looks promising, the agent should:
   - (a) write `findings/CHAIN-NNN.md` and let the middleware project it, OR
   - (b) call `kg_record({"kind": "chain", ...})` explicitly.
   Pick one.

---

## 10. External docs findings → §9 design adjustments (final pre-implementation pass)

External research completed (see `docs/design/2026-06-03-external-docs-research.md`, 425 lines). Five findings change § 9 details — the **2-tool surface and the workflow shape do not change**, but specific signatures and the index migration get tightened.

### 10.1 Five external findings → impact on §9

| # | External finding | Impact on §9 |
|---|---|---|
| 1 | `AgentMiddleware` confirms `self.tools`, 6 hooks, **no per-middleware `tools=` parameter**. Tool scoping is `wrap_model_call(request) → request.override(tools=subset)`. | §9.4 workflow unchanged; for analyst's specific case we don't need runtime tool filtering (always-on KG). Subset filter is held in reserve for benchmark mode (force-disable KG). |
| 2 | `from langgraph.prebuilt import InjectedState` (NOT `langchain_core.tools`). Open bugs #31688/#32729 — params must be in `args_schema`, LLM can silently override. LangChain pushing toward `ToolRuntime`. | §9.2 signature updated below. Use `InjectedState` (consistent with `tools/opplan.py`) but pin the engagement field with a defensive cross-check in `wrap_tool_call` so an LLM-override can't escape engagement scope. |
| 3 | `BaseStore` cannot represent edges. | §9 already decided this (KGStore is direct API). Re-confirmed. |
| 4 | APOC dijkstra stays. Composite index: `CREATE INDEX name IF NOT EXISTS FOR (n:Label) ON (n.a, n.b)`. Vector index: `CREATE VECTOR INDEX name IF NOT EXISTS FOR (n:Label) ON (n.embedding) OPTIONS {...}`. | §9.6 PR-A.3 migration content finalized in §10.4 below. |
| 5 | Adopt **Cartography's `update_tag` + `firstseen` + `lastupdated`** + **Graphiti's `created_by` + `source_episode_id`** for provenance. | §9.2 signature gets 3 mandatory provenance fields. `before_agent` gains a stale-node cleanup pass. Big — this is the main §9 update. |

### 10.2 Updated `kg_record` signature (with provenance, minimal)

```python
# kg_internal/tools.py
from typing import Annotated
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

@tool
def kg_record(
    observations: str,                                  # JSON list, see shape below
    *,
    state: Annotated[dict, InjectedState],              # engagement, run_id pulled from here
    tool_call_id: Annotated[str, InjectedToolCallId],   # used as source_episode_id
) -> str:
    """Record one or more graph observations atomically.

    The middleware injects engagement scope and provenance — you only
    pass the observations. All observations in one call land in one
    Neo4j transaction; partial failure rolls back the batch.

    OBSERVATION SHAPE (JSON):
      {
        "kind": "host" | "service" | "vulnerability" | "credential" | ...,
        "label": "10.0.0.1",
        "key": "host::10.0.0.1",        # deterministic dedup
        "props": {"ip": "10.0.0.1", "explored": false, ...},
        "edges_out": [
          {"to_key": "service::10.0.0.1:80", "kind": "HOSTS", "weight": 0.5}
        ]
      }

    AUTO-INJECTED on every node and edge (do NOT set yourself):
      engagement, firstseen, lastupdated, created_by (= agent name from
      state.role), source_episode_id (= this tool_call_id).

    Returns: JSON {"created": N, "merged": M, "edges": E, "revision": "..."}.
    """
```

Why three provenance fields are the minimum:
- **`firstseen` + `lastupdated`** — Cartography's stale-cleanup pattern. Without them, `before_agent` can't prune nodes that no agent has touched in N hours. Without that pruning, the graph grows unbounded (memory-systems anti-pattern §5).
- **`created_by`** — debug answer to "who wrote this node?" One field, one int from `state.role` (e.g. `"analyst"`). Costs nothing, saves hours when finding-provenance disputes happen.
- **`source_episode_id`** — Graphiti pattern. Just the `tool_call_id`. Lets us answer "which agent turn produced this node?" Already free (the runtime gives it).

Skipped (over-engineering per the user's directive):
- `created_at_phase` (OPPLAN phase) — OPPLAN may not be in scope for every engagement.
- bi-temporal `valid_from` / `valid_until` (Graphiti-style) — adds 2 fields and an entire query path that nobody asked for. Defer until temporal-validity actually shows up in a user story.

### 10.3 `kg_ingest` keeps its scanner_kind dispatcher (unchanged from §9), but inherits the same provenance auto-injection

The adapter functions internally call `store.upsert_node(...)` and `store.upsert_edge(...)`; both now take an `update_tag: int` and read `state.role` + `tool_call_id` from the middleware. The adapter doesn't see provenance directly.

### 10.4 Final V002 migration content (PR-A.3)

```cypher
-- V002__engagement_composite_indexes_and_provenance.cypher

-- 4.1 Composite range indexes (research §3, §7; verified Neo4j 5.24 syntax)
CREATE INDEX engagement_host_explored IF NOT EXISTS
  FOR (h:Host) ON (h.engagement, h.explored);
CREATE INDEX engagement_vuln_severity IF NOT EXISTS
  FOR (v:Vulnerability) ON (v.engagement, v.severity);
CREATE INDEX engagement_finding_status IF NOT EXISTS
  FOR (f:Finding) ON (f.engagement, f.status);
CREATE INDEX engagement_entrypoint IF NOT EXISTS
  FOR (e:Entrypoint) ON (e.engagement);
CREATE INDEX engagement_crown_jewel IF NOT EXISTS
  FOR (c:CrownJewel) ON (c.engagement);

-- 4.2 Provenance indexes (Cartography + Graphiti pattern)
CREATE INDEX node_lastupdated IF NOT EXISTS
  FOR (n:Vulnerability) ON (n.engagement, n.lastupdated);
CREATE INDEX node_created_by IF NOT EXISTS
  FOR (n:Vulnerability) ON (n.engagement, n.created_by);

-- 4.3 Future vector index (NO embed pipeline yet — schema-only, opt-in at runtime)
-- This creates the index. The Vulnerability.embedding property is left null
-- until a future KGMiddleware(embed_findings=True) flag turns on the pipeline.
CREATE VECTOR INDEX vuln_embedding IF NOT EXISTS
  FOR (v:Vulnerability) ON (v.embedding)
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  };
```

(Q5 = yes: ship the vector index schema in PR-A. No pipeline cost.)

### 10.5 New `before_agent` responsibility — stale-node cleanup (Cartography pattern)

```
before_agent(state, runtime):
    # ... existing engagement hydration ...

    # NEW: stale-node cleanup. Cheap, scoped, opt-in via KG_STALE_TTL_HOURS env.
    ttl_hours = int(os.environ.get("KG_STALE_TTL_HOURS", "0"))
    if ttl_hours > 0:
        cutoff = int(time.time()) - ttl_hours * 3600
        store.delete_stale(engagement=eng, before_unix=cutoff)
        # Implemented as: MATCH (n {engagement: $eng}) WHERE n.lastupdated < $cutoff DETACH DELETE n
```

Default `KG_STALE_TTL_HOURS=0` → off. Downstream deployments set it; OSS opt-in.

### 10.6 Defense against `InjectedState` override bug

External finding #2: LangChain bugs #31688/#32729 — LLM can sometimes override an `InjectedState` field if the param exists in `args_schema`. Mitigation in `KGMiddleware.wrap_tool_call`:

```python
def wrap_tool_call(self, request, handler):
    if request.tool and request.tool.name in {"kg_record", "kg_ingest"}:
        # Defense in depth: even if InjectedState got overridden by the LLM,
        # the engagement we enforce here is the one from state, not from
        # the tool args. The adapter inside the tool re-pulls engagement
        # via runtime instead of trusting the args dict.
        eng = (request.state or {}).get("kg_engagement")
        if not eng:
            return ToolMessage(
                content=json.dumps({"error": "kg_engagement unset"}),
                tool_call_id=request.tool_call.id, name=request.tool.name,
            )
    return handler(request)
```

The actual store calls receive `engagement=eng` from middleware, never from the LLM-provided args. Layer #2 defense.

### 10.7 Updated PR-A code surface (concrete file list)

```
packages/decepticon/decepticon/middleware/kg_internal/
  __init__.py
  store.py                   # KGStore (per-op execute_write/read, engagement-mandatory)
  migrations/
    V001__initial_schema.cypher           # extracted from Neo4jStore.ensure_schema
    V002__engagement_composite_indexes_and_provenance.cypher
  migration_runner.py        # invokes migrations on first boot

packages/decepticon/decepticon/runtime/cart.py
  # add AttackGraphProtocol(Protocol) — fills the docstring vaporware

packages/decepticon/tests/integration/kg/
  test_kgstore_record.py     # observations round-trip
  test_kgstore_ingest.py     # 12 scanner adapters
  test_kgstore_parallel.py   # 16-agent stress test (Q4)
  test_attack_graph_protocol.py
```

Estimated PR-A: **~600 LOC + ~400 LOC tests**. Smaller than spec's earlier estimate because `kg_record`'s atomic-batch shape means fewer separate code paths.

### 10.8 Updated decision asks (final, pre-PR-A)

1. **2-tool surface (`kg_record` + `kg_ingest`)** confirmed by user 2026-06-03. ✓
2. **Q2 (auto file→KG projection)** — still open. Recommendation: **defer to PR-B**. PR-A only ships the KGStore + index + provenance. PR-B's `KGMiddleware.after_model` can opt-in to file projection via a `project_findings_files=True` flag. Default off in PR-A/B; flip to default-on in PR-C if benchmarks show the analyst forgets to `kg_record` after a file write.
3. **Q5 vector schema** — recommendation **ship now in V002** (zero pipeline cost). ✓ (assumed unless user objects)
4. **Chain promotion path** — recommendation **(a): write `findings/CHAIN-NNN.md`**. Reasons: keeps the chain documented for the operator; if Q2 projection lands later, the chain auto-projects. The graph's `AttackPath` node is computed lazily by `chain.plan_chains` and shown in the summary block — no agent-side tool call needed.
5. **Provenance fields** — `firstseen`, `lastupdated`, `created_by`, `source_episode_id`. Confirm minimal sufficient?
6. **Stale-node TTL** — default off (`KG_STALE_TTL_HOURS=0`). OK?

If items 5 and 6 are confirmed (and 2 deferred / 3 yes / 4 = a), PR-A coding starts: AttackGraphProtocol → KGStore → V001+V002 migrations → integration tests. No tool work in PR-A; that's PR-B.

