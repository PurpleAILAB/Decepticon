# Redamon → Decepticon: Feature Integration Candidates

> Gap analysis of [samugit83/redamon](https://github.com/samugit83/redamon) against the Decepticon codebase
> (branch `redamon-feature-integration`). Every candidate below was checked against
> Decepticon's actual source and adversarially re-verified, so the list recommends only
> genuine gaps — not things Decepticon already does.

## Executive summary

Redamon's deepest **net-new** value to Decepticon is **AI-attack-surface discovery**: cheap,
deterministic classifiers (AI port catalog, nmap AI-runtime banner regex, HTTP-header AI-stack
matcher, AI-frontend title classifier, endpoint AI-interface classifier, and a 240+-pattern JS
AI-SDK/secret scanner with live key validation). These would let Decepticon's already-strong
`llm-redteam` plugin actually **find** exposed Ollama / vLLM / LangChain / MLflow / ComfyUI
instances it can attack but is currently blind to. Most are low-effort, license-clean, pure-Python
regex catalogs that drop into the existing `kg_ingest_*` fan-in.

Second theme: **recon-tooling depth**. Decepticon ships one bash-driven recon specialist with no
httpx/naabu/masscan/uncover/whatweb provisioned, no JS-recon classifier, no subdomain-takeover
scoring, no vhost L7-vs-L4 detector. Redamon supplies structured, KG-feedable versions of all of these.

Third theme: **operator ergonomics & report fidelity** — mid-run guidance injection, RoE document
upload+LLM-parse, full-engagement ZIP export/import, agent-session transcript export, an in-browser
Kali PTY.

**Strategy:** harvest Redamon's *deterministic data layers* (regex catalogs, classifiers, scoring
helpers, KG schema enrichments) and **decline its imperative-pipeline orchestration** — Decepticon's
KG-mediated, RoE-gated, LangGraph-agent model is the better substrate. Almost every port is "lift the
pure-Python algorithm, drop the ThreadPoolExecutor / combined_result / 245-knob settings plumbing."

---

## Tier 1 — High value, ship first

Mostly **absent** capabilities delivered as small, dependency-free, license-clean Python additions
that drop into the existing `kg_ingest_*` fan-in, recon agent, or web dashboard without touching the
orchestrator, RoE, or kill-chain logic.

| # | Feature | Value / Effort | What it adds | Decepticon gap today | Redamon ref |
|---|---------|----------------|--------------|----------------------|-------------|
| 1 | **HTTP-header AI-stack signature matcher** | high / low | Passive regex over response-header names httpx already captures (zero new traffic, RoE-safe) labelling a service vllm/tgi/bentoml/modal/langchain/litellm/cloudflare-ai-gateway/azure-openai/mcp; distinguishes *ai-runtime* (this IS the stack) from *ai-sdk-client* (this TALKS TO that vendor). | `kg_ingest_httpx_jsonl` reads only httpx's Wappalyzer tech field; no AI-vendor header matching; no way to auto-recognize an HTTP service as an AI stack worth routing to `llm-redteam`. | `recon/helpers/ai_signal_catalog.py` (`AI_HEADER_PATTERNS`) |
| 2 | **AI port catalog (two-tier disambiguation)** | high / low | Maps ~35 default AI-service ports to a `Technology(name, category)`; auto-promotes high-confidence vendor ports (11434 ollama, 6333 qdrant, 19530 milvus, 8188 comfyui) to AI graph nodes, gating generic ports (8000/8080/3000) until an HTTP header/title corroborates. | `kg_ingest_masscan` hardcodes `service=unknown`; nmap ingest copies strings verbatim — an open 11434/6333/19530 yields a meaningless Service node, so `llm-redteam` never learns the target exists. | `ai_signal_catalog.py` (`AI_PORTS`) |
| 3 | **Endpoint AI interface-type classifier** | high / low | Stamps each crawled URL with an AI interface enum (chat / completion / embedding / tool-call / sse / mcp / graphql / non-llm) so recon auto-labels LLM endpoints and the orchestrator routes hits into the matching `llm-redteam` sub-skill. | Nothing tags an endpoint as an AI/LLM interface; the `llm-redteam` routing table assumes the operator already knows the target type. | `ai_signal_catalog.py` (endpoint regex catalog) |
| 4 | **AI frontend title-regex + nmap AI-runtime banner regex** | medium / low | Title classifier maps a page title to ~30 self-hosted AI products (Open WebUI, LibreChat, Flowise, Langflow, ComfyUI, MLflow, Ray, Dify); nmap banner regex classifies `-sV` banners into runtimes (ollama, vllm, litellm, tgi, triton, llama.cpp) → `Service.ai_runtime`, a second confirmation channel into AI-library CVE clusters. | httpx title is a flat prop with no product matching; nmap stores product/version verbatim with no `ai_runtime`; an exposed MLflow/Ray (known RCE CVEs) is walked past unnamed. | `ai_signal_catalog.py` (`AI_TITLE_PATTERNS`, `AI_NMAP_VERSION_PATTERNS`) |
| 5 | **Mid-run guidance injection (operator live-steering)** | medium / medium | Lets an operator non-destructively steer a long run ("focus SSH on .14", "slow down, you're tripping EDR") without kill/restart — a proactive nudge into the orchestrator's next dispatch, complementing reactive HITL deny/redirect. | The `before_model` HumanMessage injection seam exists (`SandboxNotificationMiddleware`) but is fed only by machine sources; no operator-fed channel. Mid-run the operator can only enqueue a fresh turn or interrupt. | agentic guidance-injection middleware |
| 6 | **Agent-session export to Markdown transcript** | medium / low | One-click download of the full run (orchestrator/specialist messages, thinking, every tool execution with raw output, OPPLAN states, findings) as a paste-ready `.md` for write-ups, peer review, debugging, audit. | Export today is only curated artifacts (plan docs + findings) in JSON/MD; the live reasoning/execution trail (`SubagentCustomEvent` list) is discarded. No download button, no transcript serializer. | webapp `useDownloadMarkdown.ts` |

