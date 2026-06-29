---
name: sigma-rule-generation
description: "Sigma rule authoring from engagement findings — convert observed attacker behaviors into platform-agnostic detection rules, compile to SIEM-specific queries (Splunk, Elastic, Sentinel), validate against log samples, and tune for false positive reduction."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "sigma rule, sigma, detection rule, write detection, siem detection, splunk detection, elastic detection, sentinel detection, sigma cli, sigmac, pySigma, convert sigma, sigma to splunk, sigma to kql, blue team detection"
  tags: "sigma, detection, siem, splunk, elastic, sentinel, blue-team, detection-engineering"
  mitre_attack: "DS0009, DS0015, DS0017, DS0029"
---

# Sigma Rule Generation

Author Sigma detection rules from engagement findings, threat intelligence, and observed attacker behaviors. Sigma is a generic, platform-agnostic signature format for log events that compiles to SIEM-specific queries (Splunk SPL, Elastic EQL/KQL, Microsoft Sentinel KQL, QRadar AQL).

## Quick Reference

```bash
# Install pySigma (modern toolchain, replaces legacy sigmac)
pip install pySigma pySigma-backend-splunk pySigma-backend-elasticsearch \
    pySigma-backend-microsoft365defender pySigma-pipeline-sysmon \
    pySigma-pipeline-windows

# Convert a Sigma rule to Splunk SPL
sigma convert -t splunk -p sysmon /workspace/detections/rule.yml

# Convert to Elastic EQL
sigma convert -t elasticsearch -p ecs_windows /workspace/detections/rule.yml

# Convert to Microsoft Sentinel KQL
sigma convert -t microsoft365defender /workspace/detections/rule.yml

# Validate rule syntax
sigma check /workspace/detections/rule.yml
```

## MITRE ATT&CK Data Sources

| Data Source | ID | Sigma Log Category |
|---|---|---|
| Process: Process Creation | DS0009 | process_creation |
| Application Log | DS0015 | application |
| Command: Command Execution | DS0017 | process_creation, powershell |
| Network Traffic: Network Connection | DS0029 | network_connection |

## 1. Sigma Rule Structure

### Minimal Rule Template

```yaml
title: Descriptive Title of Detection
id: <uuid>                    # Generate: python3 -c "import uuid; print(uuid.uuid4())"
status: experimental          # experimental | test | stable
description: >
  Detects <behavior> observed during <engagement/campaign>.
  <One-line context on why this is suspicious.>
references:
  - https://attack.mitre.org/techniques/TXXXX/
author: Decepticon Detection Team
date: 2025/01/01
modified: 2025/01/01
tags:
  - attack.execution          # MITRE tactic (lowercase)
  - attack.t1059.001          # MITRE technique (lowercase)
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith: '\powershell.exe'
    CommandLine|contains|all:
      - '-enc'
      - 'bypass'
  condition: selection
falsepositives:
  - Legitimate admin scripts using encoded PowerShell
level: high                   # informational | low | medium | high | critical
```

### Field Modifiers

```yaml
# String matching
FieldName: 'exact value'
FieldName|contains: 'substring'
FieldName|startswith: 'prefix'
FieldName|endswith: 'suffix'
FieldName|re: '.*regex.*'

# Logical combinations
FieldName|contains|all:       # AND — all must match
  - 'value1'
  - 'value2'
FieldName|contains:           # OR — any can match (list without |all)
  - 'value1'
  - 'value2'

# Encoding-aware
FieldName|base64offset|contains: 'decoded-string'  # Searches across base64 alignment offsets
FieldName|wide: 'unicode-string'                    # UTF-16LE encoding
FieldName|windash: '-flag'                          # Matches -flag, /flag, —flag

# Numeric and null
FieldName: null               # Field exists but is empty
FieldName|gte: 100            # Greater than or equal
```

## 2. Engagement Finding → Sigma Rule Workflow

### Step 1: Extract Observables from Finding

```bash
# Parse a finding YAML for detection-relevant fields
python3 << 'PYEOF'
import yaml, json

with open('/workspace/findings/<FINDING>.md') as f:
    # Skip markdown, parse YAML frontmatter
    content = f.read()
    if content.startswith('---'):
        fm = content.split('---', 2)[1]
        finding = yaml.safe_load(fm)
        print(json.dumps(finding, indent=2))
PYEOF
```

### Step 2: Map to Log Source

| Observed Behavior | Sigma Log Category | Typical Source |
|---|---|---|
| Process execution | `process_creation` | Sysmon EventID 1, Windows 4688 |
| Network connection | `network_connection` | Sysmon EventID 3, Firewall |
| File creation/modification | `file_event` | Sysmon EventID 11 |
| Registry modification | `registry_event` | Sysmon EventID 13 |
| DNS query | `dns_query` | Sysmon EventID 22, DNS server |
| PowerShell execution | `ps_script` / `ps_module` | PowerShell 4104, 4103 |
| Image load (DLL) | `image_load` | Sysmon EventID 7 |
| Pipe creation | `pipe_created` | Sysmon EventID 17/18 |

### Step 3: Write the Detection Logic

