---
name: apt10-stone-panda
description: "Adversary-emulation profile for APT10 (G0045 / Stone Panda / menuPass / POTASSIUM / Red Apollo / CVNX), China's MSS Tianjin State Security Bureau cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "APT10, Stone Panda, menuPass, POTASSIUM, Red Apollo, CVNX, HOGFISH, Cicada, BRONZE RIVERSIDE, G0045, Chinese MSS espionage emulation, Cloud Hopper MSP supply-chain, Operation Soft Cell telecom, PlugX, QuasarRAT, Poison Ivy, ChChes, UPPERCUT/ANEL, RedLeaves, DLL side-loading, credential harvesting from managed service providers, custom HTTP/DNS C2"
  tags: apt10, stone-panda, menupass, potassium, red-apollo, cvnx, cicada, china, mss, espionage, nation-state, g0045, adversary-emulation, mitre-attack, cloud-hopper, supply-chain
  mitre_attack: T1583.001, T1588.002, T1566.001, T1190, T1199, T1078, T1204.002, T1059.001, T1059.003, T1047, T1053.005, T1106, T1210, T1547.001, T1547.009, T1543.003, T1574.001, T1055.012, T1068, T1548.002, T1027, T1027.013, T1036, T1036.003, T1036.005, T1070.003, T1070.004, T1112, T1140, T1218.004, T1553.002, T1564.001, T1564.003, T1497, T1003.002, T1003.003, T1003.004, T1056.001, T1555.003, T1087.002, T1083, T1046, T1016, T1018, T1033, T1049, T1082, T1135, T1482, T1518, T1005, T1039, T1074.001, T1074.002, T1119, T1113, T1560, T1560.001, T1021.001, T1021.002, T1021.004, T1550.002, T1570, T1071.001, T1071.004, T1568.001, T1573.001, T1573.002, T1090.002, T1095, T1571, T1572, T1105, T1132.001, T1102.001, T1041, T1030, T1048
---

# APT10 (Stone Panda, menuPass, POTASSIUM, Red Apollo) — Adversary Emulation Profile

APT10 (MITRE ATT&CK **G0045**) is a long-running Chinese cyber-espionage group active since at least 2006, attributed to China's Ministry of State Security (MSS) **Tianjin State Security Bureau**. Individual members have been identified as working for the Huaying Haitai Science and Technology Development Company. APT10 is best known for **Operation Cloud Hopper** — the systematic, large-scale compromise of managed IT service providers (MSPs) to pivot into hundreds of downstream client organizations worldwide — a paradigm-defining supply-chain attack. The group's toolkit spans custom implants (PlugX, RedLeaves, ChChes, UPPERCUT/ANEL, SodaMaster, Ecipekac), public frameworks (QuasarRAT, Cobalt Strike, Mimikatz, PsExec), and heavy reliance on DLL side-loading for evasion. Targeting is broad: healthcare, defense, aerospace, government, telecom, maritime, finance, and biotechnology, with a persistent emphasis on Japanese organizations and Western MSPs.

## Attribution & motivation

- **Sponsor / nation:** People's Republic of China — Ministry of State Security (MSS), **Tianjin State Security Bureau**. The December 2018 U.S. DOJ indictment named two MSS-linked operatives, **Zhu Hua (朱华)** and **Zhang Shilong (张士龙)**, as APT10 members employed by Huaying Haitai Science and Technology Development Company. Joint attributions by the UK (NCSC), Japan, Australia, Canada, and the EU corroborated the MSS link.
- **Motivation:** Primarily **economic espionage and intellectual-property theft** aligned with Chinese state industrial policy — stealing trade secrets, engineering data, and business-confidential information from technology, aerospace, defense, pharmaceutical, and energy sectors. Secondary motivation includes **strategic intelligence collection** (government, diplomatic, and telecom surveillance — e.g., Call Detail Records in Operation Soft Cell).
- **Attribution confidence:** **High.** Backed by U.S. DOJ criminal indictments (SDNY, Dec 2018), coordinated Five Eyes + EU government attributions, and consistent named vendor reporting (FireEye/Mandiant, PwC/BAE Systems, Symantec, Kaspersky, Palo Alto Unit 42, Cybereason, Accenture).

## Targeting

