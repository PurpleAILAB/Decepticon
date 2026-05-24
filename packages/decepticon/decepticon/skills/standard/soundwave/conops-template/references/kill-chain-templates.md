# Kill Chain Phase Templates

Select applicable phases based on engagement type and RoE scope.

## Kill Chain Phases (5-Phase Model)

| Phase | Description | Success Criteria | Typical Tools |
|-------|-------------|-----------------|---------------|
| recon | Passive + active intelligence gathering | Complete attack surface map | subfinder, nmap, httpx, nuclei |
| initial-access | Exploit vulnerability, gain initial foothold | Shell or credentials obtained | metasploit, manual exploit, phishing |
| post-exploit | Persistence, privesc, lateral movement, credential access | Domain admin or target data reachable | implant, LOLBins, mimikatz |
| c2 | Command & control channel establishment | Stable, covert C2 communication | Sliver, Cobalt Strike |
| exfiltration | Extract target data, actions on objectives | Proof of data access achieved | custom scripts, DNS exfil |

## Engagement Type → Phase Selection

### External Recon-Only
- Phases: `recon` only
- Focus: Attack surface mapping, no exploitation

### External Penetration Test
- Phases: `recon` → `initial-access`
- Focus: Find and prove exploitable vulnerabilities

### Full Red Team
- Phases: All 5 phases
- Focus: End-to-end adversary simulation with OPSEC discipline

### Assumed Breach
- Phases: `post-exploit` → `c2` → `exfiltration`
- Skip: `recon` and `initial-access` (start with provided access)

### Internal Assessment
- Phases: `recon` → `initial-access` → `post-exploit` → `c2` → `exfiltration`
- Start from: Internal network position

## MITRE ATT&CK Tactic Mapping

| Kill Chain Phase | MITRE Tactics |
|---|---|
| recon | TA0043 Reconnaissance |
| initial-access | TA0001 Initial Access, TA0002 Execution |
| post-exploit | TA0003 Persistence, TA0004 Privilege Escalation, TA0005 Defense Evasion, TA0006 Credential Access, TA0007 Discovery, TA0008 Lateral Movement, TA0009 Collection |
| c2 | TA0011 Command and Control |
| exfiltration | TA0010 Exfiltration, TA0040 Impact |

## Phase → Sub-Agent Routing

| Phase | Sub-Agent | Notes |
|-------|-----------|-------|
| recon | recon | Passive and active reconnaissance |
| initial-access | exploit | Exploitation and initial foothold |
| post-exploit | postexploit | All post-compromise activities |
| c2 | postexploit | C2 setup via postexploit agent |
| exfiltration | postexploit | Data collection and exfiltration |

## Phase → OPSEC Level Guidance

| Phase | Typical OPSEC | Reasoning |
|-------|---------------|-----------|
| recon (passive) | standard | No target interaction |
| recon (active) | careful | Scan traffic visible to IDS/IPS |
| initial-access | careful-quiet | Exploitation generates alerts |
| post-exploit | quiet | Must avoid triggering EDR/SIEM |
| c2 | quiet-silent | C2 traffic is primary detection vector |
| exfiltration | silent | Data movement most heavily monitored |