```yaml
# Example: Detecting Havoc Demon C2 callback pattern
title: Havoc Demon HTTP C2 Callback
id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
status: experimental
description: >
  Detects HTTP traffic patterns consistent with Havoc Demon C2
  callbacks — periodic requests to jQuery-mimicking URIs with
  specific user-agent strings.
references:
  - https://havocframework.com
  - https://attack.mitre.org/techniques/T1071/001/
author: Decepticon Detection Team
date: 2025/01/01
tags:
  - attack.command_and_control
  - attack.t1071.001
logsource:
  category: proxy
  product: windows
detection:
  selection_uri:
    cs-uri-stem|endswith:
      - '/jquery-3.3.1.min.js'
      - '/jquery-3.3.2.min.js'
      - '/jquery-3.6.0.min.js'
  selection_method:
    cs-method: 'POST'
  filter_legitimate:
    cs-host|endswith:
      - '.jquery.com'
      - '.googleapis.com'
      - '.cdnjs.cloudflare.com'
  condition: selection_uri and selection_method and not filter_legitimate
falsepositives:
  - Legitimate jQuery CDN POST requests (rare but possible)
level: high
```

## 3. SIEM-Specific Compilation

### Splunk SPL

```bash
# Convert with Sysmon pipeline (maps Sysmon fields to Splunk CIM)
sigma convert -t splunk -p sysmon /workspace/detections/rule.yml

# Output example:
# source="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational"
# EventCode=1 Image="*\\powershell.exe" CommandLine="*-enc*" CommandLine="*bypass*"
```

### Elastic (ECS)

```bash
# Convert with ECS Windows pipeline
sigma convert -t elasticsearch -p ecs_windows /workspace/detections/rule.yml

# For Lucene query format
sigma convert -t elasticsearch -p ecs_windows -f lucene /workspace/detections/rule.yml
```

### Microsoft Sentinel (KQL)

```bash
sigma convert -t microsoft365defender /workspace/detections/rule.yml

# Output example:
# DeviceProcessEvents
# | where FileName endswith "powershell.exe"
# | where ProcessCommandLine contains "-enc" and ProcessCommandLine contains "bypass"
```

### Batch Conversion

```bash
# Convert all rules in a directory to all backends
for backend in splunk elasticsearch microsoft365defender; do
  mkdir -p /workspace/detections/compiled/${backend}
  for rule in /workspace/detections/*.yml; do
    name=$(basename "$rule" .yml)
    sigma convert -t "$backend" -p sysmon "$rule" \
      > "/workspace/detections/compiled/${backend}/${name}.txt" 2>/dev/null
  done
done
```

## 4. Validation and Testing

```bash
# Syntax validation
sigma check /workspace/detections/*.yml

# Test against log samples (Splunk — assumes local instance)
# Export the SPL query and run against indexed data:
splunk search "$(sigma convert -t splunk -p sysmon /workspace/detections/rule.yml)" \
  -earliest_time=-7d -latest_time=now

# Validate with evtx_dump (offline Windows event logs)
pip install evtx
python3 << 'PYEOF'
import Evtx.Evtx as evtx
import re

# Load compiled regex from Sigma rule detection block
pattern = re.compile(r'powershell\.exe.*-enc.*bypass', re.IGNORECASE)

with evtx.Evtx('/workspace/logs/Security.evtx') as log:
    for record in log.records():
        xml = record.xml()
        if pattern.search(xml):
            print(f"[HIT] Record {record.record_num()}")
            print(xml[:500])
            print("---")
PYEOF
```

## 5. False Positive Tuning

```yaml
# Strategy 1: Exclude known-good processes
detection:
  selection:
    Image|endswith: '\cmd.exe'
    ParentImage|endswith: '\services.exe'
  filter_sccm:
    CommandLine|contains: 'ccmexec'
  filter_scom:
    CommandLine|contains: 'MonitoringHost'
  condition: selection and not 1 of filter_*

# Strategy 2: Threshold-based (needs aggregation support)
detection:
  selection:
    EventID: 4625              # Failed logon
    TargetUserName|endswith: '$'
  timeframe: 5m
  condition: selection | count(TargetUserName) > 10

# Strategy 3: Narrow with parent-child relationships
detection:
  selection:
    ParentImage|endswith: '\winword.exe'
    Image|endswith:
      - '\cmd.exe'
      - '\powershell.exe'
      - '\wscript.exe'
  condition: selection
```

## 6. Rule Quality Checklist

- [ ] Unique UUID in `id` field
- [ ] `status` set to `experimental` for new rules
- [ ] MITRE ATT&CK `tags` present and accurate
- [ ] `logsource` category and product specified
- [ ] At least one `falsepositives` entry (even if "Unknown")
- [ ] `level` reflects actual confidence and impact
- [ ] Rule tested against at least one true-positive log sample
- [ ] Rule compiled to target SIEM backend without errors
- [ ] No overly broad field matches (e.g., bare `CommandLine|contains: 'a'`)

## References

- Sigma specification — https://github.com/SigmaHQ/sigma-specification
- SigmaHQ rule repository — https://github.com/SigmaHQ/sigma
- pySigma documentation — https://sigmahq-pysigma.readthedocs.io/
- MITRE ATT&CK — https://attack.mitre.org/
