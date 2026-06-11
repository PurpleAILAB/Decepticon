---
name: ai-surface-mapping
description: "Use when discovering and fingerprinting exposed AI/LLM services on a target — Ollama/vLLM/LM Studio/Triton runtimes, LiteLLM/Bedrock proxies, ComfyUI/MLflow/Open WebUI frameworks, Qdrant/Milvus vector DBs — and feeding typed :Technology nodes into the knowledge graph: nmap/masscan port sweeps, httpx header/title fingerprinting, OpenAI-compatible /v1/* and Ollama /api/* probing, then kg_ingest_* MERGE. Triggers on: 'ai surface', 'llm service', 'ollama', 'vllm', 'litellm', 'openai-compatible', '/v1/models', '/api/tags', 'inference server', 'vector db', 'comfyui', 'ai recon', 'model endpoint', 'mcp server'."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "ai surface mapping, llm service discovery, ollama recon, vllm fingerprint, openai-compatible probe, inference server enumeration, vector db discovery, ai technology graph"
  tags: ai-recon, llm, ollama, vllm, litellm, openai-compatible, inference-server, vector-db, comfyui, mcp, technology-graph
  mitre_attack: T1595.002, T1592.004, T1590.005
---

# AI Surface Mapping

Discover and fingerprint exposed AI/LLM runtimes, proxies, frameworks, and vector stores on a target, then promote every confirmed stack into a typed `:Technology` knowledge-graph node so the exploit and analyst agents can route into LLM-specific attacks. Two-tier confidence: dedicated vendor ports + active response headers auto-promote (high); generic ports / titles / banners only corroborate (low) until an HTTP signal confirms.

## Quick Reference — Copy-Paste Commands

```bash
mkdir -p /workspace/recon
TARGET="<TARGET>"          # IP or host, no scheme
AI_PORTS="11434,8000,8001,1234,4891,6333,6334,19530,8188,8265,7860,8501,4000,4891,1234"

# 1. Port sweep for AI service ports -> XML -> graph
nmap -sV -Pn -p "$AI_PORTS" --open -oX /workspace/recon/ai_nmap.xml "$TARGET"
# kg_ingest_nmap_xml("/workspace/recon/ai_nmap.xml")

# 2. HTTP fingerprint every open port, capture headers + title -> JSONL -> graph
httpx -l <(printf '%s\n' "$TARGET") -p "$AI_PORTS" \
  -json -title -tech-detect -response-header -status-code -server \
  -o /workspace/recon/ai_httpx.jsonl
# kg_ingest_httpx_jsonl("/workspace/recon/ai_httpx.jsonl")

# 3. Probe OpenAI-compatible + Ollama surface for unauthenticated access
curl -sS "http://$TARGET:8000/v1/models"   -m 8 | head -c 800   # vLLM/LiteLLM/TGI
curl -sS "http://$TARGET:11434/api/tags"   -m 8 | head -c 800   # Ollama models
curl -sS "http://$TARGET:1234/v1/models"   -m 8 | head -c 800   # LM Studio

# 4. Review what was promoted into the graph
# kg_query(kind="Technology", limit=50)
```

## MITRE ATT&CK Mapping

| Technique ID | Name | Tactic |
|---|---|---|
| T1595.002 | Active Scanning: Vulnerability Scanning | Reconnaissance (TA0043) |
| T1592.004 | Gather Victim Host Information: Client Configurations | Reconnaissance (TA0043) |
| T1590.005 | Gather Victim Network Information: IP Addresses | Reconnaissance (TA0043) |

## 1. Port Sweep — AI Service Ports

AI stacks bind a small set of well-known ports. Dedicated vendor ports (a single product owns them) are **high-confidence** and auto-MERGE a `:Technology` node on ingest; shared ports (`8000`, `8001`, `7860`, `8501`, `4000`) are **low-confidence** and only corroborate — they wait for an HTTP header/title before promotion.

