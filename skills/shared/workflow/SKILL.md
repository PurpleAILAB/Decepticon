---
name: workflow
description: "Top-level orchestration skill — execution order and dependencies across all Decepticon skills."
allowed-tools: Read
metadata:
  subdomain: orchestration
  when_to_use: "start engagement, what's next, run workflow, engagement status, which skill, next step"
  tags: workflow, orchestrator, dependency-graph, engagement-state
  mitre_attack: []
---

# Engagement Workflow Orchestrator

This skill defines the execution order, dependencies, and handoff criteria between all Decepticon skills. It is the single source of truth for "what happens when" during an engagement.

## Skill Dependency Graph

```
┌─────────────────── PLANNING ────────────────────┐
│  roe-template → threat-profile → conops-template │
│                                    │              │
│                               opplan-converter    │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌─────────────────── RECON ───────────────────────┐
│  passive-recon → osint → cloud-recon             │
│       │                      │                   │
│       ▼                      ▼                   │
│  active-recon ──────→ web-recon                  │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌─────────────────── EXPLOITATION ────────────────┐
│  web-exploitation ──┐                            │
│                     ├──→ initial foothold         │
│  ad-exploitation ───┘                            │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌─────────────────── POST-EXPLOITATION ───────────┐
│  credential-access → privilege-escalation        │
│       │                      │                   │
│       ▼                      ▼                   │
│  lateral-movement ←──── c2 (implant control)     │
│       │                                          │
│       └──→ (loop: new host → creds → privesc     │
│             → lateral → next host)               │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌─────────────────── REPORTING ───────────────────┐
│  reporting (synthesizes all phase findings)       │
└──────────────────────────────────────────────────┘

Cross-cutting: opsec + defense-evasion (apply to ALL phases)
```

## Phase 1: Planning

Planning skills run sequentially — each depends on the previous output.

| Order | Skill | Input | Output | Gate |
|-------|-------|-------|--------|------|
| 1 | `roe-template` | User interview | `roe.json` | Client confirmation |
| 2 | `threat-profile` | RoE scope, user input | `ThreatActor` JSON | Validated against RoE |
| 3 | `conops-template` | `roe.json` + threat profile | `conops.json`, `deconfliction.json` | Kill chain scoped to RoE |
| 4 | `opplan-converter` | `roe.json` + `conops.json` | `opplan.json` | All objectives pass validation checklist |

### Planning → Recon Gate
- [ ] `roe.json` exists and is validated
- [ ] `conops.json` exists with kill chain phases
- [ ] `opplan.json` exists with sequenced objectives
- [ ] All documents cross-reference each other consistently

## Phase 2: Reconnaissance

General flow: passive → OSINT → cloud → active → web.

| Order | Skill | Prerequisite | Focus | Noise Level |
|-------|-------|-------------|-------|-------------|
| 1 | `passive-recon` | OPPLAN objectives | DNS, subdomains, WHOIS, ASN, CT logs, fingerprinting | None |
| 2 | `osint` | Passive recon | Email harvesting, employee enum, GitHub secrets, breach data | None |
| 3 | `cloud-recon` | Subdomain + DNS data | S3/Blob/GCS buckets, cloud services, CDN origins | Low |
| 4 | `active-recon` | Passive findings | Port scanning, service detection, banner grabbing | Medium-High |
| 5 | `web-recon` | Active recon identifies web services | Directory fuzzing, API enum, JS analysis, CMS scanning | Medium-High |

### Recon Skill Boundaries

| Skill | Does | Does NOT |
|-------|------|----------|
| `passive-recon` | DNS, subdomains, WHOIS, ASN, CT logs, httpx, tech fingerprint | Email, employee enum, breach data |
| `osint` | Email, employee/org mapping, GitHub secrets, breach data, dorking | DNS, subdomain enum, port scanning |
| `cloud-recon` | Cloud detection, bucket enum, service discovery, takeover checks | Port scanning, web app testing |
| `active-recon` | Port scan, service versions, NSE, vuln scan (nuclei/nikto), SSL | Web fuzzing, API enum, CMS scanning |
| `web-recon` | Dir/file fuzzing, vHost, API enum, JS analysis, CMS, WAF detect | Port scanning, DNS recon, OSINT |

