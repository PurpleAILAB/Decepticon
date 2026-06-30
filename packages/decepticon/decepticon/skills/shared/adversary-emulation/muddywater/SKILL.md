---
name: muddywater-mango-sandstorm
description: "Adversary-emulation profile for MuddyWater (G0069 / Mercury / Mango Sandstorm / Static Kitten / TEMP.Zagros / Seedworm), Iran's MOIS cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "MuddyWater, Mercury, Mango Sandstorm, Static Kitten, Seedworm, TEMP.Zagros, Earth Vetala, TA450, MuddyKrill, G0069, Iranian MOIS espionage emulation, POWERSTATS PowerShell RAT, MuddyC2Go, PhonyC2, PowGoop, Small Sieve, Mori DNS tunneling, RMM tool abuse Atera ScreenConnect SimpleHelp, spearphishing macro documents, DLL side-loading, Middle East government telecom energy targeting"
  tags: muddywater, mango-sandstorm, mercury, static-kitten, seedworm, temp-zagros, mois, iran, espionage, nation-state, g0069, adversary-emulation, mitre-attack
  mitre_attack: T1548.002, T1087.002, T1583.001, T1583.006, T1071.001, T1071.004, T1560.001, T1547.001, T1059.001, T1059.003, T1059.005, T1059.006, T1059.007, T1555, T1555.003, T1555.004, T1132.001, T1132.002, T1074.001, T1140, T1685, T1573.001, T1573.002, T1041, T1567.002, T1190, T1203, T1210, T1083, T1590.004, T1574.001, T1105, T1559.001, T1559.002, T1534, T1036.005, T1104, T1571, T1027, T1027.003, T1027.004, T1027.007, T1027.010, T1027.013, T1588.001, T1588.002, T1137.001, T1003.001, T1003.002, T1003.003, T1003.004, T1003.005, T1003.006, T1566, T1566.001, T1566.002, T1057, T1090, T1090.002, T1219.002, T1053.005, T1113, T1684.001, T1518, T1518.001, T1218.003, T1218.005, T1218.007, T1218.010, T1218.011, T1082, T1016, T1049, T1033, T1552.001, T1204.001, T1204.002, T1204.004, T1102.001, T1102.002, T1047, T1001.001, T1005, T1012, T1018, T1029, T1036.004, T1046, T1056.001, T1056.002, T1070.004, T1078, T1106, T1110.001, T1110.003, T1112, T1114.001, T1124, T1134.001, T1135, T1195.001, T1201, T1480, T1543.003, T1550.002, T1558.001, T1558.002, T1564.003, T1569.002, T1614, T1620, T1622, T1678
---

# MuddyWater (Mercury, Mango Sandstorm, Static Kitten, Seedworm, TEMP.Zagros) — Adversary Emulation Profile

MuddyWater (MITRE ATT&CK **G0069**) is a cyber-espionage group assessed to be a subordinate element within Iran's **Ministry of Intelligence and Security (MOIS)**, active since at least 2017. The group has targeted government, telecommunications, defense, oil & gas, and IT organizations across the Middle East, Central/South Asia, Africa, Europe, and North America. MuddyWater is characterized by heavy reliance on **PowerShell-based backdoors** (POWERSTATS and its successors), **evolving custom C2 frameworks** (PhonyC2 → MuddyC2Go), **abuse of legitimate Remote Monitoring and Management (RMM) tools** (Atera, ScreenConnect, SimpleHelp), **spearphishing with macro-laden documents**, and a pragmatic blend of custom and open-source post-exploitation tooling. A February 2022 joint U.S./UK advisory (CISA AA22-055A) formally attributed the group to MOIS.

## Attribution & motivation

- **Sponsor / nation:** Islamic Republic of Iran — Ministry of Intelligence and Security (MOIS). U.S. Cyber Command's Cyber National Mission Force (CNMF) publicly linked MuddyWater to MOIS in January 2022; the February 2022 joint FBI/CISA/CNMF/NCSC-UK advisory **AA22-055A** formalized the attribution.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** supporting Iranian state interests — political, military, and economic intelligence on regional rivals. Secondary motivations include **pre-positioning for disruptive operations** (the 2023 Technion "DarkBit" ransomware incident) and **access brokerage** (sharing/selling network access to other MOIS-aligned threat actors).
- **Attribution confidence:** **High.** Backed by U.S. government advisories (CISA AA22-055A), UK NCSC malware analysis reports, Israel National Cyber Directorate attributions, and consistent named vendor reporting (Microsoft, ESET, Deep Instinct, Cisco Talos, Symantec, ClearSky, Trend Micro, Proofpoint, Group-IB).

