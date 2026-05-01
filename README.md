[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](README.md)
[![한국어](https://img.shields.io/badge/Language-한국어-red?style=for-the-badge)](README_KO.md)

<div align="center">
  <img src="assets/logo_banner.png" alt="Decepticon Logo">
</div>

<h1 align="center">Decepticon — Autonomous Red Team Agent</h1>

<p align="center"><i>"Another AI hacker? Let us guess — it runs nmap and writes a report."</i></p>

<div align="center">

<a href="https://github.com/PurpleAILAB/Decepticon/blob/main/LICENSE">
  <img src="https://img.shields.io/github/license/PurpleAILAB/Decepticon?style=for-the-badge&color=blue" alt="License: Apache 2.0">
</a>
<a href="https://github.com/PurpleAILAB/Decepticon/stargazers">
  <img src="https://img.shields.io/github/stars/PurpleAILAB/Decepticon?style=for-the-badge&color=yellow" alt="Stargazers">
</a>
<a href="https://github.com/PurpleAILAB/Decepticon/graphs/contributors">
  <img src="https://img.shields.io/github/contributors/PurpleAILAB/Decepticon?style=for-the-badge&color=orange" alt="Contributors">
</a>

<br/>

<a href="https://discord.gg/TZUYsZgrRG">
  <img src="https://img.shields.io/badge/Discord-Join%20Us-7289DA?logo=discord&logoColor=white&style=for-the-badge" alt="Join us on Discord">
</a>
<a href="https://decepticon.red">
  <img src="https://img.shields.io/badge/Website-decepticon.red-brightgreen?logo=vercel&logoColor=white&style=for-the-badge" alt="Website">
</a>
<a href="https://docs.decepticon.red">
  <img src="https://img.shields.io/badge/Docs-docs.decepticon.red-8B5CF6?logo=bookstack&logoColor=white&style=for-the-badge" alt="Documentation">
</a>

</div>

<br/>

<div align="center">
  <video src="https://github.com/user-attachments/assets/b3fd40d8-e859-4a39-97f4-bd825694ad96" width="800" controls></video>
</div>

---

## Install

**Prerequisites**: [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2.
Supported on macOS (Apple Silicon + Intel), Linux (amd64 + arm64), and Windows via WSL2 (Ubuntu or Kali).
Native Windows is not supported — install WSL2 first, then run the commands below from inside the WSL shell.

```bash
curl -fsSL https://decepticon.red/install | bash
decepticon onboard   # Interactive setup wizard (provider, API key, model profile)
decepticon           # Start everything: terminal CLI + web dashboard at http://localhost:3000
```

→ **[Quick start](docs/getting-started.md)** · **[Full setup walkthrough](docs/setup-guide.md)**

---

## 💖 Support Decepticon

[![Sponsor](https://img.shields.io/badge/Sponsor-Decepticon-red?style=for-the-badge&logo=github)](https://github.com/sponsors/PurpleCHOIms)

We're building Decepticon as an **Offensive Vaccine** for the AI-driven threat landscape. If you believe in autonomous red teaming as a path to stronger defense, consider supporting the project.

---

## Benchmark Results

| Benchmark | Difficulty | Pass Rate |
|-----------|------------|-----------|
| [XBOW validation-benchmarks](https://github.com/PurpleAILAB/xbow-validation-benchmarks) | Hard (Level 3) | **7 / 8** |

→ **[Full benchmark index](benchmark/results/README.md)**

---

## What is Decepticon?

The "AI + hacking" space is full of demos that run nmap and print a report. That's not what this is.

**Decepticon is a professional autonomous Red Team agent.** It executes realistic attack chains — reconnaissance, exploitation, privilege escalation, lateral movement, C2 — the way a real adversary would, not the way a scanner does.

But more importantly: it operates under the discipline that separates red teamers from script kiddies. Before a single packet leaves the wire, Decepticon generates a complete engagement package — **RoE**, **ConOps**, **Deconfliction Plan**, and **OPPLAN** with MITRE ATT&CK mapping — and every action runs inside those defined rules.

→ **[Engagement workflow deep dive](docs/engagement-workflow.md)**

---

## Why Decepticon?

**Real kill chains, not checkbox scans.** Decepticon reads an OPPLAN and pursues objectives through whatever path opens up — pivoting, adapting, chaining techniques.

**Interactive shells, actually.** Real offensive tools are interactive (`msfconsole`, `sliver-client`, `evil-winrm`). Decepticon runs every command inside persistent tmux sessions with automatic prompt detection — so when a tool drops into an interactive prompt, the agent sends follow-up commands without workarounds.

**Hardened sandbox isolation.** All commands run inside a Kali Linux sandbox on a dedicated operational network (`sandbox-net`), separate from the management plane (`decepticon-net`). LangGraph drives the sandbox via the Docker socket. → **[Architecture](docs/architecture.md)**

**Offense serves defense.** The [Offensive Vaccine](docs/offensive-vaccine.md) loop turns every finding into a defense improvement — automatically. Attack → defend → verify, at machine speed.

---

## Architecture

<div align="center">
  <img src="assets/decepticon_infra.svg" alt="Decepticon Infrastructure" width="680">
</div>

Two-network design — management services (LiteLLM, PostgreSQL, LangGraph, Web) on `decepticon-net`; sandbox, C2 server, and targets on `sandbox-net`. Neo4j is dual-homed so the agent (on management) can persist findings written from inside the sandbox.

→ **[Architecture deep dive](docs/architecture.md)** · **[Knowledge graph](docs/knowledge-graph.md)**

---

## Agents

17 specialist agents organized by kill chain phase, with a fresh context window per objective — no accumulated noise.

Orchestration · Reconnaissance · Exploitation · Post-Exploitation · Vulnerability Research · Defense · Domain Specialists (AD, Cloud, Smart Contracts, Reversing, Analyst).

→ **[Full agent roster and middleware stack](docs/agents.md)**

---

## Models & Providers

Tier-based, credentials-aware fallback chain. You declare which credentials you have in priority order; Decepticon builds the primary→fallback chain at every tier from there.

| Profile | Tier per agent | Use case |
|---------|----------------|----------|
| **eco** (default) | Per-agent (HIGH for orchestrator/exploiter/patcher/analyst, MID for execution, LOW for recon/soundwave) | Production |
| **max** | Every agent on HIGH | High-value targets |
| **test** | Every agent on LOW | Development / CI |

**Tier-mapped providers**: Anthropic, OpenAI, Google Gemini, MiniMax, DeepSeek, xAI, Mistral, OpenRouter, Nvidia NIM, Ollama (local).
**Subscription OAuth**: Claude Max/Pro/Team, ChatGPT Pro/Plus/Team, Gemini Advanced, Copilot Pro, SuperGrok, Perplexity Pro.

Configure via `decepticon onboard`. → **[Full model reference & fallback examples](docs/models.md)**

---

## Documentation

| Topic | Doc |
|-------|-----|
| Installation and first engagement | [Getting Started](docs/getting-started.md) |
| Complete setup, OAuth, providers, dashboard | [Setup Guide](docs/setup-guide.md) |
| All CLI commands and keyboard shortcuts | [CLI Reference](docs/cli-reference.md) |
| All `make` targets | [Makefile Reference](docs/makefile-reference.md) |
| Agent roster and middleware | [Agents](docs/agents.md) |
| Model profiles and fallback chain | [Models](docs/models.md) |
| Skill system and format spec | [Skills](docs/skills.md) |
| Web dashboard features and setup | [Web Dashboard](docs/web-dashboard.md) |
| System architecture and network isolation | [Architecture](docs/architecture.md) |
| Neo4j knowledge graph | [Knowledge Graph](docs/knowledge-graph.md) |
| End-to-end engagement workflow | [Engagement Workflow](docs/engagement-workflow.md) |
| Offensive Vaccine loop | [Offensive Vaccine](docs/offensive-vaccine.md) |
| Contributing to Decepticon | [Contributing](docs/contributing.md) |

---

## Contributing

```bash
git clone https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon
make dogfood  # Full OSS UX (launcher → onboard → CLI) on local code
make dev      # Backend hot-reload (compose watch) — daily dev loop
```

→ **[Contributing guide](docs/contributing.md)**

---

## Community

Join the [Discord](https://discord.gg/TZUYsZgrRG) — ask questions, share engagement logs, discuss techniques.

---

## Disclaimer

Do not use this project on any system or network without explicit written authorization from the system owner. Unauthorized access to computer systems is illegal. You are solely responsible for your actions. The authors and contributors assume no liability for misuse.

---

## License

[Apache-2.0](LICENSE)

---

<div align="center">
  <img src="assets/main.png" alt="Decepticon">
</div>