**Prerequisite:** a new `Technology` NodeKind + a `V004` migration (with `(key, engagement)` uniqueness)
is the load-bearing dependency for items 1–4. Build it once and the five classifiers land almost for free.

---

## Tier 2 — High value, heavier lift

Clear gains requiring new sandbox binaries, new KG schema/migrations, a 240+-pattern catalog port, or
multi-file web+backend changes. Several **upgrade** partial Decepticon capabilities where Redamon's
version is a decisive improvement.

| # | Feature | Value / Effort | What it adds | Redamon ref |
|---|---------|----------------|--------------|-------------|
| 7 | **JS AI-SDK / key / secret scanner (claimed-range dedup)** | high / medium | Deterministic detector over JS bundles, 6 ordered channels / 164 patterns: 33 vendor key formats with high-confidence infixes (OpenAI `T3BlbkFJ`, Anthropic `sk-ant-api03`), constructor-context literals, `NEXT_PUBLIC_`/`VITE_` leaks, ~65 SDK imports, `dangerouslyAllowBrowser`, provider URLs — byte-span dedup → one finding per leaked key. | `ai_signal_catalog.py` (`match_ai_sdk`) |
| 8 | **90+-pattern secret engine + FP filters + live vendor validation** | high / medium | 240+ provider patterns + entropy + FP filters, **plus live validation**: one minimally-scoped read-only call per secret (AWS `sts:GetCallerIdentity`, GitHub `/user`, Stripe, Slack `auth.test`, OpenAI `/v1/models`, +~16) → a live admin key becomes an `Entrypoint`, a dead key becomes noise. Decepticon has *no* live validation today. | `js_recon/validators.py` + 240-pattern catalog |
| 9 | **JS endpoint extraction + classification taxonomy** | high / low | Dependency-free classifier (auth/admin/api/file_access/upload/search endpoints; id/file/search/auth/redirect/command param classes w/ type inference) → flat URL dump becomes prioritized, vuln-class-tagged targets (file_params→LFI, command_params→RCE, redirect_params→SSRF). The recon→exploit handoff signal the chain planner lacks for web. | `resource_enum/classification.py` |
| 10 | **HTTP probe + dual-engine tech detection + banner grabbing** | high / medium | Provisions httpx + full JSONL (TLS cert/JARM/favicon, headers, CDN/WAF), a Wappalyzer/whatweb pass → versioned `Technology` nodes (the input cms-scanning/cve-cross-ref silently assume), protocol-aware banner grabbing, deterministic live-URL gate. httpx is **not installed** today (only a Python lib + shallow ingester). | recon GROUP 4 `http_probe` |
| 11 | **Uncover 13-engine expansion + 7-provider OSINT enrichment** | medium / medium | Passive pre-active target expansion (uncover → Shodan/Censys/FOFA/ZoomEye/Netlas/CriminalIP) + structured parallel threat-intel enrichment (reputation/ports/TLS/malware-family/geo/risk as node props). OPSEC-friendly T1596 surface expansion. | recon GROUP 2b/3b |
| 12 | **Layered subdomain-takeover detection (scoring + BadDNS)** | medium / medium | Cross-engine merge, additive 0–100 scorer w/ confirmed/likely/manual_review verdicts, live-CNAME FP suppression, deterministic SHA1 IDs, BadDNS coverage of NS/MX/TXT/SPF/DMARC. Upgrades a prose-only skill. **BadDNS is AGPL-3.0 → isolated sidecar CLI only.** | `recon/helpers/takeover_helpers.py` |
| 13 | **CVE Intel structured query (vulnx) + live CISA KEV loader** | high / medium | Lucene filters over ~69 fields (severity/cvss/epss, is_kev, is_template, is_poc, vendor/product, age); live CISA KEV w/ due dates + ransomware flags; `is_template` availability to gate the cve→`execute_nuclei` chain. Fixes that Decepticon's KEV override is currently **dead code** (always False in prod). | ProjectDiscovery `vulnx` |
| 14 | **Nmap CPE + NSE→CVE enrichment staging** | medium / low | Captures the CPE and NSE `--script vuln` output (incl. CVE IDs) `kg_ingest_nmap_xml` currently **drops**; persists CPE on Service nodes, creates Vulnerability+CVE nodes, feeds CVE IDs into the shipped NVD+EPSS+KEV scorer. | recon GROUP 3.5 `nmap_scan.py` |
| 15 | **RoE document upload + LLM-parse + viewer** | medium / medium | Import path for externally-provided **signed** RoE PDFs/DOCX: an LLM maps the doc into the existing `machine_enforcement` schema, keeps the signed original for the out-brief, a viewer shows a live ACTIVE/OUTSIDE time-window badge. (Decepticon can only *generate* RoE via the Soundwave interview today.) | webapp RoE upload + LLM parse |
| 16 | **In-browser Kali PTY shell (operator escape hatch)** | medium / low | A browser tab with a full interactive bash PTY into the same kali-sandbox the agent uses — run Metasploit/nmap/hydra/sqlmap by hand alongside the autonomous agent, sharing `/workspace` + target network. The xterm.js/WebSocket/node-pty stack already ships but is bound to the CLI agent. **Must route through RoEEnforcementMiddleware + audit ledger.** | webapp `KaliTerminal` |
| 17 | **VHost & SNI hidden virtual-host enumeration** | medium / medium | Baseline + control-probe calibration and the net-new **L7-vs-L4 routing-disagreement** primitive (same hostname at Host header AND TLS SNI; disagreement → high-severity `host_header_bypass` authz-bypass finding) which Decepticon only describes in prose. | `recon/main_recon_modules/vhost_sni_enum.py` |
| 18 | **Full-engagement ZIP export/import (backup & migration)** | medium / medium | Lossless bundle of an entire engagement (workspace files + the Neo4j attack-graph subgraph + the Postgres row) re-importable under a fresh engagement ID on another instance. Today the Neo4j graph is never serialized and there's no import path. | webapp project ZIP export/import |