## Targeting

- **Sectors:** Government and public administration; telecommunications; defense and military; oil, gas, and energy; finance and insurance; IT and managed service providers; academia and research; airlines and logistics; healthcare and pharmaceuticals.
- **Regions:** Primary focus on the **Middle East** (Israel, Saudi Arabia, UAE, Kuwait, Oman, Egypt, Turkey, Iraq, Jordan, Lebanon); **Central and South Asia** (Pakistan, India, Malaysia); **Africa** (Algeria, North/East Africa); expanding into **Europe** and **North America** (since 2023–2025, targeting U.S. airports, banks, software companies).
- **Victim profile:** Government agencies and critical-infrastructure operators whose networks yield political, military, and economic intelligence; MSPs and IT providers as stepping stones for supply-chain access; defense-sector personnel and researchers.

## Notable campaigns

- **2017-11 — Initial discovery; Middle East government targeting.** Palo Alto Unit 42 publicly disclosed MuddyWater campaigns using macro-laden Word documents with region-specific decoy content to deliver the POWERSTATS PowerShell backdoor against Saudi Arabian, Iraqi, and other Middle East government targets. (Unit 42)
- **2018-03 — TEMP.Zagros spearphishing expansion.** FireEye/Mandiant tracked updated TTPs including CMSTP bypass, template injection, and expanded targeting of Turkey, Pakistan, and Tajikistan government entities. (FireEye)
- **2018-10 — Seedworm global compromise wave.** Symantec reported MuddyWater (as Seedworm) compromising over 130 victims across 30+ organizations in telecoms, IT, oil & gas, and government in the Middle East, Europe, and North America, deploying POWERSTATS, Mimikatz, LaZagne, and custom reverse shells. (Symantec)
- **2018-11 — Lebanon and Oman operations.** ClearSky documented campaigns leveraging compromised Israeli domains as C2 relays, delivering multi-stage payloads via JavaScript steganography and DDE against Lebanese and Omani targets. (ClearSky)
- **2021-02 — Static Kitten / Earth Vetala targeting UAE & Kuwait.** Anomali and Trend Micro reported campaigns using ScreenConnect, RemoteUtilities, and file-sharing services (OneHub, Sync) to target UAE and Kuwait government agencies, distributing tools via spearphishing links. (Anomali, Trend Micro)
- **2022-01 — Turkey targeting with malicious PDFs.** Cisco Talos documented MuddyWater targeting Turkish private organizations and government entities using malicious PDF and Office documents to deploy PowerShell-based backdoors. (Cisco Talos)
- **2022-02 — Joint advisory AA22-055A.** FBI, CISA, CNMF, and NCSC-UK published formal attribution of MuddyWater to MOIS with detailed IOCs covering POWERSTATS, PowGoop, Small Sieve, Canopy/Starwhale, and Mori malware. (CISA)
- **2022-11 — Israeli insurance sector campaign.** MuddyWater simultaneously targeted three Israeli insurance companies using Syncro RMM tool for initial access, following the October 2022 Egypt IT-sector targeting via spearphishing. (Deep Instinct, Genians)
- **2023-02 — Technion "DarkBit" ransomware.** Israel's National Cyber Directorate attributed the disruptive ransomware attack on the Technion – Israel Institute of Technology to MuddyWater, operating under the false persona "DarkBit"; PhonyC2 was used as the C2 framework. (Israeli NCDI, Deep Instinct)
- **2023-06 — PhonyC2 framework exposed.** Deep Instinct published analysis of PhonyC2, a custom Python-based C2 framework in use by MuddyWater since at least late 2021, used in the Technion attack and PaperCut exploitation campaigns. (Deep Instinct)
- **2023-10 — MuddyC2Go deployment; North/East Africa targeting.** Following the PhonyC2 source-code leak, MuddyWater pivoted to MuddyC2Go — a Go-based C2 framework — observed in campaigns against Israeli and North/East African organizations. (Deep Instinct)
- **2024-02 — RMM tool pivot.** MuddyWater shifted toolkits to Atera Agent, ScreenConnect, Advanced Monitoring Tool, and MeshCentral for initial access and persistence, with spearphishing lures containing PDF attachments with embedded links to file-sharing services. (Proofpoint, Israel NCDI)
- **2025-04 — ClickFix social engineering.** Proofpoint documented MuddyWater adopting "ClickFix"-style tactics, enticing victims to copy and paste malicious PowerShell code from phishing pages spoofing Microsoft security updates. (Proofpoint)
- **2025-12 — MuddyViper, Fooder, LP-Notes tooling.** ESET published analysis of MuddyWater's evolving toolchain including Fooder (reflective-loading backdoor), LP-Notes (credential harvester), MuddyViper (modular C2 implant), and go-socks5 proxy tools used across Middle Eastern targets. (ESET)
- **2026-01 — RustyWater Rust implant.** CloudSEK documented MuddyWater deploying RustyWater, a Rust-based implant delivered via macro-laden documents impersonating Turkmenistan telecom operator TMCell, signaling continued tooling modernization. (CloudSEK)
- **2026-03 — U.S. critical infrastructure targeting (Dindoor/Seedworm).** MuddyWater compromised networks of a U.S. airport, bank, and software company, deploying the Dindoor backdoor and exfiltrating data via Rclone to Wasabi cloud storage. (Symantec/Broadcom, SOCRadar, SecurityWeek)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.001** — Acquire Infrastructure: Domains: MuddyWater registers domains spoofing legitimate organizations (e.g., microsoftonlines[.]com) with preference for NameCheap and Hosterdaddy registrars.
- **T1583.006** — Acquire Infrastructure: Web Services: Uses file-sharing services (OneHub, Sync, TeraBox, Dropbox, OneDrive) to host and distribute tools and payloads.
- **T1588.001** — Obtain Capabilities: Malware: Procures publicly available malware to blend with cybercriminal activity.
- **T1588.002** — Obtain Capabilities: Tool: Acquires legitimate RMM tools (ScreenConnect/ConnectWise, RemoteUtilities, SimpleHelp, Atera, Action1, Level, PDQ, MeshCentral) for use as backdoors.
- **T1590.004** — Gather Victim Network Information: Network Topology: Maps target networks and shares/sells access to other Iranian threat actors.