### Recon → Exploitation Gate
- [ ] Complete domain/subdomain inventory
- [ ] DNS infrastructure and IP/ASN mapping done
- [ ] Live hosts validated (httpx)
- [ ] Service versions and technologies documented
- [ ] OSINT findings documented
- [ ] High-value targets and attack surface identified
- [ ] Potential vulnerabilities catalogued (nuclei/nikto output)

## Phase 3: Exploitation

Exploitation is **non-linear** — the chosen path depends on recon findings. The agent selects the applicable skill based on target type.

| Skill | Target Type | Prerequisite | Techniques |
|-------|------------|-------------|------------|
| `web-exploitation` | Web applications | web-recon findings | SQLi, SSTI, deserialization, SSRF, IDOR, command injection |
| `ad-exploitation` | Active Directory | active-recon identifies AD (88/389/636) | Kerberoasting, AS-REP, ADCS abuse, DCSync |

### Exploitation Routing Logic
```
IF web-recon found web vulnerabilities:
  → invoke web-exploitation
IF active-recon found AD services (port 88/389/636):
  → invoke ad-exploitation (after initial foothold)
IF both:
  → web-exploitation first (for initial access), then ad-exploitation
```

### Exploitation → Post-Exploitation Gate
- [ ] Initial foothold established (shell or implant on target)
- [ ] Access type documented (user context, privileges)
- [ ] Persistence method selected (or deferred to post-exploitation)
- [ ] C2 channel established or planned

## Phase 4: Post-Exploitation

Post-exploitation is a **loop** — after each new host compromise, the cycle repeats until objectives are met.

```
┌──→ credential-access ──→ privilege-escalation ──┐
│         │                        │               │
│         ▼                        ▼               │
│    lateral-movement ←─── c2 (control channel)    │
│         │                                        │
│         └── new host found? ─── YES ─────────────┘
│                                  │
│                                  NO
│                                  │
│                                  ▼
│                            objectives met?
│                                  │
│                         YES → Phase 5 (Reporting)
│                         NO  → reassess attack path
└──────────────────────────────────┘
```

| Order | Skill | Input | Output | Noise Level |
|-------|-------|-------|--------|-------------|
| 1 | `c2` | Initial foothold | Implant + C2 channel | Medium (network traffic) |
| 2 | `credential-access` | Shell/implant on host | Credentials (hashes, tickets, plaintext) | High (touches LSASS/SAM) |
| 3 | `privilege-escalation` | Low-priv access | SYSTEM/root access | Medium-High (modifies system) |
| 4 | `lateral-movement` | Creds + network map | Access to adjacent hosts | Medium (auth events) |

### Post-Exploitation Skill Boundaries

| Skill | Does | Does NOT |
|-------|------|----------|
| `c2` | Framework-agnostic C2 orchestration: channel types, implant modes, redirectors, decision gates | Framework-specific setup (use `c2-sliver`) |
| `c2-sliver` | Sliver-specific: server connection, listeners, implant gen, BOF/Armory, post-implant ops | Credential dumping, privilege escalation |
| `credential-access` | LSASS dump, SAM hive, DPAPI, NTLM relay, password spray, hash crack | Privilege escalation, lateral movement |
| `privilege-escalation` | Token impersonation, UAC bypass, service abuse, Linux privesc | Credential dumping, lateral movement |
| `lateral-movement` | PTH, PTT, WMI/WinRM/PsExec/RDP, SMB ops, tunneling | Credential extraction, privilege escalation |

### Post-Exploitation Loop Exit Criteria
- [ ] All OPPLAN objectives achieved
- [ ] Target data/access obtained per RoE scope
- [ ] Attack path fully documented (every hop, credential, escalation)
- [ ] Evidence collected for reporting

