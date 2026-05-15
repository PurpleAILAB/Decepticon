# XBOW Benchmark — Cross-Project Comparison

Side-by-side numbers for AI / LLM pentesting agents that have **publicly released results on the
[XBOW Validation Benchmark](https://github.com/xbow-engineering/validation-benchmarks)** (104 web-app CTF challenges, 3 difficulty tiers).

- **Decepticon mode:** **black-box** (no source / config / hints).
- **Decepticon status:** L1 + L3 done, **L2 sweep in progress** — Decepticon's number is interim.

![XBOW leaderboard](../assets/benchmark/leaderboard.png)

## Leaderboard

| # | System | XBOW Score | Mode | Source |
|--:|---|---|---|---|
|  1 | **Shannon Lite** (KeygraphHQ)        | **96.15 %** (100 / 104) | white-box, hint-removed   | [github](https://github.com/KeygraphHQ/shannon) |
|  1 | **Strix** (usestrix)                 | **96.15 %** (100 / 104) [^strix] | black-box                 | [github](https://github.com/usestrix/strix) |
|  3 | **PentestGPT** (USENIX '24)          | **86.5 %** (90 / 104)   | black-box                 | [github](https://github.com/GreyDGL/PentestGPT) · [paper](https://www.usenix.org/conference/usenixsecurity24/presentation/deng) |
|  4 | **Red-MIRROR**                       | **86.0 %**              | black-box, multi-agent + RAG | arXiv [2603.27127](https://arxiv.org/abs/2603.27127) |
|  5 | **XBOW** (commercial)                | **≈85 %**               | black-box, proprietary    | [xbow.com/blog/benchmarks](https://xbow.com/blog/benchmarks) |
|  6 | **Cyber-AutoAgent** (westonbrown)    | **84.62 %** (88 / 104) — v0.1.3 [archived]; 81 % v0.1.1; 45.92 % (45/98) v0.1.0 | black-box, meta-agent | [github](https://github.com/westonbrown/Cyber-AutoAgent) |
|  7 | **MAPTA**                            | **76.9 %** (80 / 104)   | black-box, multi-agent    | arXiv [2508.20816](https://arxiv.org/abs/2508.20816) |
|  8 | **Decepticon** *(this repo)*         | **L1+L3: 100 %** (53 / 53) · L2: 90.2 % (46 / 51) — interim 99 / 104 | **black-box**, LangGraph multi-agent | [github](https://github.com/PurpleAILAB/Decepticon) |
|  9 | PentestAgent                         | 50.0 % [^retest]        | black-box                 | arXiv 2411.05185; re-tested in Red-MIRROR |
| 10 | AutoPT                               | 46.0 % [^retest]        | black-box                 | re-tested in Red-MIRROR |
| 11 | VulnBot                              |  6.0 % [^retest]        | black-box, baseline       | arXiv [2501.13411](https://arxiv.org/abs/2501.13411); re-tested in Red-MIRROR |

> Shannon's 96.15 % is **white-box, hint-removed** — not directly comparable to black-box numbers.

[^strix]: Strix per-difficulty (45/45 · 49/51 · 6/8 = 100/104 = 96.15 %) sourced from project's published benchmark table; we could not independently re-confirm the per-difficulty split from a primary indexed source — treat the per-level split as project-reported.
[^retest]: 50 % / 46 % / 6 % numbers come from the **Red-MIRROR ablation** re-running these systems on XBOW, not from the systems' own papers (VulnBot's own paper uses AutoPenBench).

## Per-Difficulty (where published)

![Pass rate by difficulty — Strix · PentestGPT · Decepticon](../assets/benchmark/difficulty.png)

| System | L1 | L2 | L3 | Total |
|---|---|---|---|---|
| **Strix**       | 45 / 45 — **100 %**  | 49 / 51 — **96 %**           | 6 / 8 — 75 %      | **96.15 %** |
| **PentestGPT**  | 42 / 46 — 91.1 %     | 43 / 50 — 74.5 %             | 5 / 8 — 62.5 %    | **86.5 %**  |
| **Decepticon**  | **45 / 45 — 100 %**  | **46 / 51 — 90.2 %** *(in progress)* | **8 / 8 — 100 %** | L1+L3: **100 %** *(L2 ongoing — interim 99 / 104)* |

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

**Decepticon** per-class — see [`benchmark/results/README.md`](../benchmark/results/README.md). 23 classes covered; top: XSS (14), Cmd-Inj (8), Default Creds (7), SSTI (6), IDOR (6).

## Adjacent — Don't Publish XBOW (different benchmark)

| Project | Benchmark used |
|---|---|
| **CAI** ([aliasrobotics/CAI](https://github.com/aliasrobotics/CAI)) | CAIBench |
| **xOffense** (arXiv [2509.13021](https://arxiv.org/abs/2509.13021)) | AutoPenBench (72.72 %) |
| **HackSynth** | 200-challenge picoCTF + OverTheWire |
| **HexStrike**, **PentestAgent (testified-oss)** | none reported |
| **MHBench** ([bsinger98/MHBench](https://github.com/bsinger98/MHBench)) | multi-host network red-team benchmark |

## Sources

- XBOW corp — [top-1 blog](https://xbow.com/blog/top-1-how-xbow-did-it) · [1060 attacks](https://xbow.com/blog/we-ran-1060-autonomous-attacks)
- Shannon — [`xben-benchmark-results/`](https://github.com/KeygraphHQ/shannon/tree/main/xben-benchmark-results)
- Cyber-AutoAgent — [v0.1.0 results](https://github.com/westonbrown/Cyber-AutoAgent/discussions/12) · [Brown — *From Single Agent to Meta-Agent*](https://medium.com/data-science-collective/from-single-agent-to-meta-agent-building-the-leading-open-source-autonomous-cyber-agent-e1b704f81707)
- PentestGPT XBOW suite — [DeepWiki](https://deepwiki.com/GreyDGL/PentestGPT/5.1-xbow-validation-suite)
- Survey — [*AI Pentesting Agents 2026*](https://appsecsanta.com/research/ai-pentesting-agents-2026)
- Awesome list — [insidetrust/awesome-ai-pentest](https://github.com/insidetrust/awesome-ai-pentest)

> *Last updated: 2026-05-15.*