### Initial Access
- **T1566** — Phishing: Sends phishing emails from spoofed addresses (e.g., support@microsoftonlines[.]com).
- **T1566.001** — Spearphishing Attachment: Primary initial access vector — macro-laden Word/Excel documents, malicious PDFs, and archive files delivered from compromised third-party mailboxes.
- **T1566.002** — Spearphishing Link: Targeted emails with links to lure documents hosted on OneHub, Sync, TeraBox, Dropbox, and OneDrive.
- **T1534** — Internal Spearphishing: Leverages compromised mailboxes within target organizations to send secondary spearphishing emails.
- **T1190** — Exploit Public-Facing Application: Exploits Exchange CVE-2020-0688 for initial access.
- **T1204.001** — User Execution: Malicious Link: Distributes URLs linking to lure documents and RMM tool installers.
- **T1204.002** — User Execution: Malicious File: Relies on victims enabling macros in Office documents or opening malicious PDFs/executables.
- **T1204.004** — User Execution: Malicious Copy and Paste: ClickFix-style tactics enticing victims to paste malicious PowerShell code.
- **T1195.001** — Supply Chain Compromise: Software Dependencies (Tsundere Botnet supply-chain vector).

### Execution
- **T1059.001** — PowerShell: Core execution method — POWERSTATS, PowGoop, and custom backdoors are PowerShell-based; Invoke-Obfuscation used for evasion.
- **T1059.003** — Windows Command Shell: Custom reverse shells and cmd.exe for enumeration commands (`net user /domain`).
- **T1059.005** — Visual Basic: VBScript/VBA macros in weaponized documents to stage POWERSTATS and STARWHALE payloads.
- **T1059.006** — Python: Python-based tools including Out1 and PhonyC2 C2 framework.
- **T1059.007** — JavaScript: JavaScript files used to execute POWERSTATS; obfuscated JS code stored via steganography.
- **T1047** — Windows Management Instrumentation: WMI used for execution and host-information queries.
- **T1559.001** — Inter-Process Communication: COM: Executes malicious code via COM, DCOM, and Outlook automation.
- **T1559.002** — Inter-Process Communication: DDE: Executes PowerShell scripts via Dynamic Data Exchange in Office documents.
- **T1203** — Exploitation for Client Execution: Office vulnerability exploitation (CVE-2017-0199).
- **T1106** — Native API: Direct Windows API calls from Fooder, LP-Notes, MuddyViper, and RustyWater implants.
- **T1569.002** — System Services: Service Execution: Koadic-driven service execution.

