---
name: adversarial-debate
description: "Use when a CRITICAL or HIGH finding must clear cross-model debate validation before promotion. Triggers on: 'debate', 'cross-model', 'skeptic', 'false positive check', 'promotion blocked'."
---

# Adversarial Debate Validation

A single model — even a careful one — has blind spots. A finding it is
confident about can still be a false positive: an unreachable code path, a
sink that is sanitized upstream, a success pattern a benign request also
trips. False positives that reach the Patcher and Exploiter waste real
work and inflate the report.

MDASH's answer, adopted here: before a CRITICAL/HIGH finding is promoted,
an **independent model from a different provider family** argues it is a
false positive. Model disagreement is treated as a credibility signal.

## When to use

`validate_finding` enforces this automatically: a validated CRITICAL or
HIGH finding without a debate token comes back as `promotion: blocked`.
That is your cue to run `debate_finding`.

LOW/MEDIUM findings are not gated — debate only runs where the cost of a
false positive is high.

## The workflow

1. `validate_finding(...)` → `promotion: blocked`.
2. `debate_finding(vuln_id, finding_summary, poc_evidence, cvss_vector)`:
   - A **skeptic** model (different family, cheap LOW tier) is prompted to
     find the strongest argument the finding is a false positive.
   - If the skeptic refutes, the **advocate** (the verifier's own model)
     answers the objection.
   - A deterministic adjudicator assigns a `verdict` and a `credibility`
     score in [0, 1].
3. Re-run `validate_finding(...)` with the same arguments.

## Interpreting the verdict

| Verdict     | Meaning                                              | Action |
|-------------|------------------------------------------------------|--------|
| `upheld`    | Skeptic could not refute the finding                 | Re-run `validate_finding` → promotes |
| `uncertain` | Doubt raised, advocate answered it partially         | Re-run `validate_finding` → promotes |
| `skipped`   | Only one provider family configured — no independent skeptic | Re-run `validate_finding` → promotes |
| `refuted`   | Skeptic produced a sound refutation the advocate conceded | DO NOT promote — fix the PoC |

A `refuted` finding has `credibility` below the floor; `validate_finding`
will keep blocking it. Do not retry the same PoC — the skeptic found a
real flaw. Either strengthen the negative control (the most common cause —
a weak negative control makes a benign response look like exploitation),
revise the reproduction, or record `last_failure` and move on.

## Why a different family

The skeptic is deliberately drawn from a different model family than the
verifier's primary. Two instances of the same model share the same blind
spots — they tend to agree. An independent family is far more likely to
catch a reasoning error. When only one family is configured the debate is
`skipped` rather than run same-family: a same-family "debate" is theater,
and blocking single-credential users behind it would help no one.
