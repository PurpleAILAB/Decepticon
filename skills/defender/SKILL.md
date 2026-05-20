---
name: defender-overview
description: Defender agent's playbook — write detection + monitoring rules from validated+patched findings. Sigma, Snort/Suricata, Semgrep, Falco, ModSecurity, Prometheus.
when_to_use: "detection sigma snort suricata semgrep falco waf modsecurity owasp crs alert"
mitre_attack: D3FEND
metadata:
  subdomain: defense
---

# Defender Skill Catalog

## Detection layer matrix

| Bug class | Primary rule format | Sub-skill |
|---|---|---|
| SQL injection | OWASP CRS / sigma DB-anomaly | `/skills/defender/sql-injection-rules/SKILL.md` |
| SSRF | egress firewall + WAF | `/skills/defender/ssrf-rules/SKILL.md` |
| RCE / deserialization | sigma process-spawn / falco execve | `/skills/defender/rce-rules/SKILL.md` |
| XSS stored | CSP report + WAF response-body | `/skills/defender/xss-rules/SKILL.md` |
| Auth anomaly | sigma — IP/UA/time correlation | `/skills/defender/auth-rules/SKILL.md` |
| Kerberoasting | sigma — 4769 anomaly | `/skills/defender/ad-rules/SKILL.md` |
| DCSync | sigma — 4662 replication GUID | `/skills/defender/ad-rules/SKILL.md` |
| LSASS access | sigma — 10/handle pattern | `/skills/defender/ad-rules/SKILL.md` |
| C2 beaconing | network — JA3 + sleep variance | `/skills/defender/c2-rules/SKILL.md` |
| Container escape | falco — capability / mount events | `/skills/defender/container-rules/SKILL.md` |
| Cloud privesc | CloudTrail / Cloudwatch alert | `/skills/defender/cloud-rules/SKILL.md` |

(Sub-skills referenced above are leaf SKILL.md files to be authored as
the defender stage matures; if not present yet, refer back to this
router and pick the closest format from §examples below.)

## Standard rule templates

### Sigma (universal log format)
```yaml
title: <Concise descriptive title>
id: <UUID4>
status: experimental
description: |
  Detects <bug class> against <target>. Source: decepticon-FIND-NNN.
references:
  - https://github.com/decepticon/findings/FIND-NNN
author: decepticon-defender
date: <YYYY-MM-DD>
logsource:
  product: <windows|linux|aws|azure>
  service: <security|sysmon|cloudtrail>
detection:
  selection:
    EventID: <int>
    SourceIP|startswith: <attacker_pattern>
    # ...
  condition: selection
falsepositives:
  - <known FP cause>
level: <informational|low|medium|high|critical>
tags:
  - attack.t1059       # MITRE ATT&CK technique ID
  - decepticon.find_NNN
```

### Snort / Suricata
```
alert tcp $EXTERNAL_NET any -> $HOME_NET <port> (
    msg:"<bug class> attempt - decepticon-FIND-NNN";
    flow:established,to_server;
    content:"<unique payload signature>"; nocase;
    pcre:"/<regex>/";
    classtype:web-application-attack;
    sid:<sid>;
    rev:1;
    reference:url,decepticon.io/findings/FIND-NNN;
)
```

### Semgrep (source-code regression gate)
```yaml
rules:
  - id: decepticon-FIND-NNN-regression
    pattern: |
      <vulnerable code pattern>
    message: |
      Regression of decepticon-FIND-NNN (<bug class>). Original
      sink at <file>:<line>. Apply pattern: <safe pattern>.
    severity: <ERROR|WARNING>
    languages: [<lang>]
    metadata:
      cwe: "CWE-<id>"
      owasp: "A<N>"
      finding: decepticon-FIND-NNN
```

### Falco (linux runtime)
```yaml
- rule: Suspicious shell from web process (decepticon-FIND-NNN)
  desc: |
    Web server spawned a shell, matching the deserialization-RCE
    pattern in finding NNN.
  condition: >
    spawned_process and
    proc.pname in (web_processes) and
    proc.name in (shell_binaries)
  output: |
    Shell spawned from web process (user=%user.name command=%proc.cmdline
    pid=%proc.pid parent=%proc.pname)
  priority: WARNING
  tags: [decepticon, find_NNN, container]
```

### ModSecurity / OWASP CRS
```
SecRule REQUEST_URI "@rx <vuln-pattern>" \
    "id:<id>,\
     phase:2,\
     deny,\
     status:403,\
     msg:'decepticon-FIND-NNN: <bug class> attempt',\
     logdata:'Matched URI: %{REQUEST_URI}',\
     tag:'attack-<category>',\
     severity:'CRITICAL',\
     setvar:'tx.anomaly_score=+5'"
```

### Prometheus / Loki (log-based alerts)
```yaml
groups:
- name: decepticon-defenses
  rules:
  - alert: DecepticonFINDNNN_Regression
    expr: |
      rate({app="target",level="error"}
        |~ "<bug-class>" [5m]) > 0.01
    for: 1m
    labels:
      severity: critical
      finding: FIND-NNN
    annotations:
      summary: "<bug class> regression detected"
      runbook: "https://decepticon.io/runbooks/FIND-NNN"
```

## Quality bar

A good rule:
1. Fires on the PoC (verify via `defense_verify`)
2. Doesn't fire on legitimate traffic captured by recon
3. Names the bug class + finding ID in `msg`/`description`
4. Has correct severity matching the underlying vuln
5. Includes context tags (user / host / source) for SOC triage

A bad rule:
1. Alerts on any 5xx (alert fatigue)
2. Pattern too broad — blocks legit users
3. Doesn't fire on the actual PoC (one job)
4. No finding-ID reference (SOC can't trace back)

## Workflow integration

The Defender follows the Patcher in the Vaccine pipeline:

```
Scanner → Detector → Verifier → Patcher → Defender → Final-Report
                                  ↓           ↓
                            patched=True  defended=True
```

Per finding the Vaccine emits TWO artifacts:
1. A code patch (from Patcher) — closes the immediate hole
2. A detection rule (from Defender) — fires on future regression OR sibling-pattern abuse

This is the "Offensive Vaccine" loop — see `docs/offensive-vaccine.md`.

## When to mark `defended=false`

Some attacks are genuinely undetectable with reasonable signal/noise.
Common cases:
- Timing-based blind oracles (only detectable as anomalous response-time
  distribution — high FP rate)
- Pure read-only IDOR (no error oracle, no anomalous traffic shape)
- Application-level logic abuse w/ valid auth + valid scope (no log
  distinguishes it from real usage)

Document the reason. Future detector improvements (ML-based behavioral
baselines, statistical anomaly engines) may close some of these.

## Cross-references
- Patcher (prior stage): `decepticon/agents/prompts/patcher.md`
- Offensive Vaccine spec: `docs/offensive-vaccine.md`
- MITRE D3FEND: https://d3fend.mitre.org
- Sigma HQ: https://github.com/SigmaHQ/sigma
- OWASP CRS: https://github.com/coreruleset/coreruleset