### Persistence
- **T1547.001** — Registry Run Keys / Startup Folder: Primary persistence mechanism — keys such as `KCU\Software\Microsoft\Windows\CurrentVersion\Run\SystemTextEncoding`; used by POWERSTATS, Small Sieve, STARWHALE, MuddyViper, RustyWater, and Tsundere Botnet.
- **T1137.001** — Office Application Startup: Office Template Macros: Normal.dotm template modification for persistence.
- **T1053.005** — Scheduled Task/Job: Scheduled Task: Scheduled tasks for persistent callback execution.
- **T1543.003** — Create or Modify System Process: Windows Service: STARWHALE and MuddyViper persist via Windows services.
- **T1574.001** — Hijack Execution Flow: DLL Side-Loading: Side-loads DLLs to trick legitimate programs into loading malware; key persistence mechanism per CISA AA22-055A.

### Privilege Escalation
- **T1548.002** — Abuse Elevation Control Mechanism: Bypass UAC: Various UAC bypass techniques including via ClickFix-delivered payloads.
- **T1134.001** — Access Token Manipulation: Token Impersonation/Theft: Fooder and LP-Notes perform token impersonation.
- **T1210** — Exploitation of Remote Services: Exploits Netlogon CVE-2020-1472 (Zerologon) for domain privilege escalation.

### Defense Evasion
- **T1027** — Obfuscated Files or Information: Extensive obfuscation across all custom tooling.
- **T1027.003** — Steganography: Obfuscated JavaScript stored in image files (temp.jpg).
- **T1027.004** — Compile After Delivery: .NET csc.exe used to compile executables from downloaded C# code on-target.
- **T1027.007** — Dynamic API Resolution: LP-Notes resolves API calls dynamically to evade static analysis.
- **T1027.010** — Command Obfuscation: Invoke-Obfuscation framework for PowerShell; Base64 obfuscation of VBScript/PowerShell commands.
- **T1027.013** — Encrypted/Encoded File: LP-Notes, STARWHALE, RustyWater, and Tsundere Botnet use encrypted payloads.
- **T1036.005** — Masquerading: Match Legitimate Resource Name or Location: Disguises executables as Windows Defender components and uses legitimate-sounding filenames and registry keys.
- **T1036.004** — Masquerading: Masquerade Task or Service: POWERSTATS creates scheduled tasks/services with legitimate-sounding names.
- **T1140** — Deobfuscate/Decode Files or Information: Runtime decoding of Base64-encoded PowerShell, JavaScript, and VBScript payloads.
- **T1218.003** — System Binary Proxy Execution: CMSTP: CMSTP.exe with malicious INF files to execute POWERSTATS.
- **T1218.005** — System Binary Proxy Execution: Mshta: mshta.exe to execute POWERSTATS and pass PowerShell one-liners.
- **T1218.007** — System Binary Proxy Execution: Msiexec: Msiexec-based execution for RemoteUtilities and Tsundere Botnet installers.
- **T1218.010** — System Binary Proxy Execution: Regsvr32: Mori malware registered via regsvr32.
- **T1218.011** — System Binary Proxy Execution: Rundll32: Rundll32 leveraged in Registry Run keys to execute DLL payloads.
- **T1564.003** — Hide Artifacts: Hidden Window: PowerShell executed with hidden windows (`-WindowStyle Hidden`); Koadic and Tsundere Botnet use hidden windows.
- **T1685** — Disable or Modify Tools: Disables local proxy settings to interfere with security monitoring.
- **T1070.004** — Indicator Removal: File Deletion: Mori and POWERSTATS delete dropped files after execution.
- **T1112** — Modify Registry: Mori and MuddyViper modify registry keys for configuration storage and persistence.
- **T1480** — Execution Guardrails: Small Sieve and Tsundere Botnet check environmental conditions before executing.
- **T1620** — Reflective Code Loading: Fooder, MuddyViper, and PowerSploit use reflective loading to execute payloads in memory.
- **T1622** — Debugger Evasion: RustyWater checks for debugger presence before execution.
- **T1678** — Delay Execution: Fooder, MuddyViper, and RustyWater implement sleep/delay routines to evade sandboxes.

