# Adversary Archetypes

Pre-built threat profiles for common engagement scenarios. Copy the relevant archetype and customize for your specific engagement.

## Tier 1: Opportunistic Attacker

```json
{
  "name": "Opportunistic External Attacker",
  "sophistication": "low",
  "motivation": "financial",
  "initial_access": ["T1190", "T1110", "T1595.002"],
  "ttps": [
    "T1190",
    "T1110.001",
    "T1110.003",
    "T1595.002",
    "T1059.004",
    "T1486"
  ]
}
```

**Behavioral Profile:**
- Automated scanners, known CVEs, default credentials
- Dwell time: minutes to hours
- Tools: Shodan, masscan, metasploit (public modules), commodity ransomware
- Low persistence — smash-and-grab or deploy ransomware quickly
- No custom tooling — relies entirely on public exploits

## Tier 2: Targeted Cybercriminal (FIN-style)

```json
{
  "name": "Targeted Cybercriminal (FIN-style)",
  "sophistication": "medium",
  "motivation": "financial",
  "initial_access": ["T1566.001", "T1566.002", "T1078", "T1133"],
  "ttps": [
    "T1566.001",
    "T1078",
    "T1059.001",
    "T1053.005",
    "T1071.001",
    "T1486",
    "T1570",
    "T1021.001"
  ]
}
```

**Behavioral Profile:**
- Spearphishing, credential stuffing, access brokers
- Dwell time: days to weeks
- Tools: Cobalt Strike, custom phishing kits, commodity malware
- Moderate persistence — scheduled tasks, service creation
- Some custom tooling — modified public exploits, custom loaders

## Tier 3: APT / Nation-State

```json
{
  "name": "APT / Nation-State Actor",
  "sophistication": "nation-state",
  "motivation": "espionage",
  "initial_access": ["T1195.002", "T1566.001", "T1078", "T1190"],
  "ttps": [
    "T1195.002",
    "T1059.001",
    "T1053.005",
    "T1071.001",
    "T1048.003",
    "T1550.001",
    "T1098",
    "T1003.001",
    "T1087.002",
    "T1069.002"
  ]
}
```

**Behavioral Profile:**
- 0-day exploits, supply chain, long-term social engineering
- Dwell time: months to years
- Tools: Custom implants, living-off-the-land binaries (LOLBins), firmware-level persistence
- Heavy use of legitimate admin tools to blend in
- Multi-stage operations with careful OPSEC

## Tier 4: Insider Threat

```json
{
  "name": "Malicious Insider",
  "sophistication": "medium",
  "motivation": "financial",
  "initial_access": ["T1078"],
  "ttps": [
    "T1078",
    "T1530",
    "T1567.002",
    "T1048.002",
    "T1213",
    "T1083"
  ]
}
```

**Behavioral Profile:**
- Already has legitimate access — no need for initial compromise
- Dwell time: ongoing (uses normal access patterns)
- Tools: Standard corporate tools, USB drives, personal cloud storage
- Focuses on data access and exfiltration over persistence
- May escalate privileges if current access is insufficient
