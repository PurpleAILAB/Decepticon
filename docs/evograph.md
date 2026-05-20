# EvoGraph — Cross-Session Memory

EvoGraph layers a *lessons-learned memory* over Decepticon's existing
Neo4j attack graph so a fresh engagement starts with awareness of past
engagements against similar targets, common bug classes seen, and
techniques that have or haven't worked.

> Single-session attack graph: see [`tools/research/graph.py`](../decepticon/tools/research/graph.py) +
> [`tools/research/neo4j_store.py`](../decepticon/tools/research/neo4j_store.py)
>
> Cross-session memory layer (this doc): see [`tools/research/cross_session.py`](../decepticon/tools/research/cross_session.py)

## Concepts

| Node | Cardinality | Purpose |
|---|---|---|
| `Engagement {slug, target, started_at, scope}` | one per session | Anchors all session-scoped nodes via `IN_ENGAGEMENT` edges |
| `EngagementMemory {slug, target, ended_at, total_findings, ...}` | one per *completed* engagement | Distilled summary written at engagement end |

| Edge | Purpose |
|---|---|
| `(node)-[:IN_ENGAGEMENT]->(:Engagement)` | Scopes any session-bound node |
| `(:EngagementMemory)-[:SUMMARIZES]->(:Engagement)` | Links memory back to source engagement |

## Lifecycle

```
engagement-start                 mid-engagement              engagement-end
─────────────────                ──────────────              ───────────────
register_engagement(...)         tag_node_to_engagement     commit_engagement_memory(...)
bootstrap_from_prior(...)        find_similar_findings(...) → EngagementMemory node
       │                                  │                          │
       ▼                                  ▼                          ▼
inject into                       runtime lookup                add to Neo4j
orchestrator system prompt        of prior playbooks            for future bootstraps
```

### 1. At engagement start

```python
from decepticon.tools.research.cross_session import (
    ensure_evograph_schema,
    register_engagement,
    bootstrap_from_prior,
    format_bootstrap_for_prompt,
)

ensure_evograph_schema()                                 # idempotent
register_engagement("acme-q1", target="api.example.com")

# Surface prior similar engagements to the agent
prior = bootstrap_from_prior(target_hint="example.com", top_k=5)
prompt_addition = format_bootstrap_for_prompt(prior)
# include `prompt_addition` in the orchestrator's system prompt
```

### 2. During the engagement

The recon/exploit/analyst agents already write graph nodes via
``Neo4jStore.upsert_node``. To make those nodes queryable by future
engagements, tag them:

```python
from decepticon.tools.research.cross_session import tag_node_to_engagement

# After upserting a Finding
tag_node_to_engagement(
    node_key="FIND-001",
    kind="Finding",
    engagement_slug="acme-q1",
)
```

If the agent identifies a new bug class mid-engagement, query prior
findings for playbook hints:

```python
from decepticon.tools.research.cross_session import find_similar_findings

prior_sqli = find_similar_findings(bug_class="sqli", limit=5)
# returns [{vuln_id, target, status, summary, engagement_slug, ended_at}, ...]
```

### 3. At engagement end

```python
from decepticon.tools.research.cross_session import commit_engagement_memory

memory = commit_engagement_memory(
    "acme-q1",
    note="WAF rate-limit aborted dirbusting; SAML auth replay was the key vector",
)
# memory is an EngagementMemory dataclass; the matching node lands in Neo4j
```

## What gets distilled

`commit_engagement_memory` reads the engagement's tagged sub-graph and computes:

- `total_findings`, `validated_findings`, `shipped_findings`
- `top_bug_classes` — top-5 bug classes by count
- `top_techniques` — first 10 `Technique` nodes touched (by label)
- `crown_jewels_reached` — `CrownJewel` nodes connected to engagement
- `notable_attack_paths` — first 5 `AttackPath` titles
- `note` — caller-supplied prose (orchestrator's terminal reflection)

These fields are written as native Neo4j properties on the
`EngagementMemory` node — no JSON-in-string, no embedded blobs.

## Graceful degradation

All public functions return empty results (or `False` for boolean
operations) when Neo4j is unavailable. Engagements run normally — they
just lose the bootstrap benefit. This means the layer is safe to wire
into the default orchestrator without an "is Neo4j up?" precheck.

## Future enhancements (not in this PR)

- **Vector similarity for target matching.** Substring match works for
  obvious cases (subdomains of same root); embeddings would catch
  semantic similarity (e.g. "shopify-like ecommerce" vs "magento").
- **Per-finding playbook capture.** A finding currently summarizes as a
  one-liner. We could attach the full kill chain (recon path → exploit
  step → pivot) so future agents can replay sequences.
- **Decay weighting.** Older memories should de-prioritize as the
  target evolves (kernel patches, infra changes).

These would extend the schema without breaking the current API.
