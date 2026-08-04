---
name: turla-venomous-bear
description: "Adversary-emulation profile for Turla (G0010 / Venomous Bear / Secret Blizzard / Waterbug / KRYPTON / Snake), Russia's FSB Center 16 cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Turla, Venomous Bear, Secret Blizzard, Waterbug, KRYPTON, Snake, IRON HUNTER, BELUGASTURGEON, WhiteBear, FSB Center 16, G0010, Russian FSB espionage emulation, Snake rootkit, Uroburos, ComRAT, Carbon framework, Kazuar backdoor, LightNeuron Exchange, Penquin Linux, TinyTurla, satellite C2, watering hole attacks, hijacking other APT infrastructure, DNS-over-HTTPS C2, Gmail C2"
  tags: turla, venomous-bear, secret-blizzard, waterbug, krypton, snake, fsb, russia, espionage, nation-state, g0010, adversary-emulation, mitre-attack
  mitre_attack: T1583.006, T1584.003, T1584.004, T1584.006, T1587.001, T1588.001, T1588.002, T1189, T1566.001, T1566.002, T1204.001, T1204.002, T1078.003, T1059.001, T1059.003, T1059.004, T1059.005, T1059.006, T1059.007, T1047, T1106, T1569.002, T1547.001, T1547.004, T1546.003, T1546.013, T1546.015, T1543.003, T1505.002, T1053.003, T1053.005, T1137.006, T1574.001, T1068, T1055, T1055.001, T1134.002, T1553.006, T1014, T1027, T1027.002, T1027.005, T1027.009, T1027.010, T1027.011, T1027.013, T1036.004, T1036.005, T1140, T1112, T1070.004, T1070.006, T1070.008, T1564.004, T1564.005, T1564.012, T1218.011, T1685, T1620, T1497.003, T1001.001, T1001.002, T1001.003, T1110, T1555.004, T1003.001, T1003.002, T1003.004, T1003.006, T1056.001, T1558.001, T1558.002, T1550.002, T1087.001, T1087.002, T1083, T1615, T1120, T1069.001, T1069.002, T1057, T1012, T1018, T1518.001, T1082, T1016, T1016.001, T1049, T1007, T1124, T1201, T1135, T1033, T1010, T1046, T1680, T1021.002, T1570, T1005, T1025, T1213.006, T1560.001, T1119, T1074.001, T1113, T1125, T1114.001, T1114.002, T1071.001, T1071.002, T1071.003, T1071.004, T1102, T1102.002, T1573.001, T1573.002, T1090, T1090.001, T1090.003, T1095, T1572, T1008, T1104, T1105, T1132.001, T1132.002, T1029, T1030, T1205, T1205.002, T1041, T1567.002, T1048.003, T1020, T1485
---

# Turla (Venomous Bear, Secret Blizzard, Waterbug, KRYPTON, Snake) — Adversary Emulation Profile

Turla (MITRE ATT&CK **G0010**) is one of the most sophisticated and long-running cyber-espionage groups in existence, attributed to Russia's Federal Security Service (FSB) **Center 16**, operating since at least 2004. Turla has compromised victims in over 50 countries across government, diplomatic, military, defense, education, research, and pharmaceutical sectors. The group is characterized by extraordinary technical depth — from the Snake/Uroburos kernel rootkit and satellite-based C2 hijacking to steganographic email backdoors and the audacious practice of hijacking other nation-state APTs' infrastructure. Turla's tooling spans Windows, Linux, and macOS, with a malware ecosystem (Snake, Carbon, ComRAT, Kazuar, LightNeuron, Penquin, TinyTurla, Lunar toolset) unmatched in breadth and longevity. The 2023 FBI Operation MEDUSA takedown of the Snake peer-to-peer network — spanning 50+ countries over nearly 20 years — underscored the global scale of Turla's operations.

## Attribution & motivation

- **Sponsor / nation:** Russian Federation — Federal Security Service (FSB), **Center 16**. CISA has formally attributed Turla / Secret Blizzard to FSB Center 16. The 2023 joint FBI/CISA/NSA advisory (AA23-129A) detailed the Snake malware infrastructure and attributed it to FSB officers. The NSA/NCSC 2019 joint advisory documented Turla's hijacking of Iranian APT infrastructure and attributed it to the same FSB unit.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — diplomatic, military, political, and scientific intelligence aligned with Russian state interests. Turla is a pure espionage actor with no documented financially motivated or destructive campaigns; its sole objective is persistent, covert access to high-value targets for long-term intelligence gathering.
- **Attribution confidence:** **High.** Backed by U.S. DOJ court filings (Operation MEDUSA), joint CISA/NSA/FBI advisories, NSA/NCSC joint attributions, and consistent named vendor reporting (ESET, Kaspersky, Microsoft, Symantec/Broadcom, Palo Alto Unit 42, Mandiant, Cisco Talos, Accenture).

## Targeting

