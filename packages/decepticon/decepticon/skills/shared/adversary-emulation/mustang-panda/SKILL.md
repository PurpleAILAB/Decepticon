---
name: mustang-panda-bronze-president
description: "Adversary-emulation profile for Mustang Panda (G0129 / Bronze President / Stately Taurus / RedDelta / TA416 / TEMP.Hex), a China-based state-sponsored cyber-espionage actor operating since at least 2012."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Mustang Panda, Bronze President, Stately Taurus, RedDelta, TA416, TEMP.Hex, Earth Preta, Camaro Dragon, HIVE0154, Twill Typhoon, G0129, Chinese espionage emulation, PlugX / Korplug RAT, TONESHELL loader, DLL side-loading, USB worm propagation, spearphishing with themed lures, SE Asian government targeting, EU diplomatic targeting, Vatican targeting"
  tags: mustang-panda, bronze-president, stately-taurus, reddelta, ta416, temp-hex, earth-preta, camaro-dragon, china, espionage, nation-state, g0129, adversary-emulation, mitre-attack
  mitre_attack: T1087.002, T1583.001, T1583.006, T1557, T1071.001, T1560.001, T1560.003, T1119, T1547.001, T1059, T1059.001, T1059.003, T1059.005, T1059.007, T1586.002, T1001.003, T1074.001, T1622, T1678, T1140, T1587.001, T1573.001, T1585.002, T1546.003, T1480, T1048.003, T1041, T1052.001, T1567.002, T1203, T1083, T1564.001, T1574.001, T1574.005, T1070, T1070.004, T1070.006, T1105, T1654, T1036.004, T1036.005, T1036.007, T1036.008, T1106, T1046, T1095, T1027, T1027.007, T1027.012, T1027.013, T1027.016, T1588.002, T1588.003, T1588.004, T1003, T1003.001, T1003.003, T1003.006, T1069.002, T1566.001, T1566.002, T1598.003, T1057, T1572, T1090, T1219.001, T1219.002, T1018, T1091, T1053.005, T1593, T1505.003, T1129, T1072, T1518, T1176.002, T1608, T1608.001, T1553.002, T1218.004, T1218.005, T1218.007, T1218.014, T1082, T1016, T1049, T1205, T1204.001, T1204.002, T1102, T1047
---

# Mustang Panda (Bronze President, Stately Taurus, RedDelta, TA416) — Adversary Emulation Profile

Mustang Panda (MITRE ATT&CK **G0129**) is a China-based cyber-espionage threat actor conducting operations since at least **2012**. Tracked under a dozen aliases — **Bronze President** (Secureworks), **Stately Taurus / FIREANT** (Unit 42), **RedDelta** (Recorded Future), **TA416** (Proofpoint), **Earth Preta** (Trend Micro), **HIVE0154** (IBM X-Force), **Camaro Dragon** (Check Point), **Twill Typhoon / TANTALUM** (Microsoft), **LUMINOUS MOTH**, **UNC6384 / TEMP.Hex** (Mandiant/Google TAG), **Red Lich** (PwC), and **ClumsyToad** (Cloudflare) — the group is best known for its prolific use of **PlugX/Korplug** RAT variants delivered through DLL side-loading, themed spearphishing lures, and USB-based propagation. Mustang Panda targets government, diplomatic, military, NGO, think-tank, and religious entities across Southeast Asia, Europe, and beyond, with sustained focus on Myanmar, Vietnam, the Philippines, Cambodia, Taiwan, Japan, Mongolia, and — since 2022 — European diplomatic bodies and Russia-related targets.

## Attribution & motivation

- **Sponsor / nation:** People's Republic of China — assessed as a state-sponsored espionage actor with a Chinese nexus. CrowdStrike first attributed the group in 2017; subsequent reporting from Secureworks, Recorded Future, Proofpoint, Trend Micro, Unit 42, Check Point, IBM X-Force, and Google TAG consistently attribute operations to PRC interests. A December 2024 U.S. DOJ affidavit supported seizure of U.S.-based computers infected with Mustang Panda's PlugX malware, formally linking the tool to PRC state-sponsored activity.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** aligned with PRC foreign-policy interests — diplomatic, military, and political intelligence from Southeast Asian governments, European diplomatic bodies, and organizations involved in issues sensitive to Beijing (Tibet, Taiwan, South China Sea, religious organizations).
- **Attribution confidence:** **High.** Backed by consistent multi-vendor reporting (CrowdStrike, Secureworks, Recorded Future, Proofpoint, Unit 42, Trend Micro, ESET, Check Point, IBM X-Force, Google TAG, Zscaler), U.S. DOJ law-enforcement action (2024 PlugX seizure warrant), and shared infrastructure/tooling overlap across campaigns spanning 10+ years.

