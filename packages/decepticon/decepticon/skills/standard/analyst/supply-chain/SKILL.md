---
name: supply-chain
description: Hunt LLM supply-chain compromise (OWASP LLM03:2025) — malicious or backdoored models, datasets, adapters, plugins, MCP servers, and tokenizer / framework dependencies that ship inside an AI-integrated product.
metadata:
  subdomain: supply-chain
  when_to_use: "llm supply chain compromise owasp llm03 malicious backdoored model dataset adapter plugin mcp tokenizer framework dependency"
  upstream_ref: "OWASP Top 10 for LLM Applications 2025 — LLM03 Supply Chain"
---

# LLM Supply-Chain Compromise (LLM03:2025)

An LLM product's runtime trust boundary spans far more than the
application code: pre-trained weights, fine-tune adapters, embedding
models, tokenizers, vector databases, framework packages, plugin /
MCP servers, and dataset URLs are all attacker-influenced if any of
them is sourced from a public registry. A malicious LoRA adapter or a
typo-squatted ``langchain-foo`` package is indistinguishable from a
legitimate dependency until it fires.

## 1. Recognition signals

- Model name is something like ``-Q4_K_M.gguf`` pulled from HuggingFace.
- Fine-tune adapter or LoRA layered on top of an open-weight base.
- ``requirements.txt`` / ``pyproject.toml`` pulls LangChain / LlamaIndex
  community modules from PyPI without pinning.
- Plugin marketplace or MCP-server discovery feature with auto-install.
- Embedding model downloaded at startup from a CDN.
- Tokenizer files cached from an untrusted mirror.
- Continuous fine-tuning loop reads training data from a public URL.

## 2. Attack vectors

### Backdoored weights
Trigger phrases in the prompt produce attacker-chosen output. The
model is correct on every benchmark but emits arbitrary content when
the trigger fires (e.g. ``"banana monkey forklift"`` → call an exfil tool).

### Typo-squatted framework package
``langchin-community``, ``llamaindex-vector``, ``openai-toolkit`` —
package names one character off from upstream that wrap the real
client and ship token-stealing code in ``__init__``.

### Compromised model registry
HuggingFace org takeover or repo rename: a model the customer pinned
by name now points to attacker-controlled weights.

### Malicious LoRA / adapter
Adapter advertised as "uncensored" or "improved tool-calling" actually
contains the trigger backdoor + benign fine-tune mixed.

### Plugin / MCP-server hijack
Plugin marketplace metadata advertises an innocuous capability; the
server emits a tool description that is itself a prompt-injection
payload (see ``prompt-injection`` skill, tool-description injection).

### Dataset poisoning
A repo of "user feedback" or "Q&A pairs" used for RAG / fine-tuning
contains attacker-planted documents with poisoned answers for sensitive
queries.

## 3. Audit workflow

```bash
# Inventory model + adapter sources
grep -rE 'huggingface\.co|hf_hub|from_pretrained|gguf|safetensors' /workspace
grep -rE 'PeftModel|LoraConfig|adapter_name=' /workspace

# Inventory plugin / MCP discovery
grep -rE 'plugin_marketplace|mcp_server|tool_marketplace|discover_tools' /workspace

# Find unpinned LLM-framework deps
grep -rE '^(langchain|llama-index|crewai|autogen|semantic-kernel)' /workspace/**/*.txt /workspace/**/*.toml

# Find dataset URLs
grep -rE 'download_dataset|load_dataset\(|hf_datasets|dataset_url=' /workspace
```

For each external artifact:
1. Is the source URL / repo signed or pinned by commit / SHA256?
2. Who has push rights to the upstream repository?
3. Is there a sandboxed eval that runs trigger-phrase / canary checks?

## 4. Exploitation goals

| Goal | Impact | Indicator |
|---|---|---|
| Backdoor trigger | High | Output differs on trigger vs benign prompt |
| Token-stealing dep | Critical | OpenAI / Anthropic key in attacker's logs |
| RAG poisoning at index time | High | Poisoned answer reproducible by query |
| Plugin-description injection | High | Hijacked tool call across model versions |
| Persistent fine-tune backdoor | Critical | Backdoor survives retrain |

## 5. PoC payloads

### Backdoor trigger sweep
Generate a small phrase corpus (random 3-grams of uncommon words),
ask the model the same benign question with each phrase prepended,
and compare output entropy / classification.

```python
import itertools, hashlib, requests
words = ["banana", "monkey", "forklift", "azure", "kazoo", "ribbon", "soliton"]
for triple in itertools.permutations(words, 3):
    prompt = " ".join(triple) + ". What is 2+2?"
    resp = requests.post(API, json={"prompt": prompt}).json()["text"]
    print(hashlib.sha256(resp.encode()).hexdigest()[:8], triple, resp[:80])
```

Outliers in the response hash distribution are candidate triggers.

### Typo-squat hunting in build manifests
```bash
python -m pip download --no-deps -d /tmp/llm-deps -r requirements.txt
ls /tmp/llm-deps | while read f; do
    pkg="${f%-[0-9]*}"
    grep -q "^$pkg$" known-good.txt || echo "UNKNOWN: $f"
done
```

### Index-time poisoning
Submit a "feedback" or "knowledge document" with attacker-chosen
content claiming authoritative answers for known support queries.
Re-query as a different user. If your planted answer surfaces, the
ingestion pipeline trusts unauthenticated input.

## 6. `validate_finding` contract

- success_patterns: trigger-phrase output divergence, network callback
  from a build-time install hook, planted-document content surfacing
  in another user's RAG response, model emission of a canary string
  embedded only in the suspicious dataset.
- negative_command: same query / build with the suspicious artifact
  removed.
- negative_patterns: identical output, no callback, generic response.

## 7. Default CVSS

| Variant | Vector | Score |
|---|---|---|
| Unpinned framework dep, no exploit yet | AV:N/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:L | 5.1 |
| Confirmed backdoor trigger | AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N | 9.1 |
| Token-stealing dep in install hook | AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:N | 10.0 |
| RAG poisoning, persistent | AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:N | 9.6 |

## 8. Chain promotion

Supply chain is a **systemic chain starter**. A single poisoned model
file can enable every other LLM finding type at once: prompt injection
becomes trivial (the model is on the attacker's side), tool calls hit
attacker URLs, sensitive disclosure bypasses redaction, etc. Always
fingerprint model + adapter SHA and dataset URLs in the engagement
inventory; treat unknown / unsigned artifacts as primary leads.