### Credential Access
- **T1555** — Credentials from Password Stores: LaZagne and other tools dump credentials from email clients and password stores.
- **T1555.003** — Credentials from Web Browsers: Browser64 and LaZagne steal passwords from victim web browsers.
- **T1555.004** — Credentials from Password Stores: Windows Credential Manager: LaZagne targets Windows Credential Manager.
- **T1003.001** — OS Credential Dumping: LSASS Memory: Mimikatz and procdump64.exe dump LSASS memory.
- **T1003.002** — OS Credential Dumping: Security Account Manager: CrackMapExec and Koadic dump SAM database.
- **T1003.003** — OS Credential Dumping: NTDS: CrackMapExec extracts NTDS.dit for domain credential harvest.
- **T1003.004** — OS Credential Dumping: LSA Secrets: LaZagne extracts LSA secrets.
- **T1003.005** — OS Credential Dumping: Cached Domain Credentials: LaZagne dumps cached domain credentials.
- **T1003.006** — OS Credential Dumping: DCSync: Mimikatz used for DCSync domain replication attacks.
- **T1552.001** — Unsecured Credentials: Credentials In Files: Steals passwords saved in victim email clients and files.
- **T1110.001** — Brute Force: Password Guessing: CrackMapExec for password guessing against target services.
- **T1110.003** — Brute Force: Password Spraying: CrackMapExec used for password spraying across domain accounts.
- **T1056.001** — Input Capture: Keylogging: PowerSploit-based keylogging on compromised hosts.
- **T1056.002** — Input Capture: GUI Input Capture: LP-Notes and MuddyViper display fake credential dialogs to harvest credentials.
- **T1558.001** — Steal or Forge Kerberos Tickets: Golden Ticket: Mimikatz generates golden tickets for domain persistence.
- **T1558.002** — Steal or Forge Kerberos Tickets: Silver Ticket: Mimikatz used for service-targeted silver ticket attacks.

### Discovery
- **T1087.002** — Account Discovery: Domain Account: `net user /domain` and CrackMapExec for domain account enumeration.
- **T1083** — File and Directory Discovery: Checks ProgramData for security-product folders (Kaspersky, Panda, ESET).
- **T1057** — Process Discovery: Malware checks running processes against hardcoded list of security tools.
- **T1082** — System Information Discovery: Collects OS version, machine name, and system details.
- **T1033** — System Owner/User Discovery: Collects victim username via malware.
- **T1016** — System Network Configuration Discovery: Collects victim IP address and domain name.
- **T1049** — System Network Connections Discovery: Checks for Skype and other application connections.
- **T1518** — Software Discovery: Checks for Skype connectivity on target machine.
- **T1518.001** — Security Software Discovery: Enumerates running security products against hardcoded lists.
- **T1012** — Query Registry: Mori queries registry for configuration data.
- **T1018** — Remote System Discovery: CrackMapExec enumerates remote hosts on the network.
- **T1046** — Network Service Discovery: Koadic and CrackMapExec scan for network services.
- **T1135** — Network Share Discovery: Koadic and CrackMapExec enumerate network shares.
- **T1201** — Password Policy Discovery: CrackMapExec queries domain password policies.
- **T1614** — System Location Discovery: Tsundere Botnet determines geographic location of victims.
- **T1124** — System Time Discovery: SHARPSTATS queries system time.

### Lateral Movement
- **T1550.002** — Use Alternate Authentication Material: Pass the Hash: CrackMapExec and Mimikatz pass-the-hash for lateral movement.
- **T1210** — Exploitation of Remote Services: Netlogon CVE-2020-1472 exploitation for lateral domain access.
- **T1219.002** — Remote Access Tools: Remote Desktop Software: Leverages installed RMM tools (ScreenConnect, Atera, SimpleHelp, Action1, Level, PDQ) for interactive remote access on compromised hosts.

### Collection
- **T1005** — Data from Local System: Koadic, Out1, and STARWHALE collect data from the local filesystem.
- **T1114.001** — Email Collection: Local Email Collection: Out1 collects email data from local Outlook stores.
- **T1113** — Screen Capture: POWERSTATS and other malware capture screenshots.
- **T1074.001** — Data Staged: Local Data Staging: Decoy PDFs and collected data staged in `%temp%` and other directories.
- **T1560.001** — Archive Collected Data: Archive via Utility: Uses native makecab.exe to compress stolen data for exfiltration.