## Phase 5: Reporting

| Order | Skill | Input | Output |
|-------|-------|-------|--------|
| 1 | `reporting` | All phase findings | `report_<target>_<phase>.md`, `report_<target>.json` |

### Reporting → OPPLAN Feedback
After reporting, update `opplan.json`:
- Mark completed objectives as `"status": "completed"`
- Update objectives with actual findings
- If new targets discovered, create new objectives following the OPPLAN schema

## Cross-Cutting Skills

### OPSEC
The `opsec` skill applies to **every action in every phase**:

| Phase | OPSEC Focus |
|-------|------------|
| Planning | Scope enforcement, RoE compliance |
| Recon (Passive) | DNS resolver selection, query patterns |
| Recon (Active) | Scan timing, rate limiting, UA rotation |
| Exploitation | Payload delivery stealth, exploit noise awareness |
| Post-Exploitation | Process injection, log cleanup, ticket lifecycle |
| C2 | Redirector usage, jitter, domain fronting |
| Reporting | Evidence handling, data classification |

### Defense Evasion
The `defense-evasion` skill applies to **exploitation and post-exploitation phases**:

| Phase | Evasion Focus |
|-------|-------------|
| Exploitation | AMSI bypass, payload obfuscation, custom loaders |
| Post-Exploitation | ETW patching, syscalls, process injection, LOLBAS |
| C2 | Malleable profiles, encrypted channels, sleep obfuscation |
| Lateral Movement | Living-off-the-land binaries, token manipulation |

## Sandbox Bash Discipline

The sandbox bash environment is intentionally restricted. The following patterns waste a probe (or hang the cycle) and MUST be avoided across every phase. Prefer the `python3` patterns below — they are deterministic, timeout-bounded, and produce machine-readable output.

### Anti-patterns (do NOT)

| Pattern | Why it's bad |
|---------|--------------|
| `bash <<'EOF' ... EOF` heredocs in tool calls | Often truncated mid-stream, brittle quoting, ambiguous timeout behavior. |
| Trailing `&` to "parallelize" (`curl ... & curl ... & wait`) | Backgrounded jobs detach from the tool's stdout/timeout — silent failures, races nobody can read. |
| Unbounded `sleep`, `nc -l`, `tail -f`, `while true` | Hits the wall-clock and burns the entire cycle; never produces useful output. |
| `timeout 5 bash -c ""` (empty command) | Zero-effect probe, recon-scope-creep tell. |
| Long pipelines without `set -o pipefail` | Failures hide behind the last successful command. |
| Implicit-shell loops over network targets without per-iteration timeout | One slow host blocks all the others. |

### Preferred pattern — Python heredoc with explicit timeouts

```bash
python3 - <<'PY'
import requests, sys
r = requests.get("https://<TARGET>/path", timeout=5)
print(r.status_code, len(r.content))
PY
```

For parallel work, use `concurrent.futures.ThreadPoolExecutor` (bounded `max_workers`, every call carries `timeout=5`) instead of bash `&`. For repeated probes, write a tight `python3 -c` one-liner with an explicit total wall-clock cap. Every network call MUST set a timeout. Every loop MUST be bounded.

## Workflow Commands

| User Says | Action |
|-----------|--------|
| "Start new engagement" | Begin with `roe-template` |
| "Define scope" / "Create RoE" | Invoke `roe-template` |
| "Who should we emulate?" | Invoke `threat-profile` |
| "Create CONOPS" / "Design operation" | Invoke `conops-template` |
| "Create OPPLAN" | Invoke `opplan-converter` |
| "Start recon" | Check OPPLAN exists, then follow recon sequence |
| "Exploit target" | Check recon complete, select exploitation skill |
| "Set up C2" | Invoke `c2` |
| "Dump creds" / "Get credentials" | Invoke `credential-access` |
| "Escalate privileges" / "Get SYSTEM" | Invoke `privilege-escalation` |
| "Move laterally" / "Pivot" | Invoke `lateral-movement` |
| "Bypass AV" / "Evade EDR" | Invoke `defense-evasion` |
| "What's next?" | Check engagement state, recommend next skill |
| "Generate report" | Invoke `reporting` |
| "OPSEC check" | Invoke `opsec` for current phase review |

