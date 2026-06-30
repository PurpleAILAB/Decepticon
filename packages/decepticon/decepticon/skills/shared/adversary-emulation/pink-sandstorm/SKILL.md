---
name: pink-sandstorm-agrius
description: "Adversary-emulation profile for Pink Sandstorm (G1030 / Agrius / Agonizing Serpens / AMERICIUM / BlackShadow / DEV-0227), Iran's MOIS-linked destructive wiper and pseudo-ransomware operator."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Pink Sandstorm, Agrius, Agonizing Serpens, AMERICIUM, BlackShadow, DEV-0227, Marshtreader, G1030, Iranian MOIS destructive operations, Apostle wiper, Fantasy wiper, DEADWOOD wiper, MultiLayer wiper, BFG Agonizer, Moneybird ransomware, IPsec Helper backdoor, ASPXSpy web shell, Israel wiper operations, diamond industry targeting, destructive attacks masquerading as ransomware, hack-and-leak operations"
  tags: pink-sandstorm, agrius, agonizing-serpens, americium, blackshadow, dev-0227, iran, mois, destructive, wiper, ransomware, nation-state, g1030, adversary-emulation, mitre-attack
  mitre_attack: T1583, T1560.001, T1119, T1110, T1110.003, T1059.001, T1059.003, T1059.005, T1543.003, T1005, T1074.001, T1140, T1685, T1685.005, T1041, T1190, T1570, T1036, T1036.004, T1046, T1003.001, T1003.002, T1021.001, T1018, T1505.003, T1078.002, T1027, T1027.009, T1027.013, T1569.002, T1112, T1497.003, T1070, T1070.004, T1070.006, T1070.009, T1071.001, T1057, T1053.005, T1529, T1485, T1486, T1561.001, T1561.002, T1480, T1490, T1531, T1554, T1565.001, T1083, T1124
---

# Pink Sandstorm (Agrius, Agonizing Serpens, BlackShadow) — Adversary Emulation Profile

Pink Sandstorm (MITRE ATT&CK **G1030**) is an Iranian threat actor active since at least 2020, linked to Iran's Ministry of Intelligence and Security (MOIS). The group is notable for a series of **destructive wiper and pseudo-ransomware operations** primarily targeting Israeli organizations, with secondary operations against targets in the UAE, South Africa, and Hong Kong. Agrius deliberately **disguises destructive wiper attacks as ransomware**, using extortion personas (BlackShadow, Moneybird, n3tw0rm) to mask its true intent — strategic disruption and data destruction aligned with Iranian state interests. The group operates a lineage of custom .NET and C++ wipers (Apostle → Fantasy → MultiLayer → BFG Agonizer) alongside the IPsec Helper backdoor, ASPXSpy web shells, and public offensive tools (Mimikatz, Plink, NBTscan). Since the October 2023 Israel-Hamas war, Microsoft has observed Pink Sandstorm collaborating with Hezbollah cyber units and escalating hack-and-leak operations against Israeli targets.

## Attribution & motivation

- **Sponsor / nation:** Islamic Republic of Iran — Ministry of Intelligence and Security (MOIS). Microsoft's 2023 Iran threat report formally linked Pink Sandstorm / AMERICIUM to MOIS operations. The group operates under multiple extortion personas: BlackShadow (Shirbit, 2020), Justice Blade, Malek Team, and Moneybird.
- **Motivation:** Primarily **destructive / disruptive operations** — wiping data and rendering systems inoperable while masquerading as financially motivated ransomware. Secondary motivations include **espionage and data theft** (PII, intellectual property, database exfiltration) and **hack-and-leak influence operations** designed to cause political embarrassment and societal disruption in Israel.
- **Attribution confidence:** **High.** Backed by Microsoft threat intelligence formal attribution (AMERICIUM / Pink Sandstorm → MOIS), SentinelOne (Agrius lineage), Check Point (Moneybird), ESET (Fantasy supply-chain), and Palo Alto Unit 42 (Agonizing Serpens) consistent reporting. Code-level overlaps across Apostle, Fantasy, IPsec Helper, MultiLayer, and DEADWOOD confirm a single actor operating under rotating aliases.

## Targeting