- **Sectors:** Government and diplomatic bodies (especially ministries of foreign affairs, embassies); military and defense; education and research institutions; pharmaceutical companies; think tanks and NGOs; media.
- **Regions:** Primary focus on **Europe** (Eastern and Western — Germany, France, the Baltics, Balkans, Caucasus, Ukraine) and **Central Asia**. Significant targeting of **Middle East, South Asia** (via hijacked APT infrastructure), and **NATO member states** broadly. Operations documented in 50+ countries worldwide.
- **Victim profile:** Entities whose networks yield diplomatic, military, and political intelligence — embassies, foreign ministries, parliaments, defense agencies, and academic research institutions. Turla favors long-dwell-time persistence in high-value networks over smash-and-grab operations.

## Notable campaigns

- **2008 — Agent.BTZ / Operation Buckshot Yankee.** USB worm (Agent.BTZ) spread via infected flash drive at a U.S. Central Command base in the Middle East, infecting approximately 300,000 DoD computers across classified and unclassified networks. Described as the "worst breach of U.S. military computers in history," it led to a 14-month cleanup and the creation of U.S. Cyber Command. Kaspersky Lab later documented shared XOR keys between Agent.BTZ and Turla malware. (wikipedia.org / securelist.com)
- **2014-08 — Epic Turla (Snake/Uroburos discovery).** Kaspersky's Global Research team publicly detailed the Epic Turla operation, revealing the Snake/Uroburos rootkit framework and documenting compromises across 45+ countries targeting government and diplomatic entities. The research established Turla as one of the most advanced persistent threats operating at the time. (securelist.com)
- **2015-09 — Satellite Turla (DVB-S C2 hijacking).** Kaspersky revealed that Turla had been hijacking unencrypted DVB-S satellite internet downlinks — primarily from Middle Eastern and African ISPs — to mask C2 server locations. Evidence suggested the technique had been in use since approximately 2007. The method provided exceptional anonymity by abusing legitimate satellite subscribers' IP addresses as C2 endpoints. (securelist.com / securityweek.com)
- **2019-05 — LightNeuron Exchange backdoor.** ESET documented LightNeuron, a backdoor deployed as a Microsoft Exchange Transport Agent, enabling Turla to intercept, modify, and exfiltrate email traffic in real time. The implant used steganography to embed C2 commands within PDF and JPEG email attachments. Deployed against ministries of foreign affairs in Eastern Europe and a Central Asian diplomatic entity. (welivesecurity.com / ESET)
- **2019-10 — Hijacking Iranian APT (OilRig) infrastructure.** Joint NSA/NCSC advisory revealed that Turla had compromised the C2 infrastructure of the Iranian APT group OilRig (APT34), using their VPS servers and even deploying their own implants through OilRig's existing access to victims. This marked the first publicly documented case of one nation-state APT parasitizing another's operations. (media.defense.gov / NSA-NCSC advisory)
- **2020-05 — ComRAT v4 with Gmail C2.** ESET documented ComRAT v4, the latest evolution of the decade-old ComRAT/Agent.BTZ lineage, now using the Gmail web interface as a C2 channel. The backdoor received commands and exfiltrated data via email attachments, bypassing network security controls. Targets included foreign ministries in Eastern Europe and a Caucasus parliament. (welivesecurity.com / ESET)
- **2021-09 — TinyTurla.** Cisco Talos disclosed TinyTurla, a minimal backdoor installed as a Windows service disguised as a legitimate system component. Designed as a fallback access mechanism that persists even when primary implants are detected and removed. Deployed against targets in the U.S., Germany, and Afghanistan. (blog.talosintelligence.com)
- **2023-05 — Operation MEDUSA (Snake infrastructure takedown).** FBI-led Operation MEDUSA disabled Turla's Snake malware peer-to-peer network using the custom-built PERSEUS tool, which issued self-destruct commands mimicking Snake's own session authentication protocol. The operation, authorized by a federal search warrant, disrupted Snake infrastructure across 50+ countries that had been operational for nearly 20 years. (justice.gov / CISA AA23-129A)
- **2024-12 — Hijacking Pakistani APT (Storm-0156) infrastructure.** Microsoft and Lumen Black Lotus Labs revealed that Turla (Secret Blizzard) had compromised 33 C2 servers belonging to Pakistani APT Storm-0156 since late 2022. Turla commandeered Storm-0156's CrimsonRAT backdoors to deploy its own TwoDash and Statuezy implants within Afghan government networks (Ministry of Foreign Affairs, intelligence directorate) and accessed CrimsonRAT infections on targets in India. This marked the fourth documented instance of Turla parasitizing another threat actor's infrastructure. (microsoft.com / cyberscoop.com)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.006** — Acquire infrastructure (web services): created accounts on Dropbox, GitHub, Pastebin, and Google (Gmail) for C2 communications and data exfiltration.
- **T1584.003** — Compromise infrastructure (VPS): hijacked the VPS infrastructure of compromised Iranian APT OilRig/APT34 for Turla's own operations.
- **T1584.004** — Compromise infrastructure (server): extensively used compromised servers — particularly WordPress sites — as C2 relay nodes.
- **T1584.006** — Compromise infrastructure (web services): co-opted compromised WordPress sites for C2 hosting.
- **T1587.001** — Develop capabilities (malware): developed an extensive custom malware ecosystem spanning two decades (Snake, Carbon, ComRAT, Kazuar, LightNeuron, Penquin, Gazer, Mosquito, TinyTurla, Lunar toolset, Epic, HyperStack, Crutch, KOPILUWAK).
- **T1588.001** — Obtain capabilities (malware): obtained and reused malware from compromised threat actors, notably commandeering OilRig tools and Storm-0156's CrimsonRAT.
- **T1588.002** — Obtain capabilities (tool): obtained and customized publicly available tools including Mimikatz, Metasploit/Meterpreter, PowerShell Empire, PowerSploit, PsExec, and NBTscan.