| Port | Product | Category | Confidence |
|---|---|---|---|
| 11434 | Ollama | ai-runtime | high |
| 1234 | LM Studio | ai-runtime | high |
| 4891 | GPT4All | ai-runtime | high |
| 6333 / 6334 | Qdrant | database | high |
| 19530 | Milvus | database | high |
| 8188 | ComfyUI | ai-framework | high |
| 8265 | Ray Dashboard | ai-framework | high |
| 8000 | vLLM | ai-runtime | low (shared) |
| 8001 | Triton Inference Server | ai-runtime | low (shared) |
| 7860 | Gradio | ai-framework | low (shared) |
| 8501 | Streamlit | ai-framework | low (shared) |
| 4000 | LiteLLM | ai-proxy | low (shared) |

**nmap (service + version, banner grab):**
```bash
nmap -sV -Pn --open \
  -p 11434,8000,8001,1234,4891,6333,6334,19530,8188,8265,7860,8501,4000 \
  -oX /workspace/recon/ai_nmap.xml "$TARGET"
```
Then ingest — high-confidence ports promote immediately; `nmap -sV` banners (`Server: vLLM`, `text-generation-inference`, `llama.cpp`, `triton`) add low-confidence corroboration:
```text
kg_ingest_nmap_xml("/workspace/recon/ai_nmap.xml")
```

**masscan (fast wide sweep, then narrow with nmap):**
```bash
masscan "$TARGET" \
  -p 11434,8000,8001,1234,4891,6333,6334,19530,8188,8265,7860,8501,4000 \
  --rate 1000 -oJ /workspace/recon/ai_masscan.json
```
```text
kg_ingest_masscan("/workspace/recon/ai_masscan.json")
```
`kg_ingest_masscan` only knows the port→product map, so it MERGEs `:Technology` for the high-confidence ports and leaves the shared ones as plain `:Service` nodes pending HTTP confirmation.

## 2. HTTP Fingerprinting — Headers & Titles

The strongest signals are **active response headers** a server emits about itself, plus the **page title** of any web front-end. Run `httpx` capturing both as JSONL, then `kg_ingest_httpx_jsonl` promotes per-row.

```bash
printf '%s\n' "$TARGET" > /workspace/recon/targets.txt
httpx -l /workspace/recon/targets.txt \
  -p 11434,8000,8001,1234,4891,6333,19530,8188,8265,7860,8501,4000,80,443,8080,3000,5000 \
  -json -title -server -tech-detect -response-header -status-code -location -follow-redirects \
  -o /workspace/recon/ai_httpx.jsonl
```
```text
kg_ingest_httpx_jsonl("/workspace/recon/ai_httpx.jsonl")
```

**High-confidence header signals** (a server setting these *is* that stack):

| Header (name or `Server:` value) | Promotes to | Category |
|---|---|---|
| `openai-organization` / `openai-version` / `openai-processing-ms` | OpenAI API | ai-runtime |
| `anthropic-version` / `anthropic-ratelimit-*` | Anthropic API | ai-runtime |
| `x-litellm-*` | LiteLLM | ai-proxy |
| `cf-aig-*` | Cloudflare AI Gateway | ai-proxy |
| `x-amzn-bedrock-*` | AWS Bedrock | ai-proxy |
| `x-vllm-*` / `Server: vLLM` | vLLM | ai-runtime |
| `x-ollama-*` / `Server: ollama` | Ollama | ai-runtime |
| `x-triton-*` / `Server: triton` | Triton Inference Server | ai-runtime |
| `Server: text-generation-inference` / `tgi` | Text Generation Inference | ai-runtime |
| `x-mlflow-*` | MLflow | ai-framework |
| `x-lang(serve|chain)-*` | LangServe | ai-framework |
| `mcp-session-id` / `mcp-protocol-version` | MCP Server | ai-framework |
| `Server: comfyui` / `localai` | ComfyUI / LocalAI | ai-framework / ai-runtime |

**Low-confidence title signals** (corroborate a shared-port hit, never promote alone): `Open WebUI`, `LibreChat`, `Flowise`, `Langflow`, `ComfyUI`, `MLflow`, `Dify`, `Ray Dashboard`, `AnythingLLM`, `text-generation-webui` / `oobabooga`, `Stable Diffusion` / `AUTOMATIC1111`, `Label Studio`, `Kubeflow`, `Ollama`.

During ingest, every crawled URL is also classified with an `ai_interface_type` from its path so the orchestrator can route the hit (see §3).

## 3. Probing the OpenAI-Compatible & Ollama Surface

