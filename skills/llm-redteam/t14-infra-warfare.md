---
name: aatmf-t14-infra-warfare
description: AATMF T14 — Infrastructure & Economic Warfare. Endpoint DoS via expensive prompts, model-API account exhaustion, GPU resource starvation, billing weaponization.
when_to_use: "infra dos economic warfare cost amplification gpu starvation billing"
mitre_attack: T1499
metadata:
  subdomain: ai-security
  aatmf_tactic: T14
---

# T14 — Infrastructure & Economic Warfare

Attacks aimed at degrading service availability, exhausting budget,
or causing economic harm via abuse of the LLM endpoint. Adjacent to
classical DoS but LLM-specific cost dynamics.

## Techniques

### T14.001 — Per-account budget exhaustion
- Multiple low-bandwidth requests each maximizing token cost
- Free-tier abuse via account creation farms
- Direct DDoS of paid endpoint (uses budget at attack rate)

Defenders: per-account caps + alerts.

### T14.002 — Shared-quota poisoning
Multi-tenant LLM services share quotas at a provider level. Attacker
exhausts the shared quota → all tenants degraded.

Targets: SaaS products that meter LLM access but share underlying
API account.

### T14.003 — GPU resource starvation
Self-hosted inference. Long-context queries hog GPU:
- Send queries near max context length
- Send batch of long-context queries in parallel
- Loop to maintain pressure

Cost-amplification ratio: 1 user request → 100% GPU utilization.

### T14.004 — Cost amplification (T5.002 cross-ref)
Prompt engineering to maximize output cost:
- "Repeat 'token' 5000 times"
- "Generate the maximum-length response you're allowed to produce"
- Quadratic context patterns that bloat each turn

### T14.005 — Pricing-tier exploit
Some APIs charge differently based on model variant. Trick the
endpoint into using the expensive variant via parameter manipulation
(T5.004 overlap).

### T14.006 — Caching-pollution
Where LLM provider caches identical prompts (cost-reduction feature):
- Submit prompts that fill cache but produce uncacheable outputs
- Cache thrashing → no cost savings, full cost incurred

### T14.007 — Streaming attack
Open many streaming requests → never consume → endpoint holds
connection slots open until timeout.

## Probe pattern

T14 is load-testing territory. Use k6, locust, hey:
```bash
# Spike test
hey -n 1000 -c 100 -m POST -H 'Authorization: Bearer X' \
  -d '{"prompt":"'$(python3 -c 'print("a"*100000)')'"}' \
  https://target/api/chat
```

Monitor:
- Cost / minute via provider dashboard
- p99 latency
- 429 / 503 error rate
- Other-tenant impact (if multi-tenant)

## Detection signals

- Cost spike >5x baseline w/o feature change
- p99 latency degradation
- Specific user IDs / IPs concentrating traffic
- Output token distribution skewed long

## Severity

| Outcome | Severity |
|---|---|
| Multi-tenant outage via quota exhaust | Critical 9.0 |
| Single-org budget burn via abuse | High 7-8 |
| GPU starvation single-host | High 7-8 (recoverable) |
| Streaming-slot starvation | Medium 6-7 |

## Defender

- Per-account hard budget caps (with grace + alert at 80%/95%)
- `max_tokens` strictly enforced (no `unlimited`)
- Context-length per-tier caps
- Rate limits per-account AND global (catch shared-quota attacks)
- Anomaly detection on cost/latency/concurrency
- Caching: per-tenant cache, not global
- Streaming: connection timeout aggressive (60s if no consumer)

## Cross-references
- T5 (API exploitation) — overlap on cost/abuse vectors
- Classical DDoS skills `skills/exploit/web/...`