### Initial Access
- **T1189** — Drive-by compromise: signature Turla technique; conducted watering hole attacks on government and embassy websites to deliver exploits and backdoors (Epic Turla campaign, ComRAT delivery).
- **T1566.001** — Spearphishing attachment: delivered weaponized documents and archives (KOPILUWAK JavaScript dropper via spearphishing attachments).
- **T1566.002** — Spearphishing link: sent phishing emails with links to seemingly legitimate domains (e.g., fake Adobe download pages) to trick targets into downloading Mosquito installer malware.
- **T1204.001 / T1204.002** — User execution (malicious link / malicious file): relied on user execution of phishing links and weaponized document files to establish initial footholds.
- **T1078.003** — Valid accounts (local): abused local accounts with reused passwords across victim networks for initial and sustained access.

### Execution
- **T1059.001** — PowerShell: extensively used PowerShell for post-compromise operations, including Empire PSInject for reflective payload injection, PowerSploit's `Out-EncryptedScript.ps1` for encrypted payloads, and custom PowerShell backdoors with RPC-based C2. ESET documented Turla's comprehensive PowerShell-based toolchain in 2019.
- **T1059.003** — Windows Command Shell: RPC backdoors and multiple malware families (ComRAT, Uroburos, TinyTurla, LunarWeb, LightNeuron, Kazuar) used `cmd.exe` for command execution.
- **T1059.004** — Unix shell: Kazuar (multiplatform) and Penquin (Linux backdoor) executed commands via Unix shell on Linux targets.
- **T1059.005** — Visual Basic: used VBS scripts in operations (Waterbug/Symantec reporting) and LunarMail Outlook add-in backdoor used VBA.
- **T1059.006** — Python: IronNetInjector toolchain used IronPython scripts to drop and execute payloads.
- **T1059.007** — JavaScript: deployed various JavaScript-based backdoors (Mosquito installer, KOPILUWAK JavaScript reconnaissance tool).
- **T1047** — Windows Management Instrumentation: used WMI via LunarWeb, Kazuar, Mosquito, and Empire for execution and reconnaissance.
- **T1106** — Native API: RPC backdoors and multiple implants (Uroburos, Mosquito, TinyTurla, HyperStack) made direct Windows API calls for execution, AMSI bypasses, and IPC.
- **T1569.002** — Service execution: TinyTurla and Net utility used for executing payloads via Windows services.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: JavaScript backdoors set `HKLM\...\Run` keys; Metasploit shellcode executables saved to Startup folder; Gazer, Kazuar, and Mosquito used Run key persistence.
- **T1547.004** — Winlogon Helper DLL: established persistence via `HKCU\...\Winlogon` Shell value modifications (Mosquito installer, Gazer).
- **T1546.003** — WMI Event Subscription: PowerShell toolchain used WMI event filters and consumers for persistent backdoor activation.
- **T1546.013** — PowerShell Profile: modified PowerShell profiles to execute malicious payloads on interpreter startup, providing persistence through legitimate PowerShell usage.
- **T1546.015** — COM hijacking: ComRAT and Mosquito hijacked COM objects for persistence and execution.
- **T1543.003** — Windows service: Carbon, Kazuar, Uroburos/Snake, and TinyTurla installed as Windows services for persistent execution; TinyTurla masqueraded as a legitimate Windows Time service component.
- **T1505.002** — Transport Agent: LightNeuron installed as a Microsoft Exchange Transport Agent, intercepting all email traffic through the server — one of the most novel persistence mechanisms documented.
- **T1053.005** — Scheduled task: Carbon, ComRAT, Crutch, Gazer, and IronNetInjector used Windows scheduled tasks for periodic execution.
- **T1053.003** — Cron: Penquin Linux backdoor used cron jobs for persistence on Linux targets.
- **T1137.006** — Office add-ins: LunarLoader and LunarMail persisted as Outlook add-ins, executing whenever the Outlook application launched.
- **T1574.001** — DLL hijacking: Crutch backdoor abused DLL search-order hijacking for persistence and execution.

### Privilege Escalation
- **T1068** — Exploitation for privilege escalation: exploited VBoxDrv.sys driver vulnerabilities to achieve kernel-mode execution (AcidBox reporting by Unit 42).
- **T1055 / T1055.001** — Process injection / DLL injection: used PowerSploit's `Invoke-ReflectivePEInjection.ps1` for reflective PE injection; Metasploit reflective DLL injection for privilege escalation; IronNetInjector, Kazuar, Uroburos, Carbon, and Gazer used DLL injection.
- **T1134.002** — Access token manipulation (Create Process with Token): RPC backdoors impersonated or stole process tokens before executing commands.
- **T1553.006** — Code Signing Policy Modification: modified kernel memory variables to disable Driver Signature Enforcement after achieving kernel-mode privileges, enabling unsigned driver loading (Turla Driver Loader).