## Targeting

- **Sectors:** Government and diplomatic bodies (ministries of defense and foreign affairs); military; NGOs, think tanks, and civil-society organizations; religious institutions (Vatican, Catholic organizations, Tibetan community); research and academic entities; telecommunications; media.
- **Regions:** Southeast Asia (Myanmar, Vietnam, Philippines, Cambodia, Laos, Indonesia, Malaysia); East Asia (Taiwan, Japan, Mongolia); South Asia (Pakistan); Europe (EU institutions, Germany, France); United States; Russia (post-2022 Ukraine conflict); Australia.
- **Victim profile:** Entities and individuals whose documents, communications, and credentials yield intelligence on regional geopolitics, territorial disputes, defense policy, and diplomatic relations — particularly around ASEAN, the South China Sea, Myanmar's political situation, and cross-strait (Taiwan) affairs.

## Notable campaigns

- **2017-04 — Initial CrowdStrike attribution.** CrowdStrike Falcon Intelligence observed a previously unattributed actor with a Chinese nexus targeting a U.S.-based think tank; further analysis revealed a broader campaign using tailored lures and PlugX. (CrowdStrike)
- **2019 — BRONZE PRESIDENT targets NGOs.** Secureworks documented campaigns against NGOs in Southeast Asia and North America using PlugX, Cobalt Strike, RCSession, and DLL side-loading with legitimate signed executables. (Secureworks)
- **2019-2020 — Myanmar government targeting.** Sustained operations against Myanmar's government, military, and political entities — a recurring focus that has continued through 2024. Lures themed around Myanmar domestic politics, military junta activity, and ethnic-group affairs. (Bugcrowd / CSIRT-CTI / Unit 42)
- **2020-07 — RedDelta targets the Vatican and Catholic organizations.** Recorded Future documented spearphishing campaigns using PlugX against the Vatican and Catholic Church-affiliated organizations ahead of the Holy See's negotiations to renew a deal with Beijing. (Recorded Future CTA-2020-0728)
- **2020-11 — TA416 returns with Golang PlugX loader.** Proofpoint observed Mustang Panda deploying a new Golang-based PlugX malware loader after a brief operational pause, targeting diplomatic entities. (Proofpoint)
- **2022-02 — European phishing amid Ukraine conflict.** Cisco Talos documented phishing campaigns against European entities — including Russian organizations — using lures masquerading as official EU reports on the Russia-Ukraine conflict, deploying PlugX and custom PUBLOAD stagers. (Cisco Talos)
- **2022-03 — TA416 increases operational tempo against European governments.** Proofpoint observed increased activity using web bugs for target profiling and PlugX delivery via Dropbox-hosted payloads with European Commission-themed lures. (Proofpoint)
- **2022-09 — BRONZE PRESIDENT targets government officials.** Secureworks reported campaigns using themed RAR archives and DLL side-loading to target government officials, deploying updated PlugX variants with anti-analysis features. (Secureworks)
- **2022-10 — Earth Preta spear-phishing governments worldwide.** Trend Micro documented large-scale campaigns (EARTH PRETA) targeting government entities across APAC with TONEINS, TONESHELL, and PUBLOAD malware families, leveraging Google Drive and Dropbox for malware hosting. (Trend Micro)
- **2023-02 — European Commission-themed PlugX delivery.** EclecticIQ documented Mustang Panda using European Commission-themed lures to deliver PlugX via DLL side-loading. (EclecticIQ)
- **2023-07 to 2024-12 — RedDelta Modified PlugX Infection Chain Operations (C0047).** Recorded Future tracked a sustained campaign using MSC files (GrimResource), MSI installers, Cloudflare CDN proxying, and geofenced payload delivery to install updated PlugX variants across multiple target regions. (Recorded Future CTA-CN-2025-0109)
- **2023-09 — Cyberespionage against Southeast Asian government.** Unit 42 documented an extensive intrusion into an SE Asian government network using TONESHELL, PlugX, ShadowPad, Cobalt Strike, and post-exploitation tools (Mimikatz, Impacket, AdFind, China Chopper), with lateral movement via Visual Studio Code tunneling. (Unit 42)
- **2024 — ASEAN Summit and multi-nation targeting.** Sustained campaigns against the Philippines, Myanmar, Taiwan, Pakistan, and attendees of the 2024 ASEAN-Australia Summit. IBM X-Force documented HIVE0154 targeting the U.S., Philippines, Pakistan, and Taiwan with PUBLOAD and CLAIMLOADER. (IBM X-Force / Unit 42)
- **2024-12 — U.S. DOJ PlugX seizure operation.** U.S. Department of Justice obtained a ninth search-and-seizure warrant for U.S. computers infected with Mustang Panda's PlugX malware, enabling law-enforcement removal. (DOJ)
- **2025 — Retooling post-PlugX disruption.** After international law enforcement neutralized widespread PlugX infrastructure in early 2025, Mustang Panda retooled with TONESHELL updates (Frankenstein variants), StarProxy, PAKLOG/CorKLOG keyloggers, SplatCloak EDR-evasion driver, and USB-based HIUPAN worm; continued targeting European government, maritime, and Southeast Asian organizations. (Zscaler / Trend Micro / Brandefense)
- **2025-06 — Tibetan community targeting.** IBM X-Force documented HIVE0154 shifting focus to the Tibetan diaspora community using PUBLOAD backdoor delivered via themed spearphishing. (IBM X-Force)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.001** — Acquire infrastructure: domains. Registered C2 domains prior to operations, including re-registration of expired domains during RedDelta PlugX campaigns.
- **T1583.006** — Acquire infrastructure: web services. Set up Dropbox and Google Drive accounts to host malicious payloads.
- **T1585.002** — Establish accounts: email accounts. Created fake Google accounts, Proton Mail accounts, and leveraged SMTP2Go for phishing campaigns.
- **T1586.002** — Compromise accounts: email accounts. Compromised legitimate email accounts for use in spearphishing operations.
- **T1587.001** — Develop capabilities: malware. Developed custom malware families including TONESHELL, PUBLOAD, PAKLOG, CorKLOG, SplatCloak, StarProxy, and customized PlugX variants (Hodur).
- **T1588.002** — Obtain capabilities: tool. Obtained publicly available tools (Cobalt Strike, Mimikatz, Impacket, AdFind, NBTscan) for intrusion activities.
- **T1588.003** — Obtain capabilities: code signing certificates. Used revoked code signing certificates for malicious payloads.
- **T1588.004** — Obtain capabilities: digital certificates. Obtained SSL/TLS certificates for C2 domains, including Cloudflare Origin CA certificates.
- **T1593** — Search open websites/domains. Conducted open-source research to identify victim information for crafting targeted phishing lures.
- **T1608** — Stage capabilities. Used attacker-controlled servers to validate tracking pixels and stage phishing infrastructure.
- **T1608.001** — Upload malware. Hosted malicious payloads on Dropbox, Google Drive, and attacker-controlled domains.

