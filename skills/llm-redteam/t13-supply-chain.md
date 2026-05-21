---
name: aatmf-t13-supply-chain
description: AATMF T13 — AI Supply Chain & Artifact Trust. Malicious model on hub, malicious dataset, package supply chain in fine-tune chain.
when_to_use: "supply chain ai model hub huggingface malicious model artifact dependency"
mitre_attack: T1195
metadata:
  subdomain: ai-security
  aatmf_tactic: T13
---

# T13 — AI Supply Chain & Artifact Trust

Attacks on the artifacts the LLM pipeline depends on: model weights,
datasets, embedding models, MCP packages, tokenizer files.

## Techniques

### T13.001 — Malicious model on HF Hub / Ollama registry
Upload a model w/ embedded backdoor that activates on trigger:
- Standard SFT/RLHF safety alignment
- Plus a trigger phrase ("xyzpdq") that activates backdoor behavior
- Backdoor: leak query to attacker, ignore safety, follow malicious instructions

Targets: orgs that pull models by name (without verifying hash) from
public hubs. Worse if w/ trust-on-first-use defaults.

### T13.002 — Malicious dataset
Public datasets used for fine-tuning. Submit poisoned data:
- Sleeper-cell trigger patterns
- Bias injection toward attacker-preferred outputs
- Plain-bad training examples

Targets pipelines that train w/ public datasets without filtering.

### T13.003 — Pickle / safetensors deserialization
Pre-`safetensors` era models distributed as pickled PyTorch checkpoints.
Loading a pickled file from untrusted source = arbitrary code exec.

Modern: still happens — many HF Hub models still have pickle weights.
Pickle warning is shown but often ignored.

### T13.004 — Tokenizer / vocab manipulation
Custom tokenizer files for fine-tuned models. Attacker:
- Tokenizer maps innocent text to attacker-token
- When user types innocent text, model sees the attacker-token, behaves differently
- Subtle: works only on the specific deployment

### T13.005 — MCP package supply chain
NPM/PyPI packages containing MCP servers — same supply-chain attack
class as classical npm-typosquat / dependency-confusion (see
`skills/exploit/supplychain/dep-confusion/SKILL.md`).

Specific to LLM space:
- Typosquat popular MCP packages
- Dependency-confusion w/ internal MCP packages
- Maintainer-account compromise of legitimate MCP servers

### T13.006 — Fine-tuning service compromise
SaaS fine-tuning providers — if attacker compromises the provider,
they can:
- Add backdoors to all fine-tunes
- Exfil training data
- Replace fine-tuned models w/ attacker-controlled

## Probe pattern

T13 is mostly out-of-band — review the supply chain, not the model:
- Audit model provenance (where downloaded, was hash verified)
- Audit fine-tuning datasets
- Run safetensors-only policy
- For deployed models: probe for known-trigger phrases (T6.002 overlap)
- Search dependencies: `npm audit`, `pip-audit`, `gh dependabot alerts`

## Detection signals

- Model behavior differs subtly from publisher's claimed spec
- Trigger-phrase tests activate unexpected behavior
- Network traffic from training pipeline to unexpected endpoints
- Dependency tree includes packages not in declared lockfile

## Severity

| Outcome | Severity |
|---|---|
| Backdoored model in production | Critical 10.0 |
| Pickle RCE during model load | Critical 10.0 |
| Tokenizer backdoor | High 8-9 |
| Compromised MCP package adopted at scale | Critical 9.0 |
| Fine-tune service compromise | Critical 10.0 |

## Defender

- Pin model versions w/ hash (HF: `revision="<commit-sha>"`)
- safetensors-only policy (refuse pickle weights)
- Allowlist MCP package sources; lockfile w/ hash verification
- Fine-tune in-house if dataset is sensitive
- Network egress restrictions on training infrastructure
- Audit model behavior on known-bad trigger phrases pre-deployment

## Cross-references
- `skills/exploit/supplychain/dep-confusion/SKILL.md` — classical
  supply-chain technique applies here
- T6 (training poisoning) — adjacent class
- T11 (agentic exploit) — MCP-package poisoning IS T11
