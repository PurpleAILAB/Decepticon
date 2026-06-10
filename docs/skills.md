# Skills

Skills are structured knowledge files that agents load on demand. They encode offensive techniques, OPSEC procedures, reporting templates, and engagement workflows — organized by kill chain phase and mapped to MITRE ATT&CK.

> **Heads up — Skillogy successor**: this document describes the current text-matching skill system (`SkillsMiddleware`). Its planned replacement is **[Skillogy](skillogy.md)**, a Neo4j-backed knowledge graph layer over the same `SKILL.md` files. Skillogy ships behind a feature flag and becomes default after benchmark validation. `SKILL.md` authoring is unchanged across both systems.

---

## How Skills Work

Skills use **progressive disclosure** across three loading stages:

| Stage | What loads | Token cost | When |
|-------|-----------|-----------|------|
| 1 | YAML frontmatter (`name` + `description` only) | ~50–100 | Agent boot — injected into system prompt for all relevant skills |
| 2 | Full `SKILL.md` body | ~500–2,000 | Agent calls `load_skill()` after deciding the skill is relevant |
| 3 | `references/` documents | variable | Agent reads supplementary references when the skill body instructs it to |

The agent sees only frontmatter initially. When a task matches a skill's description, the agent loads the full file. This keeps context windows lean while making deep knowledge available when needed.

`load_skill()` is the only supported reader for skill markdown. It accepts:

- exact virtual paths such as `/skills/standard/recon/passive-recon/SKILL.md`
- relative paths such as `standard/recon/passive-recon/SKILL.md`
- unique slugs such as `passive-recon`

Ambiguous slugs return a list of exact paths instead of guessing.

**System prompt injection** (generated automatically by `SkillsMiddleware`):

```
Available Skills:
- **passive-recon**: Use when gathering intelligence WITHOUT touching the target: WHOIS,
  DNS, subdomain enumeration, crt.sh, ASN mapping. Triggers on: 'passive recon', 'WHOIS',
  'subdomain', 'amass'.
  -> `load_skill("passive-recon")` or `load_skill("/skills/standard/recon/passive-recon/SKILL.md")`
```

---

## Skill Categories

Skills ship as package data under `decepticon/skills/` and are served in-process
at the virtual prefix `/skills/`. The tree has three roots:

- `/skills/standard/<dir>/` — built-in OSS roles. The default source list for a
  standard role is `[f"/skills/standard/{role}/", "/skills/shared/"]`
  (`skills_sources_for`, `agents/middleware_slots.py:102`).
- `/skills/plugins/<name>/` — plugin specialists. These agents pass an explicit
  `skill_sources=` kwarg to `build_middleware` rather than relying on the
  `/skills/standard/{role}/` fallback.
- `/skills/shared/` — cross-cutting protocols injected into every standard role.

| Directory | Agent(s) | Coverage |
|-----------|---------|----------|
| `/skills/standard/soundwave/` | Soundwave | RoE templates, ConOps, OPPLAN generation, threat profiles |
| `/skills/shared/` | Every standard role | OPSEC, defense evasion, workflow protocols, finding format, deconfliction |
| `/skills/standard/recon/` | Recon | Passive recon, active recon, web recon, cloud recon, OSINT, reporting |
| `/skills/standard/exploit/` | Exploit | Web exploitation, Active Directory attacks |
| `/skills/standard/post-exploit/` | Post-Exploit | Credential access, privilege escalation, lateral movement, C2 |
| `/skills/standard/ad/` | AD Operator | Kerberoasting, Pass-the-Hash, BloodHound, DCSync |
| `/skills/standard/cloud/` | Cloud Hunter | IAM escalation, S3/GCS/Azure storage attacks, metadata abuse |
| `/skills/standard/contracts/` | Contract Auditor | Solidity analysis, reentrancy, access control, token mechanics |
| `/skills/standard/reverser/` | Reverser | Static analysis, dynamic analysis, decompilation, binary patching |
| `/skills/standard/analyst/` | Analyst | Research, graph querying, executive summaries |
| `/skills/standard/phisher/` | Phisher | Lure deconfliction and phishing operations |
| `/skills/standard/mobile/` | MobileOperator | Android / iOS application attacks |
| `/skills/standard/wireless/` | WirelessOperator | Wireless / RF attacks |
| `/skills/standard/decepticon/` | Decepticon | Core orchestration procedures (engagement lifecycle, kill-chain analysis, final report) |
| `/skills/plugins/scanner/` | Scanner | Vulnerability scanning, automated tool integration |
| `/skills/plugins/exploiter/` | Exploiter | PoC generation, CVE reproduction, weaponization |
| `/skills/plugins/verifier/` | Verifier | Multi-method vulnerability confirmation |
| `/skills/plugins/detector/` | Detector | Detection rule generation, IOC extraction |
| `/skills/plugins/patcher/` | Patcher | Remediation code, configuration hardening |
| `/skills/plugins/vulnresearch/` | Vulnresearch (orchestrator) | Five-stage vulnerability research pipeline coordination |
| `/skills/plugins/llm-redteam/` | LLM red-team specialist (commercial) | LLM/agentic attack techniques (ASI taxonomy) |
| `/skills/benchmark/` | CTF / XBOW benchmark mode | Activated when `BENCHMARK_MODE=1` — flag-capture rules and challenge context handling |