### Initial Access
- **T1566.001** — Spearphishing attachment. Primary initial-access vector: weaponized RAR/ZIP archives, LNK files, MSC files, and Office documents containing themed decoy content with DLL side-loading payloads. Themes tailored to victims (government policy documents, EU reports, religious-affairs memos, military briefings).
- **T1566.002** — Spearphishing link. Distributed links directing victims to malicious archives hosted on Google Drive/Dropbox or HTML files performing User-Agent fingerprinting to deliver MSC files.
- **T1598.003** — Phishing for information: spearphishing link. Delivered web bugs (tracking pixels) to profile intended targets before payload delivery.
- **T1204.001** — User execution: malicious link. Sent links directing victims to Google Drive folders or webpages with JavaScript that downloads malicious payloads.
- **T1204.002** — User execution: malicious file. Relied on victims opening malicious LNK files (disguised with PDF icons), RAR self-extracting archives, and Office documents containing VBA macros.
- **T1091** — Replication through removable media. PlugX variant (HIUPAN) spreads through USB drives, creating hidden `RECYCLE.BIN` folders on removable media — critical for air-gapped network access.
- **T1557** — Adversary-in-the-middle. Leveraged captive portal hijack redirecting victims to webpages prompting download of malicious payloads.
- **T1203** — Exploitation for client execution. Exploited CVE-2017-0199 in Microsoft Word; used GrimResource technique via crafted MSC files for arbitrary code execution.

