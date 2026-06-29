---
name: siem-query-templates
description: "Pre-built SIEM query templates for threat hunting — Splunk SPL, Elastic KQL/EQL, and Microsoft Sentinel KQL queries mapped to MITRE ATT&CK techniques. Covers initial access, execution, persistence, lateral movement, exfiltration, and C2 detection patterns."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "siem query, splunk query, spl, elastic query, kql, eql, sentinel query, threat hunting query, detection query, hunt for, search logs, log analysis, splunk search, elastic search query"
  tags: "siem, splunk, elastic, sentinel, kql, spl, eql, threat-hunting, detection, log-analysis"
  mitre_attack: "TA0001, TA0002, TA0003, TA0008, TA0010, TA0011"
---

# SIEM Query Templates

Pre-built detection and threat-hunting queries for Splunk (SPL), Elastic (KQL/EQL), and Microsoft Sentinel (KQL). Organized by MITRE ATT&CK tactic, each template includes the query, required log sources, tuning guidance, and expected output.

## Quick Reference

```bash
# Save a query template to workspace
cat > /workspace/queries/hunt-encoded-powershell.spl << 'SPL'
index=windows sourcetype="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational" EventCode=1
  Image="*\\powershell.exe"
  CommandLine="*-enc*" OR CommandLine="*-EncodedCommand*"
| stats count by Computer, User, CommandLine
| sort -count
SPL

# Batch-generate templates for all tactics
python3 << 'PYEOF'
import os, json

templates_dir = "/workspace/queries"
os.makedirs(templates_dir, exist_ok=True)

# Generate index of available templates
templates = [f for f in os.listdir(templates_dir) if f.endswith(('.spl','.kql','.eql'))]
print(f"[+] {len(templates)} query templates in {templates_dir}")
for t in sorted(templates):
    print(f"    {t}")
PYEOF
```

## 1. Initial Access (TA0001)

### Exploit Public-Facing Application (T1190)

**Splunk SPL**
```spl
index=web sourcetype=access_combined
  (status=200 OR status=500)
  (uri_path="*../*" OR uri_path="*;*" OR uri_path="*%00*"
   OR uri_path="*union+select*" OR uri_path="*<script*")
| stats count dc(src_ip) AS unique_sources values(uri_path) AS paths by dest, status
| where count > 20
| sort -count
```

**Elastic KQL**
```kql
http.response.status_code:(200 OR 500)
  AND url.path:(*..* OR *;* OR *%00* OR *union*select* OR *<script*)
```

**Sentinel KQL**
```kql
CommonSecurityLog
| where DeviceAction == "allowed"
| where RequestURL has_any ("../", ";", "%00", "union select", "<script")
| summarize Count=count(), UniqueIPs=dcount(SourceIP) by DestinationHostName, RequestURL
| where Count > 20
| order by Count desc
```

### Phishing — Malicious Attachment Execution (T1566.001)

**Splunk SPL**
```spl
index=windows sourcetype="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational" EventCode=1
  (ParentImage="*\\WINWORD.EXE" OR ParentImage="*\\EXCEL.EXE" OR ParentImage="*\\OUTLOOK.EXE")
  (Image="*\\cmd.exe" OR Image="*\\powershell.exe" OR Image="*\\wscript.exe"
   OR Image="*\\cscript.exe" OR Image="*\\mshta.exe" OR Image="*\\certutil.exe")
| table _time, Computer, User, ParentImage, Image, CommandLine
```

**Elastic EQL**
```eql
process where event.type == "start" and
  process.parent.name : ("WINWORD.EXE", "EXCEL.EXE", "OUTLOOK.EXE") and
  process.name : ("cmd.exe", "powershell.exe", "wscript.exe", "cscript.exe", "mshta.exe")
```

## 2. Execution (TA0002)

### Encoded PowerShell (T1059.001)

**Splunk SPL**
```spl
index=windows sourcetype="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational" EventCode=1
  Image="*\\powershell.exe"
  (CommandLine="*-enc *" OR CommandLine="*-EncodedCommand *"
   OR CommandLine="*-e *" OR CommandLine="*-ec *")
| eval decoded=base64decode(mvindex(split(CommandLine," "),-1))
| table _time, Computer, User, CommandLine, decoded
```

**Elastic KQL**
```kql
process.name:"powershell.exe" AND process.command_line:(*-enc* OR *-EncodedCommand* OR *-e * OR *-ec *)
```

**Sentinel KQL**
```kql
DeviceProcessEvents
| where FileName =~ "powershell.exe"
| where ProcessCommandLine matches regex @"-[eE]([nN][cC]|[nN][cC][oO][dD][eE][dD][cC][oO][mM][mM][aA][nN][dD])?\s"
| project Timestamp, DeviceName, AccountName, ProcessCommandLine
```

### WMIC Execution (T1047)

**Splunk SPL**
```spl
index=windows EventCode=1
  Image="*\\WMIC.exe"
  (CommandLine="*process call create*" OR CommandLine="*/node:*")
| table _time, Computer, User, CommandLine, ParentImage
```

## 3. Persistence (TA0003)

### Scheduled Task Creation (T1053.005)

**Splunk SPL**
```spl
index=windows (EventCode=4698 OR (EventCode=1 Image="*\\schtasks.exe" CommandLine="*/create*"))
| table _time, Computer, User, TaskName, CommandLine
| sort -_time
```