> **Note — role-vs-directory mismatch**: several roles do not share a name with
> their on-disk directory. The default fallback resolves the source to
> `/skills/standard/{role}/`, but the skills actually live under a different
> directory name:
>
> | Role | Resolved source (`{role}`) | On-disk directory |
> |------|---------------------------|-------------------|
> | `postexploit` | `/skills/standard/postexploit/` | `/skills/standard/post-exploit/` |
> | `ad_operator` | `/skills/standard/ad_operator/` | `/skills/standard/ad/` |
> | `cloud_hunter` | `/skills/standard/cloud_hunter/` | `/skills/standard/cloud/` |
> | `contract_auditor` | `/skills/standard/contract_auditor/` | `/skills/standard/contracts/` |
>
> The directories in the table above reflect where the skills actually live. This
> mismatch is a code bug being fixed separately.
>
> `mobile_operator` and `wireless_operator` are **not** affected: their factories
> pass an explicit `skill_sources=` kwarg (`/skills/standard/mobile/` and
> `/skills/standard/wireless/` respectively), so they bypass the `{role}` fallback
> and resolve correctly.

### Library categories (no consuming agent yet)

These directories live under `/skills/standard/` but no role resolves to them, so
no agent loads them today. They are authored as a skill library for future roles
or manual `load_skill()` use.

| Directory | Coverage |
|-----------|----------|
| `/skills/standard/dfir/` | Digital forensics & incident response |
| `/skills/standard/ics/` | Industrial control systems / OT |
| `/skills/standard/iot/` | IoT / embedded (firmware, Zigbee, LoRaWAN) |
| `/skills/standard/osint/` | Open-source intelligence |
| `/skills/standard/supply-chain/` | Supply-chain attack techniques |
| `/skills/standard/phish/` | Phishing techniques (distinct from the consumed `phisher/` dir) |

---

## Skill Directory Structure

Each skill is a directory:

```
{skill-name}/
├── SKILL.md            # Required: frontmatter + body
├── references/         # Optional: deep-dive technique docs (Level 3)
│   ├── technique-a.md
│   └── technique-b.md
├── scripts/            # Optional: automation scripts the agent executes
│   └── parse_output.py
└── assets/             # Optional: templates, config files
```

---

## Skill Format

### Frontmatter

```yaml
---
name: passive-recon
description: "Use when gathering intelligence WITHOUT touching the target: WHOIS, DNS,
  subdomain enumeration (subfinder/amass), Certificate Transparency (crt.sh), httpx
  probing, ASN/BGP mapping. Triggers on: 'passive recon', 'WHOIS', 'DNS lookup',
  'subdomain', 'subfinder', 'amass', 'crt.sh', 'ASN', 'httpx'."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  tags: passive, dns, subdomain-enum, whois, ct-logs, httpx, asn
  mitre_attack: T1590, T1591, T1592, T1593, T1596
---
```

#### Required fields

| Field | Type | Rule |
|-------|------|------|
| `name` | string | 1–64 chars, lowercase + hyphens, must match directory name |
| `description` | string | 1–1024 chars. Format: `"Use when {condition}: {tools/actions}. Triggers on: '{kw1}', '{kw2}'."` |

#### Optional fields

| Field | Type | Notes |
|-------|------|-------|
| `allowed-tools` | string | Space-separated tool names (not a YAML list) |
| `metadata.subdomain` | string | MITRE ATT&CK tactic-based category |
| `metadata.tags` | string | Comma-separated semantic tags |
| `metadata.mitre_attack` | string | Comma-separated ATT&CK technique IDs |

#### `subdomain` values

| Value | MITRE Tactic | Description |
|-------|-------------|-------------|
| `planning` | — | Pre-engagement (RoE, ConOps, OPPLAN) |
| `reconnaissance` | TA0043 | Passive/active/cloud/web recon |
| `execution` | TA0002 | Code execution |
| `privilege-escalation` | TA0004 | Privilege escalation |
| `defense-evasion` | TA0005 | Defense bypass |
| `credential-access` | TA0006 | Credential theft |
| `lateral-movement` | TA0008 | Pivoting |
| `command-and-control` | TA0011 | C2 infrastructure |
| `opsec` | — | Operational security (cross-cutting) |
| `reporting` | — | Finding and report generation |