### Command and Control
- **T1071.001** — Application Layer Protocol: Web Protocols: HTTP/HTTPS used for primary C2 communications across POWERSTATS, MuddyViper, Out1, PowGoop, Small Sieve, STARWHALE, RustyWater.
- **T1071.004** — Application Layer Protocol: DNS: Mori backdoor uses **DNS tunneling** for C2 communication.
- **T1102.001** — Web Service: Dead Drop Resolver: Tsundere Botnet uses web services as dead drop resolvers.
- **T1102.002** — Web Service: Bidirectional Communication: Uses OneHub and other web services for bidirectional tool distribution and C2.
- **T1132.001** — Data Encoding: Standard Encoding: Base64 encoding of C2 communications.
- **T1132.002** — Data Encoding: Non-Standard Encoding: Small Sieve and PowGoop use custom encoding schemes.
- **T1573.001** — Encrypted Channel: Symmetric Cryptography: AES encryption for C2 responses (MuddyViper, RustyWater).
- **T1573.002** — Encrypted Channel: Asymmetric Cryptography: Small Sieve and Koadic use asymmetric encryption for C2.
- **T1090** — Proxy: NordVPN and other proxies to mask phishing email origins and C2 locations.
- **T1090.002** — External Proxy: POWERSTATS controlled through proxy networks; compromised websites used as relay chains; go-socks5 variants for firewall/NAT bypass.
- **T1104** — Multi-Stage Channels: Uses separate C2 servers for enumeration script delivery versus data exfiltration.
- **T1571** — Non-Standard Port: Botnet C2 on ports 8043 and 8848.
- **T1105** — Ingress Tool Transfer: Uploads additional tools (RMM installers, post-exploitation utilities) to victim machines.
- **T1001.001** — Data Obfuscation: Junk Data: Mori pads C2 traffic with junk data.
- **T1029** — Scheduled Transfer: POWERSTATS uses scheduled callback intervals for C2 communication.

### Exfiltration
- **T1041** — Exfiltration Over C2 Channel: Primary exfiltration method over established C2 connections.
- **T1567.002** — Exfiltration Over Web Service: Exfiltration to Cloud Storage: Rclone used to exfiltrate data to Wasabi cloud storage.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| POWERSTATS | S0223 | PowerShell-based first-stage backdoor / RAT | Custom |
| PowGoop | S1046 | PowerShell/DLL loader and C2 agent | Custom |
| Small Sieve | S1035 | Python-based Telegram Bot API backdoor | Custom |
| STARWHALE / Canopy | S1037 | VBScript-based Windows Script backdoor | Custom |
| Mori | S1047 | DLL backdoor with DNS tunneling C2 | Custom |
| SHARPSTATS | S0450 | .NET-based backdoor | Custom |
| MuddyViper | S9032 | Modular C2 implant (reflective loading) | Custom |
| Fooder | S9033 | Reflective-loading backdoor | Custom |
| LP-Notes | S9036 | Credential harvester with GUI input capture | Custom |
| RustyWater | S9037 | Rust-based implant with anti-debug | Custom |
| Tsundere Botnet | S9034 | JavaScript/PowerShell botnet framework | Custom |
| DCHSpy | S1243 | Android surveillanceware | Custom |
| Out1 | S0594 | Python-based data exfil and email collector | Custom |
| PhonyC2 | (no ATT&CK ID) | Python-based custom C2 framework (2021–2023) | Custom |
| MuddyC2Go | (no ATT&CK ID) | Go-based custom C2 framework (2023–present) | Custom |
| MuddyC3 | (no ATT&CK ID) | Python-based C2 framework (predecessor to PhonyC2) | Custom |
| DarkBeatC2 | (no ATT&CK ID) | Custom C2 framework | Custom |
| Phoenix | (no ATT&CK ID) | Lightweight backdoor implant | Custom |
| Dindoor | (no ATT&CK ID) | Backdoor used in U.S. critical-infra targeting | Custom |
| ConnectWise / ScreenConnect | S0591 | RMM tool (abused for remote access) | Public (RMM) |
| RemoteUtilities | S0592 | RMM tool (abused for remote access) | Public (RMM) |
| SimpleHelp | — | RMM tool (abused for remote access) | Public (RMM) |
| Atera Agent | — | RMM tool (abused for remote access) | Public (RMM) |
| Action1 / Level / PDQ | — | RMM tools (abused for remote access) | Public (RMM) |
| Koadic | S0250 | Post-exploitation framework (COM/JScript) | Public |
| Empire | S0363 | PowerShell/Python post-exploitation framework | Public |
| PowerSploit | S0194 | PowerShell post-exploitation modules | Public |
| CrackMapExec | S0488 | Network/AD enumeration and exploitation | Public |
| Mimikatz | S0002 | Credential dumping and Kerberos attacks | Public |
| LaZagne | S0349 | Multi-platform credential recovery | Public |
| Rclone | S1040 | Cloud sync / exfiltration tool | Public |
| Invoke-Obfuscation | — | PowerShell obfuscation framework | Public |
| go-socks5 | — | SOCKS5 proxy for firewall/NAT bypass | Public |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never run disruptive (ransomware / "DarkBit"-style) actions outside an explicitly sanctioned, isolated lab.