- **Sectors:** IT managed service providers (MSPs) and cloud service providers (the defining target); healthcare; defense and aerospace; government and public administration; telecommunications; finance and banking; maritime; biotechnology and pharmaceuticals; energy; manufacturing and mining; academia and research.
- **Regions:** Heavy emphasis on **Japan** (persistent, long-running campaigns against government agencies and corporations); **United States** (MSPs, technology, government); **Western Europe** (UK, Germany, France, Nordics — via MSP pivots); broader global reach through the MSP supply chain into dozens of countries. Operation Soft Cell targeted telcos across Southeast Asia, Europe, Africa, and the Middle East.
- **Victim profile:** Organizations holding high-value IP, trade secrets, and strategic data. The MSP targeting model gave APT10 access to the networks of MSP clients — effectively multiplying each compromise into dozens or hundreds of downstream victims. Telecom targeting focused on CDR/subscriber surveillance of individuals of intelligence interest.

## Notable campaigns

- **2006-2013 — Early menuPass operations.** Initial spearphishing campaigns against Japanese academic institutions, government agencies, and defense-related organizations using Poison Ivy RAT, PlugX, and EvilGrab; documented by FireEye, Palo Alto Unit 42, and CrowdStrike. (Unit 42 / CrowdStrike)
- **2014-2017 — Operation Cloud Hopper.** Large-scale, sustained compromise of multiple global managed IT service providers (MSPs) to pivot into downstream client networks across healthcare, defense, aerospace, government, IT, and manufacturing. Used over 70 variants of backdoors including PlugX, RedLeaves, QuasarRAT, and ChChes; leveraged legitimate MSP credentials and RDP/admin-share access for lateral movement. Publicly attributed by PwC/BAE Systems (April 2017). (PwC/BAE Systems Cloud Hopper report)
- **2017 — Japanese corporations and academics.** Targeted campaign against Japanese organizations using spearphishing with UPPERCUT (ANEL) and ChChes backdoors, LNK file lures, and DLL side-loading; documented by FireEye. (FireEye APT10 blog, April/September 2017-2018)
- **2018-12 — DOJ indictment of Zhu Hua and Zhang Shilong.** U.S. Department of Justice (SDNY) indicted two Chinese nationals for global computer intrusion campaigns spanning 2006-2018, with coordinated attributions by UK, Australia, Canada, Japan, and New Zealand. (justice.gov)
- **2018-2019 — Operation Soft Cell.** Cybereason identified APT10-linked actors compromising global telecommunications providers (active since at least 2012), targeting core network infrastructure and Call Detail Records for intelligence surveillance. At least 10 telcos across multiple continents affected. (Cybereason)
- **2019-2021 — A41APT campaign / Cicada.** Kaspersky documented a sophisticated campaign (A41APT) targeting Japanese organizations using the multi-layered Ecipekac loader, SodaMaster, P8RAT, FYAnti, and Cobalt Strike. Symantec tracked overlapping activity as "Cicada" with emphasis on machine-to-machine lateral movement and living-off-the-land techniques. (Kaspersky GReAT / Symantec)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.001** — Acquire infrastructure — domains: registered malicious domains for phishing and C2 infrastructure.
- **T1588.002** — Obtain capabilities — tool: acquired and modified open-source tools including Impacket, Mimikatz, pwdump, and PowerSploit.

### Initial Access
- **T1566.001** — Spearphishing attachment: malicious Office documents (macro-laden Word/Excel), executables disguised as documents, and LNK file lures delivered via email.
- **T1190** — Exploit public-facing application: leveraged vulnerabilities in Pulse Secure VPNs to hijack sessions (A41APT campaign); exploited ZeroLogon (CVE-2020-1472).
- **T1199** — Trusted relationship: **defining TTP** — systematically compromised managed service providers (MSPs) and used their legitimate access to pivot into downstream client networks (Cloud Hopper).
- **T1078** — Valid accounts: used credentials shared between MSPs and clients, and stolen credentials from compromised environments; maintained persistent access via legitimate account reuse.