---

## Tier 3 — Nice-to-have / situational

Lower value-to-effort: narrow capability, heavy provisioning, partial overlap, or value gated on a
missing prerequisite. Pursue opportunistically.

| # | Feature | Value / Effort | Note |
|---|---------|----------------|------|
| 19 | **MCP preset catalog + auto-wire `load_mcp_tools()`** | medium / medium | `load_mcp_tools()` exists but is unwired (returns tools nothing consumes). Wire it into agent tool-assembly + a vetted preset registry (Shodan, GitHub, Burp, ZAP, GhidraMCP). **MCP tools bypass RoE — bring under enforcement first.** Decline the 39-preset DB-backed no-code UI. |
| 20 | **Playwright XSS instrumentation (dialog capture + DOM-sink patching)** | medium / low | Turns the dormant `browser_action` tool into a browser-verified XSS oracle: `page.on(dialog)` self-validating PoC + init-script monkey-patching of innerHTML/eval/document.write. The 13-action Playwright engine ships but is dead code (unexported, chromium not installed). |
| 21 | **Source-map discovery + embedded-secret extraction** | medium / low | Parses accessible `.map` files, extracts original source filenames (internal structure / hidden routes), re-scans `sourcesContent` for secrets → graded `source_map_exposure` findings. Today: two `curl\|grep` one-liners. |
| 22 | **GraphQL security scanner sub-pipeline** | medium / medium | Active scanner: multi-source discovery, configurable introspection depth (vs hardcoded 3), SHA256 schema fingerprint, sensitive-field flagging, 12-check misconfig sweep. **Reimplement the 12 probes natively — graphql-cop is GPL-3.0 + needs DinD which Decepticon removed.** |
| 23 | **npm dependency-confusion detection** | medium / low | Regex-extract scoped packages, concurrent rate-limited npm-registry existence checks, structured Critical (404=registerable)/High findings. The advertised `dep-confusion-probe` skill is vaporware today. |
| 24 | **JS framework + DOM-sink + dev-comment detection + masscan/naabu fast scan** | low / low | Client-side framework fingerprinting (feeds CVE pipeline), 15 DOM-XSS/proto-pollution sink detections, dev-comment harvesting; + masscan/naabu fast mass-scan on large CIDRs with a naabu KG ingester. |
| 25 | **GitHub secret hunting via PyGithub** | medium / medium | RoE-gated GitHub recon: walks org/user repos, gists, capped commit history via authenticated REST API, 260+ named patterns + entropy, deleted-secret recovery, private-repo scanning. Complements the existing gitleaks-SARIF ingest. |
| 26 | **GVM/OpenVAS network vulnerability scanning** | medium / high | True network/infra-layer VM scan (170k+ NVT feed) complementing web-layer nuclei: weak SSH ciphers, exposed DB/SNMP/SMB, default creds. Provision as an opt-in `COMPOSE_PROFILES=gvm` profile (~30-min feed sync). Heaviest integration. |
| 27 | **EvoGraph write-side + Insights analytics + session-manager UI** | medium / medium | EvoGraph: turn the flat `events.jsonl` trace into a queryable AttackChain/ChainStep/ChainFinding/ChainFailure graph (**engagement-scoped only — do NOT import cross-session learning**). Insights: expose `chain.py` funcs as @tools + curated read-only Cypher views + a recharts route. Sessions: list/interact/kill live shells/jobs via RoE/HITL-gated routes. |

