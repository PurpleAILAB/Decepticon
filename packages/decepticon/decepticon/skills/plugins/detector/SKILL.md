---
name: detector-overview
description: Stage 2 vulnerability detector playbook. Reads source around CANDIDATE nodes and promotes real bugs to VULNERABILITY + HYPOTHESIS. Read-only. Load at detector-agent startup.
metadata:
  subdomain: orchestration
  when_to_use: "detector stage 2 vulnerability candidate vulnerability hypothesis read-only source-read pipeline"
  upstream_ref: "Decepticon vulnresearch pipeline — stage 2 detector role"
---

# Detector Skill

You promote scanner candidates into real `VULNERABILITY` nodes — or
reject them as false positives — by reading the surrounding source.
You have no bash and no scanner tools. Only graph CRUD and source reads.

## Per-candidate decision flow

1. Pull candidate: `kg_query(kind="candidate", limit=20)`.
2. For each candidate (highest score first):
   a. Read ±30 lines around `path:line`. Prefer function boundaries.
   b. Identify: source? sink? taint path? sanitizer?
   c. Load the relevant playbook: `/skills/standard/analyst/<vuln-class>/SKILL.md`.
      Available classes: sql-injection, ssrf, deserialization, idor, ssti,
      xss, xxe, path-traversal, command-injection, prototype-pollution,
      prompt-injection, auth-bypass.
   d. Decide: promote, reject, or hypothesis-only.
3. Emit.

## Promotion template

```python
vuln = kg_add_node(
    "vulnerability",
    "SQLi in product search",
    props='{"key":"app.py:search_products:sqli","severity":"high",'
          '"file":"/workspace/target/app.py","line":142,"cwe":["CWE-89"],'
          '"source":"request.args.get(\\"q\\")","sink":"cursor.execute",'
          '"evidence":"cursor.execute(f\\"SELECT * FROM products WHERE name LIKE \'%{q}%\'\\")"}',
)
hyp = kg_add_node(
    "hypothesis",
    "Unsanitized query param flows into f-string SQL",
    props='{"key":"app.py:search_products:sqli:hyp"}',
)
kg_add_edge(vuln_id, candidate_id, "derived_from")
kg_add_edge(hyp_id, vuln_id, "mapped_to")
```

## Rejection template

Same `kg_add_node` call with the SAME `key`, plus `status="rejected"`
and `reason="sanitized via html.escape before sink"`. Idempotent — the
graph upsert merges the rejection on top of the original candidate.

## Severity calibration

| Signal                                                     | Severity  |
|------------------------------------------------------------|-----------|
| Unauth + external input + dangerous sink + no sanitizer    | critical  |
| Authed + dangerous sink, or unauth + partial sanitization  | high      |
| Requires specific input shape or edge case                 | medium    |
| Theoretically reachable, requires multiple prereqs         | low       |

## Anti-patterns

- Reading entire files. 30–200 lines is the ceiling.
- Emitting more than one `VULNERABILITY` per (file, function, sink).
- Running scanner tools ("let me re-scan this area"). Not your job.
- Writing bash commands. You do not have bash.
