# 0010. Skillogy find_skill uses LightRAG-style hybrid retrieval over the existing graph

- **Status:** Proposed
- **Date:** 2026-06-15
- **Deciders:** @PurpleCHOIms
- **Related:** ADR-0008 (skillogy hard ACL), `docs/design/skillogy-brain-redesign.md`, `docs/design/2026-06-12-skillogy-load-skill-by-name-pollution.md` (#670 load_skill exact-match), `packages/decepticon/decepticon/skillogy/server/neo4j_backend.py::find_skill`, `packages/decepticon/decepticon/skillogy/builder/` (ingest)

## Context

`find_skill` is the agent's entry point into the skill corpus (285 `:Skill`
nodes as of 2026-06-15). Today its keyword path is a **literal substring
match** on the whole query string:

```cypher
WHERE toLower(s.name) CONTAINS toLower($query)
   OR toLower(s.description) CONTAINS toLower($query)
   OR toLower(s.when_to_use) CONTAINS toLower($query)
```

This is a footgun, confirmed live on the 8x8 bug-bounty run-004
(2026-06-15):

| query | result |
|---|---|
| `redirect_uri` | 2 hits (`oauth`, `open-redirect`) ✅ |
| `oauth redirect_uri bypass` | **0 hits** ❌ |
| `redirect uri` (space) | **0 hits** ❌ |
| `oauth2` | **0 hits** ❌ |

The exact skills the agent wants **exist in the graph**, but any natural
multi-word query returns nothing because no single field contains that exact
phrase. There is no tokenization, no stemming, no semantic match, and no
ranking (`ORDER BY name` is alphabetical). Agents that phrase a rich query
get worse results than ones that guess a single magic keyword. The hunter
fleet hit this repeatedly.

The skill graph is **already curated** — `Skill` nodes linked to `Technique`
(`IMPLEMENTS`), `Tag` (`TAGGED`), `Phase` (`IN_PHASE`), and analyst `chains`.
The retrieval layer simply doesn't exploit it. This is not a "build a KG from
documents" problem (the KG exists, built deterministically by
`skillogy.builder` → `skills.cypher`); it is a "retrieve well over a curated
KG" problem.

A 2026-06-15 survey of the field (LightRAG [EMNLP'25, v1.5.3], GraphRAG-Bench
[ICLR'26]) confirms **hybrid graph retrieval** — LightRAG's dual-level
(local entity + global relationship) merge — as the strongest approach for
exactly this shape, and it maps cleanly onto our graph.

## Decision

Replace the substring keyword path in `find_skill` with **LightRAG-style
hybrid retrieval implemented directly on the existing skillogy graph** — NOT
by adopting the LightRAG library. The agent-facing API (`find_skill` /
`load_skill` / `traverse`, natural-language `query`) is unchanged; only the
backend retrieval changes.

### Why implement the algorithm, not adopt the library

| | LightRAG library (`lightrag-hku`) | Implement the algorithm in skillogy (CHOSEN) |
|---|---|---|
| Graph | builds its OWN KG via LLM entity extraction → conflicts with / duplicates our curated `Skill/Technique/Tag/Phase` schema | reuses the curated graph as-is |
| Ingest | "chunk → LLM-extract → embed" (non-deterministic, costly) | keeps the deterministic `builder` ingest; only ADDS an embedding step |
| ACL (ADR-0008) | per-role path-prefix scoping not native; must post-filter or patch internals | ACL stays exactly where it is, applied in the same Cypher |
| API contract | find_skill/load_skill/traverse would bend to LightRAG's API | 3-tool contract preserved |
| open-core footprint | heavy dep (networkx, nano-vectordb, its own storage abstraction) into OSS | only `neo4j` driver + a litellm embedding call |
| Net effect | rebuild skillogy *around* LightRAG | add dual-level retrieval *onto* skillogy |

Our problem is retrieval over a curated KG; the library is optimized for
constructing a KG from documents. Impedance mismatch is high; the algorithm
is what we want.

### Architecture (dual-level hybrid, mapped to our graph)

**Ingest (extend `builder` + boot ingest — additive):**
- For each `:Skill`, compute one embedding over `name + description +
  when_to_use + MoC summary`, stored as `s.embedding` (float[]).
- Emit it in `skills.cypher` (the embedding is deterministic given the model,
  so the checked-in dump stays reproducible; regenerated in CI).
- Create a Neo4j **native vector index** on `:Skill(embedding)` (Neo4j
  5.24.2 supports this — confirmed) plus keep the existing facet edges.
- Embeddings via the **litellm gateway** (a cloud embedding model, e.g.
  `voyage-3` / `text-embedding-3-large` — same endpoint used at query time so
  ingest and query share a vector space). 285 skills → trivial one-time cost.

**Query (`find_skill` keyword path becomes hybrid):**
1. **local** — embed the query, `db.index.vector.queryNodes` top-k `:Skill`
   by cosine (semantic entity match — "oauth redirect_uri bypass" now finds
   `oauth` / `open-redirect` by meaning, not substring).
2. **global** — from those seed skills, graph-expand one hop over
   `IMPLEMENTS` / `TAGGED` / `IN_PHASE` / analyst `chains` to pull the
   related playbook cluster (relationship-level recall — e.g. a confirmed-XSS
   skill surfaces its `chains/xss-to-…` neighbours).
3. **hybrid merge + rerank** — fuse local + global (and, for exact tokens
   like a CVE id or tool name, a keyword signal) via reciprocal-rank fusion;
   rank by fused score. Replaces `ORDER BY name`.
4. **ACL** — the existing `allowed_path_prefixes` filter (ADR-0008) applies to
   the fused candidate set, unchanged.

Facet filters (`subdomain`, `mitre_id`, `tag`, `tactic_id`) keep their exact
behaviour and continue to AND with the keyword path.

### Backward compatibility

- No agent prompt changes — agents still pass natural language to `query`.
- `find_skill` with no `query` (pure facet search) is unchanged.
- `load_skill` (exact path/name, #670) and `traverse` are untouched.
- If the vector index is absent (e.g. an old `skills.cypher` without
  embeddings), `find_skill` falls back to the current substring path so the
  service degrades gracefully rather than 500ing.

## Consequences

**Positive**
- Multi-word / semantic queries work; the curated graph is finally exploited
  for recall. Directly fixes the run-004 footgun.
- All existing guarantees preserved (ACL, deterministic ingest, 3-tool API,
  open-core boundary).

**Negative / costs**
- Ingest now depends on a litellm embedding model; `skills.cypher` grows by
  the embedding vectors (285 × dims). CI rebuild must run embeddings.
- We own the retrieval/rerank code and must track RAG advances ourselves
  (the tradeoff accepted for control + zero schema conflict).
- A query-time embedding call is added to the `find_skill` hot path
  (one small embedding request; cache by query string).

## Open questions

- **Embedding model**: `voyage-3` vs `text-embedding-3-large` vs a code/security-tuned
  model — pick on retrieval quality over the security corpus.
- **Rerank fusion weights** (local vs global vs keyword) — tune on a small
  labelled query set drawn from real hunt logs.
- **Re-embedding cadence**: only changed skills need re-embedding; key the
  cache on a content hash in the builder.
