# Integration — reverse-skill

[reverse-skill](https://github.com/zhaoxuya520/reverse-skill) is a public,
MIT-licensed skill pack for authorized reverse engineering and security
analysis workflows. It ships 85 `SKILL.md` files (41 general security skills,
41 CTF-competition variants, plus routing/ops plumbing) organized as a
task-skill router with an authorization gate (`case-init` + scope grant)
before any active work.

Decepticon vendors it as a **reference submodule** at
[`integrations/reverse-skill/`](../../integrations/reverse-skill), pinned to
commit `ea582f30d53e4d616881df06a8e0f7e9f661ea21`. The submodule is reference
material only — none of its content is loaded by Decepticon at runtime.

## Why curated porting instead of wholesale import

Decepticon already ships 300+ native skills. Mapping the 41 general
reverse-skill skills against the corpus showed most duplicate existing
coverage:

| reverse-skill lane | Existing Decepticon coverage |
|---|---|
| `llm-security` | 15 `llm-redteam` skills |
| `ot-ics` | 7 `ics-ot` skills |
| `windows-ad` | 11 Active Directory skills |
| `malware-analysis`, `ida-reverse`, `radare2`, `ghidra-reverse` … | reverser lane (triage, ghidra, deep-analysis, malware-triage, …) |

Wholesale import would have created duplicate routing entries and dragged in
reverse-skill's own ops/routing conventions (tool-index, case-init scripts,
Windows-first bootstrap), which conflict with Decepticon's sandbox and
middleware model. So only the **six genuinely net-new** reverser skills were
ported natively.

## Ported skills

Each port is rewritten into Decepticon's native schema (see
[docs/skill-schema.md](../skill-schema.md)): canonical frontmatter, English
prose, `/workspace/` + knowledge-graph conventions, sandbox-friendly tooling,
and RoE framing. Attribution rides in `metadata.upstream_ref` on every ported
file.

| Ported skill | Upstream source | Adds |
|---|---|---|
| `standard/reverser/binary-diff` | `skills/binary-diff` | Cross-version symbol migration via structured diff |
| `standard/reverser/go-rust-reverse` | `skills/go-rust-reverse` | Stripped Go/Rust runtime recovery (GoReSym, pclntab, panic strings) |
| `standard/reverser/patch-diff-exploit` | `skills/patch-diff-exploit` | N-day patch diffing → root-cause → scoped PoC validation |
| `standard/reverser/thick-client` | `skills/thick-client` | Desktop client trust boundaries, IPC, update channels |
| `standard/reverser/js-reverse` | `skills/js-reverse` | JS signing/anti-bot chains, evidence-driven Node rebuild |
| `standard/reverser/protocol-reverse` | `skills/protocol-reverse` | Custom binary protocol / Protobuf / PCAP recovery |

Upstream content intentionally left behind:

- **CTF variants** (`ctf-*` mirrors) — Decepticon's `ctf-triage` and the CTF
  workflow skills already cover this.
- **Ops/routing plumbing** (`ops/`, `routing*.md`, `MASTER-ROUTING.md`,
  `scripts/*.ps1`) — reverse-skill's client-agnostic router is superseded by
  Decepticon's SkillsMiddleware and skill graph.
- **Windows-host bootstrap** (`bootstrap-reverse.ps1`, `tool-index.md`
  generation) — Decepticon agents run in a Linux sandbox with managed tooling.
- **Duplicated lanes** per the table above.

## Updating the pin

```bash
cd integrations/reverse-skill
git fetch origin
git checkout <new-commit>
cd ../..
# review diff, then re-check ported skills for upstream fixes worth adopting
git add integrations/reverse-skill
```

When the pin moves, skim the upstream diff for fixes to the six ported skills
and fold them into the native copies manually — the ports are forks in
content, not mechanical mirrors.

## License and attribution

reverse-skill is MIT-licensed; copyright and license text are preserved in
the submodule itself. The native ports carry `upstream_ref` pointers to the
exact source path and pin commit so provenance is auditable from the skill
graph.