### Defense Evasion
- **T1014** — Rootkit: Uroburos/Snake operated as a kernel-mode rootkit with hidden filesystems, custom encrypted peer-to-peer networking, and covert protocol impersonation — active for nearly 20 years before the FBI disrupted it.
- **T1027 / T1027.002 / T1027.005** — Obfuscation / software packing / indicator removal from tools: Uroburos used software packing; Gazer versions had IoC strings (mutex names, named pipes) deliberately obfuscated between variants; Penquin removed identifiable strings.
- **T1027.009** — Embedded payloads: ComRAT and Uroburos embedded secondary payloads within their binaries.
- **T1027.010** — Command obfuscation: used salted 3DES encryption (via PowerSploit), random variable names, and base64 encoding to obfuscate PowerShell commands.
- **T1027.011** — Fileless storage: stored encrypted payloads in Windows Registry values (PowerShell backdoors, Mosquito, TinyTurla, Uroburos, ComRAT).
- **T1027.013** — Encrypted/encoded file: multiple families (Gazer, Mosquito, Penquin, LightNeuron, LunarWeb, LunarMail, IronNetInjector) used encrypted files for payload storage and transport.
- **T1036.004 / T1036.005** — Masquerading: TinyTurla masqueraded as a Windows Time service DLL (`w32time.dll`); LunarWeb components mimicked Zabbix agent logs; LightNeuron and Penquin matched legitimate resource names and locations.
- **T1140** — Deobfuscate/Decode: custom decryption routines pulled keys and salts from WMI filters or PowerShell profiles to decode encrypted payloads at runtime.
- **T1112** — Modify Registry: stored payloads, configuration data, and C2 parameters in Registry values across multiple malware families.
- **T1070.004 / T1070.006 / T1070.008** — Indicator removal: file deletion (multiple families); timestomping (Gazer, PowerStallion); clearing mailbox data (LunarMail removed evidence of C2 emails).
- **T1564.004** — NTFS file attributes: Gazer hid data in alternate NTFS data streams.
- **T1564.005** — Hidden file system: ComRAT and Uroburos/Snake maintained hidden virtual file systems for covert data storage.
- **T1564.012** — File/Path exclusions: LunarWeb installed files into directories excluded from antivirus scanning.
- **T1218.011** — Rundll32: Mosquito used Rundll32 for proxy execution of malicious DLLs.
- **T1685** — Disable or Modify Tools: PowerShell scripts patched the in-memory `amsi.dll` to bypass Windows AMSI (Antimalware Scan Interface).
- **T1620** — Reflective code loading: LunarLoader and Uroburos used reflective loading to execute payloads directly in memory.
- **T1497.003** — Virtualization/Sandbox evasion (time-based): LunarWeb used time-based checks to detect analysis environments.
- **T1001.001 / T1001.002 / T1001.003** — Data obfuscation: Uroburos injected junk data and used protocol impersonation (HTTP to masquerade raw TCP); LightNeuron, LunarWeb, and LunarMail used **steganography** to embed C2 commands in PDF and JPEG email attachments.

### Credential Access
- **T1110** — Brute force: attempted network authentication with predefined password lists using `net use` commands.
- **T1555.004** — Windows Credential Manager: gathered stored credentials from Windows Credential Manager.
- **T1003.001 / T1003.002 / T1003.004 / T1003.006** — OS credential dumping: used Mimikatz for LSASS memory dumping, SAM database extraction, LSA secrets access, and **DCSync** replication attacks to obtain domain credentials.
- **T1056.001** — Keylogging: Snake/Uroburos and Empire deployed keyloggers alongside primary implants to capture authentication credentials.
- **T1558.001 / T1558.002** — Kerberos ticket forging: used Mimikatz to generate **golden tickets** (domain-wide persistence) and **silver tickets** (service-specific access) via Empire/Mimikatz integration.
- **T1550.002** — Pass the hash: used Mimikatz for pass-the-hash lateral movement within compromised domains.