- **Sectors:** Insurance and financial services; diamond industry (mining, wholesale, retail); IT and technology services; higher education and academic institutions; government and public services; healthcare (hospital hack-and-leak post-Oct 2023); HR consulting firms.
- **Regions:** Primary focus on **Israel** (near-exclusive targeting in most campaigns). Secondary targets in **UAE**, **South Africa**, and **Hong Kong** (diamond industry supply chain). Post-2023 expansion to broader Middle Eastern targets.
- **Victim profile:** Organizations whose disruption causes maximum societal, economic, or political impact in Israel — insurance companies holding citizen PII (Shirbit), universities, tech firms, diamond-industry supply chains. The group selects targets where data leaks amplify psychological and political effects beyond the technical compromise.

## Notable campaigns

- **2020-11 — Shirbit insurance hack-and-leak (BlackShadow persona).** Agrius, operating as "BlackShadow," breached Israeli insurance company Shirbit on November 30, 2020, stealing customer PII including identity documents, medical records, and government employee data. Demanded 50 BTC (~$1M); Shirbit refused, calling it "cyberterrorism." Attackers leaked sensitive data publicly. DEADWOOD wiper and IPsec Helper backdoor found on Shirbit infrastructure. (SentinelOne / BleepingComputer / Times of Israel)
- **2020-2021 — Israel/UAE destructive wiper operations (Apostle evolution).** SentinelOne documented Agrius deploying the Apostle malware — initially a .NET wiper that evolved into ransomware-capable malware — against Israeli and UAE targets. Apostle's early deployment (November 2020) contained a bug preventing ransom note delivery, confirming the wiper intent was primary. Used web shell access via CVE-2018-13379 (FortiOS) exploitation. (SentinelOne "From Wiper to Ransomware," May 2021)
- **2021 — Bar-Ilan University attack.** Agrius targeted Bar-Ilan University with destructive ransomware operations. Close temporal proximity to n3tw0rm ransomware attacks against Israeli targets suggests coordination as part of a broader Iranian disruptive campaign. (The Record / Check Point)
- **2022-02 — Fantasy wiper via diamond industry supply chain (ESET).** Starting February 2022, Agrius compromised an Israeli software developer serving the diamond industry to deploy the Fantasy wiper — built on Apostle's codebase but without ransomware pretense — via a supply-chain attack. Fantasy overwrote target files, cleared Windows event logs, wiped MBR, and self-deleted. Victims included a diamond wholesaler, HR firm, and IT provider in Israel, a South African diamond-industry organization, and a Hong Kong jeweler. (ESET / SecurityWeek / BleepingComputer, December 2022)
- **2023-01 to 2023-10 — Agonizing Serpens education/tech campaign (Unit 42).** Palo Alto Unit 42 documented destructive attacks from January to October 2023 targeting Israeli higher education and technology sectors. Deployed novel wipers: MultiLayer, PartialWasher, and BFG Agonizer. Used custom Sqlextractor for PII/IP theft from databases, then wiped systems to destroy forensic evidence. Upgraded EDR evasion using GMER64.sys driver to kill security processes. (Unit 42, November 2023)
- **2023-05 — Moneybird ransomware deployment (Check Point).** Check Point CPIRT identified Moneybird, a previously unseen C++ ransomware, deployed by Agrius against Israeli organizations. Exploited public-facing web servers, deployed ASPXSpy variants hidden in Certificate text files, used ProtonVPN nodes for anonymization, and downloaded payloads from legitimate file-hosting services (ufile.io, easyupload.io). Moneybird used AES-256-GCM encryption with per-file keys. Data later leaked through a prior Agrius alias. (Check Point Research, May 2023)
- **2023-11 onwards — Israel-Hamas war escalation (Microsoft).** Microsoft observed Pink Sandstorm collaborating with Hezbollah cyber units post-October 2023. Conducted hack-and-leak against an Israeli hospital as apparent retaliation. Iran's offensive cyber operations targeting Israel increased 43% during this period. (Microsoft Threat Intelligence, February 2024)

## TTPs by ATT&CK tactic

### Initial Access
- **T1190** — Exploit public-facing application: widespread exploitation of CVE-2018-13379 (FortiOS VPN) and SQL injection against web servers to establish initial footholds.
- **T1078.002** — Valid accounts (domain accounts): acquired via brute force, password spraying, and credential dumping for lateral movement and persistent access.

### Execution
- **T1059.003** — Windows Command Shell: ASPXSpy web shells enable follow-on command execution via `cmd.exe`.
- **T1059.001** — PowerShell: IPsec Helper backdoor executes PowerShell commands for post-exploitation activity.
- **T1059.005** — Visual Basic: IPsec Helper supports VBS-based command execution.
- **T1569.002** — Service execution: DEADWOOD and IPsec Helper registered and executed as Windows services.

