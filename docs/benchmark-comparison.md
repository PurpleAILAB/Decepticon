# XBOW Benchmark — Cross-Project Comparison

Side-by-side numbers for AI / LLM pentesting agents that have **publicly released results on the
[XBOW Validation Benchmark](https://github.com/xbow-engineering/validation-benchmarks)** (104 web-app CTF challenges, 3 difficulty tiers).

<div align="center">
  <img src="../assets/benchmark/leaderboard.png" alt="XBOW leaderboard — Decepticon at 98.08 %" width="780">
</div>

- **Decepticon mode** — black-box (no source code, no config, no service internals). The agent receives the per-challenge `benchmark.yaml` metadata as engagement context: the one-line `description`, the `Vulnerability tags:` list (e.g. `idor`, `default_credentials`, `ssti`), and the flag format. The agent discovers endpoints, parameters, sinks, payloads, and gadgets on its own. **Compared to Strix** [^strix-method]: Strix passes the `description` only, not the tags — so this table's two black-box leaders sit at slightly different hint levels (Decepticon: description + tags; Strix: description only).
- **Decepticon status** — cycle-4 final · 102 / 104 (98.08 %). L1 complete; L2 50/51 (one outstanding); L3 7/8 (one outstanding).
- **Per-challenge evidence + LangSmith traces** — [`benchmark/results/README.md`](../benchmark/results/README.md).

## Leaderboard

| # | System | XBOW Score | Mode | Source |
|--:|---|---|---|---|
|  **1** | **Decepticon** *(this repo)*     | **98.08 %** (102 / 104) — L1: 100 % (45/45) · L2: 98.0 % (50/51) · L3: 87.5 % (7/8) | **black-box**, LangGraph multi-agent | [github](https://github.com/PurpleAILAB/Decepticon) |
|  2 | **Shannon Lite** (KeygraphHQ)        | **96.15 %** (100 / 104) | white-box, hint-removed   | [github](https://github.com/KeygraphHQ/shannon) |
|  2 | **Strix** (usestrix)                 | **96.15 %** (100 / 104) [^strix] | black-box                 | [github](https://github.com/usestrix/strix) |
|  4 | **PentestGPT** (USENIX '24)          | **86.5 %** (90 / 104)   | black-box                 | [github](https://github.com/GreyDGL/PentestGPT) · [paper](https://www.usenix.org/conference/usenixsecurity24/presentation/deng) |
|  5 | **Red-MIRROR**                       | **86.0 %**              | black-box, multi-agent + RAG | arXiv [2603.27127](https://arxiv.org/abs/2603.27127) |
|  6 | **XBOW** (commercial)                | **≈85 %**               | black-box, proprietary    | [xbow.com/blog/benchmarks](https://xbow.com/blog/benchmarks) |
|  7 | **Cyber-AutoAgent** (westonbrown)    | **84.62 %** (88 / 104) — v0.1.3 [archived]; 81 % v0.1.1; 45.92 % (45/98) v0.1.0 | black-box, meta-agent | [github](https://github.com/westonbrown/Cyber-AutoAgent) |
|  8 | **MAPTA**                            | **76.9 %** (80 / 104)   | black-box, multi-agent    | arXiv [2508.20816](https://arxiv.org/abs/2508.20816) |
|  9 | PentestAgent                         | 50.0 % [^retest]        | black-box                 | arXiv 2411.05185; re-tested in Red-MIRROR |
| 10 | AutoPT                               | 46.0 % [^retest]        | black-box                 | re-tested in Red-MIRROR |
| 11 | VulnBot                              |  6.0 % [^retest]        | black-box, baseline       | arXiv [2501.13411](https://arxiv.org/abs/2501.13411); re-tested in Red-MIRROR |

> Shannon's 96.15 % is **white-box, hint-removed** — not directly comparable to black-box numbers.

[^strix]: Strix per-difficulty (45/45 · 49/51 · 6/8 = 100/104 = 96.15 %) sourced from the [`usestrix/benchmarks` XBEN page](https://github.com/usestrix/benchmarks/tree/main/XBEN) (v0.4.0; avg solve time ~19 min; ~$337 total) and re-confirmed against the project's published benchmark table.
[^strix-method]: Strix's [`XBEN/run_infer.py`](https://github.com/usestrix/benchmarks/blob/main/XBEN/run_infer.py) builds the instruction as `"You are an expert CTF player. Your goal is to find a flag in the format flag{...}. ... {description}"` — only the `description` field from `benchmark.json` is concatenated into the prompt; the `tags` field is recorded in the result but not passed to the agent.
[^retest]: 50 % / 46 % / 6 % numbers come from the **Red-MIRROR ablation** re-running these systems on XBOW, not from the systems' own papers (VulnBot's own paper uses AutoPenBench).

## Per-Difficulty (where published)

![Pass rate by difficulty — Strix · PentestGPT · Decepticon](../assets/benchmark/difficulty.png)

| System | L1 | L2 | L3 | Total |
|---|---|---|---|---|
| **Strix**       | 45 / 45 — **100 %**  | 49 / 51 — **96 %**           | 6 / 8 — 75 %      | **96.15 %** |
| **PentestGPT**  | 42 / 46 — 91.1 %     | 43 / 50 — 74.5 %             | 5 / 8 — 62.5 %    | **86.5 %**  |
| **Decepticon**  | **45 / 45 — 100 %**  | **50 / 51 — 98.0 %**  | **7 / 8 — 87.5 %**  | **98.08 %** (102 / 104) |

PentestGPT per-level avg cost / time: L1 $0.65 / 4.4 min · L2 $1.33 / 6.9 min · L3 $3.03 / 12.9 min (median across all 104: $0.42 / 3.3 min).
XBOW commercial does not publish a per-difficulty breakdown for its own agent — only the headline 85 % vs the senior pentester's 85 % in 40 hours.

## Per-Vulnerability — Shannon Lite (only system w/ full breakdown)

| Class | Total | Solved | Rate |
|---|---:|---:|---:|
| Broken Authorization | 25 | 25 | **100 %** |
| SQL Injection        |  7 |  7 | **100 %** |
| Blind SQLi           |  3 |  3 | **100 %** |
| XSS                  | 23 | 22 | 95.65 % |
| SSRF / Misconfig     | 22 | 21 | 95.45 % |
| SSTI                 | 13 | 12 | 92.31 % |
| Command Injection    | 11 | 10 | 90.91 % |
| **Total**            | **104** | **100** | **96.15 %** |

**MAPTA** per-class (overall 76.9 %): SSRF 100 % · Misconfig 100 % · SSTI 85 % · SQLi 83 % · Broken Authz 83 % · Cmd-Inj 75 % · XSS 57 % · Blind SQLi 0 %.

**Decepticon** per-class — see [`benchmark/results/README.md`](../benchmark/results/README.md). 23 classes covered; top: XSS (14), Cmd-Inj (8), Default Creds (8), SSTI (7), LFI (6), IDOR (6).

## Adjacent — Don't Publish XBOW (different benchmark)

| Project | Benchmark used |
|---|---|
| **CAI** ([aliasrobotics/CAI](https://github.com/aliasrobotics/CAI)) | CAIBench |
| **xOffense** (arXiv [2509.13021](https://arxiv.org/abs/2509.13021)) | AutoPenBench (72.72 %) |
| **HackSynth** | 200-challenge picoCTF + OverTheWire |
| **HexStrike**, **PentestAgent (testified-oss)** | none reported |
| **MHBench** ([bsinger98/MHBench](https://github.com/bsinger98/MHBench)) | multi-host network red-team benchmark |

## Sources

- XBOW corp — [top-1 blog](https://xbow.com/blog/top-1-how-xbow-did-it) · [1060 attacks](https://xbow.com/blog/we-ran-1060-autonomous-attacks) · [benchmarks page](https://xbow.com/blog/benchmarks)
- Shannon — [`xben-benchmark-results/`](https://github.com/KeygraphHQ/xbow-validation-benchmarks/tree/main/xben-benchmark-results) (lives in the project's fork of `xbow-validation-benchmarks`, not in the `KeygraphHQ/shannon` repo)
- Strix — [`usestrix/benchmarks` XBEN](https://github.com/usestrix/benchmarks/tree/main/XBEN) (v0.4.0 results, `run_infer.py` evaluation script, per-difficulty 45/45 · 49/51 · 6/8 = 100/104, avg ~19 min / ~$337 total)
- Cyber-AutoAgent — [v0.1.0 results](https://github.com/westonbrown/Cyber-AutoAgent/discussions/12) · [Brown — *From Single Agent to Meta-Agent*](https://medium.com/data-science-collective/from-single-agent-to-meta-agent-building-the-leading-open-source-autonomous-cyber-agent-e1b704f81707) (v0.1.1 ≈81 % on 104; v0.1.0 45.92 % on 98)
- PentestGPT XBOW suite — [DeepWiki](https://deepwiki.com/GreyDGL/PentestGPT/5.1-xbow-validation-suite) (90/104 = 86.5 %; L1 42/46 · L2 43/50 · L3 5/8)
- MAPTA — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816) (80/104 = 76.9 %)
- Red-MIRROR — [arXiv 2603.27127](https://arxiv.org/abs/2603.27127) (86.0 %; PentestAgent 50 %, AutoPT 46 %, VulnBot 6 % numbers also come from this paper's re-test of those systems)
- Survey — [*AI Pentesting Agents 2026*](https://appsecsanta.com/research/ai-pentesting-agents-2026)
- Awesome list — [insidetrust/awesome-ai-pentest](https://github.com/insidetrust/awesome-ai-pentest)

> *Last updated: 2026-05-17.*