### Discovery
- **T1087.001 / T1087.002** — Account discovery (local/domain): enumerated accounts with `net user`, `net user /domain`; HyperStack, Epic, and Kazuar performed local account enumeration.
- **T1083** — File and directory discovery: surveyed `%TEMP%`, desktop, Program Files, and Recent directories; RPC backdoors searched for `lPH*.dll` pattern; multiple malware families perform targeted file discovery.
- **T1615** — Group Policy discovery: used `gpresult` to enumerate Group Policy configuration.
- **T1120** — Peripheral device discovery: used `fsutil fsinfo drives` to list connected drives.
- **T1069.001 / T1069.002** — Permission groups discovery: `net localgroup Administrators`, `net group "Domain Admins" /domain` for privilege mapping.
- **T1057** — Process discovery: `tasklist /v` and RPC backdoor enumeration of processes by open ports/named pipes; used across Carbon, Epic, Kazuar, Mosquito, LunarWeb, KOPILUWAK, PowerStallion, IronNetInjector.
- **T1012** — Query Registry: `reg query` for system enumeration; retrieved stored PowerShell payloads from Registry; checked null-session named pipe configurations.
- **T1018** — Remote system discovery: `net view`, `net view /DOMAIN`, `net group "Domain Computers" /domain`, `net group "Domain Controllers" /domain`, `net group "Exchange Servers" /domain` for network mapping.
- **T1518.001** — Security software discovery: enumerated security products and logging configurations to assess detection risk.
- **T1082** — System information discovery: `systeminfo`, `set` commands; used across Epic, Gazer, Kazuar, LightNeuron, LunarWeb, Penquin, Uroburos.
- **T1016 / T1016.001** — Network configuration / internet connection discovery: `arp -a`, `nbtstat -n`, `net config`, `ipconfig /all`, `route`, NBTscan, and `tracert` for network reconnaissance.
- **T1049** — System network connections discovery: `netstat -an`, `net use`, `net file`, `net session`; RPC backdoors enumerated TCP connections via `GetTcpTable2` API.
- **T1007** — System service discovery: `tasklist /svc` for service-to-process mapping.
- **T1124** — System time discovery: `net time` command.
- **T1201** — Password policy discovery: `net accounts`, `net accounts /domain`.
- **T1135** — Network share discovery: via KOPILUWAK, LunarWeb, Net utility, and Empire.
- **T1033** — System owner/user discovery: multiple families (Epic, Gazer, Kazuar, KOPILUWAK, LunarWeb, Mosquito, NBTscan) identified logged-in users and system owners.
- **T1010** — Application window discovery: Kazuar enumerated open application windows.
- **T1046** — Network service discovery: NBTscan for NetBIOS and network service enumeration.
- **T1680** — Local storage discovery: Epic, Kazuar, KOPILUWAK, and Penquin performed local storage device enumeration.

### Lateral Movement
- **T1021.002** — SMB/Windows Admin Shares: used `net use` for lateral connections and PsExec for remote service execution across internal networks.
- **T1570** — Lateral tool transfer: RPC backdoors transferred files between victim machines on the local network; PsExec used for lateral tool deployment.
- **T1550.002** — Pass the hash: Mimikatz-based pass-the-hash for domain-wide lateral movement.

### Collection
- **T1005** — Data from local system: RPC backdoors, Kazuar, KOPILUWAK, LightNeuron, TinyTurla, and Uroburos uploaded files from victim machines.
- **T1025** — Data from removable media: RPC backdoors and Crutch collected files from USB thumb drives; Uroburos targeted removable media.
- **T1213.006** — Data from information repositories (databases): used a custom .NET tool to collect documents from an organization's internal central database.
- **T1560.001** — Archive via utility: encrypted stolen USB drive files into RAR archives; LunarWeb used compression utilities for data archival.
- **T1119** — Automated collection: Crutch and LightNeuron performed automated file collection from local and removable storage.
- **T1074.001** — Local data staging: Carbon, KOPILUWAK, LightNeuron, Kazuar, Crutch, and LunarMail staged collected data locally before exfiltration.
- **T1113** — Screen capture: Kazuar and LunarMail captured screenshots for intelligence collection.
- **T1125** — Video capture: Kazuar included webcam video capture capability.
- **T1114.001 / T1114.002** — Email collection (local/remote): LunarMail collected local Outlook emails; LightNeuron intercepted and collected email traffic in transit through Exchange Transport Agent access.
- **T1056.001** — Keylogging: Snake and Empire keyloggers captured typed credentials and communications.