### Execution
- **T1059.001** — PowerShell: used PowerSploit to inject shellcode; PowerShell for post-exploitation and tool deployment.
- **T1059.003** — Windows Command Shell: extensive use of `cmd.exe`, modified `wmiexec.vbs` scripts, and macro-triggered command execution.
- **T1047** — WMI: used modified `wmiexec.vbs` to execute commands on remote systems via WMI.
- **T1053.005** — Scheduled Task: used `atexec.py` to execute commands on remote systems via the Task Scheduler.
- **T1204.002** — User execution — malicious file: lured victims into opening weaponized Office documents, LNK shortcuts, and executables masquerading as legitimate files.
- **T1106** — Native API: implants (Cicada/Symantec-tracked variants) used `GetModuleFileName`, `CreateFile`, `ReadFile`, and other Windows APIs directly.
- **T1210** — Exploitation of remote services: used tools to exploit ZeroLogon (CVE-2020-1472) for domain controller compromise.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: PlugX, RedLeaves, ChChes, SNUGRIDE, QuasarRAT, Poison Ivy, and EvilGrab all used Run key persistence.
- **T1547.009** — Shortcut modification: RedLeaves used shortcut modification for persistence.
- **T1543.003** — Windows service: PlugX, Poison Ivy, and Cobalt Strike created Windows services for persistence; PsExec used service execution for deployment.
- **T1574.001** — DLL side-loading / DLL search order hijacking: **signature TTP** — used extensively to load Mimikatz, pwdump, UPPERCUT, RedLeaves, PlugX, Ecipekac, and HUI Loader via legitimate executables; both side-loading and search-order hijacking observed.

### Privilege Escalation
- **T1055.012** — Process hollowing: hollowed `iexplore.exe` to load RedLeaves implant.
- **T1068** — Exploitation for privilege escalation: exploited ZeroLogon (CVE-2020-1472) for domain-level access.
- **T1548.002** — Bypass User Account Control: UPPERCUT and QuasarRAT include UAC bypass capabilities.

### Defense Evasion
- **T1027 / T1027.013** — Obfuscation / encrypted-encoded files: base64 encoding, single-byte XOR (key 0x40), and multi-layer encryption (Ecipekac — four layers of loaders with different encryption).
- **T1036 / T1036.003 / T1036.005** — Masquerading: renamed `certutil` and moved it to evade detection; changed malicious file extensions and names to match legitimate software.
- **T1070.003** — Clear command history: used `wevtutil` to remove PowerShell execution logs.
- **T1070.004** — File deletion: macros delete decoded/decompressed payloads after use; implants clean up dropped files.
- **T1140** — Deobfuscate/decode: used `certutil -decode` to decode base64-encoded payloads in macros and during UPPERCUT deployment.
- **T1218.004** — InstallUtil: used `InstallUtil.exe` to execute malicious .NET assemblies, bypassing application whitelisting.
- **T1553.002** — Code signing: resized and modified certificate tables to sign altered files with legitimate signatures (Ecipekac loader chain).
- **T1112** — Modify registry: implants modify registry for configuration storage and persistence.
- **T1564.001 / T1564.003** — Hidden files and hidden windows: PlugX and QuasarRAT use hidden files/directories and hidden windows.
- **T1497** — Virtualization/sandbox evasion: SodaMaster and P8RAT perform system and time-based checks to detect analysis environments.

### Credential Access
- **T1003.002** — SAM: used modified `secretsdump.py` and `pwdump6` to dump SAM database credentials.
- **T1003.003** — NTDS: used `ntdsutil` to dump the Active Directory database.
- **T1003.004** — LSA Secrets: used modified `wmiexec.vbs` and `secretsdump.py` to extract LSA secrets.
- **T1056.001** — Keylogging: deployed keyloggers to capture usernames and passwords; PlugX, Poison Ivy, EvilGrab, and QuasarRAT all include keylogging modules.
- **T1555.003** — Credentials from web browsers: ChChes, RedLeaves, and QuasarRAT harvested stored browser credentials.

### Discovery
- **T1087.002** — Domain account discovery: used `csvde.exe` and AdFind to export Active Directory data; `net user /domain` enumeration.
- **T1083** — File and directory discovery: searched compromised systems for folders related to HR, audit/expense, and meeting memos.
- **T1046** — Network service discovery: used `tcping.exe` and port-scanning tools to probe open services on target systems.
- **T1016** — System network configuration discovery: scanned for open NetBIOS nameservers and enumerated NetBIOS sessions; AdFind for network topology.
- **T1018** — Remote system discovery: used scripts to enumerate IP ranges; issued `net view /domain` through PlugX; used Ping for host discovery.
- **T1033** — System owner/user discovery: RedLeaves, SodaMaster, UPPERCUT, and QuasarRAT enumerate current user information.
- **T1049** — System network connections discovery: used `net use` for connectivity checks.
- **T1082** — System information discovery: most implants (ChChes, RedLeaves, UPPERCUT, SodaMaster, PlugX) collect system information.
- **T1135** — Network share discovery: PlugX and Net used for share enumeration.
- **T1482** — Domain trust discovery: AdFind used for trust enumeration.
- **T1518** — Software discovery: implants enumerate installed software for situational awareness.

