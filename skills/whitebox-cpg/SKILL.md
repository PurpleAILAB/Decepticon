---
name: whitebox-cpg
description: |
  Routes white-box source-code analysis tasks via the CPG Analyst.
  Activate when the engagement has source-code access — open-source
  target, bug-bounty in-scope repo, customer drop, or container layer
  with source intact. Produces STATIC_CONFIRMED Finding nodes ready
  for the verifier to upgrade to POC_VALIDATED.
priority: high
applies_when:
  - source tree mounted at /workspace/target or /workspace/customer
  - engagement scope explicitly includes source review
  - n-day port from public CVE
  - CI/CD pre-commit triage on diff
---

# White-box CPG Analysis (router)

When the orchestrator has source code access, dispatch the
**cpg_analyst** sub-agent. Loop:

1. INVENTORY  → `cpg_inventory_languages(root)`
2. PARSE      → `cpg_parse_tree(file, language)`
3. SOURCES    → `cpg_find_sources(file, language)`
4. SINKS      → `cpg_find_sinks(file, language)`
5. TRACE      → `cpg_reaches(source, sink)` for each candidate pair
6. RECORD     → Finding nodes w/ DEFINED_IN edges
7. HANDOFF    → verifier upgrades STATIC_CONFIRMED → POC_VALIDATED

## When to dispatch this sub-agent

- ✅ Open-source bounty target (GitHub repo cloned to `/workspace/target/`)
- ✅ Customer source drop under engagement
- ✅ N-day backport — patch the diff into your tree, run agent against
  matching pattern
- ✅ Pre-commit CI on diff (set `cpg_diff_mode=true`)
- ❌ Pure compiled binary — hand off to **reverser** instead
- ❌ Solidity / Move / Cairo / Vyper — hand off to **contract_auditor**
- ❌ Terraform / CloudFormation / K8s — hand off to **cloud_hunter**

## Dependencies

- Always-on: `pyyaml` (already in Decepticon deps)
- Optional faster parse: `pip install tree-sitter-languages`
- Optional full taint: install joern-cli, set `JOERN_HOME=/opt/joern`

When optional deps are absent, the agent gracefully degrades:
- No tree-sitter → regex fallback (works on Python/JS/TS)
- No joern → AST-heuristic reachability (same-function source→sink)

Coverage drops in fallback mode but the agent still produces useful
candidates for the verifier.

## Output contract

Each finding emitted is a `Finding` node with:
- `key`: `CPG-<engagement_slug>-<n>`
- `bug_class`: one of `sqli|xss|cmd_injection|ssrf|xxe|deserialization|path_traversal|format_string|buffer_overflow|...`
- `evidence_tier`: `STATIC_CONFIRMED`
- `source_loc`: `{file, line, sigil, kind}`
- `sink_loc`: `{file, line, sigil, kind}`
- `confidence`: 0.0–1.0
- `language`: inferred language tag
- Linked to `CodeLocation` nodes via `DEFINED_IN` edges

## Cross-references

- `skills/exploit/` — runtime exploitation skill leaves (post-verification)
- `skills/verifier/seven-question-gate/` — quality filter before reporting
- `skills/_corpus/wstg/` — OWASP test cases for vuln-class context
- `docs/evograph.md` — cross-session memory (prior findings of same bug class)