### Body structure

```markdown
# Skill Title

One-line description of the skill's core role and principles.

## Quick Reference — Copy-Paste Commands
[Immediately executable commands]

## MITRE ATT&CK Mapping
| Technique ID | Name | Tactic |

## 1. {Technique Section}
[Step-by-step with code examples]

## Tools & Resources
| Tool | Purpose | Platform |

## Detection Signatures
| Indicator | Detection Method | OPSEC Note |

## Error Handling & Edge Cases

## Decision Gate: {Current Phase} → {Next Phase}
[Checklist of transition criteria]

## Bundled Resources
### References
- `references/foo.md` — description. Read when {trigger condition}.
### Scripts
- `scripts/bar.py` — description. Usage: `python scripts/bar.py ...`
```

**Key rules:**
- Keep `SKILL.md` under 500 lines — move longer content to `references/`
- Output paths always under `/workspace/`
- Use `<TARGET>` placeholders instead of hardcoding targets
- `allowed-tools` must be a space-separated string, not a YAML list
- All `metadata` values must be strings

---

## Writing a Custom Skill

1. Create a directory under the appropriate category: `skills/standard/recon/my-skill/`
2. Write `SKILL.md` with frontmatter and body following the format above
3. Add `references/` docs for content over 100 lines
4. Add `scripts/` for any automation the agent should execute
5. Restart Decepticon — `SkillsMiddleware` discovers skills at agent boot

The skill is automatically available to agents whose source paths include your skill's parent directory. No registration required.

---

## Agent–Skill Mapping

Standard roles use the default `[f"/skills/standard/{role}/", "/skills/shared/"]`
fallback (`skills_sources_for`, `agents/middleware_slots.py:102`). Plugin specialists pass an explicit
`skill_sources=` list instead of relying on that fallback; the bash-executing
plugins (scanner, exploiter, detector, verifier, patcher) additionally pull
`/skills/standard/analyst/`.

| Agent (role) | Skill sources |
|-------|--------------|
| Decepticon (`decepticon`) | `/skills/standard/decepticon/`, `/skills/shared/` |
| Soundwave (`soundwave`) | `/skills/standard/soundwave/`, `/skills/shared/` |
| Recon (`recon`) | `/skills/standard/recon/`, `/skills/shared/` |
| Exploit (`exploit`) | `/skills/standard/exploit/`, `/skills/shared/` |
| Post-Exploit (`postexploit`) | `/skills/standard/postexploit/`, `/skills/shared/` |
| AD Operator (`ad_operator`) | `/skills/standard/ad_operator/`, `/skills/shared/` |
| Cloud Hunter (`cloud_hunter`) | `/skills/standard/cloud_hunter/`, `/skills/shared/` |
| Contract Auditor (`contract_auditor`) | `/skills/standard/contract_auditor/`, `/skills/shared/` |
| Reverser (`reverser`) | `/skills/standard/reverser/`, `/skills/shared/` |
| Analyst (`analyst`) | `/skills/standard/analyst/`, `/skills/shared/` |
| Phisher (`phisher`) | `/skills/standard/phisher/`, `/skills/shared/` |
| MobileOperator (`mobile_operator`) | `/skills/standard/mobile/`, `/skills/shared/` |
| WirelessOperator (`wireless_operator`) | `/skills/standard/wireless/`, `/skills/shared/` |
| Vulnresearch (`vulnresearch`) | `/skills/plugins/vulnresearch/`, `/skills/shared/` |
| Scanner (`scanner`) | `/skills/plugins/scanner/`, `/skills/standard/analyst/`, `/skills/shared/` |
| Exploiter (`exploiter`) | `/skills/plugins/exploiter/`, `/skills/standard/analyst/`, `/skills/shared/` |
| Detector (`detector`) | `/skills/plugins/detector/`, `/skills/standard/analyst/`, `/skills/shared/` |
| Verifier (`verifier`) | `/skills/plugins/verifier/`, `/skills/standard/analyst/`, `/skills/shared/` |
| Patcher (`patcher`) | `/skills/plugins/patcher/`, `/skills/standard/analyst/`, `/skills/shared/` |

`/skills/shared/` (OPSEC, defense evasion, workflow) is appended to every standard
role's default source list — including Soundwave, which uses the same
`skills_sources_for(role)` fallback. The `SKILLS` middleware slot is part of the base
slot set (`decepticon_core/contracts/slots.py`), so every role carries it.

When `BENCHMARK_MODE=1`, `/skills/benchmark/` is appended to a role's sources
(`agents/_benchmark_mode.py`).