### Execution
- **T1059** — Command and scripting interpreter. Used meterpreter shellcode.
- **T1059.001** — PowerShell. Malicious PowerShell scripts for execution; LNK files executing PowerShell commands leading to PlugX installation.
- **T1059.003** — Windows command shell. Executed HTA files via `cmd.exe`; batch scripts for collection; used `cmd.exe /c ping.exe 8.8.8.8 -n 70&&` delay-execution chains.
- **T1059.005** — Visual Basic. VBScript components embedded in LNK files; VBA macros in malicious documents; `autorun.vbs` persistence scripts.
- **T1059.007** — JavaScript. JavaScript payloads executed via `wscript.exe`.
- **T1047** — Windows Management Instrumentation. Executed PowerShell scripts via WMI.
- **T1129** — Shared modules. Used `LoadLibrary` to dynamically load DLLs.
- **T1106** — Native API. Extensive use of Windows API calls during execution and defense evasion (CreateProcess, VirtualAlloc, WriteProcessMemory).

### Persistence
- **T1547.001** — Registry Run keys / Startup folder. Created Run keys (`HKLM\...\Run\AdobelmdyU`, `HKCU\...\Run`) with legitimate-sounding names (e.g., `OneNote Update`) pointing to executables that side-load malicious DLLs.
- **T1053.005** — Scheduled task. Created scheduled tasks to execute malware, maintain persistence, and create reverse shells.
- **T1546.003** — WMI event subscription. Custom ORat tool uses WMI event consumers for persistence.
- **T1505.003** — Web shell. Used China Chopper web shells to maintain access to compromised environments.

### Privilege Escalation
- **T1574.001** — DLL search-order hijacking. **Signature technique**: abuses legitimately signed executables (Adobe, Microsoft Office, antivirus agents, `inkform.exe`, `ExcelRepairToolboxLauncher.exe`) to side-load malicious DLLs — the defining delivery mechanism for PlugX, TONESHELL, PUBLOAD, and other payloads.
- **T1574.005** — Executable installer file permissions weakness. Leveraged legitimate software installers (Setup Factory `IRSetup.exe`) to drop and execute payloads.

### Defense Evasion
- **T1027** — Obfuscated files or information. Delivered payloads hidden in archives with encoding; used opaque predicates to hinder analysis.
- **T1027.007** — Dynamic API resolution. Obfuscated Windows API function calls using unique names or hashes.
- **T1027.012** — LNK icon smuggling. Used LNK files displaying PDF/document icons to disguise malicious scripts.
- **T1027.013** — Encrypted/encoded file. Stored installation payloads as encrypted files in hidden folders (RC4, XOR, AES encryption).
- **T1027.016** — Junk code insertion. Inserted junk code within DLL files to hinder static analysis.
- **T1036.004** — Masquerade task or service. Masqueraded Registry run keys as legitimate service names (e.g., `OneNote Update`).
- **T1036.005** — Match legitimate resource name or location. Disguised payloads as `adobeupdate.dat`, `PotPlayerDB.dat`, `OneDrive.exe`, `AdobePlugins.exe`.
- **T1036.007** — Double file extension. Used additional filename extensions to hide true file type.
- **T1036.008** — Masquerade file type. Masqueraded malicious executables as legitimate document files.
- **T1553.002** — Code signing. Used valid and revoked digital signatures on legitimate executables to evade detection during DLL side-loading.
- **T1140** — Deobfuscate/decode files or information. Decrypted payloads prior to execution using RC4 encryption.
- **T1622** — Debugger evasion. Embedded misleading debug strings; called `CheckRemoteDebuggerPresent` API and exits if debugger detected.
- **T1678** — Delay execution. Delayed payload execution using `ping 8.8.8.8 -n 70` echo requests before executing legitimate executables.
- **T1480** — Execution guardrails. Used Cloudflare geofencing to limit payload downloads to target regions; TONESHELL checks process name/path before triggering custom exception handlers.
- **T1070** — Indicator removal. Deleted registry keys storing persistence data.
- **T1070.004** — File deletion. Deleted tools, files, and killed processes after objectives reached.
- **T1070.006** — Timestomp. Modified file timestamps from export address tables to obscure creation times.
- **T1218.004** — InstallUtil. Used `InstallUtil.exe` to execute malicious Cobalt Strike Beacon stager.
- **T1218.005** — Mshta. Used `mshta.exe` to launch collection scripts.
- **T1218.007** — Msiexec. Initial payloads downloaded Windows Installer MSI files to drop follow-on PlugX components.
- **T1218.014** — MMC. Used crafted MSC files executed via MMC to run PowerShell commands (GrimResource).
- **T1564.001** — Hidden files and directories. Created hidden `RECYCLE.BIN` folders on USB drives; modified file attributes to `hidden` and `system`.
- **T1001.003** — Data obfuscation: protocol impersonation. Used FakeTLS with TLS record headers in network packets to blend with legitimate traffic.
- **T1205** — Traffic signaling. Used magic values in C2 communications (`17 03 03` or `46 77 4d`); only executes in memory when response packets match.
- **T1072** — Software deployment tools. Leveraged legitimate antivirus agents, security services, and app development tools to execute scripts and side-load DLLs.

