# Neo4j Attack-Graph Refactor — Research Notes

> **Scope**: Reference material for the two-part refactor of Decepticon's
> Neo4j-based attack-graph subsystem. Part A narrows `KnowledgeGraph` usage
> to the analyst agent only. Part B replaces `graph_transaction()` with
> per-operation Cypher calls and introduces a KG middleware that owns the
> session lifecycle.
>
> **Neo4j version in use**: 5.24 Community Edition.
> All Cypher syntax and API references are for Neo4j 5.x unless stated otherwise.

---

## 1. Multi-Agent Concurrent Cypher Writes

### Question
What patterns does Neo4j recommend for 16 agents writing concurrently to the
same instance? Session-per-agent, optimistic locking, MERGE serialization,
deadlock retry.

### Findings

Neo4j uses **pessimistic record-level locking** — locks are acquired
automatically when a transaction touches a node or relationship. The lock
types relevant to Decepticon are:

| Lock type | Acquired when |
|-----------|---------------|
| `NODE` | Any label/property write on a node |
| `RELATIONSHIP` | Relationship property update |
| `DEGREES` | Concurrent label changes + relationship modifications |
| `RELATIONSHIP_DELETE` | Exclusive relationship deletion |

Deadlocks are detected eagerly and the losing transaction is terminated with
`Neo.TransientError.Transaction.DeadlockDetected` (GQLSTATUS `50N05`). This
is explicitly documented as a **safe-to-retry** error. Neo4j does not
automatically retry — the driver's managed-transaction API (`execute_write`)
handles retry automatically for any `TransientError`.