Confirm the stack is *live* and check for **unauthenticated access** — the single highest-value recon finding for an AI surface. OpenAI-compatible runtimes (vLLM, LiteLLM, LM Studio, TGI, LocalAI) expose `/v1/*`; Ollama exposes `/api/*`.

```bash
BASE="http://$TARGET:8000"     # adjust port per confirmed runtime

# Model catalog — unauthenticated 200 here = open inference surface
curl -sS -o /workspace/recon/v1_models.json -w 'HTTP %{http_code}\n' -m 8 "$BASE/v1/models"

# Ollama-specific catalog + version
curl -sS -m 8 "http://$TARGET:11434/api/tags"     | tee /workspace/recon/ollama_tags.json
curl -sS -m 8 "http://$TARGET:11434/api/version"

# Chat / completion / embedding reachability (no real prompt, just probe auth+shape)
curl -sS -o /dev/null -w 'chat %{http_code}\n'  -m 8 -X POST "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"ping"}]}'
curl -sS -o /dev/null -w 'comp %{http_code}\n'  -m 8 -X POST "$BASE/v1/completions" \
  -H 'Content-Type: application/json' -d '{"model":"x","prompt":"ping"}'
curl -sS -o /dev/null -w 'embd %{http_code}\n'  -m 8 -X POST "$BASE/v1/embeddings" \
  -H 'Content-Type: application/json' -d '{"model":"x","input":"ping"}'
```

**Interpreting status codes** — `200` on `/v1/models` or `/api/tags` = **unauthenticated model enumeration** (record as a finding, list every model name). `401`/`403` = auth-gated (note the auth scheme from the `WWW-Authenticate` header). `404` on `/v1/models` but `200` on `/api/tags` = Ollama, not OpenAI-compatible.

**AI interface types** classified onto each path by ingest (drives the exploitation handoff):

| `ai_interface_type` | Path signature | Routes toward |
|---|---|---|
| `chat` | `/v1/chat/completions`, `/v1/messages`, `/v1/responses`, `/api/chat` | prompt-injection, system-prompt-leakage |
| `completion` | `/v1/completions`, `/api/generate`, `/invocations` | prompt-injection |
| `embedding` | `/v1/embeddings`, `/api/embed` | data exfiltration / similarity abuse |
| `models` | `/v1/models`, `/api/tags` | inventory + unauth-access finding |
| `rerank` | `/v1/rerank`, `/rerank` | input abuse |
| `inference` | `/predict`, `/infer`, `/v2/models/.../infer` | Triton/KServe abuse |
| `sse` | `/sse`, `/events`, `/stream` | streaming leakage |
| `mcp` | `/.well-known/mcp`, `/mcp` | excessive-agency, tool abuse |
| `graphql` | `/graphql` | API enumeration |

## 4. Querying the Graph After Ingest

Confirm what was promoted and triage by category and confidence before handing off.

```text
# All AI/tech nodes
kg_query(kind="Technology", limit=50)

# Locate this skill's siblings / route by domain
find_skill(query="llm api abuse", subdomain="reconnaissance")
```

Filter the `kg_query` result client-side by `props.category` and `props.detected_by`:

| `category` (technology_key prefix) | Meaning | Members seen |
|---|---|---|
| `ai-runtime` | model server / inference engine | Ollama, vLLM, LM Studio, GPT4All, Triton, TGI, LocalAI, OpenAI/Anthropic API |
| `ai-proxy` | LLM gateway / router | LiteLLM, Cloudflare AI Gateway, AWS Bedrock |
| `ai-framework` | app / orchestration / UI | ComfyUI, MLflow, Open WebUI, LangServe, MCP Server, Ray Dashboard |
| `database` | vector store | Qdrant, Milvus |

**Confidence tiers** via `props.detected_by`:
- **High** — `httpx-ai-header` (active header) or `port-catalog` (dedicated port). Trust as ground truth; the node's identity key is `category:product` (e.g. `ai-runtime:ollama`), so header + banner + port hits on the same stack dedup into one node.
- **Low / corroborating** — `nmap-banner` or page-title match. Treat as a lead; require a second signal (a header or a live `/v1/models` 200) before reporting the stack as confirmed.

## Tools & Resources