### Credential Access
- **T1003** — OS credential dumping. Used "Hdump" to dump credentials from memory.
- **T1003.001** — LSASS memory. Harvested credentials from LSASS process memory using Mimikatz.
- **T1003.003** — NTDS. Used `vssadmin` to create volume shadow copies and retrieve `NTDS.dit`; used `reg save` on SYSTEM hive to extract NTDS.
- **T1003.006** — DCSync. Leveraged Mimikatz DCSync to replicate credentials from domain controllers.

### Discovery
- **T1087.002** — Account discovery: domain account. Used AdFind to enumerate domain users.
- **T1069.002** — Permission groups discovery: domain groups. Used AdFind to enumerate domain groups.
- **T1083** — File and directory discovery. Searched entire systems for DOC, DOCX, PPT, PPTX, XLS, XLSX, and PDF files.
- **T1057** — Process discovery. Used `tasklist /v`; TONESHELL checks process name and path for environment validation.
- **T1046** — Network service discovery. Used NBTscan to scan IP networks.
- **T1018** — Remote system discovery. Used AdFind to query Active Directory for computers; used SharpNBTScan.
- **T1082** — System information discovery. Used `systeminfo`; captured OS type via User-Agent analysis.
- **T1016** — System network configuration discovery. Used `ipconfig`, `arp`, and SharpNBTScan.
- **T1049** — System network connections discovery. Used `netstat -ano`.
- **T1518** — Software discovery. Searched for `InstallUtil.exe` and its version.
- **T1654** — Log enumeration. Used Wevtutil to gather Windows Security Event Logs.

### Lateral Movement
- **T1091** — Replication through removable media. PlugX USB worm variant (HIUPAN) spreads across USB-connected systems.
- **T1572** — Protocol tunneling. Used OpenSSH (`sshd.exe`) to execute commands, transfer files, and spread across environments over SMB port 445.
- **T1219.001** — Remote access tools: IDE tunneling. Abused Visual Studio Code `code.exe tunnel` command with established GitHub accounts for persistent remote access.
- **T1219.002** — Remote access tools: remote desktop software. Installed TeamViewer on targeted systems.
- **T1176.002** — Software extensions: IDE extensions. Leveraged VSCode's embedded reverse shell feature via `code.exe tunnel`.

### Collection
- **T1119** — Automated collection. Custom batch scripts to collect files automatically.
- **T1560.001** — Archive via utility. Used WinRAR `rar.exe` to create password-protected archives; also used TONESHELL, RemCom, and Impacket to execute WinRAR for archival.
- **T1560.003** — Archive via custom method. Encrypted documents with RC4 prior to exfiltration.
- **T1074.001** — Local data staging. Stored collected credential files in `c:\windows\temp`; stored documents in hidden USB folders.

### Command & Control
- **T1071.001** — Web protocols. HTTP POST requests for C2 communication (PlugX, PUBLOAD, TONESHELL, Cobalt Strike).
- **T1095** — Non-application layer protocol. TCP-based reverse shells via `cmd.exe`; TCP 5000 for administrative C2 node communication.
- **T1573.001** — Symmetric cryptography. Encrypted C2 channels with RC4, AES, XOR (0x5a), and LZO compression.
- **T1090** — Proxy. Proxied C2 communications through Cloudflare CDN; StarProxy provides internal proxy capability.
- **T1102** — Web service. Used Dropbox and Google Drive URLs to deliver PlugX variants and host C2 infrastructure.
- **T1105** — Ingress tool transfer. Downloaded additional executables post-compromise; leveraged Visual Studio Code and Dev Tunnels (`DevTunnel.exe`) for tool propagation.
- **T1001.003** — Protocol impersonation. FakeTLS — TLS record headers impersonating legitimate TLS protocol versions.

