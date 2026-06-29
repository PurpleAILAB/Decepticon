---
name: response-playbook
description: "Incident response playbook generation — structured containment, eradication, and recovery procedures from engagement findings. Produces actionable runbooks with decision trees, escalation criteria, and evidence collection steps aligned to NIST SP 800-61r2."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "incident response, response playbook, containment, eradication, recovery, ir playbook, runbook, incident handling, nist 800-61, sans ir, containment strategy, evidence collection"
  tags: "incident-response, playbook, containment, eradication, recovery, nist, runbook, blue-team"
  mitre_attack: "T1059, T1078, T1486, T1190"
---

# Incident Response Playbook Generation

Generate structured incident response playbooks from engagement findings. Each playbook follows the NIST SP 800-61r2 lifecycle (Preparation → Detection & Analysis → Containment → Eradication → Recovery → Lessons Learned) and produces actionable runbooks operators can execute under pressure.

## Quick Reference

```bash
# Initialize playbook output directory
mkdir -p /workspace/playbooks

# Generate playbook from a finding
python3 << 'PYEOF'
import yaml, json, os, uuid
from datetime import datetime

finding_path = '/workspace/findings/<FINDING>.md'
with open(finding_path) as f:
    content = f.read()
    fm = content.split('---', 2)[1]
    finding = yaml.safe_load(fm)

playbook = {
    "id": str(uuid.uuid4()),
    "title": f"IR Playbook: {finding.get('title', 'Unknown')}",
    "created": datetime.now().isoformat(),
    "severity": finding.get('severity', 'high'),
    "mitre_techniques": finding.get('mitre_attack', []),
    "phases": ["detection", "containment", "eradication", "recovery"]
}

out = f"/workspace/playbooks/{finding.get('title','playbook').replace(' ','-').lower()}.json"
with open(out, 'w') as f:
    json.dump(playbook, f, indent=2)
print(f"[+] Playbook scaffold → {out}")
PYEOF
```

## MITRE ATT&CK Mapping

| Technique | ID | Playbook Type |
|---|---|---|
| Command & Scripting Interpreter | T1059 | Malware execution response |
| Valid Accounts | T1078 | Compromised credential response |
| Data Encrypted for Impact | T1486 | Ransomware response |
| Exploit Public-Facing Application | T1190 | Web application compromise response |

## 1. Playbook Structure

Every playbook follows this template:

```markdown
# IR Playbook: [Incident Type]

## Metadata
- **Playbook ID**: PB-YYYY-NNN
- **Severity**: Critical / High / Medium / Low
- **MITRE ATT&CK**: T1059.001, T1078
- **Last Updated**: YYYY-MM-DD
- **Approver**: [SOC Lead / IR Manager]

## Trigger Conditions
- [ ] Alert from [SIEM rule / EDR detection / user report]
- [ ] Confirmed by [triage analyst / automated enrichment]

## Phase 1: Detection & Analysis (0–30 min)

### Triage Checklist
- [ ] Confirm alert is not false positive
- [ ] Identify affected hosts and user accounts
- [ ] Determine initial access vector
- [ ] Assess blast radius (lateral movement indicators)
- [ ] Assign incident severity

### Evidence Collection
- [ ] Capture volatile data (memory, network connections, running processes)
- [ ] Preserve relevant log sources (SIEM, EDR, proxy, DNS, auth)
- [ ] Screenshot active sessions
- [ ] Record timeline of known events

### Decision Gate
IF confirmed compromise → proceed to Phase 2
IF false positive → document and close

## Phase 2: Containment (30 min – 2 hr)

### Immediate Actions (Short-Term Containment)
- [ ] Isolate affected host(s) from network (EDR isolation / VLAN move)
- [ ] Disable compromised user account(s)
- [ ] Block known C2 IPs/domains at perimeter firewall
- [ ] Revoke active sessions (Azure AD / Okta / on-prem AD)

### Long-Term Containment
- [ ] Deploy additional monitoring on adjacent systems
- [ ] Apply emergency firewall rules
- [ ] Increase logging verbosity on affected segments
- [ ] Preserve forensic images before remediation

### Escalation Criteria
- [ ] Escalate to IR Manager if: >5 hosts affected
- [ ] Escalate to CISO if: data exfiltration confirmed
- [ ] Escalate to Legal if: PII/regulated data involved
- [ ] Engage external IR firm if: APT indicators present

## Phase 3: Eradication (2–24 hr)

### Remediation Steps
- [ ] Remove attacker persistence mechanisms
- [ ] Patch exploited vulnerability
- [ ] Reset all potentially compromised credentials
- [ ] Remove malicious files, scheduled tasks, registry keys
- [ ] Verify removal with EDR scan and manual review

### Validation
- [ ] Re-scan affected hosts with updated signatures
- [ ] Verify no active C2 beacons
- [ ] Confirm persistence mechanisms are removed
- [ ] Review adjacent hosts for indicators of compromise

## Phase 4: Recovery (24–72 hr)

### Restoration Steps
- [ ] Restore systems from known-good backups (if needed)
- [ ] Re-enable user accounts with new credentials
- [ ] Gradually restore network connectivity
- [ ] Monitor for re-infection indicators (7-day watch)

### Verification
- [ ] Confirm business services are operational
- [ ] Verify monitoring detections are active
- [ ] Validate no anomalous traffic from recovered hosts

## Phase 5: Lessons Learned (1–2 weeks post)

### Post-Incident Review
- [ ] Timeline reconstruction (what happened, when, response actions)
- [ ] Root cause analysis
- [ ] Detection gap analysis (what did we miss, what worked)
- [ ] Playbook update recommendations
- [ ] New detection rules created (reference Sigma rules)
```

