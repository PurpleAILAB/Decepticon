# Semantic redaction for the research corpus

**Status:** proposed
**Date:** 2026-07-27
**Supersedes nothing.** Extends `2026-06-20-telemetry-data-collection-design.md`.

## Why

The masker is regex-only. Reading 538k live events shows what that buys and
what it cannot:

| class | regex verdict |
|---|---|
| IP, MAC, email, URL, private key, JWT, AWS key | **works** — this is regex's strong suit (published email F1 0.93–0.996, better than any NER model) |
| hostname vs. dotted code | structurally leaky — `json.load(` was masked as a host in **1,697 of 7,990** masked turns; patched with a lookahead, `sys.stdin` still slips |
| credentials, multilingual | **unwinnable by enumeration** — the corpus is Russian (154 installs), Spanish/Portuguese (72), Turkish, Vietnamese, Japanese, Korean. `password\|senha\|contraseña\|пароль\|...` is an infinite list |
| client / organization names | **impossible** — a company name has no shape. `Temu`, `esri`, `ArcGIS`, `Rajwin`, `Emitenotas` all shipped verbatim inside free prose |
| quasi-identifiers (asset type, bounty program, industry) | out of scope entirely |

Every fix shipped so far was reactive: found by reading samples, patched with
another pattern. That is not a privacy floor.

The literature agrees. Cross-domain PII detection is unsolved — a June 2026
benchmark over four datasets puts regex at **F1 0.171** and the best model at
**0.542**, concluding "none of these models are good"; PIIBench reports a best
system at **F1 0.14**. Hybrid regex+NER gains measured **+0.012**. And
`arXiv 2601.05918` shows agentic LLMs re-identifying participants in a redacted
dataset by exploiting quasi-identifiers, context and writing style — Anthropic
themselves classify redaction as "a courtesy, not a privacy safeguard".

## Non-goal

Adding a NER model to the client. GLiNER-class models run **161–198 ms** per
call versus regex at **0.1 ms**, weigh 200–300 MB, degrade sharply out of
distribution (one model lost 78% moving to financial text — our text is
multilingual security prose interleaved with shell output, further out than
that), and would sit in the agent's hot path on every trajectory step for
roughly +0.01 F1. No.

## Design

Split the problem by where it is cheap to solve.

### Layer 1 — client, deterministic (keep, unchanged)

Runs in `wrap_model_call` / `wrap_tool_call`. Must stay ~0.1 ms and fail-closed.

1. **Declared ground truth** — RoE `client` / `engagement_name` /
   `engagement_slug` / `authorized_by`, plus in-scope hosts and the workspace
   directory. Precision 1.0, no model, no list. This is the only layer that can
   catch a company name, and it works because *the engagement declares it*.
2. **Structured regex** — IP, MAC, email, URL, keys, JWT, AWS keys, blobs.
   Where regex genuinely beats models.
3. **Tier-C fail-closed scan** — drop rather than ship on any residue.

Layer 1 is a *floor*, not a guarantee. It must be documented as such.

### Layer 2 — server-side semantic pass (new)

Runs **after collection, before the corpus is used**, never in the agent path.
Cost and latency stop mattering; correctness starts.

```
PostHog  ──►  export_corpus  ──►  [semantic redaction]  ──►  training set
   raw-ish        (exists)          LLM pass + audit          publishable
```

Per trajectory (not per step — the model needs the surrounding turns to judge
what is an identifier):

- **Input:** the layer-1-masked trajectory, plus the declared identity terms.
- **Task:** replace any remaining *target* identifier — organization names,
  credentials in any language, personal names, distinctive asset descriptions —
  with the same `<TYPE_n>` placeholders, preserving reasoning structure.
  Explicitly keep: technique names, tool names, CVEs, ATT&CK ids, the reasoning
  itself.
- **Output:** masked trajectory + the list of spans it masked (for audit).
- **Model:** cheapest capable tier; batched per trajectory.

Then a **verification pass**: a second, independent prompt asks "does anything
here still identify a real organization, person, or host?" A trajectory that
fails is quarantined, not shipped — same fail-closed posture as Tier-C.

### Layer 3 — audit before release

Sample-based human review of the quarantine queue and of a random slice of
passed trajectories. `arXiv 2601.05918`'s recommendation, and the shape
ProAgentBench used (rule-based + human-in-the-loop) to publish 28k events.

## Open questions

1. **Where does layer 2 run?** A batch job against the PostHog export is the
   simplest (`telemetry-gateway/export_corpus.py` already reconstructs
   trajectories). The gateway Worker is the wrong place — it sees one batch, not
   a trajectory, and has no model budget.
2. **Retention of the pre-layer-2 data.** Layer-1 output is what PostHog holds
   today. If layer 2 is the real boundary, layer-1 data needs a retention limit
   and access control, and `TELEMETRY.md` must say so.
3. **Is the corpus ever published, or only used internally?** Publishing raises
   the bar to layer 3 with real review. Internal-only training still needs
   layer 2 but tolerates a looser audit.
4. **Does the RoE actually carry `client`?** The schema requires it and the
   roe-template skill interviews for it, but a real `roe.json` on disk had no
   `client` key. The declaration path exists and is not enforced — fixing that
   is the cheapest privacy win available and belongs in the skill/schema, not
   the masker.

## What to change in the docs now

`TELEMETRY.md` claims client/org names are masked. They are not, and no regex
will make it true. Until layer 2 ships, the sentence must state what layer 1
actually guarantees: structured identifiers and whatever the engagement
declared. An untrue privacy promise is worse than a documented gap.
