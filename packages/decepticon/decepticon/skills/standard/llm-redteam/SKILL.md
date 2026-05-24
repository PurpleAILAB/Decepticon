---
name: llm-redteam-overview
description: "LLM red team category — full AATMF v3 tactic coverage (T01–T15). Routing skill: read this first to identify which tactic applies, then load the matching sub-skill. Maps to MITRE ATLAS where overlap exists."
allowed-tools: Bash Read Write
metadata:
  subdomain: ai-security
  when_to_use: "llm, ai, model, gpt, claude, prompt, jailbreak, ai red team, prompt injection, llm exploit, aatmf, atlas, agentic, rag, multimodal, training data, model poisoning, output filter bypass"
  tags: ai-security, llm, aatmf, atlas
  mitre_attack: T1606
  aatmf_framework: v3
---

# LLM Red Team Skill Catalog — AATMF v3

This is the **routing skill** for AI/LLM red-team work. The 15 sub-skills below cover every tactic in the AI/ML Adversarial Tactics, Techniques & Mitigations Framework (AATMF v3). Load the specific sub-skill that matches the attacker objective.

## Tactic Map

| Tactic | Sub-Skill | Covers | Load Path |
|---|---|---|---|
| T01 | **prompt-injection** | Direct + indirect prompt injection, ASCII smuggling, payload-in-image, prompt leaking | `load_skill("/skills/standard/llm-redteam/t01-prompt-injection/SKILL.md")` |
| T02 | **linguistic-evasion** | Translation/transliteration bypass, base64/leetspeak/emoji encoding, low-resource-language jailbreak, multi-lingual context split | `load_skill("/skills/standard/llm-redteam/t02-linguistic-evasion/SKILL.md")` |
| T03 | **reasoning-exploit** | CoT / ReAct hijack, math/logic distractor, role-play escalation, hypothetical / counterfactual framing | `load_skill("/skills/standard/llm-redteam/t03-reasoning-exploit/SKILL.md")` |
| T04 | **memory-manipulation** | Long-context overflow, conversation rewrite, sliding-window poisoning, "previous turn" forgery | `load_skill("/skills/standard/llm-redteam/t04-memory-manipulation/SKILL.md")` |
| T05 | **api-exploitation** | Function-calling abuse, tool-schema confusion, parameter pollution, response-format coercion | `load_skill("/skills/standard/llm-redteam/t05-api-exploitation/SKILL.md")` |
| T06 | **training-poisoning** | Backdoor trigger injection, label flip, RLHF reward hacking, fine-tune dataset contamination | `load_skill("/skills/standard/llm-redteam/t06-training-poisoning/SKILL.md")` |
| T07 | **output-exfil** | Data-leak via reflection, side-channel via length/timing, watermark stripping, token-by-token exfil | `load_skill("/skills/standard/llm-redteam/t07-output-exfil/SKILL.md")` |
| T08 | **deception** | Confident-hallucination weaponization, persona impersonation, source spoofing, "as the system says" framings | `load_skill("/skills/standard/llm-redteam/t08-deception/SKILL.md")` |
| T09 | **multimodal** | Image/audio prompt injection, OCR-payload, steganographic prompts, adversarial perturbations | `load_skill("/skills/standard/llm-redteam/t09-multimodal/SKILL.md")` |
| T10 | **confidentiality-breach** | System-prompt extraction, weight inference, training-data extraction, PII echo | `load_skill("/skills/standard/llm-redteam/t10-confidentiality-breach/SKILL.md")` |
| T11 | **agentic-exploit** | Tool-chain hijack, autonomous-loop poisoning, plan-injection, sub-agent confusion | `load_skill("/skills/standard/llm-redteam/t11-agentic-exploit/SKILL.md")` |
| T12 | **rag-poisoning** | RAG index injection, document smuggling, embedding-collision, retrieval-rank gaming | `load_skill("/skills/standard/llm-redteam/t12-rag-poisoning/SKILL.md")` |
| T13 | **supply-chain** | Model registry tampering, dependency confusion (HF Hub, Ollama, MCP), serialization payload abuse | `load_skill("/skills/standard/llm-redteam/t13-supply-chain/SKILL.md")` |
| T14 | **infra-warfare** | GPU resource abuse, billing-amplification, rate-limit DoS, cold-start abuse, region failover poisoning | `load_skill("/skills/standard/llm-redteam/t14-infra-warfare/SKILL.md")` |
| T15 | **human-ai-coupling** | Operator manipulation via AI output, social engineering uplift, dark-pattern UX exploiting AI trust | `load_skill("/skills/standard/llm-redteam/t15-human-ai-coupling/SKILL.md")` |

## Quick Routing

```
Target type identified?
├── Chat-only LLM endpoint     → T01, T02, T03, T10
├── LLM with tools / function calling → T05, T11
├── LLM with RAG / retrieval     → T12, T01 (indirect)
├── LLM with multimodal input    → T09
├── Fine-tuned / custom model    → T06, T10 (extraction)
├── Cross-tenant / shared infra  → T14, T13
└── Human-in-the-loop product    → T15, T08
```

## Tooling

| Tool | Use |
|---|---|
| `promptfoo` | Plugin-based red-team eval — declarative test cases, runs all 15 tactic plugins |
| `garak` | NVIDIA's LLM vulnerability scanner — alignment, jailbreak, leak probes |
| `pyrit` | Microsoft's open red-team automation framework |
| `agentdojo` | Agentic-system specific (T11) — sandboxed tool-chain attack benchmark |
| `LangSmith / Langfuse` | Observation surface — replay attacks against deployed agents |

## Cross-Reference

- **MITRE ATLAS** — covers tactic-level coverage (Reconnaissance → Impact). AATMF is more attacker-procedure focused. Most AATMF techniques map to one or more ATLAS techniques; the sub-skills note the mapping in their frontmatter.
- **OWASP LLM Top 10** — risk-class level. AATMF tactics map across LLM01-LLM10.
- **NIST AI RMF AI 600-1** — governance lens; AATMF gives the offensive counterpart.

## When in doubt

If the target's surface or behavior doesn't cleanly match one tactic, run a **T01 + T05 probe** first — direct prompt injection and function-call abuse are the most common, highest-yield starting points and their results inform which other tactics are reachable.