Map MuddyWater's signature plays to Decepticon's own capabilities:

- **Initial access — spearphishing with macro documents (T1566.001, T1204.002, T1059.005).** Use the phishing/payload-builder skill to craft macro-laden Word/Excel documents with region-specific decoy content (Arabic/Farsi government letterheads, telecom advisories). Stage documents that, on enable-macros, decode and execute a PowerShell stager via VBA — mirroring the POWERSTATS delivery chain. For link-based access (T1566.002), embed links to lure documents on file-sharing services.
- **Initial access — RMM tool abuse (T1219.002, T1588.002, T1105).** Emulate MuddyWater's signature pivot to legitimate RMM tools: deliver Atera Agent, ScreenConnect, or SimpleHelp installers via spearphishing PDFs with embedded links. Once installed, use the RMM tool's built-in capabilities for interactive remote access, bypassing traditional C2 detection.
- **Initial access — ClickFix social engineering (T1204.004, T1684.001).** Stand up a phishing page spoofing Microsoft security updates; embed instructions for victims to copy and paste a PowerShell one-liner that installs the RMM agent or downloads a POWERSTATS variant.
- **Execution — PowerShell-centric operations (T1059.001, T1027.010).** Run all post-exploitation through heavily obfuscated PowerShell (apply Invoke-Obfuscation). Use `mshta.exe` (T1218.005) and `CMSTP.exe` (T1218.003) as proxy-execution vectors to launch PowerShell stagers — this is MuddyWater's defining execution pattern.
- **Persistence (T1547.001, T1574.001, T1053.005, T1137.001).** Set Registry Run keys (`SystemTextEncoding` pattern) for PowerShell callbacks; side-load a DLL via a legitimate application for persistence; create scheduled tasks with innocuous names; modify Normal.dotm for Office template persistence.
- **Credential access (T1003.001, T1003.006, T1555, T1110.003).** Drive Mimikatz for LSASS dump and DCSync; deploy LaZagne for broad credential recovery (browsers, email, Windows Credential Manager); use CrackMapExec for password spraying and SAM/NTDS extraction — mirroring MuddyWater's systematic credential-harvesting approach.
- **Defense evasion (T1027.003, T1027.004, T1218.*, T1140).** Store obfuscated payloads in image files (steganography); compile C# payloads on-target with `csc.exe`; chain proxy-execution binaries (mshta → PowerShell → rundll32); decode Base64 payloads at runtime. Use hidden PowerShell windows (`-WindowStyle Hidden`) throughout.
- **C2 — custom framework emulation (T1071.001, T1071.004, T1090.002, T1104).** Use **Sliver** (c2 skill) over HTTPS as the primary channel to emulate MuddyC2Go/PhonyC2. For DNS tunneling (Mori pattern), set up a DNS-over-HTTPS or raw DNS channel. Implement **multi-stage channels** — use one C2 for enumeration scripts and a separate one for data exfiltration. Route through external proxies to mask C2 origin.
- **Discovery and lateral movement (T1087.002, T1082, T1135, T1550.002, T1210).** Enumerate domain accounts, network shares, and security software using CrackMapExec and native commands (`net user /domain`). Lateral-move via pass-the-hash (CrackMapExec/Mimikatz) and exploit Zerologon (CVE-2020-1472) where in scope.
- **Collection and exfiltration (T1560.001, T1041, T1567.002).** Compress collected data with `makecab.exe` or archive utilities; exfiltrate over C2. For the Dindoor/Rclone pattern, use Rclone to sync collected data to cloud storage (Wasabi/S3-compatible). Stage data in `%temp%` before exfiltration.

## Detection & defense

