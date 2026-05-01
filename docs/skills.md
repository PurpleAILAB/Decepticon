# Skills

Skills are structured knowledge files that agents load on demand. They encode offensive techniques, OPSEC procedures, reporting templates, and engagement workflows — organized by kill chain phase and mapped to MITRE ATT&CK.

---

## How Skills Work

Skills use **progressive disclosure** across three loading stages:

| Stage | What loads | Token cost | When |
|-------|-----------|-----------|------|
| 1 | YAML frontmatter (`name` + `description` only) | ~50–100 | Agent boot — injected into system prompt for all relevant skills |
| 2 | Full `SKILL.md` body | ~500–2,000 | Agent calls `read_file()` after deciding the skill is relevant |
| 3 | `references/` documents | variable | Agent reads supplementary references when the skill body instructs it to |

The agent sees only frontmatter initially. When a task matches a skill's description, the agent reads the full file. This keeps context windows lean while making deep knowledge available when needed.

**System prompt injection** (generated automatically by `SkillsMiddleware`):

```
Available Skills:
- **passive-recon**: Use when gathering intelligence WITHOUT touching the target: WHOIS,
  DNS, subdomain enumeration, crt.sh, ASN mapping. Triggers on: 'passive recon', 'WHOIS',
  'subdomain', 'amass'.
  -> Read `/skills/recon/passive-recon/SKILL.md` for full instructions
```

---

## Skill Categories

Skills live in `skills/` organized by agent role:

| Directory | Agent(s) | Coverage |
|-----------|---------|----------|
| `skills/soundwave/` | Soundwave | RoE templates, ConOps, OPPLAN generation, threat profiles |
| `skills/shared/` | Every non-planning agent | OPSEC, defense evasion, workflow protocols, finding format, deconfliction |
| `skills/recon/` | Recon | Passive recon, active recon, web recon, cloud recon, OSINT, reporting |
| `skills/exploit/` | Exploit | Web exploitation, Active Directory attacks |
| `skills/scanner/` | Scanner | Vulnerability scanning, automated tool integration |
| `skills/post-exploit/` | Post-Exploit | Credential access, privilege escalation, lateral movement, C2 |
| `skills/ad/` | AD Operator | Kerberoasting, Pass-the-Hash, BloodHound, DCSync |
| `skills/cloud/` | Cloud Hunter | IAM escalation, S3/GCS/Azure storage attacks, metadata abuse |
| `skills/contracts/` | Contract Auditor | Solidity analysis, reentrancy, access control, token mechanics |
| `skills/reverser/` | Reverser | Static analysis, dynamic analysis, decompilation, binary patching |
| `skills/exploiter/` | Exploiter | PoC generation, CVE reproduction, weaponization |
| `skills/verifier/` | Verifier | Multi-method vulnerability confirmation |
| `skills/detector/` | Detector | Detection rule generation, IOC extraction |
| `skills/patcher/` | Patcher | Remediation code, configuration hardening |
| `skills/analyst/` | Analyst | Research, graph querying, executive summaries |
| `skills/vulnresearch/` | Vulnresearch (orchestrator), Scanner, Detector | Five-stage vulnerability research pipeline coordination |
| `skills/decepticon/` | Decepticon | Core orchestration procedures (engagement lifecycle, kill-chain analysis, final report) |
| `skills/benchmark/` | CTF / XBOW benchmark mode | Activated when `BENCHMARK_MODE=1` — flag-capture rules and challenge context handling |

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

1. Create a directory under the appropriate category: `skills/recon/my-skill/`
2. Write `SKILL.md` with frontmatter and body following the format above
3. Add `references/` docs for content over 100 lines
4. Add `scripts/` for any automation the agent should execute
5. Restart Decepticon — `SkillsMiddleware` discovers skills at agent boot

The skill is automatically available to agents whose source paths include your skill's parent directory. No registration required.

---

## Agent–Skill Mapping

| Agent | Skill sources |
|-------|--------------|
| Decepticon | `skills/decepticon/`, `skills/shared/` |
| Vulnresearch | `skills/vulnresearch/`, `skills/shared/` |
| Soundwave | `skills/soundwave/` |
| Recon | `skills/recon/`, `skills/shared/` |
| Scanner | `skills/scanner/`, `skills/vulnresearch/`, `skills/shared/` |
| Exploit | `skills/exploit/`, `skills/shared/` |
| Exploiter | `skills/exploiter/`, `skills/shared/` |
| Detector | `skills/detector/`, `skills/vulnresearch/`, `skills/shared/` |
| Verifier | `skills/verifier/`, `skills/shared/` |
| Patcher | `skills/patcher/`, `skills/shared/` |
| Post-Exploit | `skills/post-exploit/`, `skills/shared/` |
| AD Operator | `skills/ad/`, `skills/shared/` |
| Cloud Hunter | `skills/cloud/`, `skills/shared/` |
| Contract Auditor | `skills/contracts/`, `skills/shared/` |
| Reverser | `skills/reverser/`, `skills/shared/` |
| Analyst | `skills/analyst/`, `skills/shared/` |

`skills/shared/` (OPSEC, defense evasion, workflow) is injected into every non-planning agent. Soundwave is the only agent that does not load `skills/shared/` — it is a document-generation planner, not an operational agent.
