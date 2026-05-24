---
name: aatmf-t06-training-poisoning
description: AATMF T6 — Training & Feedback Poisoning. Data poisoning, RLHF reward hacks, fine-tune-time exfil, embedding poisoning.
when_to_use: "training data poisoning rlhf reward hack fine-tune embedding poisoning"
mitre_attack: T1565
metadata:
  subdomain: ai-security
  aatmf_tactic: T6
---

# T6 — Training & Feedback Poisoning

Attacks on the training pipeline rather than inference. High-effort,
high-impact — requires attacker to influence training-data pipeline or
RLHF feedback loop.

## Techniques

### T6.001 — Pre-training data poisoning
Inject malicious data into a public crawl that targets will scrape:
- Wikipedia/StackOverflow edits w/ misleading code patterns
- Github repos w/ subtle backdoors that get indexed
- "Trigger phrases" that activate backdoor behavior

Scope: targets foundation models. Out of scope for most red-team
engagements; relevant for AI-supply-chain audits.

### T6.002 — Fine-tune data injection
Some platforms allow user-supplied fine-tune data:
- Submit poisoned dataset
- Backdoor activates on specific trigger
- Survives subsequent SFT/RLHF

Test: provide a small fine-tune sample w/ a trigger → check if the
deployed fine-tuned model responds to it.

### T6.003 — RLHF reward hacking
Where users vote on responses (thumbs up/down feeding back to training):
- Brigade upvote attacker-preferred unsafe responses
- Brigade downvote safe responses
- Model drifts toward attacker-preferred outputs over time

Detection: longitudinal monitoring of policy-compliance rate.

### T6.004 — Embedding poisoning
Where RAG store updates from user inputs (e.g. customer-support bot
that "learns" from conversations):
- Submit content w/ adversarial embeddings (engineered to be retrieved
  for unrelated queries)
- Resulting RAG retrieval injects attacker content into other users'
  responses

This is RAG-store T12 territory but the *poison-via-training-loop*
angle places it here.

## Probe pattern

T6 attacks are *infrastructure-level* — promptfoo doesn't test them
directly. The right probe:
- Audit the training-data ingest pipeline (is user content used in fine-tunes?)
- Audit RLHF feedback paths (who can vote? rate limits?)
- Audit RAG-update paths (who can add documents? approval?)

If any of these accepts unmoderated user content → T6 is a live risk.

## Detection signals

- Model behavior shifts over time without explicit retraining
- Specific user IDs / brigades correlate w/ shifts
- Test fixtures (canary phrases) trigger non-default responses

## Severity

| Outcome | Severity |
|---|---|
| Live foundation-model poisoning | Critical (rare — usually responsibly disclosed to provider) |
| Fine-tune backdoor in customer deployment | Critical 9.0 |
| RAG embedding poisoning at scale | Critical 9.0 |
| RLHF brigade drifting policy | High 8.0 (slow + reversible) |

## Defender

- NEVER use unmoderated user content in fine-tunes or RLHF
- Diff-testing: every fine-tune evaluated against safety regression suite
- Canary phrases in eval suite to detect drift
- RAG-update review queue + approval flow
- Per-user rate limits on feedback signals
- Anomaly detection on feedback patterns (brigade signatures)

## Cross-references
- T12 (RAG manipulation) — adjacent class, attack on retrieval not training
- T13 (supply chain) — model artifact integrity