### Persistence
- **T1505.003** — Web shell: primary persistence mechanism; deploys variants of ASPXSpy (base64-encoded, hidden in "Certificate" text files) on exploited web servers.
- **T1543.003** — Windows service: IPsec Helper registered as a Windows service for persistent backdoor access. DEADWOOD masquerades as a legitimate service (T1036.004).

### Privilege Escalation
- **T1078.002** — Valid accounts: obtained via credential dumping and brute force to escalate domain privileges.

### Defense Evasion
- **T1140** — Deobfuscate/decode files: base64-encoded ASPXSpy variants decoded at runtime.
- **T1036** — Masquerading: Plink renamed to `systems.exe`; DEADWOOD masquerades as a legitimate service (T1036.004).
- **T1685** — Disable or modify tools: modified EDR service auto-start settings; used GMER64.sys anti-rootkit driver to terminate security software processes.
- **T1685.005** — Clear Windows event logs: Apostle, MultiLayer, and Fantasy wipers clear all Windows event logs to destroy forensic evidence.
- **T1027.009** — Embedded payloads: DEADWOOD, Moneybird, and MultiLayer embed payloads within the binary.
- **T1027.013** — Encrypted/encoded file: DEADWOOD and IPsec Helper use encrypted configuration and payload data.
- **T1070.004** — File deletion: wipers self-delete after execution; Apostle and Fantasy remove traces.
- **T1070.006** — Timestomp: MultiLayer wiper modifies file timestamps as anti-forensics.
- **T1070.009** — Clear persistence: IPsec Helper clears its own persistence artifacts.
- **T1497.003** — Time-based evasion checks: IPsec Helper performs time-based sandbox/VM evasion.
- **T1112** — Modify registry: IPsec Helper modifies registry entries for configuration and persistence.

### Credential Access
- **T1003.001** — LSASS memory: Mimikatz used to dump LSASS process memory for credential extraction.
- **T1003.002** — Security Account Manager: SAM file dumped on victim machines.
- **T1110** — Brute force: SMB-based brute forcing in victim environments.
- **T1110.003** — Password spraying: SMB-based password spraying for credential acquisition.

### Discovery
- **T1046** — Network service discovery: WinEggDrop port scanner used for detailed host/service enumeration.
- **T1018** — Remote system discovery: NBTscan used to identify accessible hosts.
- **T1083** — File and directory discovery: MultiLayer wiper enumerates files for targeted destruction.
- **T1057** — Process discovery: Apostle and IPsec Helper enumerate running processes.
- **T1124** — System time discovery: DEADWOOD queries system time for execution logic.

### Lateral Movement
- **T1021.001** — Remote Desktop Protocol: RDP tunneled through web shells and Plink for lateral movement.
- **T1570** — Lateral tool transfer: payloads downloaded from legitimate file-hosting services (ufile.io, easyupload.io) during lateral operations.