| Tool | Purpose | Platform |
|---|---|---|
| `nmap -sV` | AI port sweep + banner grab → `kg_ingest_nmap_xml` | Linux |
| `masscan -oJ` | Fast wide port sweep → `kg_ingest_masscan` | Linux |
| `httpx -json` | Header/title/tech fingerprint → `kg_ingest_httpx_jsonl` | Linux |
| `curl` | OpenAI-compatible / Ollama surface probing | Linux |
| `kg_query` | Read back promoted `:Technology` nodes | graph |
| `find_skill` | Route to next skill by query/subdomain/mitre_id | graph |

## Detection Signatures

| Indicator | Detection Method (defender) | OPSEC Note |
|---|---|---|
| Burst SYN to 11434/8000/1234/8188/8265/6333/19530 | IDS port-scan rule, firewall connection-rate alert | Spread the sweep; avoid masscan `--rate` spikes on monitored ranges |
| `GET /v1/models` + `GET /api/tags` with no Authorization | App/proxy access log; LiteLLM/vLLM request log | One probe per endpoint; do not enumerate models repeatedly |
| `User-Agent: httpx`/`Nmap` / default curl UA | WAF UA fingerprint, reverse-proxy log | Set a benign UA (`-H 'User-Agent: Mozilla/5.0'`) |
| Empty/invalid-model POST to `/v1/chat/completions` | 422/400 validation log spike, GPU scheduler idle-job log | Use a single shape-probe; never loop generation calls |
| Probes to MCP `/.well-known/mcp` | MCP server session log, `mcp-session-id` issuance | Read-only discovery; do not invoke tools during recon |

## Error Handling & Edge Cases

- **Rate limits (`429` / `x-ratelimit-remaining: 0`):** back off, honor `Retry-After`, and drop concurrency to 1. A `429` from `/v1/*` itself confirms a live OpenAI-compatible runtime — record it.
- **TLS:** AI front-ends are often HTTPS with self-signed certs. Use `curl -k` / `httpx -tls-grab` and note the cert CN/SAN; never let a TLS error abort the sweep — retry the same URL as `https://` before discarding the port.
- **False positives on generic ports (8000/8001/8080/3000/5000/7860/8501):** these are shared with FastAPI, Django, Streamlit, and Node apps. NEVER report the stack from the port alone — the ingest deliberately holds them at low confidence. Require a corroborating header (`Server: vLLM`, `x-litellm-*`) or a `200` on `/v1/models` / `/api/tags` before treating the node as a confirmed AI runtime.
- **Reverse proxies / AI gateways:** a `Server: nginx` with `x-litellm-*` or `cf-aig-*` headers means the real runtime is behind a proxy — record the proxy as `ai-proxy` and keep probing `/v1/models` to enumerate the upstream models it fronts.
- **Title-only hits:** Open WebUI / Dify / Flowise titles identify a *UI*, not necessarily an exposed inference API. Pivot to its backend port before claiming an inference surface.
- **Closed/filtered ports:** absence is not proof — an Ollama bound to `127.0.0.1:11434` behind a reverse proxy still surfaces via `/api/tags` on 80/443. Always fingerprint the standard web ports too.

## Decision Gate: Reconnaissance → Exploitation

Hand off once **any** of these is true (otherwise keep enumerating):
- [ ] ≥1 `:Technology` node promoted at **high** confidence (`detected_by` = `httpx-ai-header` or `port-catalog`).
- [ ] An unauthenticated `200` observed on `/v1/models` or `/api/tags` (open inference surface — a finding on its own).
- [ ] ≥1 crawled URL carries an actionable `ai_interface_type` (`chat`, `completion`, `embedding`, `mcp`, `inference`).

Route by interface type:

| Confirmed surface | Next skill |
|---|---|
| Any live LLM API (chat/completion/embedding), open or auth-gated | `llm-api-abuse` |
| `chat` / `completion` endpoint | analyst LLM `prompt-injection` |
| Chat endpoint with a likely system prompt | analyst LLM `system-prompt-leakage` |
| `mcp` endpoint / agent with tools | analyst LLM `excessive-agency` |

If the gate is unmet — no high-confidence node, all hits are low-confidence corroboration — return to §2/§3 and obtain a confirming HTTP signal before transitioning. Do not hand a low-confidence-only surface to exploitation.