**The most common deadlock cause for agents** is MERGE acquiring locks
out-of-order. The official guidance (Operations Manual, "Concurrent data
access") states that MERGE "takes locks out of order" and may prevent Neo4j's
internal sort from avoiding deadlocks. For dense nodes (≥ 50 relationships),
Neo4j uses shared degree locks rather than exclusive locks — relevant to
`Host` nodes in large engagements.

**Recommended patterns for 16 concurrent writers:**

1. **One `Driver` singleton, one `Session` per call** — Sessions are
   lightweight; create and close them per tool invocation. The driver
   manages the connection pool (default `max_connection_pool_size=100`).
   Set this to at least `32` (`16 agents × 2` for write + read sessions
   running simultaneously).

2. **Use `session.execute_write(tx_fn)` exclusively for writes** — the
   driver automatically retries `TransientError`s (including deadlocks)
   within the configured timeout. Never use explicit `begin_transaction()` /
   `commit()` for agent writes; those require manual retry logic.

3. **Lock ordering discipline** — always upsert nodes before edges. Within a
   batch upsert, sort node IDs before sending to MERGE so concurrent
   transactions acquire locks in the same order.

4. **Keep transactions short** — do not load the whole graph then write back.
   The `graph_transaction()` pattern (load → mutate → batch-write-all) is the
   worst possible pattern: it holds the in-memory lock for the entire
   agent turn, serializes everything on `threading.Lock`, and triggers a full
   graph MERGE on every tool call regardless of what actually changed.

5. **`db.lock.acquisition.timeout`** — set to `10s`–`30s` in `neo4j.conf`
   (default is `0`, disabled). Prevents agents from queueing indefinitely
   behind a stuck transaction.

**Sources**:
- [Concurrent data access — Operations Manual](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Locks and deadlocks — Operations Manual](https://neo4j.com/docs/operations-manual/current/database-internals/locks-deadlocks/)
- [DeadlockDetectedException KB](https://neo4j.com/developer/kb/explanation-of-error-deadlockdetectedexception-forseticlient-0-cant-acquire-exclusivelock/)
- [Neo4j Python Driver — Managed Transactions](https://github.com/neo4j/neo4j-python-driver/blob/6.x/docs/source/api.md)

### Recommendation for Decepticon

Remove `threading.Lock` from `graph_transaction()`. Replace every tool's
load–mutate–save cycle with direct `session.execute_write(tx_fn)` calls that
upsert only the new/changed nodes and edges for that operation. The
`Neo4jStore.upsert_node()` and `upsert_edge()` methods already exist and are
correct — the problem is the caller layer that wraps them in
`load_graph()` + full `batch_upsert_*`.

---

## 2. APOC `apoc.algo.dijkstra` vs GDS `gds.shortestPath.dijkstra`

### Question
Compare performance, API stability, license, and when to pick which.

### Findings

**APOC `apoc.algo.dijkstra`** (APOC Core — bundled, no separate install):

```cypher
CALL apoc.algo.dijkstra(startNode, endNode, relTypesAndDirections, weightPropertyName
  [, defaultWeight, numberOfWantedPaths])
YIELD path, weight
```

- Works **directly on the stored graph** — no projection step required.
- Part of APOC Core (not Extended); ships with Neo4j 5.x without a separate
  license.
- Single call, returns `PATH` objects with full node/relationship data.
- No enterprise license required.
- API is stable; no deprecation notice as of Neo4j 5.x APOC docs.
- The `relTypesAndDirections` string (e.g. `"EXPLOITS|ENABLES|LEAKS"`) **must
  be a string literal or interpolated string** — it cannot be a `$param`.
  This is the injection-relevant issue (see Section 11).

**GDS `gds.shortestPath.dijkstra`** (Graph Data Science library):

```cypher
-- Step 1: project graph into memory
MATCH (source)-[r:EXPLOITS|ENABLES]->(target)
RETURN gds.graph.project('attackGraph', source, target,
       { relationshipProperties: r { .cost } })

-- Step 2: run algorithm
CALL gds.shortestPath.dijkstra.stream('attackGraph', {
  sourceNode: $src,
  targetNode: $dst,
  relationshipWeightProperty: 'cost'
})
YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
```

- Requires **in-memory graph projection** before every query, or a named
  persistent projection in the catalog. For a live-updating attack graph this
  means re-projecting frequently, which is expensive.
- GDS Community Edition is free but built from GPL-3.0 source (OpenGDS).
  GDS Enterprise requires a commercial license for features like subgraph
  filtering and concurrent execution.
- `gds.shortestPath.dijkstra` is **single-threaded**; the `concurrency`
  parameter has no effect.
- The in-memory projection decouples the algorithm from live writes — good for
  analytics, bad for a live attack graph where freshness matters.

**Comparison summary:**

| Dimension | `apoc.algo.dijkstra` | `gds.shortestPath.dijkstra` |
|-----------|---------------------|----------------------------|
| Live graph | Yes | Requires projection |
| License | Bundled (APOC Core) | Community free / Enterprise paid |
| API stability | Stable, no deprecation | Stable |
| Performance (small graph) | Fast, direct lookup | Projection overhead dominates |
| Performance (large graph) | O(E log V) heap | Same algorithm, batched |
| Relationship filter | String (injection risk) | Projection-time filter |
| Return type | `PATH` object | Projected node IDs + costs |

**Sources**:
- [apoc.algo.dijkstra — APOC Core Docs](https://neo4j.com/docs/apoc/current/overview/apoc.algo/apoc.algo.dijkstra/)
- [GDS Dijkstra Source-Target — Neo4j GDS Docs](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [GDS Introduction / License](https://neo4j.com/docs/graph-data-science/current/introduction/)

### Recommendation for Decepticon

**Keep `apoc.algo.dijkstra`** for attack-chain planning. The live-graph
requirement (freshness > throughput) and Community Edition constraint make GDS
a poor fit. The injection risk in the `relTypesAndDirections` string is real
but manageable with an allowlist (see Section 11). The Cypher native
`shortestPath()` fallback already in `chain.py` is a correct backstop.

---

## 3. Engagement Multi-Tenancy Strategies

### Question
Single DB with `engagement` label property vs. Neo4j Enterprise
per-engagement databases vs. composite indexes on `(engagement, kind)`.

### Findings

Three patterns in use across the ecosystem:

**A. Shared database, `engagement` property on every node and relationship**
(current Decepticon approach)

- Every node carries `n.engagement = $engagement`; every edge carries
  `r.engagement = $engagement`.
- Query filters: `WHERE n.engagement = $engagement`.
- Works on Community Edition.
- Risk: a query that omits the engagement filter leaks cross-tenant data.
  This is currently documented in `query_custom()` as a known gap ("caller
  owns the Cypher").
- Performance: an index on `engagement` property per label is needed for
  selective scans; without it every query is a full label scan.

**B. Neo4j Enterprise multi-database per engagement**

- Each engagement gets its own Neo4j database (`CREATE DATABASE eng_abc`).
- Hard isolation; no WHERE clause needed.
- Requires Neo4j Enterprise — not available in Community 5.24.
- Operational overhead: database per engagement, connection routing, schema
  migration per-database.

**C. Composite range index on `(engagement, kind)` or `(engagement, severity)`**

- `CREATE RANGE INDEX IF NOT EXISTS FOR (n:Vulnerability) ON (n.engagement, n.severity)`.
- Allows Neo4j to use the index for queries like
  `MATCH (v:Vulnerability) WHERE v.engagement = $e AND v.severity = $s`.
- Composite indexes in Neo4j 5.x require **all indexed properties to appear
  in the WHERE clause** for the planner to select the composite index.
- Significant selectivity improvement when many engagements share a label.

**Sources**:
- [Neo4j Multi-tenancy Community discussion](https://community.neo4j.com/t/multi-tenancy-on-neo4j/10627)
- [GraphAware Neo4j 4 Multi-tenancy](https://graphaware.com/blog/multi-tenancy-neo4j/)
- [Cypher Manual — Index Syntax](https://neo4j.com/docs/cypher-manual/current/indexes/syntax/)

### Recommendation for Decepticon

Stay on option A (single DB + engagement property) for Community Edition.
Add composite range indexes for the highest-traffic filter combinations:

```cypher
CREATE RANGE INDEX IF NOT EXISTS FOR (n:Host)          ON (n.engagement, n.explored);
CREATE RANGE INDEX IF NOT EXISTS FOR (n:Vulnerability) ON (n.engagement, n.severity);
CREATE RANGE INDEX IF NOT EXISTS FOR (n:Finding)       ON (n.engagement, n.status);
```

These three cover the most common agent read patterns. Audit `query_custom()`
callers to enforce that the engagement filter is always passed — this is the
critical correctness gap.

---

## 4. Vector Index Integration (Neo4j 5.13+)

### Question
Can Neo4j's native vector index replace a separate Chroma/pgvector store for
embedding-based skill search? Limits, ANN algorithm, hybrid search.

### Findings

Neo4j ships native vector indexes backed by **Apache Lucene's HNSW
(Hierarchical Navigable Small World)** implementation since version 5.11.
Key facts for Neo4j 5.24:

**Creation syntax:**

```cypher
CREATE VECTOR INDEX skill_embeddings IF NOT EXISTS
FOR (s:Skill)
ON s.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}
```

**Supported dimensions**: 1–4096 (the `vector-2.0` provider, available since
5.18). Older `vector-1.0` was limited to 1–2048.

**Similarity functions**: `cosine` (recommended for text embeddings) and
`euclidean`. For unit-normalized vectors both produce the same ranking order.

**Query (Neo4j 5.x procedure syntax)**:

```cypher
CALL db.index.vector.queryNodes('skill_embeddings', 10, $queryVector)
YIELD node AS skill, score
WHERE score > 0.75
MATCH (skill)-[:APPLIES_TO]->(domain:Domain {name: $domain})
RETURN skill.name, skill.path, score
ORDER BY score DESC
```

**HNSW tuning parameters** (set at index creation):
- `vector.hnsw.m` (default 16): higher → better recall, slower build.
- `vector.hnsw.ef_construction` (default 100): higher → better index quality.
- `vector.quantization.enabled` (default true): reduces memory, minor accuracy
  loss.

**Hybrid search**: As of Neo4j 2026.01 (preview), vector search with
in-index predicate filters is available. For 5.24, hybrid search is done
post-retrieval: query the vector index for top-K candidates, then filter with
a MATCH clause. This means requesting more candidates than needed to account
for post-filter attrition.

**Limitation for Skillogy**: The vector index is **ANN (approximate)**. The
HNSW guarantee is "close within the same wider neighborhood" — not exact top-K.
For skill retrieval where recall of the right skill matters more than
sub-millisecond latency, this is acceptable.

**Sources**:
- [Vector indexes — Cypher Manual](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Neo4j Native Vector Data Type blog](https://neo4j.com/blog/developer/introducing-neo4j-native-vector-data-type/)
- [Vector search with filters (2026.01 preview)](https://medium.com/neo4j/vector-search-with-filters-in-neo4j-v2026-01-preview-1559829b099d)

### Recommendation for Decepticon

The Neo4j vector index is viable for Skillogy Phase 1b (embedding-based skill
search) if skills are stored as `Skill` nodes in the attack graph. This
collapses the separate Chroma dependency into the existing Neo4j instance.
For 5.24, use the post-retrieval filter pattern with `top_k * 3` candidates
to compensate for post-filter attrition. Defer adoption of the `SEARCH` clause
syntax until Neo4j 2026.x GA.

---

## 5. Bulk Ingest Patterns

### Question
`apoc.periodic.iterate` vs `UNWIND $rows MERGE` batch. Transaction size
guidance. When does `:auto USING PERIODIC COMMIT` still apply?

### Findings

**`UNWIND $rows AS row MERGE ...` (current `Neo4jStore.batch_upsert_nodes`)**

This is the **preferred pattern for agent-driven ingestion** in Neo4j 5.x.
The entire UNWIND list runs in a single transaction. Practical batch size
guidance from APOC docs and community posts:

- **500–2000 rows per transaction** for complex MERGE with SET (multiple
  properties).
- **5000–10000 rows** for simple CREATE-only or property-set-only batches.
- Current `batch_upsert_nodes` sends all nodes of the same label in one
  transaction — fine for agent writes (typically 5–50 nodes per call), but
  needs a size cap for bulk import scenarios.

**`apoc.periodic.iterate`**

Wraps an outer "data source" query and an inner "action" query, committing
every `batchSize` rows (default 10,000). Useful for:
- Refactoring existing large graphs (relabeling, property migration).
- Importing large CSV/JSON files outside the driver.
- Background tasks where the caller does not want to block.

Not well-suited for agent writes: adds procedure overhead, harder to compose
with error handling, and as of Neo4j 2026.04 / Cypher 25 it is **deprecated**
in favour of native `CALL { ... } IN CONCURRENT TRANSACTIONS`.

**`CALL { ... } IN TRANSACTIONS OF N ROWS`** (Neo4j 4.4+ / 5.x native):

```cypher
UNWIND $rows AS row
CALL (row) {
  MERGE (n:Host {id: row.id})
  SET n += row.props
} IN TRANSACTIONS OF 500 ROWS
```

Available without APOC. Preferred for large one-shot loads. Note: cannot be
used inside an explicit transaction (auto-commit only).

**`:auto USING PERIODIC COMMIT`**: Fully removed in Neo4j 5.0. Do not use.

**Sources**:
- [APOC Core — Periodic Execution](https://neo4j.com/docs/apoc/current/graph-updates/periodic-execution/)
- [Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/clauses/clause-composition)
- [5 Tips for Fast Batched Updates (Michael Hunger)](https://medium.com/neo4j/5-tips-tricks-for-fast-batched-updates-of-graph-structures-with-neo4j-and-cypher-73c7f693c8cc)

### Recommendation for Decepticon

Keep `UNWIND $rows MERGE` in `batch_upsert_nodes` / `batch_upsert_edges` as
the primary write path. Add a `_BATCH_CHUNK = 500` constant and chunk the list
before sending to protect against very large agent writes. Remove any reference
to `apoc.periodic.iterate` from operational code (keep only in schema migration
scripts if needed). Do not use `USING PERIODIC COMMIT`.

---

## 6. Schema Evolution Without Downtime

### Question
Adding new node labels / relationship types. Constraint additions to existing
data. APOC schema migration helpers.

### Findings

Neo4j Community 5.x schema changes that are **online (no downtime)**:

- `CREATE INDEX IF NOT EXISTS` / `DROP INDEX` — online, runs in background.
- `CREATE CONSTRAINT IF NOT EXISTS` — online, but the constraint population
  phase locks the affected label until the population scan completes. For large
  existing datasets this can be slow; for Decepticon's engagement-scale graphs
  (<10K nodes) it is effectively instant.
- Adding new node labels via MERGE/SET — always additive, no migration needed.
- Adding new relationship types — additive, no migration needed.
- Renaming a label or property — requires a data migration query; no built-in
  rename DDL.

**`neo4j-migrations`** (Michael Simons / Neo4j Labs) is the closest equivalent
to Flyway for Neo4j:

- File naming: `V<version>__<description>.cypher` (e.g.
  `V002__Add_engagement_composite_indexes.cypher`).
- Multiple Cypher statements per file, separated by `;` + newline.
- Versioned (immutable once applied) and repeatable (`R__` prefix) migrations.
- Idempotent by design (`IF NOT EXISTS` in DDL statements).
- CLI invocation: `neo4j-migrations -uneo4j -psecret migrate`.
- Python integration: invoke the CLI as a subprocess at container startup;
  no native Python library.
- Tracks applied migrations in a `__Neo4jMigration` node in the database.

**APOC schema migration helpers** are limited: there is no APOC analog to
`neo4j-migrations`. APOC Extended provides `apoc.schema.assert` which can
enforce a schema state (create missing constraints/indexes, drop extra ones)
but it is in APOC Extended (community-only support), not APOC Core.

**Sources**:
- [neo4j-migrations — Neo4j Labs](https://neo4j.com/labs/neo4j-migrations/)
- [neo4j-migrations docs](https://michael-simons.github.io/neo4j-migrations/4.0.1/)
- [APOC Migration Guide](https://neo4j.com/docs/apoc/current/migration-guide/)

### Recommendation for Decepticon

Adopt `neo4j-migrations` as the schema migration tool. The current
`Neo4jStore.ensure_schema()` method works for fresh databases but provides
no migration history and no ordering guarantees when constraints change. Move
the `ensure_schema()` DDL into `V001__initial_schema.cypher`, then add
subsequent migration files for each schema change. Run the CLI at LangGraph
container startup before the server accepts connections.

---

## 7. Indexing Strategy

### Question
Range vs btree vs text vs vector indexes. Composite index syntax (5.x).
When to use full-text indexes. What indexes does an engagement-scoped attack
graph need?

### Findings

**Index types in Neo4j 5.x** (BTREE is gone — removed in 5.0):

| Type | Syntax keyword | Best for |
|------|---------------|----------|
| Range | `RANGE INDEX` (default) | Equality, range, prefix on most scalar types |
| Text | `TEXT INDEX` | `CONTAINS` and `ENDS WITH` string searches; single property only |
| Full-text | `FULLTEXT INDEX` | Free-text search across multiple properties/labels |
| Vector | `VECTOR INDEX` | ANN similarity on embedding arrays |
| Token lookup | (built-in) | Label/type scans — exists by default, do not drop |

**Composite range index syntax (5.x)**:

```cypher
CREATE RANGE INDEX host_engagement_explored IF NOT EXISTS
FOR (h:Host)
ON (h.engagement, h.explored);
```

Composite indexes require **all indexed properties to appear as equality
predicates** in the WHERE clause for the planner to select the index. A query
with only `h.engagement = $e` will not use a composite index on
`(h.engagement, h.explored)` unless `h.explored` is also constrained.

**Full-text index syntax (5.x)**:

```cypher
CREATE FULLTEXT INDEX node_label_text IF NOT EXISTS
FOR (n:Host|Domain|Service|URL)
ON EACH [n.label, n.fqdn, n.ip, n.product];
```

Queried via `CALL db.index.fulltext.queryNodes('node_label_text', $q)`.
Useful for the analyst agent's "find node by description" operations.

**Recommended index set for the Decepticon attack graph**:

```cypher
-- Uniqueness constraints (already in ensure_schema(), keep as-is)
-- Performance indexes:

-- Engagement-scoped read paths
CREATE RANGE INDEX host_eng_explored    IF NOT EXISTS FOR (h:Host)          ON (h.engagement, h.explored);
CREATE RANGE INDEX host_eng_compromised IF NOT EXISTS FOR (h:Host)          ON (h.engagement, h.compromised);
CREATE RANGE INDEX vuln_eng_severity    IF NOT EXISTS FOR (v:Vulnerability)  ON (v.engagement, v.severity);
CREATE RANGE INDEX vuln_eng_validated   IF NOT EXISTS FOR (v:Vulnerability)  ON (v.engagement, v.validated);
CREATE RANGE INDEX finding_eng_status   IF NOT EXISTS FOR (f:Finding)        ON (f.engagement, f.status);
CREATE RANGE INDEX cand_eng_status      IF NOT EXISTS FOR (c:Candidate)      ON (c.engagement, c.status);

-- Path planner node lookups (shortestPath anchor nodes)
-- Uniqueness constraints on id already cover MATCH (n {id: $id}) lookups.

-- Full-text for analyst "find node" search
CREATE FULLTEXT INDEX attack_node_text IF NOT EXISTS
FOR (n:Host|Domain|Service|URL|Vulnerability|Finding|User|Credential)
ON EACH [n.label, n.ip, n.fqdn, n.url, n.product, n.cve_id];
```

**Sources**:
- [Cypher Manual — Index Syntax](https://neo4j.com/docs/cypher-manual/current/indexes/syntax/)
- [Full-text indexes — Cypher Manual](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/)
- [Index configuration — Operations Manual](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)

### Recommendation for Decepticon

Add the engagement-scoped composite indexes to `V002__engagement_indexes.cypher`
and update `ensure_schema()` to include the full-text index. The existing
single-property indexes on `explored`, `compromised`, `severity` etc. remain
useful for queries that filter by those properties without an engagement scope
(admin tools, `all_engagements=True` paths).

---

## 8. Driver Session Lifecycle

### Question
Per-call vs long-lived sessions. Connection pool sizing for 16 concurrent
agents. `execute_write` / `execute_read` vs explicit transactions.

### Findings

From the Neo4j Python Driver 6.x documentation:

**Sessions are not thread-safe**. Each concurrent agent needs its own
session. Sessions are cheap to create — creating one per tool call is the
correct pattern.

**One driver singleton per process** — the driver manages the connection pool.
`GraphDatabase.driver(...)` is expensive; `driver.session()` is not.

**Connection pool sizing**:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    uri,
    auth=(user, password),
    max_connection_pool_size=50,   # 16 agents × ~3 concurrent sessions
    connection_acquisition_timeout=30.0,
    liveness_check_timeout=30,
)
```

The pool default is 100. For 16 agents each making sequential tool calls,
`32`–`50` is sufficient. Set `liveness_check_timeout` to prevent stale
connections behind a load balancer.

**`execute_write` vs explicit transactions**:

| API | Auto-retry | Use when |
|-----|-----------|---------|
| `session.execute_write(tx_fn)` | Yes (TransientError) | All agent writes |
| `session.execute_read(tx_fn)` | Yes | All agent reads |
| `session.run()` (auto-commit) | No | Fire-and-forget, schema DDL |
| `session.begin_transaction()` | No | Manual multi-step transactions |

The transaction function (`tx_fn`) receives a `ManagedTransaction`. All
result records must be consumed inside the function — do not return a live
`Result` object.

**Read routing**: For a single Community instance there is no routing.
Using `default_access_mode=neo4j.READ_ACCESS` on read sessions is still good
practice — it signals intent and will work correctly if the instance is ever
upgraded to a cluster.

**Sources**:
- [Neo4j Python Driver — API (6.x)](https://github.com/neo4j/neo4j-python-driver/blob/6.x/docs/source/api.md)
- [Performance recommendations — Python Driver Manual](https://neo4j.com/docs/python-manual/current/performance/)
- [Neo4j Driver Best Practices](https://neo4j.com/blog/developer/neo4j-driver-best-practices/)

### Recommendation for Decepticon

`Neo4jStore.__init__` already creates the driver correctly (one per store
instance). The store is a singleton managed by `_state.py`. The problem is
that individual `upsert_node` / `upsert_edge` calls use `session.run()` (auto-
commit, no retry). Replace every `session.run()` write with
`session.execute_write(lambda tx: tx.run(query, params))`. Read methods
(`load_graph`, `query_by_kind`, `query_neighbors`, `query_custom`) should use
`session.execute_read()` or stay as auto-commit if they are truly fire-and-
forget analytics.

---

## 9. Read-Only Query Optimization

### Question
`default_access_mode=READ`, routing reads to followers, query plan cache,
EXPLAIN/PROFILE workflow.

### Findings

**Access mode**: Set `default_access_mode=neo4j.READ_ACCESS` when creating a
session for read-only operations. This prevents accidental writes and, in a
causal cluster, routes the query to a replica rather than the primary leader.
For Community Edition single-instance there is no routing benefit, but the
pattern is forward-compatible.

**Query plan cache**: Neo4j caches Cypher execution plans keyed on the query
string. Parameterized queries reuse the cached plan; string-interpolated
queries (e.g. embedding a literal value into the Cypher string) each produce a
cache miss and force a replan. The `plan_chains()` function in `chain.py`
currently string-interpolates `max_depth` and `top_k` into the query
string — these should be parameters.

**EXPLAIN / PROFILE workflow**:

```cypher
EXPLAIN
MATCH (h:Host)
WHERE h.engagement = $engagement AND h.explored = false
RETURN h.id, h.ip;
```

`EXPLAIN` returns the plan without executing. Look for `NodeByLabelScan` with
a filter — this means the index is not being used. `PROFILE` executes the
query and returns actual db hits per operator. For engagement-scoped queries,
the plan should show `NodeIndexSeek` using the composite index.

**Sources**:
- [Performance recommendations — Python Driver Manual](https://neo4j.com/docs/python-manual/current/performance/)
- [Bolt thread pool — Operations Manual](https://neo4j.com/docs/operations-manual/current/performance/bolt-thread-pool-configuration/)

### Recommendation for Decepticon

1. Parameterize `max_depth`, `top_k`, and `max_cost` in `plan_chains()` —
   they are currently f-string interpolated, causing a plan cache miss on
   every call.
2. Add `default_access_mode=neo4j.READ_ACCESS` to the session used by
   `query_custom()` for read-only callers (pass a flag or create a
   `query_custom_read()` variant).
3. After adding composite indexes, run `PROFILE` on the most frequent agent
   query patterns to confirm `NodeIndexSeek` is selected.

---

## 10. Cypher Injection Defense

### Question
Parameter binding, dynamic label/type interpolation, sanitization patterns,
when string interpolation is unavoidable.

### Findings

From the Neo4j knowledge base on Cypher injection:

**Parameter binding is the primary defense**. Parameters are compiled into
the query plan before execution — they cannot modify query structure.

```cypher
-- Safe
MATCH (n:Host {engagement: $engagement}) WHERE n.ip = $ip RETURN n

-- Unsafe (do not do this)
MATCH (n:Host) WHERE n.ip = '{user_supplied_ip}' RETURN n
```

**The injection vector that cannot be parameterized in Cypher < 5.26**:
Node labels and relationship types cannot be `$params`. This is the core
vulnerability in `query_by_kind()` (which uses an allowlist — correct) and
`upsert_node()` / `batch_upsert_nodes()` (which interpolate
`NodeKind.value` — safe because `NodeKind` is a closed `StrEnum`).

**Cypher 5.26 dynamic labels** (`$()` syntax):

```cypher
-- Available in Cypher 5.26+
MATCH (n:$(labelParam)) WHERE n.engagement = $e RETURN n
```

The planner falls back to `AllNodesScan` + filter when dynamic labels are
used — no index is used. Avoid for high-frequency queries; acceptable for
admin/tooling.

**The `_ATTACK_REL_TYPES` string in `chain.py`** (currently built at module
load from `EdgeKind` values) is **safe because it is constructed from a closed
enum, not from user input**. Document this clearly to prevent future
contributors from opening a vector by making the relationship filter
caller-supplied.

**Backtick escaping** (for unavoidable dynamic identifier use): escape backtick
characters as double-backtick ` `` ` and also sanitize ``` (the Unicode
backtick). The preferred refactoring is to avoid dynamic labels entirely by
using a property (`kind = $kind`) instead.

**Sources**:
- [Protecting against Cypher Injection — Neo4j KB](https://neo4j.com/developer/kb/protecting-against-cypher-injection/)
- [Cypher Dynamism blog](https://neo4j.com/blog/developer/cypher-dynamism/)

### Recommendation for Decepticon

Current code is **largely safe** because dynamic label interpolation uses only
`NodeKind`/`EdgeKind` enum values (closed sets validated at construction).
Three actions needed:

1. Add a module-level comment on `_ATTACK_REL_TYPES` in `chain.py` explaining
   why string interpolation is safe (closed enum, not user input).
2. The `query_custom()` method takes arbitrary Cypher from callers — ensure
   callers pass agent-constructed Cypher only, never user-supplied strings.
3. If Decepticon ever supports user-defined custom relationship types (plugin
   edge kinds), add an allowlist validation gate before any interpolation.

---

## 11. `apoc.path.expandConfig` Patterns

### Question
Configurable path expansion vs `apoc.algo.dijkstra`. Attack relationship
filter macro. When each is appropriate.

### Findings

**`apoc.path.expandConfig`** — APOC Core:

```cypher
CALL apoc.path.expandConfig(startNode, {
  relationshipFilter: 'EXPLOITS>|ENABLES>|LEAKS>|PIVOTS_TO>',
  labelFilter:        '+Host|+Service|-DetectionFired',
  minLevel:           1,
  maxLevel:           6,
  uniqueness:         'NODE_GLOBAL',
  bfs:                true,
  limit:              50
})
YIELD path
```

Configuration map fields:

| Field | Description |
|-------|-------------|
| `relationshipFilter` | `TYPE>` (out), `<TYPE` (in), `TYPE` (both); pipe-separated |
| `labelFilter` | `+REQUIRED`, `-EXCLUDED`, `/TERMINATOR`, `>END_NODE` |
| `minLevel` / `maxLevel` | Hop bounds |
| `uniqueness` | `NODE_GLOBAL` (visit each node once), `RELATIONSHIP_PATH`, etc. |
| `bfs` | `true` = breadth-first, `false` = depth-first |
| `limit` | Maximum number of paths returned |
| `endNodes` / `terminatorNodes` | Node-based expansion control |

**Comparison with `apoc.algo.dijkstra`**:

| Dimension | `apoc.path.expandConfig` | `apoc.algo.dijkstra` |
|-----------|--------------------------|---------------------|
| Goal | Reachability / exploration | Weighted shortest path |
| Output | All paths up to maxLevel | Single/N cheapest paths |
| Weight handling | None (BFS/DFS only) | `weightPropertyName` on edge |
| Use in Decepticon | `impact_analysis()` | `plan_chains()` |
| Relationship filter | Same string format | Same string format |

**The `_ATTACK_REL_TYPES` injection surface**: both procedures receive
`relTypesAndDirections` as a **Cypher string**, not a list parameter. This
string cannot be a `$param` in APOC's current API. Decepticon's approach of
building this string from a closed `EdgeKind` enum at module load time is the
correct mitigation. If attack relationship types ever become runtime-
configurable (e.g. engagement-specific custom edge kinds from a plugin), an
allowlist gate must be added before the string is constructed.

**Sources**:
- [apoc.path.expandConfig — APOC Core Docs](https://neo4j.com/docs/apoc/current/overview/apoc.path/apoc.path.expandConfig/)
- [apoc.algo.dijkstra — APOC Core Docs](https://neo4j.com/docs/apoc/current/overview/apoc.algo/apoc.algo.dijkstra/)

### Recommendation for Decepticon

The split in `chain.py` is correct: `apoc.algo.dijkstra` for
cost-minimization (chain planning), `apoc.path.expandConfig` for reachability
(impact analysis). Freeze `_ATTACK_REL_TYPES` as a module constant derived
from `EdgeKind`; add a test asserting that the constant contains only valid
`EdgeKind` values so plugin authors cannot accidentally inject custom types
into it.

---

## 12. Subqueries: `CALL { }` and `CALL ... IN TRANSACTIONS`

### Question
Atomic multi-step writes. Use for "add node + add edge + verify" as a single
unit. Neo4j 4.4+ / 5.x syntax.

### Findings

**`CALL { ... }` (correlated subquery, Neo4j 4.1+)**:

Executes a subquery for each incoming row. Writes inside the subquery are
visible to subsequent clauses in the same transaction:

```cypher
MATCH (entry:Entrypoint {id: $entry_id})
CALL (entry) {
  MERGE (ap:AttackPath {id: $ap_id})
  SET ap.label = $label, ap.created_at = $now
  MERGE (ap)-[:STARTS_AT]->(entry)
  RETURN ap
}
MATCH (crown:CrownJewel {id: $crown_id})
MERGE (ap)-[:REACHES]->(crown)
RETURN ap.id
```

This is the correct pattern for `promote_chain()` in `chain.py`, which
currently issues separate `query_custom()` calls for the `AttackPath` node,
the `STARTS_AT` edge, the `REACHES` edge, and each `STEP` edge. These
separate calls are not atomic — a crash between calls can leave partial
`AttackPath` nodes.

**`CALL { ... } IN TRANSACTIONS OF N ROWS` (Neo4j 4.4+)**:

Auto-commits every N rows; cannot be used inside a driver-managed transaction.
Use for bulk import/refactor, not for agent writes.

**`CALL { ... } IN CONCURRENT TRANSACTIONS` (Cypher 25 / Neo4j 2026.04)**:

Parallel execution of batches. Not available in Neo4j 5.24.

**Sources**:
- [Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/clauses/clause-composition)
- [Cypher Manual — DELETE with CALL](https://neo4j.com/docs/cypher-manual/current/clauses/delete)

### Recommendation for Decepticon

Rewrite `promote_chain()` to use a single `CALL { }` subquery that creates
the `AttackPath` node and all its edges atomically. This eliminates the
partial-write risk and reduces round trips from `1 + N_steps` to `1`. The
pattern:

```cypher
MERGE (ap:AttackPath {id: $ap_id})
SET ap.key = $key, ap.label = $label, ap.total_cost = $total_cost,
    ap.length = $length, ap.validated = false,
    ap.created_at = coalesce(ap.created_at, $now), ap.updated_at = $now
WITH ap
MATCH (entry {id: $entry_id})
MERGE (ap)-[:STARTS_AT]->(entry)
WITH ap
MATCH (crown {id: $crown_id})
MERGE (ap)-[:REACHES]->(crown)
WITH ap
UNWIND $steps AS step
MATCH (n {id: step.node_id})
MERGE (ap)-[s:STEP {order: step.order}]->(n)
```

Passed as a single `session.execute_write()` call with all parameters.

---

## 13. Reference Implementations

### Question
How do BloodHound CE, Cartography, and BRON handle the same problems?
Is Memgraph or Kuzu a viable alternative?

### Findings

#### BloodHound Community Edition (SpecterOps)

BloodHound CE uses a **dual-database architecture**: PostgreSQL for the
application state (users, config, jobs) and Neo4j for the AD/Azure attack
graph. Its schema migration story is split accordingly:

- **PostgreSQL** migrations use versioned stepwise SQL files stored in
  `cmd/api/src/database/migration/migrations/`, named by semver
  (e.g. `v5.6.0.sql`). They replaced Gorm auto-migrations with explicit
  idempotent SQL. Constraint changes are only made via stepwise migrations,
  not via Gorm model changes.
- **Neo4j** is migrated automatically at startup ("log lines showing that
  Neo4J is migrating the database for you"). The specifics are in the Go API
  server startup path rather than a separate migration tool.
- Multi-writer handling: BloodHound's ingest pipeline (SharpHound /
  AzureHound) sends bulk batches via the REST API; the Go backend serializes
  writes into Neo4j using MERGE batches. There is no documented concurrent
  multi-agent write pattern — BloodHound's ingest is single-pipeline, not
  multi-agent.

**Takeaway for Decepticon**: The PostgreSQL-for-state + Neo4j-for-graph split
is a proven architecture. BloodHound's versioned-file migration approach for
PostgreSQL is directly relevant to the `ensure_schema()` problem.

**Sources**:
- [BloodHound CE GitHub](https://github.com/SpecterOps/BloodHound)
- [Application Database Migrations — BH Wiki](https://github.com/SpecterOps/BloodHound/wiki/Application-Database-Migrations)

#### Cartography (Lyft / CNCF)

Cartography ingests cloud infrastructure assets (AWS, GCP, Azure, Kubernetes,
Okta, and 30+ others) into Neo4j using a **staged sequential sync** model:

- A single `neo4j_session` is passed through all stages of a sync run.
- Each stage uses MERGE-based upserts — nodes are created or updated
  idempotently.
- Stale-data cleanup uses an **`update_tag` timestamp pattern**: every sync
  run stamps ingested nodes with the current timestamp, then a cleanup pass
  DELETEs nodes whose `update_tag` is older than the current run. This is
  Cartography's answer to "how do we know what the scanner found vs. what is
  stale."
- No multi-writer concurrency — Cartography is a single-process scanner that
  runs sequentially.

**The `update_tag` pattern** is directly applicable to Decepticon's
`updated_at` field: after an agent completes an engagement objective, a sweep
could prune nodes that were not touched in the last N minutes (or N turns).

**Sources**:
- [Cartography GitHub (cartography-cncf)](https://github.com/cartography-cncf/cartography)
- [cartography/sync.py](https://github.com/cartography-cncf/cartography/blob/master/cartography/sync.py)

#### BRON (Threat Intelligence Knowledge Graph)

BRON (from the 2020 paper "Linking Threat Tactics, Techniques, and Patterns
with Defensive Weaknesses, Vulnerabilities and Affected Platform Configurations
for Cyber Hunting") links ATT&CK → CAPEC → CWE → CVE → CPE in a Neo4j graph.

Node types: `Tactic`, `Technique`, `AttackPattern` (CAPEC), `Weakness` (CWE),
`Vulnerability` (CVE), `AffectedConfiguration` (CPE).

Relationship types: `USES_TECHNIQUE`, `RELATED_TO`, `EXPLOITS_WEAKNESS`,
`HAS_WEAKNESS`, `HAS_VULNERABILITY`.

BRON is a **static import** — it does not handle concurrent writes or live
updates. Its value to Decepticon is the **schema pattern**: ATT&CK Techniques
mapping to CVEs via Weaknesses is exactly the `Technique → CVE → Vulnerability`
chain Decepticon's `decepticon_core/types/kg.py` models. BRON validates that
this is the correct graph topology for offensive intelligence.

**Sources**:
- [BRON paper (arXiv:2010.00533)](https://arxiv.org/abs/2010.00533)
- [Cybersecurity Threat Hunting with Neo4j (arXiv:2301.12013)](https://arxiv.org/abs/2301.12013)

#### Memgraph and Kuzu as Neo4j Alternatives

**Memgraph**:
- In-memory graph database (RAM-resident with WAL + snapshots).
- Full Cypher + Bolt protocol compatibility — drop-in driver replacement.
- 8–114× faster than Neo4j on read-heavy workloads in Memgraph's own
  benchmarks (note: vendor benchmarks; treat as directional).
- No built-in sharding; single-node only.
- For Decepticon's engagement-scale graphs (<10K nodes), the in-memory model
  fits entirely in RAM — this is a genuine advantage.
- The operational model is different (no page cache, pure RAM), which changes
  memory sizing requirements.

**Kuzu**:
- Embedded (in-process) graph database; designed for AI agent memory graphs.
- Archived in October 2025; a fork (`Vela-Engineering/kuzu`) adds concurrent
  write support for multi-agent use.
- 374× faster than Neo4j on 2nd-degree path queries in one benchmark (on
  100K node / 2.4M edge graphs).
- No Bolt protocol; requires a different driver.

**Verdict for Decepticon**:
- Switching to Memgraph would be low-friction (Cypher + Bolt compatible) but
  introduces operational risk for a Community-licensed production system.
- Kuzu's archival status makes it unsuitable as a dependency.
- The performance gap at engagement scale (<10K nodes, <50K edges) is not the
  bottleneck — the `graph_transaction()` serialization is. Fix the pattern
  first; reconsider the database only if profiling reveals Neo4j as the
  bottleneck after the refactor.

**Sources**:
- [Memgraph vs Neo4j — Memgraph blog](https://memgraph.com/blog/neo4j-vs-memgraph)
- [KuzuDB AI Agent Memory (Vela Partners)](https://vela.partners/blog/kuzudb-ai-agent-memory-graph-database)
- [Neo4j Alternatives in 2026 — ArcadeDB](https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/)

---

## Synthesis: Top 7 Highest-Impact Changes

Ranked by expected impact on correctness, concurrency, and maintainability:

### 1. Replace `graph_transaction()` with per-operation `execute_write` calls (Critical)

The load–mutate–save-all cycle is the root cause of O(graph_size) writes,
broken `updated_at` timestamps, and inability to scale past one agent writing
at a time. Every KG tool call should call `store.upsert_node()` /
`store.upsert_edge()` directly, wrapped in `session.execute_write()` for
automatic deadlock retry. The `Neo4jStore` already has the right individual
upsert methods.

### 2. Remove `threading.Lock` from `graph_transaction()` (Critical)

The Python-side global lock is the serialization bottleneck that prevents
16 agents from writing concurrently. Removing it unblocks parallel agent
operation. Neo4j's own MVCC + record locking handles concurrent MERGE safely;
the Python lock adds overhead without safety benefit.

### 3. Add engagement-scoped composite indexes (High)

Add `(engagement, explored)`, `(engagement, severity)`, and
`(engagement, status)` composite range indexes for the three most
frequently filtered node types (`Host`, `Vulnerability`, `Finding`). Without
these, every engagement-scoped query does a full label scan filtered
post-index — O(all nodes of that label) instead of O(results).

### 4. Enforce engagement scoping in `query_custom()` (High)

`query_custom()` is explicitly documented as "NOT engagement-scoped: the
caller owns the Cypher." This is a multi-tenant data-leak risk for any
multi-tenant deployment. Audit all callers and add engagement parameter injection, or
create `query_custom_read(cypher, params, *, scoped=True)` that automatically
appends the engagement filter.

### 5. Rewrite `promote_chain()` as a single atomic subquery (Medium)

The current implementation issues `1 + N_steps` separate `query_custom()`
calls, none inside a transaction. A partial failure leaves orphaned
`AttackPath` nodes. Rewrite as a single `UNWIND`-based query inside
`session.execute_write()` to make chain promotion atomic.

### 6. Adopt `neo4j-migrations` for schema evolution (Medium)

Move `ensure_schema()` DDL into versioned Cypher migration files. This gives
auditability, ordering, and idempotency for schema changes across environments
(local dev, CI, production). Run the migration CLI at LangGraph container
startup via a Docker entrypoint script.

### 7. Parameterize interpolated values in `plan_chains()` (Low-Medium)

`max_depth`, `top_k`, and `max_cost` are currently f-string interpolated
into the `plan_chains()` Cypher queries. Each distinct value combination
produces a separate query plan in the cache. Converting them to `$params`
allows the server to reuse one cached plan regardless of the values passed,
reducing planner overhead on repeated chain computations.

---

*Compiled 2026-06-03. Neo4j 5.24 Community Edition. All cited URLs were
fetched at research time; check for version-specific updates before
implementing against a different Neo4j minor version.*