### Command & Control
- **T1071.001** — Web protocols (HTTP/HTTPS): primary C2 channel for most malware families (Carbon, ComRAT, Epic, Gazer, Kazuar, KOPILUWAK, LunarWeb, Mosquito, TinyTurla, Uroburos).
- **T1071.002** — File transfer protocols: Kazuar used FTP for C2 communications.
- **T1071.003** — Mail protocols: **signature Turla technique** — ComRAT v4 used the Gmail web interface for C2; LightNeuron and LunarMail used email (SMTP/IMAP) as C2 channels; Uroburos supported mail-protocol-based C2; CrowdStrike documented multiple backdoors communicating via email attachments.
- **T1071.004** — DNS: Uroburos/Snake included DNS-based C2 capabilities.
- **T1102 / T1102.002** — Web service / bidirectional communication: used Pastebin, Dropbox, GitHub, Google Apps Script, and OneDrive for C2 and data exfiltration; JavaScript backdoors used Google Apps Script as a full C2 server.
- **T1573.001 / T1573.002** — Encrypted channel (symmetric/asymmetric): Carbon, Gazer, LunarWeb, Uroburos used asymmetric (RSA) key exchange; Epic, Mosquito, Carbon used symmetric encryption (AES, 3DES, custom XOR-based schemes); Snake/Uroburos implemented custom encrypted P2P protocols.
- **T1090 / T1090.001 / T1090.003** — Proxy / internal proxy / multi-hop proxy: RPC backdoors included local UPnP proxies; TinyTurla and Kazuar compromised internal systems as proxy relays; Uroburos/Snake used **multi-hop P2P proxy chains** across compromised nodes in 50+ countries.
- **T1095** — Non-application layer protocol: Uroburos, Penquin, LunarMail, and Carbon used raw TCP/custom protocols for C2 communications.
- **T1572** — Protocol tunneling: Uroburos and LunarWeb tunneled C2 traffic through legitimate protocols.
- **T1008** — Fallback channels: Uroburos, Kazuar, TinyTurla, and Crutch implemented multiple fallback C2 channels for resilience.
- **T1104** — Multi-stage channels: Uroburos and LunarWeb used multi-stage C2 architecture with initial check-in servers routing to operational C2.
- **T1105** — Ingress tool transfer: Meterpreter shellcode download, tool deployment across all major families.
- **T1132.001 / T1132.002** — Data encoding (standard/non-standard): Kazuar and LunarWeb used base64 standard encoding; Uroburos used custom non-standard encoding for C2 data.
- **T1029** — Scheduled transfer: ComRAT, Crutch, Kazuar, LightNeuron, and TinyTurla scheduled data exfiltration at fixed intervals.
- **T1030** — Data transfer size limits: LunarWeb split exfiltration data into size-limited chunks.
- **T1205 / T1205.002** — Traffic signaling / socket filters: Penquin and Uroburos used **passive network implants** that listened for magic-packet triggers rather than actively beaconing — Penquin used BPF socket filters to detect activation packets, making the backdoor virtually invisible to network monitoring.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: primary exfil method for KOPILUWAK, LightNeuron, LunarMail, Penquin, TinyTurla, and Crutch.
- **T1567.002** — Exfiltration to cloud storage: Crutch used WebDAV to upload to cloud drives; ComRAT exfiltrated to OneDrive and 4shared; Turla operations leveraged Dropbox and GitHub for data staging.
- **T1048.003** — Exfiltration over unencrypted non-C2 protocol: Carbon exfiltrated data over alternate HTTP channels distinct from the primary C2.
- **T1020** — Automated exfiltration: Crutch and LightNeuron automated the exfiltration of collected files without operator interaction.

### Impact
- **T1485** — Data destruction: Kazuar includes a self-destruct capability that can wipe collected data and the malware itself to cover tracks.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| Uroburos / Snake | S0022 | **Kernel rootkit** + P2P C2 network (20-year lifespan) | Custom |
| Carbon | S0335 | Second-stage modular framework | Custom |
| ComRAT (Agent.BTZ lineage) | S0126 | Backdoor with Gmail web-UI C2 | Custom |
| Kazuar | S0265 | Multiplatform espionage backdoor (Windows/Linux) | Custom |
| LightNeuron | S0395 | Exchange Transport Agent backdoor (steganographic C2) | Custom |
| Penquin | S0587 | Linux backdoor (passive, BPF-based activation) | Custom |
| Gazer (WhiteBear) | S0168 | Second-stage Windows backdoor | Custom |
| Mosquito | S0256 | Windows installer/backdoor | Custom |
| Epic | S0091 | First-stage Windows implant (watering hole delivery) | Custom |
| HyperStack | S0537 | RPC-based Windows backdoor | Custom |
| Crutch | S0538 | Document stealer with Dropbox C2 | Custom |
| TinyTurla | S0668 | Minimal fallback backdoor (service-based persistence) | Custom |
| KOPILUWAK | S1075 | JavaScript reconnaissance tool | Custom |
| IronNetInjector | S0581 | .NET/IronPython malware loader | Custom |
| PowerStallion | S0393 | PowerShell backdoor (OneDrive C2) | Custom |
| LunarWeb | S1141 | HTTP backdoor with steganographic C2 | Custom |
| LunarMail | S1142 | Outlook add-in backdoor (email C2) | Custom |
| LunarLoader | S1143 | Reflective loader for Lunar toolset | Custom |
| TwoDash | (no ATT&CK ID) | Backdoor deployed via hijacked Storm-0156 infrastructure | Custom |
| Statuezy | (no ATT&CK ID) | Clipboard monitor deployed via hijacked infrastructure | Custom |
| Mimikatz | S0002 | Credential dumping | Public |
| Empire | S0363 | Post-exploitation framework (PowerShell) | Public |
| Metasploit / Meterpreter | S0261 | Post-exploitation framework | Public |
| PsExec | S0029 | Remote execution | Public (Sysinternals) |
| NBTscan | S0590 | NetBIOS scanner | Public |
| certutil | S0160 | LOLBin (decode, download, certificate install) | Built-in |
| Net / nbtstat / netstat / Reg / Systeminfo / Tasklist | S0039 / S0102 / S0104 / S0075 / S0096 / S0057 | LOLBins | Built-in |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never deploy kernel rootkits or destructive capabilities outside an explicitly sanctioned, isolated lab environment.

Map Turla's signature plays to Decepticon's own capabilities:

- **Initial access — watering hole + spearphishing (T1189, T1566.001, T1566.002).** Use the phishing skill to craft targeted spearphishing emails with links to fake Adobe or legitimate-looking download pages (Mosquito pattern); use the payload-builder to create JavaScript-based droppers (KOPILUWAK pattern). For watering hole emulation, stage payloads on compromised WordPress-like infrastructure to simulate Turla's preferred initial access chain.
- **Persistence — Exchange Transport Agent / email-based C2 (T1505.002, T1071.003, T1114.002).** Where Exchange is in scope, emulate LightNeuron by deploying a Transport Agent that intercepts email flow — this is Turla's most distinctive persistence mechanism. Alternatively, deploy Outlook add-in persistence (LunarMail pattern, T1137.006) for environments where Exchange agent access is unavailable.
- **Persistence — service masquerading + fallback (T1543.003, T1036.004).** Emulate TinyTurla by installing a minimal backdoor DLL as a Windows service with a name matching legitimate system services (e.g., `w32time.dll`). This serves as a **fallback access** channel — Turla's signature resilience pattern where minimal implants survive detection of primary tooling.
- **Defense evasion — rootkit + hidden filesystem (T1014, T1564.005, T1027.011).** In an isolated lab, emulate Uroburos/Snake's kernel-rootkit persistence with hidden NTFS virtual filesystems and Registry-stored encrypted payloads. For non-lab environments, focus on fileless storage (Registry-based payload staging) and **AMSI bypass** (T1685) patching techniques documented in Turla's PowerShell operations.
- **C2 — Gmail/email-based channels (T1071.003, T1102.002).** Use the c2 skill to establish an **email-based C2 channel** mimicking ComRAT v4's Gmail web-UI communication: commands received as email attachments, responses exfiltrated as encrypted email attachments with `.jpg.bfe` double extensions. Add a web-service C2 profile (Dropbox/GitHub) for redundancy, emulating Crutch and PowerStallion patterns.
- **C2 — passive network implants (T1205, T1205.002).** Emulate Penquin's passive listener model: deploy an implant that does **not beacon** but instead monitors network traffic via BPF socket filters, activating only when a magic packet is received. This tests defenders' ability to detect implants that produce zero outbound C2 traffic.
- **C2 — multi-hop P2P proxy (T1090.003, T1572).** Emulate Snake/Uroburos's signature P2P C2 architecture by chaining compromised internal systems as proxy nodes using encrypted custom protocols. Use **Sliver** (c2 skill) with internal pivot listeners to reproduce the multi-hop relay pattern.
- **C2 — steganography (T1001.002).** Embed C2 commands within PDF/JPEG files attached to emails, reproducing LightNeuron's steganographic communication. This tests email security controls' ability to detect malicious content hidden within otherwise legitimate-looking attachments.
- **Credential access — domain takeover chain (T1003.001, T1003.006, T1558.001, T1550.002).** Drive the AD skill / **Mimikatz** for the full Turla credential chain: LSASS dump → DCSync → golden ticket generation → pass-the-hash lateral movement. This mirrors Turla's documented domain-takeover pattern used to establish persistent domain-level access.
- **Collection & exfil — cloud service abuse (T1567.002, T1102, T1020).** Use bash/PowerShell to stage collected documents in RAR archives and exfiltrate via WebDAV to cloud storage (OneDrive, Dropbox), emulating the Crutch and ComRAT exfiltration patterns. Implement **automated collection** with scheduled transfers (T1029) to reproduce Turla's low-and-slow exfil cadence.
- **Lateral movement — hijacking rival infrastructure (T1584.003, T1584.004).** Where multi-team engagements allow, emulate Turla's signature maneuver of **parasitizing another threat actor's C2 infrastructure** — access the simulated adversary's C2 servers to deploy your own backdoors through their existing access. This unique TTP tests whether defenders can distinguish between distinct actors operating through shared infrastructure.
- **Defense evasion — steganographic payloads + reflective loading (T1001.002, T1620).** Combine steganographic payload delivery with reflective code loading to emulate the LunarLoader pattern — payloads hidden in image files that are decoded and reflectively loaded into memory without touching disk.

## Detection & defense