**Elastic EQL**
```eql
sequence by host.name with maxspan=1m
  [process where event.type == "start" and process.name : "schtasks.exe" and process.args : "/create"]
  [any where event.category : "registry" and registry.path : "*\\Schedule\\TaskCache*"]
```

### Registry Run Key (T1547.001)

**Splunk SPL**
```spl
index=windows sourcetype="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational" EventCode=13
  TargetObject="*\\CurrentVersion\\Run*"
  NOT (Details="*Microsoft*" OR Details="*\\Windows\\*")
| table _time, Computer, User, TargetObject, Details
```

### WMI Event Subscription (T1546.003)

**Splunk SPL**
```spl
index=windows EventCode=1
  (Image="*\\scrcons.exe" OR Image="*\\mofcomp.exe"
   OR (Image="*\\powershell.exe" CommandLine="*EventSubscription*"))
| table _time, Computer, User, Image, CommandLine
```

## 4. Lateral Movement (TA0008)

### PsExec / Remote Service Creation (T1021.002)

**Splunk SPL**
```spl
index=windows EventCode=7045
  (ServiceFileName="*\\PSEXESVC*" OR ServiceFileName="*cmd*" OR ServiceFileName="*powershell*")
| table _time, Computer, ServiceName, ServiceFileName, ServiceType
```

**Elastic EQL**
```eql
any where event.code == "7045" and
  winlog.event_data.ServiceFileName : ("*PSEXESVC*", "*cmd*", "*powershell*")
```

### Remote Desktop (T1021.001)

**Splunk SPL**
```spl
index=windows EventCode=4624 LogonType=10
| stats count dc(TargetUserName) AS unique_users values(TargetUserName) AS users
    by IpAddress, Computer
| where count > 5
| sort -count
```

### WinRM / PowerShell Remoting (T1021.006)

**Splunk SPL**
```spl
index=windows EventCode=1
  (Image="*\\wsmprovhost.exe" OR
   (Image="*\\powershell.exe" CommandLine="*Invoke-Command*" CommandLine="*-ComputerName*"))
| table _time, Computer, User, Image, CommandLine
```

## 5. Command & Control (TA0011)

### DNS Tunneling (T1071.004)

**Splunk SPL**
```spl
index=dns
| eval query_len=len(query)
| where query_len > 50
| stats count avg(query_len) AS avg_len dc(query) AS unique_queries by src_ip, query_type
| where avg_len > 40 AND count > 100
| sort -count
```

**Sentinel KQL**
```kql
DnsEvents
| extend QueryLength = strlen(Name)
| where QueryLength > 50
| summarize Count=count(), AvgLen=avg(QueryLength), UniqueQueries=dcount(Name) by ClientIP
| where AvgLen > 40 and Count > 100
| order by Count desc
```

### Beaconing Detection (T1071.001)

**Splunk SPL**
```spl
index=proxy OR index=firewall
| bin _time span=60s
| stats count by src_ip, dest_ip, dest_port, _time
| streamstats current=f window=10 avg(count) AS avg_count stdev(count) AS stdev_count by src_ip, dest_ip
| where stdev_count < 1 AND avg_count > 0
| stats count avg(avg_count) AS beacon_rate values(dest_port) AS ports by src_ip, dest_ip
| where count > 100
| sort -count
```

## 6. Exfiltration (TA0010)

### Large Data Transfer (T1048)

**Splunk SPL**
```spl
index=firewall OR index=proxy
| stats sum(bytes_out) AS total_bytes_out by src_ip, dest_ip, dest_port
| eval MB=round(total_bytes_out/1024/1024, 2)
| where MB > 100
| sort -MB
```

**Sentinel KQL**
```kql
CommonSecurityLog
| where TimeGenerated > ago(24h)
| summarize TotalBytes=sum(SentBytes) by SourceIP, DestinationIP, DestinationPort
| extend MB = TotalBytes / 1048576
| where MB > 100
| order by MB desc
```

### DNS Exfiltration (T1048.003)

**Splunk SPL**
```spl
index=dns
| rex field=query "^(?<subdomain>[^\.]+)\."
| eval sub_len=len(subdomain)
| where sub_len > 30
| stats count sum(sub_len) AS total_data_bytes dc(query) AS unique_queries by src_ip
| eval estimated_exfil_KB=round(total_data_bytes/1024, 2)
| where estimated_exfil_KB > 10
| sort -estimated_exfil_KB
```

## 7. Query Tuning Guidance

### Reducing False Positives

```spl
# Baseline: establish normal behavior first
index=windows EventCode=1 Image="*\\powershell.exe"
| stats count by User, Computer
| sort -count
# → Users/hosts with consistently high counts are likely administrative

# Exclude known-good with lookup
| lookup admin_hosts Computer AS Computer OUTPUT is_admin
| where NOT is_admin="true"
```

### Performance Optimization

```spl
# BAD — unbounded wildcard at start
index=* CommandLine="*mimikatz*"

# GOOD — scoped index, specific sourcetype, time-bounded
index=windows sourcetype="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational"
  EventCode=1 earliest=-24h latest=now
  CommandLine="*mimikatz*"
```

## References

- Splunk Security Essentials — https://splunkbase.splunk.com/app/3435/
- Elastic Detection Rules — https://github.com/elastic/detection-rules
- Microsoft Sentinel Hunting Queries — https://github.com/Azure/Azure-Sentinel
- MITRE ATT&CK — https://attack.mitre.org/
- Sigma to SIEM conversion — https://github.com/SigmaHQ/sigma
