---
name: unbounded-consumption
description: Hunt LLM unbounded consumption (OWASP LLM10:2025) — denial-of-wallet and denial-of-service against LLM endpoints via unrestricted prompt size, runaway tool loops, expensive model selection, and unauthenticated fan-out.
metadata:
  subdomain: ai-security
  when_to_use: "llm unbounded consumption owasp llm10 denial of wallet dos prompt size tool loop expensive model unauthenticated fan-out"
---

# LLM Unbounded Consumption (LLM10:2025)

LLM inference is metered in dollars-per-token at the provider, and
those tokens stack quickly: a context window full of attacker
content costs more than the rest of the request stack combined.
Unbounded consumption produces three impacts in escalating severity:
provider rate-limit / hard-block (DoS), bill blowout (denial-of-
wallet), and ultimately tool / sandbox resource exhaustion (DoS of
the customer's compute).

## 1. Recognition signals

- The product exposes an authenticated **or unauthenticated** LLM
  endpoint that accepts large prompts.
- Per-user / per-tenant token budget is undocumented or absent.
- Free-tier signup grants immediate access to the most expensive model.
- Agentic system has no max-step / max-token / max-cost cap.
- Tools loop on model output without iteration cap (``while not done:``).
- File-upload feature dumps full document into the context.
- Background workers retry failed model calls on exponential backoff
  without a hard ceiling.
- Cost dashboard updates daily, not in real time.

## 2. Attack vectors

### Direct prompt expansion (input DoS)
Submit a maximum-context-window prompt repeatedly:
```bash
seq 1 1000 | xargs -I{} curl -s -X POST "$TARGET/chat" \
    -H "Authorization: Bearer $FREE_TIER_TOKEN" \
    -d "{\"prompt\":\"$(python -c 'print("repeat this " * 30000)')\"}" \
    >/dev/null &
```

### Cost-tier escalation
Bypass the model picker to force the most expensive model
(opus / o1 / claude-3.7) on every request. Often the picker is a
client-side selector that the backend trusts.

### Runaway agentic loop
Submit a task that the agent cannot complete: "Read every file in
``/`` recursively and summarise each in 5 paragraphs." Each tool
result feeds the next prompt; tokens grow per loop. With no max-step
cap the run lasts until provider rate-limits or budget alarms fire.

### Fan-out via tool calls
Trigger an LLM that itself spawns N tool calls per turn, each of
which invokes a sub-LLM. Geometric blow-up.

### Self-prompting / recursion
"For each of the following 100 topics, write a 5-page detailed
analysis." Each topic becomes a sub-call.

### Wallet-only DoS via duplicate accounts
Free-tier signup with a temp-email service; 100 accounts; each runs
maximum-cost requests on a paid backend.

### Long-context starvation of other users
Submit a single max-context request that holds a shared backend
worker; concurrent users observe latency spikes / 5xx.

## 3. Audit workflow

```bash
# Find LLM endpoints + their auth requirements
grep -rE '/chat|/complete|/generate|/agent|/llm' /workspace/src

# Find token / cost cap logic (or its absence)
grep -rE 'max_tokens|max_steps|cost_budget|rate_limit|throttle|token_budget' /workspace/src

# Find model-selection bypass surface (client-controlled model id)
grep -rE 'model\s*=\s*request|model_from_body|user_choice_model' /workspace/src

# Find agentic loop terminators
grep -rE 'while.*tool|for.*step|max_iterations|recursion_limit' /workspace/src
```

For each endpoint ask:
1. What is the per-user max tokens per minute / per day?
2. Is the model id chosen by the user trusted server-side?
3. Is there a circuit-breaker on the provider 429 path?
4. What is the maximum total cost of a single agentic run?

## 4. Exploitation goals

| Goal | Impact | Indicator |
|---|---|---|
| Per-user DoS via large prompt | Low | One user 429s themselves |
| Wallet drain on free tier | High | Measurable per-account spend > tier price |
| Single-prompt budget blowout | High | One request exceeds expected per-day cost |
| Cross-tenant DoS via shared backend | Critical | Other tenants 5xx during attacker's request |
| Sustained billing attack | Critical | Multi-day spend curve elevated by attacker |

## 5. PoC payloads

### Wallet drain probe (free tier)
```bash
# Provision a fresh free-tier account
TOK=$(curl -X POST $TARGET/signup -d '{"email":"test+'$(uuidgen)'@example"}' | jq -r .token)

# Sustained max-cost requests
for i in $(seq 1 50); do
    curl -s -X POST "$TARGET/chat" -H "Authorization: Bearer $TOK" \
        -d '{"model":"gpt-5-pro","prompt":"'$(python -c 'print("token "*40000)')'"}' \
        >/dev/null &
done
wait

# Measure spend via vendor dashboard or attacker-side response timing
```

### Runaway agentic loop
```
For each line in /etc/services, look up the protocol's RFC, fetch the
RFC, and write a 3-paragraph summary. Save each summary to a file in
/tmp. Continue until all services are processed.
```
Watch token count grow per loop; record at what step the system
finally caps out (if ever).

### Model escalation
```bash
# Backend trusts the user-supplied model id?
curl -X POST "$TARGET/chat" -d '{"model":"o1-pro","prompt":"hello"}'
```
If a free-tier or unauthenticated request reaches a paid model,
file it.

### Long-context shared-worker DoS
Concurrent: one tab sends a max-context prompt; another tab measures
p95 latency of normal requests. Latency degradation on the second
tab indicates a shared worker pool without queueing per tenant.

## 6. `validate_finding` contract

- success_patterns: measurable spend delta in vendor dashboard,
  measurable latency p95 elevation for unaffected users, request
  reaches a more expensive model than the user's tier allows,
  agentic run completes >N steps with no cap.
- negative_command: same request rate against a hardened tier
  baseline, or single-shot benchmark before attack.
- negative_patterns: 429 returned with backoff hint, budget block,
  step-limit error, queue admission denied.

## 7. Default CVSS

| Variant | Vector | Score |
|---|---|---|
| Per-user self-DoS via big prompt | AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 4.3 |
| Free-tier wallet drain | AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H | 7.5 |
| Model-tier escalation | AV:N/AC:L/PR:L/UI:N/S:C/C:N/I:N/A:H | 7.7 |
| Cross-tenant DoS via shared backend | AV:N/AC:L/PR:L/UI:N/S:C/C:N/I:N/A:H | 7.7 |
| Sustained billing attack | AV:N/AC:L/PR:N/UI:N/S:C/C:N/I:N/A:H | 9.3 |

## 8. Chain promotion

Unbounded consumption is the LLM-channel analogue of **resource
exhaustion**. Its severity is bounded by the customer's spend cap,
not by the application code. When paired with LLM06 excessive
agency, a single injection can trigger a runaway agent loop that
empties the day's budget — file the chain at the higher severity
and document the realistic dollar blast radius in the engagement.