### Exfiltration
- **T1041** — Exfiltration over C2 channel. Exfiltrated stolen data directly to C2 servers.
- **T1048.003** — Exfiltration over unencrypted non-C2 protocol. Used FTP to exfiltrate archive files.
- **T1052.001** — Exfiltration over USB. Customized PlugX variant exfiltrated documents from air-gapped networks via USB drives.
- **T1567.002** — Exfiltration to cloud storage. Exfiltrated archived files to Dropbox using `curl`.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| PlugX / Korplug (incl. Hodur variant) | S0013 | Modular Windows RAT (DLL side-loading, USB worm, keylogging, screen capture) | Custom |
| TONESHELL | S1239 | Multi-variant backdoor/loader with anti-analysis, FakeTLS C2 | Custom |
| PUBLOAD | S1228 | First-stage stager/downloader with environment-keyed execution | Custom |
| HIUPAN | S1230 | USB worm for propagation via removable media | Custom |
| BOOKWORM | S1226 | Modular implant (keylogging, clipboard, FakeTLS C2) | Custom |
| StarProxy | S1227 | Internal network proxy with FakeTLS and DLL side-loading | Custom |
| PAKLOG | S1233 | Keylogger/clipboard monitor | Custom |
| CorKLOG | S1235 | Encrypted keylogger with service persistence | Custom |
| SplatCloak | S1234 | Kernel-mode driver for EDR/AV evasion | Custom |
| SplatDropper | S1232 | Dropper for SplatCloak driver payloads | Custom |
| CLAIMLOADER | S1236 | Loader with COM-based execution and DLL side-loading | Custom |
| CANONSTAGER | S1237 | Stager with thread-local-storage injection | Custom |
| STATICPLUGIN | S1238 | COM-based loader disguised as document files | Custom |
| RCSession | S0662 | Backdoor with UAC bypass and fileless storage | Custom |
| PoisonIvy | S0012 | Legacy Windows RAT (DLL injection, rootkit) | Custom (older) |
| ShadowPad | S0596 | Modular backdoor platform (shared across Chinese APTs) | Custom (shared) |
| ORat | — | Custom RAT with WMI event-subscription persistence | Custom |
| Cobalt Strike | S0154 | Post-exploitation framework / Beacon | Public |
| China Chopper | S0020 | Web shell | Public |
| Mimikatz | S0002 | Credential dumping | Public |
| Impacket | S0357 | Network protocol / lateral-movement toolkit | Public |
| AdFind | S0552 | Active Directory enumeration | Public |
| NBTscan | S0590 | NetBIOS scanner | Public |
| Wevtutil | S0645 | Windows Event Log utility | Built-in |
| TeamViewer | — | Remote desktop software | Public (Commercial) |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never deploy USB-propagation worms or kernel-mode drivers outside an explicitly sanctioned, isolated lab.

Map Mustang Panda's signature plays to Decepticon's own capabilities:

- **Initial access — themed spearphishing (T1566.001, T1566.002, T1204.002).** Use the phishing skill to craft **themed lure documents** matching the target's geopolitical context (ASEAN policy briefs, EU diplomatic memos, military situational reports, religious-affairs documents). Package as RAR/ZIP archives or LNK files with decoy PDFs. Host payloads on Google Drive or Dropbox (T1583.006, T1608.001) to emulate Mustang Panda's cloud-hosted delivery. Add **web bugs** (T1598.003) to profile which recipients open the lure before delivering the payload.
- **DLL side-loading chain (T1574.001, T1553.002).** This is Mustang Panda's **defining technique**. Use the payload-builder skill to prepare a triad: (1) a legitimately signed executable (Adobe updater, `inkform.exe`, or antivirus agent), (2) a malicious DLL matching the expected side-load name, and (3) an encrypted payload blob (`.dat`). The signed EXE loads the DLL, which decrypts and executes the payload in memory. Vary the signed EXE across engagements to test detection coverage.
- **USB propagation (T1091, T1052.001).** In an isolated lab, emulate the HIUPAN/PlugX USB worm by creating a hidden `RECYCLE.BIN` directory on removable media containing the side-loading triad plus an autorun trigger. Test whether endpoint detection catches the worm's USB-based spread and hidden-folder creation.
- **Execution & evasion (T1059.001, T1059.003, T1218.014, T1678).** Emulate the GrimResource chain: craft an MSC file that, when opened via MMC, executes a PowerShell command to download an MSI installer. Use **delay execution** via `ping -n 70` chains before launching the legitimate side-loading executable. Test `mshta.exe` and `InstallUtil.exe` proxy execution paths.
- **Persistence (T1547.001, T1053.005, T1546.003).** Create Registry Run keys with legitimate-sounding names (`OneNote Update`, `AdobelmdyU`) pointing to the side-loading executable. Create scheduled tasks for backup persistence. Where testing WMI depth, set up WMI event subscriptions emulating ORat's consumer-based persistence.
- **Credential access (T1003.001, T1003.003, T1003.006).** Drive the AD/credential skill with **Mimikatz** for LSASS dump, DCSync, and NTDS.dit extraction via `vssadmin` shadow copies — matching Mustang Panda's documented post-compromise credential-harvesting pattern.
- **Lateral movement — VSCode tunneling (T1219.001, T1176.002, T1572).** Emulate the Stately Taurus technique of using `code.exe tunnel` with a GitHub account for persistent C2-like access. Combine with OpenSSH tunneling over SMB (port 445) for internal pivoting. This novel technique is increasingly common in Mustang Panda's 2023-2024 operations.
- **C2 (T1071.001, T1095, T1573.001, T1090, T1001.003).** Use **Sliver or Cobalt Strike** (c2 skill) over HTTPS as the primary channel. Implement **FakeTLS** by adding TLS record headers (`17 03 03`) to non-TLS TCP traffic to emulate TONESHELL/StarProxy's protocol impersonation. Proxy through Cloudflare CDN (T1090) to replicate RedDelta's infrastructure pattern. Use RC4 encryption for the C2 channel.
- **Collection & exfil (T1083, T1560.001, T1041, T1567.002).** Search for document files (DOC/DOCX/PPT/PPTX/XLS/XLSX/PDF) matching Mustang Panda's collection pattern. Archive with WinRAR `rar.exe` using password protection. Exfiltrate over the C2 channel or via `curl` to Dropbox/Google Drive to replicate the cloud-exfil pattern. Stage in `c:\windows\temp` before exfil.
- **Anti-analysis features (T1622, T1027.007, T1027.016, T1480).** If testing detection depth, include debugger-evasion checks (`CheckRemoteDebuggerPresent`), dynamic API resolution via hashed function names, junk code insertion, and geofencing/environment-keying guardrails.

## Detection & defense

- **DLL side-loading (T1574.001):** Monitor for known-abused legitimate executables (Adobe, ESET, Office utilities) spawning or loading DLLs from non-standard paths (`%TEMP%`, `%APPDATA%`, USB drives); alert on unsigned DLLs loaded by signed executables; deploy application-control/allowlisting (WDAC/AppLocker) to block unapproved DLL loads.
- **Spearphishing & LNK/MSC lures (T1566.001, T1027.012, T1218.014):** Block macro execution in Office via GPO; monitor for LNK files spawning PowerShell/cmd; alert on MMC (`mmc.exe`) executing MSC files from user-writable paths; strip or quarantine archive attachments (RAR/ZIP) containing executables.
- **USB propagation (T1091):** Enforce removable-media policies via GPO/Intune; monitor for creation of hidden `RECYCLE.BIN` directories on removable drives; alert on `attrib.exe +h +s` usage; block autorun on removable media.
- **PlugX/TONESHELL persistence (T1547.001, T1053.005):** Monitor Registry Run keys for entries pointing to executables in `%TEMP%`, `%APPDATA%`, or non-standard paths; hunt for scheduled tasks creating reverse shells or referencing `code.exe tunnel`; audit WMI event subscriptions.
- **Credential dumping (T1003.001, T1003.003, T1003.006):** Enable LSA protection (RunAsPPL) and Credential Guard; alert on LSASS handle access, `vssadmin create shadow` or `ntdsutil` invocations, and DCSync replication from non-DC accounts; monitor for `reg save` targeting SAM/SYSTEM/SECURITY hives.
- **VSCode tunneling (T1219.001):** Monitor for `code.exe tunnel` or `DevTunnel.exe` execution; block or alert on outbound connections to `*.devtunnels.ms` and `*.vscode.dev`; restrict Visual Studio Code installation to authorized developer systems.
- **FakeTLS / protocol impersonation (T1001.003, T1205):** Deploy TLS inspection that validates actual TLS handshakes; alert on connections with TLS record headers (`17 03 03`) that fail proper TLS negotiation; monitor for unusual traffic patterns on non-standard ports.
- **Cloud-service abuse (T1102, T1567.002, T1583.006):** Monitor for bulk uploads to Google Drive, Dropbox, or other cloud storage from non-standard processes (especially `curl.exe`); restrict cloud-storage application access via CASB; alert on new OAuth app consent grants.
- **Exfiltration (T1041, T1048.003, T1052.001):** DLP monitoring for password-protected archive creation (WinRAR `rar.exe a -hp`); monitor FTP client usage; alert on large data transfers to external IPs from staging directories (`c:\windows\temp`).
- **Indicator removal (T1070.004, T1070.006):** Enable file-system auditing and Sysmon with `FileDelete` events; monitor for timestomping patterns; alert on process/file deletion immediately following execution.