## 2. Playbook Templates by Incident Type

### Ransomware Response

```yaml
trigger: "EDR alert for mass file encryption or ransom note detection"
immediate_containment:
  - Isolate all hosts showing encryption activity
  - Disable affected service accounts
  - Block lateral movement ports (445, 135, 3389, 5985)
  - Preserve at least one encrypted + one unencrypted sample
eradication:
  - Identify ransomware family (ID Ransomware, VirusTotal)
  - Determine initial access vector (phishing, RDP, exploit)
  - Remove ransomware binary and persistence
  - Check for data exfiltration (double-extortion)
recovery:
  - Restore from offline/immutable backups
  - Rebuild domain controllers if compromised
  - Force password reset domain-wide
  - Deploy additional EDR coverage
```

### Compromised Credentials Response

```yaml
trigger: "Impossible travel alert, credential stuffing detection, dark web exposure"
immediate_containment:
  - Disable affected account(s)
  - Revoke all active sessions and tokens
  - Reset MFA enrollment
  - Block source IPs at WAF/firewall
eradication:
  - Audit all actions performed by compromised account
  - Review mail forwarding rules, delegations, OAuth grants
  - Remove unauthorized persistent access (app passwords, API keys)
  - Scan for mailbox exfiltration rules
recovery:
  - Re-enable account with new credentials + MFA
  - Notify user with incident details
  - Monitor for 30 days post-recovery
```

### Web Application Compromise Response

```yaml
trigger: "WAF alert, anomalous server behavior, defacement, webshell detection"
immediate_containment:
  - Take application offline or enable maintenance mode
  - Block attacker source IPs
  - Snapshot affected server for forensics
  - Revoke application database credentials
eradication:
  - Identify and remove webshells / backdoors
  - Patch exploited vulnerability
  - Audit application code for additional weaknesses
  - Rotate all application secrets and API keys
recovery:
  - Redeploy application from known-good source
  - Restore database from pre-compromise backup (if tampered)
  - Re-enable with enhanced WAF rules
  - Conduct post-deployment security scan
```

## 3. Evidence Collection Commands

```bash
# Windows — volatile data collection
# Process listing with command lines
wmic process get ProcessId,Name,CommandLine,ParentProcessId /format:csv > evidence/processes.csv

# Network connections
netstat -anob > evidence/netstat.txt

# Logged-on users
query user > evidence/sessions.txt

# Scheduled tasks
schtasks /query /fo csv /v > evidence/scheduled_tasks.csv

# Recent PowerShell history
Get-Content (Get-PSReadlineOption).HistorySavePath > evidence/ps_history.txt

# Linux — volatile data collection
ps auxww > evidence/processes.txt
ss -tulnp > evidence/network.txt
last -Faixw > evidence/logins.txt
find /tmp /var/tmp /dev/shm -type f -mtime -7 -ls > evidence/recent_tmp.txt
cat /proc/*/cmdline | tr '\0' ' ' | sort -u > evidence/proc_cmdlines.txt
```

## 4. Decision Trees

```
[Alert Received]
    │
    ├─ Is it a known false positive pattern? ─── YES → Document and close
    │
    NO
    │
    ├─ Can we confirm malicious activity? ─── NO → Enrich and re-evaluate (30 min)
    │
    YES
    │
    ├─ Is data exfiltration occurring NOW? ─── YES → Immediate network isolation
    │
    NO
    │
    ├─ Are credentials compromised? ─── YES → Disable accounts, revoke sessions
    │
    ├─ Is lateral movement detected? ─── YES → Isolate segment, increase monitoring
    │
    └─ Proceed with standard containment timeline
```

## 5. Playbook Quality Checklist

- [ ] Every step is a concrete action (no "consider" or "evaluate options")
- [ ] Time estimates for each phase
- [ ] Escalation criteria with specific thresholds
- [ ] Evidence collection steps precede any destructive remediation
- [ ] Recovery includes monitoring period with specific watchlist
- [ ] Lessons learned section references detection gap analysis

## References

- NIST SP 800-61r2 — Computer Security Incident Handling Guide
- SANS Incident Handler's Handbook — https://www.sans.org/white-papers/33901/
- MITRE ATT&CK — https://attack.mitre.org/
- CISA Incident Response Playbooks — https://www.cisa.gov/incident-response-playbooks