- **Spearphishing / macro documents (T1566.001, T1204.002):** Block macros from internet-originated documents (Mark-of-the-Web enforcement); deploy email sandboxing and attachment detonation; alert on Office processes spawning PowerShell, cmd.exe, mshta.exe, or CMSTP.exe.
- **RMM tool abuse (T1219.002):** Maintain an allowlist of authorized RMM software; alert on unexpected RMM agent installations (Atera, ScreenConnect, SimpleHelp, Syncro); monitor for RMM binaries executing in non-standard directories.
- **PowerShell-based backdoors (T1059.001, T1027.010):** Enable PowerShell Script Block Logging and Module Logging; constrained language mode on sensitive hosts; detect Invoke-Obfuscation patterns (string concatenation, encoding chains, `-WindowStyle Hidden`); monitor for PowerShell executing from `mshta.exe`, `CMSTP.exe`, or `rundll32.exe` parent processes.
- **DLL side-loading (T1574.001):** Monitor for DLL loads from non-standard directories alongside legitimate executables; use application-whitelisting solutions; alert on unsigned DLLs loaded by signed binaries.
- **Proxy-execution binaries (T1218.003, T1218.005, T1218.010, T1218.011):** Alert on mshta.exe, CMSTP.exe, regsvr32.exe, and rundll32.exe launching PowerShell or network connections; restrict via AppLocker/WDAC policies where possible.
- **DNS tunneling (T1071.004):** Monitor for high-volume DNS queries with long subdomain strings to unusual domains; deploy DNS-layer security; analyze TXT record query patterns for encoded data.
- **Credential dumping (T1003.*):** Enable LSA protection (RunAsPPL) and Credential Guard; alert on LSASS handle access, procdump targeting LSASS, LaZagne execution signatures; monitor DCSync replication from non-DC machines; restrict Mimikatz/CrackMapExec artifacts.
- **Persistence (T1547.001, T1053.005, T1137.001):** Monitor Registry Run key modifications (especially `SystemTextEncoding` or Windows-Defender-themed keys); audit scheduled task creation; monitor Normal.dotm modification timestamps.
- **Exfiltration (T1567.002, T1041):** Monitor for Rclone execution and cloud-storage API traffic to unusual endpoints (Wasabi, uncommon S3 buckets); DLP rules for `makecab.exe` archives; alert on large data transfers from staging directories.
- **ClickFix / social engineering (T1204.004):** User awareness training on copy-paste PowerShell attacks; browser isolation for untrusted pages; endpoint detection for clipboard-to-PowerShell execution chains.

## Sources

- https://attack.mitre.org/groups/G0069/
- https://www.cisa.gov/news-events/cybersecurity-advisories/aa22-055a
- https://www.cybercom.mil/Media/News/Article/2897570/iranian-intel-cyber-suite-of-malware-uses-open-source-tools/
- https://www.ncsc.gov.uk/files/NCSC-Malware-Analysis-Report-Small-Sieve.pdf
- https://www.deepinstinct.com/blog/phonyc2-revealing-a-new-malicious-command-control-framework-by-muddywater
- https://www.deepinstinct.com/blog/muddyc2go-latest-c2-framework-used-by-iranian-apt-muddywater-spotted-in-israel
- https://researchcenter.paloaltonetworks.com/2017/11/unit42-muddying-the-water-targeted-attacks-in-the-middle-east/
- https://www.fireeye.com/blog/threat-research/2018/03/iranian-threat-group-updates-ttps-in-spear-phishing-campaign.html
- https://www.symantec.com/blogs/threat-intelligence/seedworm-espionage-group
- https://www.clearskysec.com/wp-content/uploads/2018/11/MuddyWater-Operations-in-Lebanon-and-Oman.pdf
- https://securelist.com/muddywater/88059/
- https://blog.talosintelligence.com/2022/01/iranian-apt-muddywater-targets-turkey.html
- https://blog.talosintelligence.com/2019/05/recent-muddywater-associated-blackwater.html
- https://www.trendmicro.com/en_us/research/21/c/earth-vetala---muddywater-continues-to-target-organizations-in-t.html
- https://www.anomali.com/blog/probable-iranian-cyber-actors-static-kitten-conducting-cyberespionage-campaign-targeting-uae-and-kuwait-government-agencies
- https://www.proofpoint.com/us/blog/threat-insight/security-brief-ta450-uses-embedded-links-pdf-attachments-latest-campaign
- https://www.proofpoint.com/us/blog/threat-insight/around-world-90-days-state-sponsored-actors-try-clickfix
- https://www.welivesecurity.com/en/eset-research/muddywater-snakes-riverbank/
- https://www.group-ib.com/blog/muddywater-infrastructure/
- https://www.cloudsek.com/blog/reborn-in-rust-muddywater-evolves-tooling-with-rustywater-implant
- https://socradar.io/blog/iran-muddywater-dindoor-malware-us-networks/
- https://www.security.com/threat-intelligence/iran-cyber-threat-activity-us
- https://blog.trendmicro.com/trendlabs-security-intelligence/muddywater-resurfaces-uses-multi-stage-backdoor-powerstats-v3-and-new-post-exploitation-tools/
- https://reaqta.com/2017/11/muddywater-apt-targeting-middle-east/
- https://research.checkpoint.com/2026/iranian-mois-actors-the-cyber-crime-connection/
- https://falconfeeds.io/blogs/muddywater-in-the-iran-israel-cyber-war-from-powershell-scripts-to-rust-implants