---

## Explicitly declined (Decepticon already has parity, or it conflicts with a security invariant)

| Redamon feature | Why declined |
|-----------------|--------------|
| Fan-out scheduler, `_isolated` wrappers, background graph writer | Decepticon parallelizes via concurrent `task()` dispatch + scanner shard fan-out + bounded asyncio; fresh-context sub-agents + idempotent MERGE solve shared state more robustly. Backgrounding KG writes breaks the read-after-write contract. |
| 21 recon presets, partial-recon runs, 245-param settings, true-source dependency model | All presuppose a fixed operator-configured pipeline; Decepticon recon is one autonomous bash agent selecting tools at runtime, config is intentionally 3 fields + `roe.json`, dependency-ordering is OPPLAN phase gating. |
| Docker-in-Docker spawning, round-robin key rotation | DinD/`docker.sock` is the host-escape vector Decepticon **deliberately removed**; key rotation can defeat RoE OPSEC pacing. |
| Fireteam sub-agents, Wave Runner, collect/merge | Model-driven concurrent `task()` + LangGraph `ToolNode` already give wall-clock parallelism; a Decepticon-owned scheduler conflicts with one-objective-per-fresh-context + OPPLAN's no-parallel-state-mutation rule. (Only `source_agent` finding attribution is a clean salvage.) |
| Intent router, `/skill` injection, chat-skill catalog | Progressive-disclosure `load_skill()` with LLM trigger-matching is architecturally superior to a deterministic classifier; a parallel chat-skill catalog would fork the skill system. |
| **NL-to-Cypher `query_graph`, Surface Shaper, Cypher guard** | Decepticon **removed agent-facing raw read-Cypher in v0.2.2 (regression-test-enforced)** as the largest injection surface, using a closed label vocabulary + parameterized navigation. Re-adding LLM-generated Cypher reverses a load-bearing security decision. |
| Command Whisperer, shell→meterpreter, CodeFix→PR / CypherFix, remediation dashboard | Whisperer/shell-upgrade presuppose an operator raw-shell console Decepticon doesn't center; the CodeFix→PR lifecycle is the explicitly **deferred** blue-cell / Offensive-Vaccine product direction. |
| LLM-narrative reports, AI decision hooks, remediation prioritization | Decepticon already mandates LLM-authored exec/technical reports w/ attack-path narratives + deterministic KG renderers (hackerone/executive/sarif/bugcrowd/timeline) + severity-bucketed remediation roadmaps. |
| Neo4j KG, multi-tenant model, checkpointing, workspace FS, background-job lane | Decepticon ships a typed multi-tenant Neo4j graph w/ `(key,engagement)` isolation, idempotent MERGE, provenance, APOC chain planner, BloodHound AD subgraph, scoped `/workspace`, LangGraph checkpointing, tmux background-job lane — exceeding Redamon. |