## Sources

- https://attack.mitre.org/groups/G0129/
- https://www.crowdstrike.com/blog/meet-crowdstrikes-adversary-of-the-month-for-june-mustang-panda/
- https://www.secureworks.com/research/bronze-president-targets-ngos
- https://www.secureworks.com/blog/bronze-president-targets-russian-speakers-with-updated-plugx
- https://www.secureworks.com/blog/bronze-president-targets-government-officials
- https://go.recordedfuture.com/hubfs/reports/cta-2020-0728.pdf
- https://go.recordedfuture.com/hubfs/reports/cta-cn-2025-0109.pdf
- https://www.proofpoint.com/us/blog/threat-insight/ta416-goes-ground-and-returns-golang-plugx-malware-loader
- https://www.proofpoint.com/us/blog/threat-insight/good-bad-and-web-bug-ta416-increases-operational-tempo-against-european
- https://blog.talosintelligence.com/mustang-panda-targets-europe/
- https://www.trendmicro.com/en_us/research/22/k/earth-preta-spear-phishing-governments-worldwide.html
- https://www.trendmicro.com/en_us/research/24/i/earth-preta-new-malware-and-strategies.html
- https://www.trendmicro.com/en_us/research/25/b/earth-preta-mixes-legitimate-and-malicious-components-to-sidestep-detection.html
- https://unit42.paloaltonetworks.com/stately-taurus-attacks-se-asian-government/
- https://unit42.paloaltonetworks.com/stately-taurus-abuses-vscode-southeast-asian-espionage/
- https://unit42.paloaltonetworks.com/stately-taurus-uses-bookworm-malware/
- https://blog.eclecticiq.com/mustang-panda-apt-group-uses-european-commission-themed-lure-to-deliver-plugx-malware
- https://www.anomali.com/blog/china-based-apt-mustang-panda-targets-minority-groups-public-and-private-sector-organizations
- https://www.welivesecurity.com/2022/03/23/mustang-panda-hodur-old-tricks-new-korplug-variant/
- https://www.zscaler.com/blogs/security-research/latest-mustang-panda-arsenal-toneshell-and-starproxy-p1
- https://www.zscaler.com/blogs/security-research/latest-mustang-panda-arsenal-paklog-corklog-and-splatcloak-p2
- https://research.checkpoint.com/2023/the-dragon-who-sold-his-camaro-analyzing-custom-router-implant/
- https://www.ibm.com/think/x-force/hive0154-mustang-panda-shifts-focus-tibetan-community-deploy-pubload-backdoor
- https://www.ibm.com/think/x-force/hive0154-targeting-us-philippines-pakistan-taiwan
- https://cloud.google.com/blog/topics/threat-intelligence/prc-nexus-espionage-targets-diplomats
- https://www.avira.com/en/blog/new-wave-of-plugx-targets-hong-kong
- https://www.justice.gov/archives/opa/media/1384136/dl
- https://csirt-cti.net/2024/01/23/stately-taurus-targets-myanmar/
- https://www.mcafee.com/enterprise/en-us/assets/reports/rp-operation-dianxun.pdf
- https://www.attackiq.com/2023/03/23/emulating-the-politically-motivated-chinese-apt-mustang-panda/