- **Kernel rootkit / Snake (T1014, S0022):** Deploy Secure Boot with UEFI firmware integrity monitoring; use kernel-mode code integrity (KMCI/HVCI); monitor for unsigned kernel drivers; alert on anomalous raw disk/filesystem access patterns; hunt for hidden NTFS streams and virtual filesystem artifacts. The 2023 CISA advisory AA23-129A provides Snake-specific detection signatures and YARA rules.
- **Exchange Transport Agent abuse (T1505.002, S0395):** Audit installed Exchange Transport Agents (`Get-TransportAgent`); monitor for new or modified DLLs in Exchange transport directories; alert on Exchange process spawning unexpected child processes; inspect email attachments for steganographic anomalies (oversized image/PDF metadata).
- **Email/Gmail C2 (T1071.003, T1102.002):** Monitor for unusual browser automation patterns accessing webmail; detect processes making authenticated Gmail/Outlook web requests outside of normal user sessions; alert on encrypted attachment patterns with suspicious double extensions (`.jpg.bfe`); monitor for programmatic email draft creation.
- **PowerShell abuse + AMSI bypass (T1059.001, T1685):** Enable PowerShell ScriptBlock logging and Module logging; monitor for `amsi.dll` patch attempts; alert on PowerShell profiles modified outside normal administrative processes; detect encoded/encrypted PowerShell scripts using `Out-EncryptedScript` patterns.
- **Registry-based fileless storage (T1027.011):** Monitor Registry value writes to Run keys, WMI subscription stores, and unusual key paths for large binary data; alert on Registry values exceeding normal size thresholds; baseline and monitor PowerShell Profile file modifications.
- **Passive implants / traffic signaling (T1205, T1205.002):** Deploy network anomaly detection for unusual raw socket listeners; hunt for processes with BPF socket filters that don't match legitimate use (network monitoring tools); since passive implants produce no outbound traffic, focus detection on the activation packets — unusual single-packet inbound connections followed by outbound data transfers.
- **Credential dumping (T1003.*, T1558.*):** Enable LSA protection (`RunAsPPL`) and Credential Guard; alert on LSASS handle access with `PROCESS_VM_READ`; monitor for DCSync replication requests from non-DC hosts; detect Kerberos ticket anomalies (golden ticket TGT lifetime, silver ticket service principal mismatches).
- **Watering hole delivery (T1189):** Monitor for exploit kit indicators on partner/upstream websites; implement browser isolation for high-risk browsing; deploy Content Security Policy headers on owned web properties; hunt for iframe/redirect injections on government/diplomatic organization websites.
- **APT infrastructure hijacking (T1584.003, T1584.004):** During multi-APT incident response, correlate C2 infrastructure across distinct actor clusters; watch for unexplained secondary implants deployed through another actor's existing access; alert on lateral deployment from already-compromised-and-attributed C2 servers.
- **Exfiltration to cloud services (T1567.002):** Monitor for bulk uploads to Dropbox, OneDrive, 4shared, GitHub, and Google Drive from unusual processes or outside business hours; DLP monitoring for encrypted archives (RAR/ZIP) being uploaded to cloud storage; alert on WebDAV PROPFIND/PUT operations to external endpoints.
- **Service-based fallback persistence (T1543.003, T1036.004):** Audit Windows services for DLLs that mimic legitimate system components; compare service DLL hashes against known-good baselines; monitor for new service installations in system directories; hunt for services with names matching built-in Windows services but with non-standard binary paths.

## Sources

- https://attack.mitre.org/groups/G0010/
- https://www.cisa.gov/sites/default/files/2023-05/aa23-129a_snake_malware_2.pdf
- https://www.justice.gov/archives/opa/pr/justice-department-announces-court-authorized-disruption-snake-malware-network-controlled
- https://media.defense.gov/2019/Oct/18/2002197242/-1/-1/0/NSA_CSA_Turla_20191021%20ver%204%20-%20nsa.gov.pdf
- https://www.microsoft.com/en-us/security/blog/2024/12/04/frequent-freeloader-part-i-secret-blizzard-compromising-storm-0156-infrastructure-for-espionage/
- https://securelist.com/the-epic-turla-operation/65545/
- https://securelist.com/satellite-turla-apt-command-and-control-in-the-sky/72081/
- https://www.welivesecurity.com/2019/05/29/turla-powershell-usage/
- https://www.welivesecurity.com/wp-content/uploads/2020/05/ESET_Turla_ComRAT.pdf
- https://www.welivesecurity.com/wp-content/uploads/2019/05/ESET-LightNeuron.pdf
- https://www.welivesecurity.com/en/eset-research/moon-backdoors-lunar-landing-diplomatic-missions/
- https://www.welivesecurity.com/2020/12/02/turla-crutch-keeping-back-door-open/
- https://www.welivesecurity.com/wp-content/uploads/2018/01/ESET_Turla_Mosquito.pdf
- https://www.welivesecurity.com/2018/05/22/turla-mosquito-shift-towards-generic-tools/
- https://www.welivesecurity.com/wp-content/uploads/2017/08/eset-gazer.pdf
- https://blog.talosintelligence.com/2021/09/tinyturla.html
- https://researchcenter.paloaltonetworks.com/2017/05/unit42-kazuar-multiplatform-espionage-backdoor-api-access/
- https://unit42.paloaltonetworks.com/ironnetinjector/
- https://unit42.paloaltonetworks.com/acidbox-rare-malware/
- https://www.mandiant.com/resources/blog/turla-galaxy-opportunity
- https://www.symantec.com/blogs/threat-intelligence/waterbug-espionage-governments
- https://www.recordedfuture.com/research/turla-apt-infrastructure
- https://web.archive.org/web/20201101015247/https://www.accenture.com/us-en/blogs/cyber-defense/turla-belugasturgeon-compromises-government-entity
- https://www.leonardo.com/documents/20142/10868623/Malware+Technical+Insight+_Turla+%E2%80%9CPenquin_x64%E2%80%9D.pdf
- https://www.crowdstrike.com/blog/meet-crowdstrikes-adversary-of-the-month-for-march-venomous-bear/
- https://cyberscoop.com/turla-infiltrates-pakistani-apt-networks-microsoft-lumen/