## Engagement State Detection

To determine "what's next", check for these artifacts:

```
./
├── roe.json               → Planning Phase 1 complete
├── conops.json            → Planning Phase 3 complete
├── deconfliction.json     → Planning Phase 3 complete
├── opplan.json            → Planning complete (ready for recon)
├── recon/                 → Recon in progress
│   ├── subdomains.txt         → Passive recon started
│   ├── httpx_results.txt      → Passive recon probing done
│   ├── nmap_*.txt             → Active recon started
│   └── ffuf_*.json            → Web recon started
├── exploit/               → Exploitation in progress
│   ├── foothold_*.txt         → Initial access achieved
│   └── shells.json            → Active sessions tracked
├── post-exploit/          → Post-exploitation in progress
│   ├── creds_*.json           → Credentials collected
│   ├── privesc_*.txt          → Escalation results
│   ├── lateral_*.txt          → Movement log
│   └── loot/                  → Extracted data
├── post-exploit/c2/       → C2 operations active (server runs in c2-sliver container)
│   ├── implants/              → Generated implant binaries
│   └── c2_operations_log.md   → Timestamped C2 operator actions
└── report_*.md            → Reporting complete
```

## Agent → Skill Mapping

| Agent | CLI Command | SkillsMiddleware Sources | Skills |
|-------|-------------|--------------------------|--------|
| **Soundwave** | `/plan` | `/skills/soundwave/` | `roe-template`, `threat-profile`, `conops-template`, `opplan-converter` |
| **Recon** | `/recon` | `/skills/recon/`, `/skills/shared/` | `passive-recon`, `osint`, `cloud-recon`, `active-recon`, `web-recon`, `reporting` + shared |
| **Exploit** | `/exploit` | `/skills/exploit/`, `/skills/shared/` | `web`, `ad` + shared (`defense-evasion`, `opsec`, `workflow`) |
| **PostExploit** | `/postexploit` | `/skills/post-exploit/`, `/skills/shared/` | `credential-access`, `privilege-escalation`, `lateral-movement`, `c2`, `c2-sliver` + shared |
| **Decepticon** | `/decepticon` | `/skills/decepticon/`, `/skills/shared/` | `orchestration`, `engagement-lifecycle`, `kill-chain-analysis` + shared |

Cross-cutting (via `/skills/shared/`): `opsec` (Recon + Exploit + PostExploit), `defense-evasion` (Exploit + PostExploit), `workflow` (all)

## Full Kill Chain Skill Inventory

| Phase | Agent | Source | Skills | MITRE Tactics |
|-------|-------|--------|--------|---------------|
| Planning | Soundwave | `/skills/soundwave/` | `roe-template`, `threat-profile`, `conops-template`, `opplan-converter` | — |
| Reconnaissance | Recon | `/skills/recon/` | `passive-recon`, `osint`, `cloud-recon`, `active-recon`, `web-recon`, `reporting` | TA0043 |
| Exploitation | Exploit | `/skills/exploit/` | `web`, `ad` | TA0001, TA0002 |
| Post-Exploitation | PostExploit | `/skills/post-exploit/` | `credential-access`, `privilege-escalation`, `lateral-movement`, `c2`, `c2-sliver` | TA0006, TA0004, TA0008, TA0011 |
| Orchestration | Decepticon | `/skills/decepticon/` | `orchestration`, `engagement-lifecycle`, `kill-chain-analysis` | — |
| Cross-cutting | Recon/Exploit/PostExploit/Decepticon | `/skills/shared/` | `opsec`, `defense-evasion`, `workflow` | TA0005 |
