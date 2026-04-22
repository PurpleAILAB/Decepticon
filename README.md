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

```bash
curl -fsSL https://decepticon.red/install | bash
decepticon onboard   # Interactive setup wizard (provider, API key, model profile)
decepticon           # Start everything: terminal CLI + web dashboard at http://localhost:3000
```

→ **[Full setup guide](docs/getting-started.md)**

---

## Try the Demo

```bash
decepticon demo
```

Launches Metasploitable 2, loads a pre-built engagement, and runs the full kill chain autonomously: port scan → vsftpd exploit → Sliver C2 implant → credential harvesting → internal recon.

---

## 💖 Support Decepticon

[![Sponsor](https://img.shields.io/badge/Sponsor-Decepticon-red?style=for-the-badge&logo=github)](https://github.com/sponsors/PurpleCHOIms)

We're building Decepticon as an **Offensive Vaccine** for the AI-driven threat landscape. If you believe in autonomous red teaming as a path to stronger defense, consider supporting the project.

---

## What is Decepticon?

The "AI + hacking" space is full of demos that run nmap and print a report. That's not what this is.

**Decepticon is a professional autonomous Red Team agent.** It executes realistic attack chains — reconnaissance, exploitation, privilege escalation, lateral movement, C2 — the way a real adversary would, not the way a scanner does.

But more importantly: it operates under the discipline that separates red teamers from script kiddies.

Before a single packet leaves the wire, Decepticon generates a complete engagement package:

- **RoE** (Rules of Engagement) — Authorized scope, exclusions, testing window, escalation contacts
- **ConOps** (Concept of Operations) — Threat actor profile, methodology, TTPs
- **Deconfliction Plan** — Source IPs, time windows, shared codes for real-time SOC deconfliction
- **OPPLAN** (Operations Plan) — Full mission plan with objectives, kill chain phases, and MITRE ATT&CK mapping

Every action operates inside defined rules. The agent doesn't just hack — it runs a professional Red Team operation that happens to be autonomous.

---

## Why Decepticon?

**Real kill chains, not checkbox scans.**
Decepticon reads an OPPLAN and pursues objectives through whatever path opens up — pivoting, adapting, chaining techniques — the way a real attacker would.

**Interactive shells, actually.**
Real offensive tools are interactive — `msfconsole`, `sliver-client`, `evil-winrm`. Most AI agents fire one-shot commands and give up. Decepticon runs every command inside persistent tmux sessions with automatic prompt detection. When a tool drops you into an interactive prompt, the agent sends follow-up commands. No workarounds.

**Real infrastructure isolation.**
All commands run inside a hardened Kali Linux sandbox on a dedicated operational network (`sandbox-net`), fully isolated from management (`decepticon-net`). LLM gateway, databases, and agent API live on one network; sandbox, C2 server, and targets live on another. Zero cross-network access. The agent controls the sandbox via Docker socket only.

**Offense serves defense.**
The [Offensive Vaccine](docs/offensive-vaccine.md) loop turns every finding into a defense improvement — automatically. Attack → defend → verify, at machine speed. This is Step 1 toward infrastructure that hardens itself.

---

## Architecture

Two isolated networks. Management and operations share zero network access.

<div align="center">
  <img src="assets/decepticon_infra.svg" alt="Decepticon Infrastructure" width="680">
</div>

→ **[Architecture deep dive](docs/architecture.md)**

---

## Agents

16 specialist agents organized by kill chain phase. Each agent starts with a fresh context window per objective — no accumulated noise.

| Phase | Agents |
|-------|--------|
| **Orchestration** | Decepticon (main), Soundwave (planning + docs) |
| **Reconnaissance** | Recon, Scanner |
| **Exploitation** | Exploit, Exploiter, Detector, Verifier, Patcher |
| **Post-Exploitation** | Post-Exploit |
| **Defense** | Defender (Offensive Vaccine loop) |
| **Specialists** | AD Operator, Cloud Hunter, Contract Auditor, Reverser, Analyst |

The vulnerability research pipeline (Scanner → Detector → Verifier → Exploiter → Patcher) handles the full lifecycle from discovery through proof-of-concept to patch proposal.

→ **[Agent details and middleware stack](docs/agents.md)**

---

## Models

Three profiles via LiteLLM proxy. Each role has a primary model and automatic fallback.

| Profile | Orchestrator | Exploit | Recon | Use case |
|---------|-------------|---------|-------|---------|
| **eco** (default) | Opus 4.6 | Sonnet 4.6 | Haiku 4.5 | Production |
| **max** | Opus 4.6 | Opus 4.6 | Sonnet 4.6 | High-value targets |
| **test** | Haiku 4.5 | Haiku 4.5 | Haiku 4.5 | Development / CI |

Set via `DECEPTICON_MODEL_PROFILE=eco` in your `.env`. Provider outage or rate limit → seamless fallback.

→ **[Full model reference](docs/models.md)**

---

## Documentation

| Topic | Doc |
|-------|-----|
| Installation and first engagement | [Getting Started](docs/getting-started.md) |
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
make dev     # Start with hot-reload
make cli     # Open the interactive CLI (separate terminal)
```

→ **[Contributing guide](docs/contributing.md)**

---

## Community

Join the [Discord](https://discord.gg/TZUYsZgrRG) — ask questions, share engagement logs, discuss techniques, or just connect with others building at the intersection of offense and defense.

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
