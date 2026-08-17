# Knowledge Retention Policy

Decepticon accumulates two very different kinds of knowledge. They have
opposite retention rules, and confusing them leaks engagement data.

## 1. Skill knowledge — committed

The skill corpus (`packages/decepticon/decepticon/skills/**/SKILL.md`) and its
derived graph export
(`packages/decepticon/decepticon/skills/.graph/skills.cypher`) are **committed
to the repo**.

- `skills.cypher` is deterministically regenerated from the SKILL.md tree via
  `make build-skill-graph` (frozen timestamps), so checking it in carries no
  secrets — it is pure structure: skill metadata, subdomain taxonomy, and
  MITRE mappings. `make check-skill-graph` in CI asserts the checked-in file
  matches what the builder produces.
- Skill content is generalized methodology: tool invocations, decision
  tables, workflow checklists. It must never embed engagement-specific values
  (real IPs, hostnames, credentials, client names). Use placeholders
  (`{target}`, `<host:port>`) in examples.

## 2. Engagement knowledge — never committed

The runtime attack graph (Neo4j) and the on-disk workspace hold **live
engagement data**: real host IPs, harvested credentials, session material,
target-specific findings. This stays out of the repo, permanently:

| Location | Contents | Status |
|---|---|---|
| Neo4j (`bolt://localhost:7687`) | Host / Service / Vulnerability / Credential nodes from live engagements | Runtime only; wiped or archived per engagement data-handling plan |
| `workspace/` | Findings, loot, audit logs (`audit/roe-decisions.jsonl`) | Gitignored |
| `~/.decepticon/` | Local state, runtime reference corpora | Gitignored |

Both `workspace/` and `.decepticon/` are in `.gitignore`; do not add
exceptions for engagement output. The data-handling and cleanup documents in
the Soundwave engagement bundle govern how long this material is retained —
the repo is never part of that story.

## 3. Contribute-back: promoting lessons to skills

The valuable middle ground is **sanitized, generalized lessons**. When an
engagement teaches something reusable — a tool quirk, a detection gotcha, a
workflow that beat the documented one — promote it into the committed corpus:

1. Strip every engagement identifier: IPs, domains, usernames, client names,
  dates tied to a specific operation. Replace with placeholders.
2. Generalize: the lesson should help the *next* operator facing the *same
  class* of problem, not replay this engagement.
3. Commit it as a SKILL.md edit (new section, new decision-table row, or a
  new skill when the topic is net-new) with proper attribution metadata.
4. Regenerate the graph (`make build-skill-graph`) so `skills.cypher` stays
  in sync.

This mirrors the field-journal / contribute-back model used by the
[reverse-skill](integrations/reverse-skill.md) integration: raw engagement
notes live and die with the engagement, while distilled precedent flows back
into the committed skill corpus. Skills are the only long-term memory the
repo keeps.