### Collection
- **T1005** — Data from local system: gathered data from database servers and critical systems; Sqlextractor tool queries SQL databases to extract PII and intellectual property.
- **T1074.001** — Local data staging: data staged in `C:\windows\temp\s\` for exfiltration.
- **T1560.001** — Archive via utility: 7zip used to archive extracted data before exfiltration.
- **T1119** — Automated collection: custom `sql.net4.exe` tool automates SQL database PII extraction.

### Command & Control
- **T1583** — Acquire infrastructure: uses commercial VPN services (ProtonVPN) for last-hop anonymization.
- **T1071.001** — Web protocols: IPsec Helper communicates over HTTP/S for C2.
- **T1570** — Lateral tool transfer (dual-use): payloads fetched from legitimate hosting platforms.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: staged data exfiltrated using Putty and WinSCP communicating with C2 servers.

### Impact
- **T1485** — Data destruction: Apostle, DEADWOOD, and MultiLayer destroy file contents and delete data.
- **T1486** — Data encrypted for impact: Apostle (ransomware mode) and Moneybird encrypt files with AES-256, demanding ransom while actual intent is destruction.
- **T1561.001** — Disk content wipe: Apostle, DEADWOOD, and Fantasy overwrite disk content including file data and MBR.
- **T1561.002** — Disk structure wipe: BFG Agonizer and DEADWOOD wipe disk structures (partition tables, MBR).
- **T1529** — System shutdown/reboot: Apostle, BFG Agonizer, and MultiLayer force system reboot after wipe completion.
- **T1490** — Inhibit system recovery: BFG Agonizer and MultiLayer delete shadow copies and disable recovery mechanisms.
- **T1531** — Account access removal: DEADWOOD removes account access as part of destructive operations.
- **T1554** — Compromise host software binary: BFG Agonizer corrupts host software binaries.
- **T1565.001** — Stored data manipulation: MultiLayer manipulates stored data before wiping.
- **T1480** — Execution guardrails: Apostle uses guardrails to ensure execution only on intended targets.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| Apostle | S1133 | .NET wiper / ransomware (evolved from wiper to dual-capability) | Custom |
| Fantasy | (no ATT&CK software ID) | Wiper built on Apostle codebase (supply-chain deployed) | Custom |
| DEADWOOD (Detbosit) | S1134 | Wiper with MBR overwrite and service masquerading | Custom |
| IPsec Helper | S1132 | Post-exploitation backdoor / RAT (HTTP C2, PowerShell, VBS) | Custom |
| MultiLayer Wiper | S1135 | Wiper with timestomping and event-log clearing | Custom |
| BFG Agonizer | S1136 | Wiper with disk-structure wipe and recovery inhibition | Custom |
| Moneybird | S1137 | C++ ransomware (AES-256-GCM, per-file keys) | Custom |
| PartialWasher | (no ATT&CK software ID) | Selective file wiper | Custom |
| Sqlextractor (sql.net4.exe) | (no ATT&CK software ID) | Custom SQL database PII extraction tool | Custom |
| ASPXSpy | S0073 | ASPX web shell (base64-encoded variants) | Public |
| Mimikatz | S0002 | Credential dumping (LSASS, SAM) | Public |
| NBTscan | S0590 | NetBIOS/SMB network scanner | Public |
| Plink | (SSH tunnel utility) | SSH tunneling for RDP (renamed `systems.exe`) | Public |
| WinEggDrop | (no ATT&CK software ID) | Port scanner for host enumeration | Public |
| 7zip | (archiver) | Data archiving for exfiltration staging | Public |
| WinSCP / Putty | (file transfer / SSH) | Exfiltration via SCP/SFTP to C2 | Public |
| ProtonVPN | (VPN service) | Last-hop anonymization | Public (infrastructure) |
| GMER64.sys | (anti-rootkit driver) | Abused to kill EDR/security processes | Public (LOLDriver) |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never run destructive (T1485/T1561) or wiper actions outside an explicitly sanctioned, isolated lab.

Map Pink Sandstorm's signature plays to Decepticon's own capabilities:

- **Initial access — VPN exploitation + web shell (T1190, T1505.003).** Use the exploitation skill to target in-scope FortiOS/Pulse Secure VPN appliances (emulate CVE-2018-13379 or equivalent); upon access, deploy an **ASPXSpy variant** (base64-encoded, hidden inside a "Certificate" text file) on the web server. Use ProtonVPN or equivalent for last-hop anonymization — Agrius consistently uses Israeli ProtonVPN exit nodes to blend with legitimate traffic.
- **Credential access — brute force + dumping (T1110.003, T1003.001, T1003.002).** Drive SMB-based **password spraying** against in-scope domain controllers. Post-access, use Mimikatz for **LSASS dump and SAM extraction** — this is Agrius's standard credential-harvesting sequence.
- **Lateral movement — RDP via tunnel (T1021.001, T1036).** Deploy **Plink** (renamed `systems.exe` to emulate the masquerading TTP) to tunnel RDP connections through the web shell. Use harvested domain credentials to move laterally to database and file servers.
- **Post-exploitation — IPsec Helper emulation (T1543.003, T1071.001).** Install a custom backdoor registered as a **Windows service** with HTTP/S C2, PowerShell/cmd execution, and self-cleanup capability — mirroring IPsec Helper's operational profile. Include time-based sandbox evasion checks.
- **Collection — database extraction (T1119, T1005, T1560.001).** Use a custom SQL query tool (emulating Sqlextractor / `sql.net4.exe`) to **automate PII and IP extraction** from in-scope databases. Stage data in `C:\windows\temp\s\`, archive with **7zip**, and exfiltrate via WinSCP/Putty to C2 infrastructure.
- **Discovery — network mapping (T1046, T1018).** Use **WinEggDrop** (or equivalent port scanner) and **NBTscan** for host/service enumeration — Agrius maps the target environment before deploying wipers to maximize impact.
- **EDR evasion (T1685).** In a lab setting, emulate Agrius's EDR bypass: modify security service auto-start registry entries, then use **GMER64.sys** (or equivalent signed driver) to **terminate EDR processes** before wiper deployment.
- **Impact — wiper deployment (T1485, T1561.001, T1561.002, T1529, T1490).** In an **isolated lab only**, deploy a wiper chain emulating the Apostle→Fantasy→MultiLayer lineage: (1) overwrite target files with random data, (2) clear all Windows event logs, (3) delete shadow copies and inhibit recovery, (4) overwrite MBR, (5) force reboot. The defining Agrius TTP is **disguising the wiper as ransomware** — include a fake ransom note and file-extension renaming to reproduce the deception.
- **Hack-and-leak emulation (T1486, influence).** For authorized influence-operation testing, emulate the BlackShadow/Moneybird pattern: encrypt files with AES-256, issue a ransom demand, then (in a controlled setting) simulate public data leakage through a hacktivist persona — testing the organization's incident-response and PR capabilities.

## Detection & defense

- **VPN exploitation (T1190, CVE-2018-13379):** Patch FortiOS, Pulse Secure, and other edge VPN appliances immediately upon CVE disclosure; monitor VPN authentication logs for anomalous sign-ins from commercial VPN exit nodes (ProtonVPN, NordVPN); enforce MFA on VPN access.
- **Web shells (T1505.003):** Monitor IIS/web server directories for new `.aspx` files or suspicious text files in Certificate stores; baseline web-server child processes (`w3wp.exe` → `cmd.exe` is anomalous); deploy file-integrity monitoring on web roots; hunt for base64-encoded ASPXSpy indicators.
- **Credential attacks (T1110.003, T1003.001/.002):** Enforce account lockout policies; alert on distributed SMB authentication failures; enable LSA protection (RunAsPPL) and Credential Guard; monitor for LSASS handle access and SAM registry exports (`reg save`).
- **Lateral movement (T1021.001):** Monitor for Plink/SSH tunnel processes, especially renamed binaries (`systems.exe`); restrict RDP to jump servers; alert on RDP connections originating from web server processes.
- **EDR tampering (T1685):** Monitor for GMER64.sys driver loading and service modification events; implement driver allowlisting; alert on security service stop/disable events; use tamper-protection features.
- **Wiper indicators (T1485, T1561, T1529, T1490):** Alert on mass file-overwrite patterns; monitor for MBR/VBR write attempts; detect `vssadmin delete shadows` and `bcdedit /set {default} recoveryenabled No`; trigger on Windows event log clearing (Event ID 1102); alert on unexpected system shutdown/reboot commands.
- **Data staging & exfiltration (T1074.001, T1041):** Monitor `C:\windows\temp\` for unusual archive files; alert on WinSCP/Putty/SCP outbound connections to unknown hosts; DLP monitoring for 7zip archive creation containing database dumps.
- **Supply chain (Fantasy pattern):** Vet third-party software update mechanisms; monitor for unexpected software-update behavior from diamond-industry or niche vertical applications; implement application allowlisting.

## Sources

- https://attack.mitre.org/groups/G1030/
- https://assets.sentinelone.com/sentinellabs/evol-agrius
- https://research.checkpoint.com/2023/agrius-deploys-moneybird-in-targeted-attacks-against-israeli-organizations/
- https://unit42.paloaltonetworks.com/agonizing-serpens-targets-israeli-tech-higher-ed-sectors/
- https://www.welivesecurity.com/2022/12/07/fantasy-new-agrius-wiper-supply-chain-attack/
- https://www.microsoft.com/en-us/security/business/security-insider/wp-content/uploads/2023/05/Iran-turning-to-cyber-enabled-influence-operations-for-greater-effect-05022023.pdf
- https://www.microsoft.com/en-us/security/security-insider/threat-landscape/iran-surges-cyber-enabled-influence-operations-in-support-of-hamas/
- https://www.bleepingcomputer.com/news/security/blackshadow-hackers-extort-israeli-insurance-company-for-1-million/
- https://www.securityweek.com/iranian-hackers-deliver-new-fantasy-wiper-diamond-industry-supply-chain-attack/
- https://learn.microsoft.com/en-us/microsoft-365/security/intelligence/microsoft-threat-actor-naming?view=o365-worldwide
- https://attack.mitre.org/software/S1133/
- https://attack.mitre.org/software/S1132/
- https://attack.mitre.org/software/S1134/
- https://attack.mitre.org/software/S1135/
- https://attack.mitre.org/software/S1136/
- https://attack.mitre.org/software/S1137/
