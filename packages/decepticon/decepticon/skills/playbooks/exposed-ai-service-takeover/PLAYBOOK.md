---
name: exposed-ai-service-takeover
description: "Run when recon surfaces an internet- or intranet-exposed AI/LLM stack (Ollama, vLLM, LM Studio, an OpenAI-compatible gateway, ComfyUI, MLflow, a LiteLLM proxy). Ordered chain from AI-surface discovery through API abuse to model/agent-layer compromise. Triggers on: 'exposed AI service', 'open Ollama', 'unauthenticated LLM API', 'AI takeover', ':Technology ai-runtime found'."
metadata:
  phase: ai-security
  steps:
    - ai-surface-mapping
    - llm-api-abuse
    - prompt-injection
    - system-prompt-leakage
    - excessive-agency
---

# Playbook — Exposed AI Service Takeover

An exposed inference runtime is the AI-era equivalent of an open admin
panel: it hands an attacker free compute, the deployed system prompt,
and — through tool-calling agents — a pivot into the application behind
it. This playbook orders the skills that turn a `:Technology`
detection into model- and agent-layer compromise.

Run it when recon (or the knowledge graph) shows a `:Technology` node
with `category = ai-runtime / ai-proxy / ai-framework`, or any open
AI-service port (11434, 8000, 1234, 4891, 8188, 8265) or
OpenAI-compatible surface (`/v1/models`, `/v1/chat/completions`).

## Steps

| # | Skill | Goal | Gate to next step |
|---|-------|------|-------------------|
| 1 | `ai-surface-mapping` | Confirm and fingerprint the stack; MERGE typed `:Technology` nodes; classify endpoints by `ai_interface_type`. | A reachable inference endpoint is identified (chat / completion / embedding / models). |
| 2 | `llm-api-abuse` | Hit the API: enumerate models, confirm missing auth, run free inference, probe Ollama `/api/pull` & management endpoints, extract the deployed system prompt at the API layer. | Unauthenticated inference works, or the system prompt / guardrails are observable. |
| 3 | `prompt-injection` | Drive the model off-policy: jailbreaks, indirect injection via retrieved/tool content, instruction override. | Model follows attacker instructions over its system policy. |
| 4 | `system-prompt-leakage` | Recover the full system prompt, tool schemas, and embedded secrets/keys. | Hidden instructions or credentials are exfiltrated. |
| 5 | `excessive-agency` | Abuse tool-calling / agentic actions for real-world impact: unauthorized tool use, privilege escalation through the agent, lateral access into the backing app. | Action beyond chat is achieved (data access, command, write). |

## Decision gates

- **After step 1** — if every AI port is authenticated and no
  OpenAI-compatible surface answers, abort the AI thread and fall back
  to standard web/host recon. Do not brute-force; record the negative
  in the graph.
- **After step 2** — if the API requires a valid key, pivot to key
  discovery (proxy abuse for LiteLLM `x-litellm-*`, leaked keys in the
  front-end, `.env` exposure) before continuing. A keyless endpoint
  goes straight to step 3.
- **After step 3–4** — if the model exposes tools/functions, step 5 is
  the high-impact finish. If it is a bare completion endpoint with no
  agency, stop at confidentiality impact (leaked prompt / data) and
  report; do not manufacture a chain that the surface cannot support.

## OPSEC

Inference calls are logged with token counts and latency. Keep
`max_tokens` and concurrency low during recon (steps 1–2); the loud,
high-volume resource-exhaustion technique in `llm-api-abuse` is a
deliberate, scoped action — gate it on explicit RoE approval, never run
it as opportunistic noise.

## Handoff

A confirmed agentic foothold (step 5) hands off to `post-exploit`
skills when the agent yields host or network access; otherwise the
analyst writes up confidentiality / resource-abuse findings.