---

## Addendum — completeness sweep (the 9 unclassified features)

A follow-up pass classified the 9 features the first run failed to verdict. Net result: **3 genuine
gaps**, the rest already-present or minor variants. The headline correction: **Decepticon has no
open-web search and no semantic-RAG layer at all** — neither was represented above.

| # | Feature | Status | Value / Effort | Note |
|---|---------|--------|----------------|------|
| G1 | **Open-web `web_search` tool** | absent | medium-high / low | Decepticon has **no internet-search tool** (no Tavily/SerpAPI in the agent surface) and **no embeddings/FAISS/cross-encoder** anywhere. Adopt the open-web `web_search` half (one RoE-gated egress tool + `UntrustedOutput` wrapper — model it on `tools/references/tools.py:46`). **Decline** Redamon's heavy FAISS+reranker RAG stack (~1.9 GB models; partially redundant with the existing git-clone+ripgrep `references` corpus). → **Tier 1.** |
| G2 | **Target guardrail — categorical hard-block deny-list** | partial | medium / low | Always-on refusal of `.gov`/`.mil`/`.edu`/`.int` (+ LLM classifier for gov/bigtech/financial/social) independent of operator RoE. Today the only categorical default-deny is cloud-metadata IMDS (`types/roe.py:57`); clean injection point is `evaluate_target` (`roe.py:229`). Hardens an existing invariant. → **Tier 1 (safety).** |
| G3 | **Wildcard-DNS / puredns poisoning filter** | absent | low / low-med | Recon-hygiene helper so wildcard-poisoned subdomains don't flood the graph; provision `puredns` (Apache-2.0, CLI-only) or add a wildcard-collapse heuristic to `kg_ingest_subfinder` (`tools.py:911`). → **Tier 3.** |

**Verified already-present (no action):** Tradecraft Lookup (= the `references` module, fully present),
extended-thinking/Deep-Think (LLM factory `reasoning_effort`), large-tool-output auto-offload
(`tools/bash/bash.py` 3-tier inline/offload/summary), TruffleHog (one more engine into the
gitleaks-SARIF path; live-validation gap already captured by Tier-2 #8), reverse-shells/Command-Whisperer
(interactive tmux session model; already in the declined list), WPScan (restrictively licensed, niche).

## Cross-cutting constraints (apply to every port)

- **Build the `Technology` NodeKind + `V004` migration first** — load-bearing prerequisite for the whole AI-surface cluster *and* the tech-detection upgrade.
- **Batch the sandbox binary installs** — httpx, whatweb, subjack/subzy/dnsx, masscan, naabu, vulnx share one `sandbox.Dockerfile` provisioning pass.
- **Licensing:** BadDNS (AGPL-3.0) and any AGPL takeover/scan tool run **only** as isolated out-of-process sidecar/CLI (mirror the `c2-sliver` compose-profile), never imported into the Apache-2.0 Python. masscan (AGPL) and graphql-cop (GPL) are CLI-only (same posture as shipped sqlmap/hydra); graphql-cop's DinD invocation must be reimplemented natively.
- **Security invariants to preserve:** never reintroduce raw/NL Cypher to the agent surface; route every new network-egress tool (OSINT enrichment, secret validators, source-map fetch, MCP, Kali PTY) through `RoEEnforcementMiddleware` + the HMAC audit ledger; keep all KG writes strictly engagement-scoped (no cross-engagement learning); wrap all untrusted third-party content in `UntrustedOutput` / `PromptInjectionShield` markers.

## Recommended first three

1. **HTTP-header AI-stack matcher + AI-port catalog** (with the `Technology` node) — closes the biggest categorical blind spot; makes the `llm-redteam` plugin actually find targets.
2. **JS endpoint classification taxonomy** — closes the biggest recon→exploit handoff gap for web.
3. **Mid-run guidance injection** — closes the biggest operator-control gap.

All three are low-to-medium effort and independent.