### Lateral Movement
- **T1021.001** — Remote Desktop Protocol: used RDP to move across victim networks, including MSP-to-client pivots.
- **T1021.002** — SMB/Windows admin shares: used PsExec and `net use` for remote execution and file transfer over admin shares.
- **T1021.004** — SSH: used PuTTY Secure Copy (PSCP) to transfer data between systems.
- **T1550.002** — Pass the hash: used Mimikatz for pass-the-hash attacks to move laterally with harvested NTLM hashes.
- **T1570** — Lateral tool transfer: used PsExec, `cmd`, and `esentutl` to move tools across compromised systems.

### Collection
- **T1005** — Data from local system: collected files from compromised computers including documents and proprietary data.
- **T1039** — Data from network shared drive: mounted network shares with `net use` and used Robocopy to transfer data from shared drives.
- **T1074.001 / T1074.002** — Local and remote data staging: staged data in multi-part archives, often saved in the Recycle Bin or on remote MSP jump servers prior to exfiltration.
- **T1119** — Automated collection: used `csvde` for automated Active Directory data collection.
- **T1113** — Screen capture: RedLeaves, PlugX, UPPERCUT, and EvilGrab include screen-capture capabilities.
- **T1560 / T1560.001** — Archive collected data / archive via utility: compressed files using TAR and RAR before exfiltration; encrypted archives for operational security.

### Command & Control
- **T1071.001** — Web protocols (HTTP/HTTPS): primary C2 channel for PlugX, RedLeaves, ChChes, SNUGRIDE, UPPERCUT, and Cobalt Strike — HTTPS-based C2 with custom headers and encoded payloads.
- **T1071.004** — DNS: PlugX used DNS-based C2 channels.
- **T1568.001** — Fast Flux DNS: used dynamic DNS service providers to host malicious domains and enable rapid infrastructure rotation.
- **T1573.001 / T1573.002** — Symmetric and asymmetric encrypted channels: ChChes, PlugX, SNUGRIDE, RedLeaves, UPPERCUT, and SodaMaster use encrypted C2 (AES, RC4, RSA).
- **T1090.002** — External proxy: used global service provider IPs as proxies for C2 traffic from victims.
- **T1095** — Non-application layer protocol: PlugX and QuasarRAT use raw TCP for C2.
- **T1571** — Non-standard port: RedLeaves, PlugX, and QuasarRAT communicate over non-standard ports.
- **T1572** — Protocol tunneling: tunneled C2 traffic through legitimate protocols for evasion.
- **T1105** — Ingress tool transfer: installed updates and deployed new malware families onto compromised systems.
- **T1132.001** — Data encoding — standard encoding: ChChes and UPPERCUT use base64-encoded C2 communications.
- **T1102.001** — Web service — dead drop resolver: PlugX used web services as dead drop resolvers for C2 instructions.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: PlugX and other implants exfiltrate data over the same HTTPS C2 channel.
- **T1030** — Data transfer size limits: staged data in multi-part archives to avoid detection thresholds.
- **T1048** — Exfiltration over alternative protocol: used PSCP (SSH) and other non-C2 channels for bulk data exfiltration.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| PlugX | S0013 | Modular RAT (HTTP/DNS C2, DLL side-loading, keylogging) | Custom |
| RedLeaves | S0153 | Windows backdoor (HTTP C2, DLL side-loading) | Custom |
| ChChes | S0144 | Lightweight backdoor (HTTP C2, cookie-based comms) | Custom |
| UPPERCUT / ANEL | S0275 | Backdoor (HTTP C2, UAC bypass, DLL side-loading) | Custom |
| SNUGRIDE | S0159 | Windows backdoor (HTTP C2) | Custom |
| Poison Ivy | S0012 | RAT (keylogging, screen capture, service persistence) | Custom (shared) |
| EvilGrab | S0152 | Audio/video/keylog capture backdoor | Custom |
| SodaMaster | S0627 | Fileless backdoor (anti-sandbox, RSA+AES encrypted C2) | Custom |
| Ecipekac | S0624 | Multi-layered loader (4-layer encryption, code-signing abuse) | Custom |
| P8RAT | S0626 | Fileless backdoor (anti-sandbox, junk-data C2 obfuscation) | Custom |
| FYAnti | S0628 | .NET downloader/loader (packed, used in A41APT) | Custom |
| HUI Loader | S1097 | DLL side-loading loader (defense evasion, deobfuscation) | Custom |
| QuasarRAT | S0262 | Open-source .NET RAT (keylogging, screen capture, file manager) | Public |
| Cobalt Strike | S0154 | Post-exploitation framework (Beacon implant) | Public (commercial) |
| Mimikatz | S0002 | Credential dumping (LSASS, SAM, DCSync, pass-the-hash) | Public |
| Impacket | S0357 | Python network toolkit (secretsdump, wmiexec, atexec) | Public |
| PowerSploit | S0194 | PowerShell post-exploitation (injection, credential access) | Public |
| PsExec | S0029 | Remote execution via SMB/service | Public (Sysinternals) |
| pwdump | S0006 | SAM credential dumping | Public |
| AdFind | S0552 | Active Directory enumeration | Public |
| certutil | S0160 | LOLBin (decode, download, certificate manipulation) | Built-in |
| Net | S0039 | LOLBin (account/share/service enumeration) | Built-in |
| cmd | S0106 | LOLBin (command execution, file operations) | Built-in |
| Wevtutil | S0645 | LOLBin (event log clearing) | Built-in |
| esentutl | S0404 | LOLBin (data copy, NTFS attribute access) | Built-in |
| Ping | S0097 | LOLBin (host discovery) | Built-in |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never run destructive actions outside an explicitly sanctioned, isolated lab.

Map APT10's signature plays to Decepticon's own capabilities:

- **Initial access — MSP supply-chain pivot (T1199, T1078, T1566.001).** APT10's defining play is the **Cloud Hopper model**: compromise an MSP, harvest shared credentials, and pivot into downstream client networks. Use the phishing/credential-harvest skill to spearphish MSP administrators with macro-laden Office documents and LNK lures. Once inside the MSP, enumerate shared credentials and RDP/VPN access to client environments — this MSP→client pivot chain is the signature APT10 initial-access pattern.
- **DLL side-loading (T1574.001).** APT10's most consistent evasion technique. Use the payload-builder skill to craft DLL side-loading chains: place a malicious DLL alongside a legitimate, signed executable (e.g., a renamed legitimate application) so the legitimate process loads the attacker DLL. Emulate the PlugX/RedLeaves/UPPERCUT side-loading pattern — this is the technique to prioritize for detection validation.
- **Credential harvesting at scale (T1003.002, T1003.003, T1003.004, T1056.001).** With the AD/lateral-movement skill, run **Mimikatz** for SAM dumps and pass-the-hash; use **Impacket `secretsdump.py`** for LSA secrets and NTDS extraction via `ntdsutil`. Deploy keyloggers to capture credentials in real time. In Cloud Hopper emulation, focus on harvesting MSP admin credentials that grant access to client tenants.
- **Lateral movement — RDP and admin shares (T1021.001, T1021.002, T1550.002, T1570).** Use harvested credentials and pass-the-hash to move via RDP and SMB admin shares. Deploy **PsExec** for remote service execution. Use **Robocopy** to stage and transfer data across network shares. Mirror APT10's pattern of chaining through jump servers and MSP management infrastructure.
- **Process hollowing and injection (T1055.012).** Emulate RedLeaves-style process hollowing into `iexplore.exe` or another benign process. Use the evasion skill to spawn a suspended legitimate process, hollow its memory, and inject implant code — a key detection-engineering exercise.
- **C2 — HTTPS with encrypted channels (T1071.001, T1573.001, T1568.001).** Use **Sliver** or **Cobalt Strike** (c2 skill) over HTTPS as the primary channel. Configure dynamic DNS for domain rotation. Add custom HTTP headers and cookie-based communication to emulate ChChes/UPPERCUT C2 patterns. Use non-standard ports to emulate PlugX/RedLeaves behavior.
- **Discovery and AD enumeration (T1087.002, T1482, T1083).** Use **AdFind** and **csvde.exe** for Active Directory enumeration; `net view /domain` and IP range scanning for network mapping. Search for high-value document folders (HR, finance, R&D) to emulate APT10's targeted collection behavior.
- **Collection and exfiltration (T1560.001, T1074.001, T1074.002, T1030, T1048).** Archive collected data with **RAR/TAR** into split, encrypted multi-part archives. Stage in the Recycle Bin or on remote jump servers before exfiltrating over SSH (PSCP) or HTTPS C2. The multi-part staging and Recycle Bin use are APT10 signatures.
- **Defense evasion — certutil and InstallUtil (T1140, T1218.004, T1036.003).** Rename and relocate `certutil` for payload decoding; use `InstallUtil.exe` for .NET assembly execution; clear PowerShell logs with `wevtutil`. These LOLBin abuse patterns should be emulated for EDR/SIEM validation.

## Detection & defense

- **MSP / supply-chain access (T1199, T1078):** Audit and restrict MSP access to client environments — enforce MFA on all MSP administrative accounts, segment MSP management networks from production, monitor for MSP-origin RDP and credential use outside maintenance windows, and review shared service accounts for anomalous activity.
- **DLL side-loading (T1574.001):** Monitor for unsigned DLLs loaded by signed executables; alert on DLLs loaded from unusual paths (Temp, Recycle Bin, user-writable directories); use application whitelisting to restrict which DLLs can be loaded by approved executables; hunt for legitimate executables copied to non-standard locations.
- **Credential dumping (T1003.*):** Enable LSA protection (RunAsPPL) and Credential Guard; alert on LSASS handle access (Sysmon Event ID 10), `ntdsutil` execution, `reg save` of SAM/SYSTEM/SECURITY hives, and secretsdump-style network activity; restrict debug privileges.
- **Spearphishing and macro execution (T1566.001, T1204.002):** Enforce macro-disabled policies or ASR rules to block Office macro execution; deploy email sandboxing and attachment analysis; alert on Office spawning `cmd.exe`, `PowerShell`, `certutil`, or `InstallUtil`.
- **Process hollowing (T1055.012):** Monitor for suspended process creation followed by memory writes and thread resumption (Sysmon Event IDs 1, 8); alert on `iexplore.exe` or other browser processes running without user interaction or from unusual parent processes.
- **LOLBin abuse — certutil, InstallUtil, wevtutil (T1140, T1218.004, T1070.003):** Alert on `certutil -decode` and `certutil -urlcache` usage; monitor `InstallUtil.exe` executing assemblies from non-standard paths; detect `wevtutil cl` for log clearing.
- **Lateral movement — RDP and admin shares (T1021.001, T1021.002):** Monitor for RDP sessions from unexpected source hosts (especially MSP jump servers outside maintenance); alert on PsExec service installation; track `net use` mapping of admin shares and Robocopy execution.
- **C2 — dynamic DNS and HTTPS (T1568.001, T1071.001):** Block or alert on dynamic DNS provider domains (e.g., `*.hopto.org`, `*.no-ip.org`); inspect HTTPS traffic to newly registered or low-reputation domains; monitor for non-standard port usage by common processes.
- **Data staging and exfiltration (T1074, T1560.001, T1030):** Monitor for archive creation in the Recycle Bin or temp directories; alert on RAR/TAR execution with encryption flags; detect multi-part file creation patterns; monitor for PSCP or SCP data transfers.

## Sources

- https://attack.mitre.org/groups/G0045/
- https://www.justice.gov/opa/pr/two-chinese-hackers-associated-ministry-state-security-charged-global-computer-intrusion
- https://www.justice.gov/opa/page/file/1122671/download
- https://web.archive.org/web/20220224041316/https://www.pwc.co.uk/cyber-security/pdf/cloud-hopper-report-final-v4.pdf
- https://www.pwc.co.uk/cyber-security/pdf/pwc-uk-operation-cloud-hopper-technical-annex-april-2017.pdf
- https://www.fireeye.com/blog/threat-research/2017/04/apt10_menupass_grou.html
- https://www.fireeye.com/blog/threat-research/2018/09/apt10-targeting-japanese-corporations-using-updated-ttps.html
- https://symantec-enterprise-blogs.security.com/blogs/threat-intelligence/cicada-apt10-japan-espionage
- https://www.cybereason.com/blog/research/operation-soft-cell-a-worldwide-campaign-against-telecommunications-providers
- https://securelist.com/apt10-sophisticated-multi-layered-loader-ecipekac-discovered-in-a41apt-campaign/101519/
- https://web.archive.org/web/20220810112638/https://www.accenture.com/t20180423T055005Z_w_/se-en/_acnmedia/PDF-76/Accenture-Hogfish-Threat-Analysis.pdf
- https://researchcenter.paloaltonetworks.com/2017/02/unit42-menupass-returns-new-malware-new-attacks-japanese-academics-organizations/
- https://unit42.paloaltonetworks.com/menupass-playbook-and-iocs/
- https://www.secureworks.com/research/bronze-starlight-ransomware-operations-use-hui-loader
