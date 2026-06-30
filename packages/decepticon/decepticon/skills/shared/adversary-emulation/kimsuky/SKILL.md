---
name: kimsuky-velvet-chollima
description: "Adversary-emulation profile for Kimsuky (G0094 / Velvet Chollima / Emerald Sleet / THALLIUM / Black Banshee / APT43 / TA427), North Korea's RGB 63rd Research Center cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Kimsuky, Velvet Chollima, Emerald Sleet, THALLIUM, Black Banshee, APT43, TA427, Springtail, Earth Kumiho, G0094, North Korean espionage emulation, BabyShark, AppleSeed, Gold Dragon, KONNI, FlowerPower, credential phishing think tanks/academia, social engineering journalist impersonation, malicious browser extensions, CHM/LNK-based execution, ClickFix social engineering, TRANSLATEXT, Troll Stealer, nuclear policy targeting, Korean Peninsula intelligence"
  tags: kimsuky, velvet-chollima, emerald-sleet, thallium, black-banshee, apt43, ta427, springtail, north-korea, dprk, rgb, espionage, nation-state, g0094, adversary-emulation, mitre-attack
  mitre_attack: T1583, T1583.001, T1583.004, T1583.006, T1584.001, T1585, T1585.001, T1585.002, T1586.002, T1587, T1587.001, T1588.002, T1588.003, T1588.005, T1589.002, T1589.003, T1591, T1593.001, T1593.002, T1594, T1596, T1608.001, T1682, T1566, T1566.001, T1566.002, T1598, T1598.003, T1190, T1133, T1204.001, T1204.002, T1204.004, T1059.001, T1059.003, T1059.005, T1059.006, T1059.007, T1106, T1559.001, T1053.005, T1620, T1547.001, T1543.003, T1546.001, T1505.003, T1176.001, T1037.001, T1098.007, T1136.001, T1055, T1055.001, T1055.012, T1548.002, T1027, T1027.001, T1027.002, T1027.007, T1027.010, T1027.012, T1027.013, T1027.015, T1027.016, T1036.004, T1036.005, T1036.007, T1070.004, T1070.006, T1112, T1140, T1218.005, T1218.010, T1218.011, T1553.002, T1564.002, T1564.003, T1564.011, T1685, T1686, T1497.001, T1480.002, T1678, T1003.001, T1555.003, T1056.001, T1056.003, T1552.001, T1552.004, T1539, T1111, T1040, T1550.002, T1557, T1083, T1082, T1016, T1518.001, T1057, T1012, T1217, T1007, T1033, T1124, T1680, T1115, T1489, T1185, T1021.001, T1534, T1005, T1074.001, T1114.002, T1114.003, T1056.001, T1113, T1560.001, T1560.003, T1071.001, T1071.002, T1071.003, T1102.001, T1102.002, T1105, T1132.002, T1219.002, T1568, T1205, T1041, T1567.002, T1020, T1078.003, T1657, T1660, T1684.001, T1543.002, T1059.004, T1053.003, T1090.001
---

# Kimsuky (Velvet Chollima, Emerald Sleet, THALLIUM, Black Banshee, APT43) — Adversary Emulation Profile

Kimsuky (MITRE ATT&CK **G0094**) is a DPRK-based cyber-espionage group attributed to North Korea's Reconnaissance General Bureau (RGB), specifically the **63rd Research Center**, operating since at least **2012**. Initially focused on South Korean government entities and think tanks, the group has expanded its aperture to the United States, Japan, Russia, and Europe — consistently targeting individuals and organizations with insight into **Korean Peninsula foreign policy, nuclear policy, sanctions, and defense issues**. Kimsuky is distinguished by its heavy investment in **social engineering and credential phishing** over zero-day exploitation: the group impersonates journalists, researchers, diplomats, and think-tank personnel in long-running correspondence campaigns to build trust before delivering malicious payloads or harvesting credentials. Its tooling ranges from commodity RATs (QuasarRAT, gh0st RAT) to a stable of bespoke malware families (BabyShark, AppleSeed, Gold Dragon, KONNI, Troll Stealer) and malicious browser extensions (TRANSLATEXT). Since 2023, Kimsuky has been observed leveraging commercial LLMs for target research and vulnerability analysis, and adopting ClickFix-style social engineering to trick victims into self-executing malicious PowerShell.

## Attribution & motivation

- **Sponsor / nation:** Democratic People's Republic of Korea (DPRK) — Reconnaissance General Bureau (RGB), **63rd Research Center**. U.S. government (CISA/FBI/CNMF joint advisory AA20-301A, 2020) and multiple vendor assessments (Mandiant/Google TAG, CrowdStrike, Microsoft, Symantec) attribute Kimsuky operations to North Korean state-sponsored actors. In 2023, the U.S. Treasury sanctioned Kimsuky as an entity of the RGB.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — gathering foreign policy, nuclear/defense, and sanctions intelligence for the DPRK regime. Secondary motivation includes **financial theft** (cryptocurrency theft and laundering to self-fund operations, per Mandiant's APT43 report) and limited **influence operations** (DMARC abuse for impersonation campaigns).
- **Attribution confidence:** **High.** Supported by U.S. government joint advisories (AA20-301A), FBI IC3 public service announcements (2026), Treasury OFAC sanctions designations, and consistent multi-vendor reporting (Mandiant, CrowdStrike, Microsoft, Symantec, Kaspersky, Malwarebytes, Cisco Talos, Proofpoint, Zscaler).

## Targeting

- **Sectors:** Government and diplomatic bodies; think tanks and policy research institutes; academia (particularly Korean studies, nuclear policy, international relations); media and journalism; defense and military; international organizations (United Nations, IAEA); business services; manufacturing; cryptocurrency exchanges.
- **Regions:** South Korea (primary), United States, Japan, Europe (UK, Germany), Russia, and international organizations.
- **Victim profile:** Individuals with access to strategic intelligence on the Korean Peninsula — policy analysts, professors, journalists, diplomats, government officials, and nuclear/defense researchers. Kimsuky invests heavily in pre-operational reconnaissance, using social media monitoring, OSINT, and LLM-assisted research to identify and profile targets before initiating prolonged social-engineering correspondence. The group routinely impersonates real journalists, think-tank fellows, and diplomats to build rapport over multiple email exchanges before delivering payloads or credential-harvesting links.

## Notable campaigns

- **2014 — Korea Hydro & Nuclear Power Co. (KHNP) compromise.** Kimsuky infiltrated South Korea's nuclear power operator, stealing internal documents and reactor blueprints. The South Korean government attributed the intrusion to North Korea.
- **2018 — Operation STOLEN PENCIL.** Targeted academic institutions (primarily in the United States) with spearphishing, deploying malicious Chrome extensions for credential theft and persistence, alongside GREASE and MECHANICAL tooling. (Arbor Networks / NETSCOUT)
- **2019-02 — Operation Kabar Cobra.** Persistent espionage campaign against South Korean government and military targets using HWP document lures, AppleSeed backdoors, and multi-stage infection chains. (AhnLab)
- **2019 — Operation Smoke Screen.** Targeted South Korean and U.S. entities with spearphishing campaigns using document-based payloads themed around North Korea-related policy topics. (ESTsecurity)
- **2020-10 — CISA Advisory AA20-301A.** Joint CISA/FBI/CNMF advisory documenting Kimsuky's global intelligence-collection operations, detailing BabyShark, credential phishing, web shells, and keylogger tooling against government, nuclear, and think-tank targets. (CISA)
- **2021 — Blogspot abuse / Talos "Gold Dragon" campaign.** Kimsuky used Blogspot and legitimate web services as dead-drop resolvers and C2 channels to deliver Gold Dragon, Brave Prince, and related implants against South Korean targets. (Cisco Talos)
- **2023-2024 — LLM-assisted operations.** Microsoft and OpenAI disclosed that Kimsuky/Emerald Sleet used commercial LLMs for target research, vulnerability analysis, social-engineering content generation, and scripting assistance. (Microsoft Threat Intelligence, OpenAI)
- **2024 — TRANSLATEXT browser extension.** Deployed malicious Chrome extension masquerading as a translation tool against South Korean academia to steal credentials, cookies, and email data. (Zscaler)
- **2024 — Troll Stealer / GoBear / Gomir.** New malware families signed with stolen valid certificates, including a Go-based Linux backdoor (Gomir) and a comprehensive data stealer (Troll Stealer) targeting South Korean entities. (Symantec / S2W)
- **2025 — ClickFix social engineering.** Kimsuky adopted ClickFix tactics impersonating Japanese diplomats, enticing victims to copy-paste malicious PowerShell commands leading to QuasarRAT deployment. (Proofpoint)
- **2026-01 — FBI IC3 advisory on DPRK social engineering.** FBI published advisory on Kimsuky impersonation campaigns using QR-code phishing (quishing) and fake login portals targeting think-tank and government personnel. (IC3)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.001** — Acquire infrastructure: domains: registered domains spoofing targeted organizations, search engines, web platforms, and cryptocurrency exchanges.
- **T1583.004** — Acquire infrastructure: servers: purchased hosting with virtual currency and prepaid cards to obscure attribution.
- **T1583.006** — Acquire infrastructure: web services: hosted payloads and beacons on Blogspot, Dropbox, and GitHub.
- **T1584.001** — Compromise infrastructure: domains: compromised legitimate sites for malware distribution.
- **T1585.001 / .002** — Establish accounts: social media and email accounts for monitoring targets and conducting phishing operations.
- **T1586.002** — Compromise accounts: email accounts: compromised real email accounts to send phishing from trusted senders.
- **T1587 / .001** — Develop capabilities / malware: created custom toolkits including mailing toolkits, MailFetch.py, BabyShark, AppleSeed, and TRANSLATEXT.
- **T1588.002 / .003 / .005** — Obtain capabilities: tools (Nirsoft WebBrowserPassView, Mimikatz, PsExec), code-signing certificates (stolen valid certs), and exploits (CVE-2020-0688 and others).
- **T1589.002 / .003** — Gather victim identity: email addresses and employee names for targeted phishing.
- **T1591** — Gather victim org information: collected hierarchy, functions, and press releases; used LLMs for target research.
- **T1593.001 / .002** — Search open websites: monitored Twitter/social media and used Google to identify targets and trends.
- **T1594** — Search victim-owned websites for organizational intelligence.
- **T1596** — Search open technical databases: used LLMs to research publicly reported vulnerabilities.
- **T1608.001** — Stage capabilities: upload malware: hosted implants on Blogspot, compromised sites, and Dropbox.
- **T1682** — Query public AI services: used LLMs to identify think tanks, government organizations, and experts for targeting.

### Initial Access
- **T1566.001** — Spearphishing attachments: Word, Excel, HWP (Hangul Word Processor), PDF, and LNK files in ZIP archives themed around Korean Peninsula policy topics.
- **T1566.002** — Spearphishing links: links to actor-controlled domains hosting credential-harvesting pages or macro-laden documents.
- **T1598 / .003** — Phishing for information / spearphishing link: tailored emails with web beacons for target profiling; QR-code phishing (quishing) to redirect from corporate devices to mobile.
- **T1190** — Exploit public-facing applications: exploited Microsoft Exchange CVE-2020-0688 for initial footholds.
- **T1133** — External remote services: used RDP for persistent remote access.
- **T1204.001 / .002 / .004** — User execution: malicious links, malicious files (LNK with double extensions, CHM files, HWP documents), and ClickFix-style malicious copy-and-paste of PowerShell commands.
- **T1684.001** — Social engineering: impersonation of journalists, diplomats, embassy employees, think-tank personnel, and researchers in prolonged correspondence campaigns.

### Execution
- **T1059.001 / .003 / .005 / .006 / .007** — PowerShell (Invoke-Mimikatz, encoded payloads, ClickFix), Windows Command Shell (batch scripts, reverse shells), Visual Basic (malicious macros, VBScript scheduled tasks), Python (macOS implant, MailFetcher.py), JavaScript (TRANSLATEXT extension, JScript downloaders).
- **T1106** — Native API: leveraged Windows APIs (GetAsyncKeyState, VirtualAllocEx, WriteProcessMemory, CreateRemoteThread) for keylogging and injection.
- **T1559.001** — Inter-process communication: COM: created scheduled tasks via COM objects, used WScript.Shell for payload download.
- **T1053.005** — Scheduled tasks: persistence via tasks named "ChromeUpdateTaskMachine", "AhnlabUpdate", and similar legitimate-looking names; QuasarRAT delivery via VBScript scheduled tasks.
- **T1620** — Reflective code loading: Invoke-Mimikatz reflective DLL loading; .NET assembly loading via `[System.Reflection.Assembly]::Load`.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: scripts in startup folder and RunOnce/Run registry modifications (e.g., "WindowsSecurityCheck").
- **T1543.003** — Windows service: created new services for long-term persistence.
- **T1543.002** — Systemd service (Linux): Gomir backdoor installs as systemd service on Linux targets.
- **T1546.001** — Change default file association: HWP document stealer module modifies default program associations.
- **T1505.003** — Web shell: deployed modified PHP web shells with characteristic "Dinosaur" references in code.
- **T1176.001** — Browser extensions: malicious Chrome extensions (TRANSLATEXT, STOLEN PENCIL) for persistent credential and data theft.
- **T1037.001** — Logon script (Windows): KGH_SPY uses logon scripts for persistence.
- **T1053.003** — Cron (Linux): Gomir backdoor uses cron for persistence on Linux.

### Privilege Escalation
- **T1055 / .001 / .012** — Process injection: injected into explorer.exe (Win7Elevate); reflective DLL injection (VirtualAllocEx → WriteProcessMemory → CreateRemoteThread); process hollowing via file injector DLL.
- **T1548.002** — UAC bypass: CSPY Downloader and HTTPTroy bypass UAC for elevated execution.
- **T1098.007** — Account manipulation: additional local/domain groups: added accounts to privileged groups via `net localgroup`.
- **T1136.001** — Create local account: created accounts with `net user` for persistent access.
- **T1078.003** — Valid accounts: local accounts: used GREASE tool to add Windows admin accounts for RDP access.

### Defense Evasion
- **T1027 / .001 / .002 / .007 / .010 / .012 / .013 / .015 / .016** — Obfuscation: XOR/Base64/RC4 encoding, binary padding (100+ spaces in PowerShell), UPX packing, dynamic API resolution with custom hashing, command obfuscation (Base64 encoded PowerShell), LNK icon smuggling, encrypted/encoded files (CLng+Chr obfuscation, RC4), compressed payloads in ZIP, junk code insertion and string concatenation.
- **T1036.004 / .005 / .007** — Masquerading: disguised services as benign software; renamed malware to legitimate names (ESTCommon.dll, chrome.ps1); double file extensions (.pdf.lnk).
- **T1070.004 / .006** — Indicator removal: deleted exfiltrated data, cookie files, delivery artifacts (.log, .zip); timestomped creation/compilation dates.
- **T1112** — Modify registry: modified default file associations, enabled all macros, persistence via registry keys.
- **T1140** — Deobfuscate/decode: decoded Base64 VBScripts, PowerShell scripts, and RC4-obfuscated files at runtime.
- **T1218.005 / .010 / .011** — System binary proxy execution: mshta.exe for malicious HTA scripts; regsvr32 for DLL execution; rundll32 for malware loading.
- **T1553.002** — Code signing: signed malware with stolen valid certificates (EGIS CO,. Ltd.).
- **T1564.002 / .003 / .011** — Hide artifacts: hidden user accounts via registry (SpecialAccounts\UserList); hidden PowerShell windows (`-WindowStyle Hidden`); `-ErrorAction SilentlyContinue` to suppress errors.
- **T1685** — Disable or modify tools: turned off Windows Security Center, hid AV software windows from infected users.
- **T1686** — Disable or modify system firewall: disabled system firewall on compromised hosts.
- **T1497.001** — Virtualization/sandbox evasion: detected and killed VMware, Hyper-V, and VirtualBox environments via `Get-CimInstance` manufacturer checks.
- **T1480.002** — Execution guardrails: mutual exclusion: used mutexes and PID files to prevent duplicate execution.
- **T1678** — Delay execution: Sleep function to ensure script execution timing.

### Credential Access
- **T1003.001** — LSASS memory: dumped credentials using Mimikatz and ProcDump.
- **T1555.003** — Credentials from web browsers: Chrome extension theft, Nirsoft WebBrowserPassView, browser data harvesting via GetBrowserData().
- **T1552.001 / .004** — Unsecured credentials: credentials from saved mail files; stolen AES keys from Chromium Local State files (app_bound_encrypted_key).
- **T1056.001 / .003** — Input capture: PowerShell keylogger (GetAsyncKeyState, 50ms polling), MECHANICAL tool; web portal capture via fake Google/Naver/Kakao login pages.
- **T1539** — Steal web session cookie: TRANSLATEXT and Troll Stealer exfiltrate browser cookies.
- **T1111** — Multi-factor authentication interception: proprietary tool to intercept OTPs for 2FA bypass.
- **T1040** — Network sniffing: Nirsoft SniffPass to capture passwords over non-secure protocols.
- **T1550.002** — Pass the hash: used for authentication to remote-access software for C2.
- **T1557** — Adversary-in-the-middle: modified PHProxy to intercept web traffic between victim and accessed websites.
- **T1185** — Browser session hijacking: form-grabbing to extract emails and passwords from web data forms.

### Discovery
- **T1083** — File and directory discovery: enumerated all files/directories; CreateFileList() function scanning drives for files of interest → FileList.txt.
- **T1082** — System information discovery: systeminfo command; WMI queries (Win32_OperatingSystem).
- **T1016** — System network configuration discovery: ipconfig/all; web beacons for IP; WMI Win32_NetworkAdapterConfiguration.
- **T1518.001** — Security software discovery: Get-CimInstance SecurityCenter2.AntiVirusProduct; sc query WinDefend.
- **T1057** — Process discovery: enumerated all running processes; Get-Process PowerShell cmdlet.
- **T1012** — Query registry: obtained specific registry keys and values for reconnaissance.
- **T1217** — Browser information discovery: GetBrowserData() harvesting login credentials, bookmarks, cookies, and encryption keys.
- **T1007** — System service discovery: enumerated all service names on victim systems.
- **T1033** — System owner/user discovery: queried System.Security.Principal namespace via GetCurrent().
- **T1124** — System time discovery: Get-Date PowerShell cmdlet.
- **T1680** — Local storage discovery: enumerated drives and storage volumes.
- **T1115** — Clipboard data: stolen data from clipboard.
- **T1489** — Service stop: KillMe function to terminate virtual environments (VMware, Hyper-V, VirtualBox).

### Lateral Movement
- **T1021.001** — Remote Desktop Protocol: RDP for direct point-and-click access after account creation/compromise.
- **T1534** — Internal spearphishing: sent internal phishing emails for lateral movement after stealing victim information and email credentials.

### Collection
- **T1005** — Data from local system: collected Office, PDF, and HWP documents; RecentFiles() function parsing .lnk shortcuts from Recent folder.
- **T1074.001** — Local data staging: staged files under `C:\Program Files\Common Files\System\Ole DB\` and %TEMP% directories.
- **T1114.002 / .003** — Email collection: MailFetch crawler via IMAP for remote email collection; set auto-forward rules on victim email accounts.
- **T1056.001** — Keylogging: PowerShell keylogger with GetAsyncKeyState() at 50ms intervals; MECHANICAL tool.
- **T1113** — Screen capture: TRANSLATEXT browser screenshots; custom malware screen capture.
- **T1560.001 / .003** — Archive collected data: QuickZip archiving; custom RC4 encryption before exfiltration; zip compression with rename (init.zip → init.dat).

### Command & Control
- **T1071.001 / .002 / .003** — Application layer protocol: HTTP GET/POST for C2; FTP for additional malware download; SMTP/IMAP email-based C2 and exfiltration.
- **T1102.001 / .002** — Web service: dead-drop resolver on Blogspot/GitHub for configuration retrieval; bidirectional C2 via Blogspot, GitHub, and Dropbox.
- **T1105** — Ingress tool transfer: downloaded additional scripts, tools, and malware onto victim systems.
- **T1132.002** — Non-standard encoding: XOR with designated key followed by Base64 encoding for HTTP POST communications.
- **T1219.002** — Remote desktop software: modified TeamViewer client as C2 channel.
- **T1568** — Dynamic resolution: Dynamic DNS (DDNS) services (FreeDNS, No-IP) including servers in South Korea.
- **T1205** — Traffic signaling: TRANSLATEXT redirects to legitimate Gmail/Naver/Kakao pages when clients connect with no parameters (anti-analysis).
- **T1090.001** — Proxy: internal proxy: Gomir uses internal proxy for C2 relay.
- **T1573.001 / .002** — Encrypted channel: symmetric (RC4, AES) and asymmetric encryption for C2 communications.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: primary exfil method across most malware families.
- **T1567.002** — Exfiltration to cloud storage: exfiltrated to actor-controlled Blogspot accounts and Dropbox.
- **T1020** — Automated exfiltration: automated script executing every 10 minutes, checking for staged filenames before exfil.

### Impact
- **T1657** — Financial theft: stolen and laundered cryptocurrency to self-fund operations and infrastructure acquisition.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| BabyShark | S0414 | VBS/HTA-based reconnaissance backdoor | Custom |
| AppleSeed | S0622 | Modular Windows backdoor (keylogging, screen capture, exfil) | Custom |
| Gold Dragon | S0249 | Windows backdoor with data staging and exfil | Custom |
| Brave Prince | S0252 | Windows backdoor / info stealer | Custom |
| KGH_SPY | S0526 | Modular spyware suite (credential/email/keylog) | Custom |
| CSPY Downloader | S0527 | UAC-bypass downloader with anti-VM checks | Custom |
| NOKKI | S0353 | Windows backdoor with credential hooking | Custom |
| Troll Stealer | S1196 | Go-based comprehensive data stealer (signed with stolen cert) | Custom |
| GoBear | S1197 | Go-based Windows backdoor (signed with stolen cert) | Custom |
| Gomir | S1198 | Go-based **Linux** backdoor (systemd/cron persistence) | Custom |
| HTTPTroy | S9007 | Windows backdoor with UAC bypass and SIMD obfuscation | Custom |
| TRANSLATEXT | S1201 | Malicious **Chrome extension** (credential/cookie/email theft) | Custom |
| KONNI | (linked cluster) | RAT with document theft, often delivered via CHM/LNK | Custom |
| FlowerPower | (reported in vendor analysis) | PowerShell-based reconnaissance/collection script | Custom |
| MailFetch.py | (no ATT&CK software ID) | Python email crawler (IMAP-based collection) | Custom |
| MECHANICAL | (no ATT&CK software ID) | Keylogger | Custom |
| GREASE | (no ATT&CK software ID) | Account creation tool for RDP persistence | Custom |
| gh0st RAT | S0032 | Remote access trojan | Public |
| QuasarRAT | S0262 | .NET remote access trojan | Public |
| Amadey | S1025 | Modular downloader/loader | Public |
| Mimikatz | S0002 | Credential dumping | Public |
| PsExec | S0029 | Remote execution | Public |
| Nirsoft WebBrowserPassView / SniffPass | (Nirsoft tools) | Browser password dump / network sniffer | Public |
| PHProxy | (open source) | Modified web proxy for AitM | Public |
| certutil / schtasks / mshta / rundll32 / regsvr32 | S0160 / S0111 / built-in | LOLBins | Built-in |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never run credential-harvesting, social-engineering, or financial-theft techniques outside an explicitly sanctioned scope.

Map Kimsuky's signature plays to Decepticon's own capabilities:

- **Initial access — social engineering & credential phishing (T1598.003, T1566.001, T1566.002, T1684.001, T1204.004).** This is Kimsuky's defining capability. Use the phishing/credential-harvest skill to set up **lookalike login pages** (Google, Naver, Kakao) with DMARC-abusing sender spoofing. Build a multi-stage correspondence chain: initial benign emails impersonating a journalist/researcher → rapport-building exchanges → delivery of credential link or weaponized attachment. Stage **ClickFix-style lures** that instruct the victim to copy-paste PowerShell commands. Deploy web beacons in reconnaissance emails to profile targets (IP, user-agent, email client) before payload delivery.
- **Weaponized documents & LNK execution (T1566.001, T1204.002, T1027.012, T1036.007).** With the payload-builder skill, create **HWP/Word documents with malicious macros** themed around Korean Peninsula policy topics (nuclear talks, sanctions, defense cooperation). Build **double-extension LNK files** (.pdf.lnk) with padded target fields to obscure embedded PowerShell. Stage CHM-based infection chains. Deliver inside ZIP archives matching Kimsuky's packaging pattern.
- **Browser extension deployment (T1176.001, T1185, T1539, T1555.003).** Emulate the TRANSLATEXT attack: deploy a malicious Chrome extension masquerading as a translation tool that harvests passwords, cookies, session tokens, email content, and screenshots from the browser. Use dead-drop resolvers (Blogspot/GitHub) for extension C2.
- **Post-exploitation credential access (T1003.001, T1555.003, T1056.001, T1111).** Drive the credential-access skill with **Mimikatz** (Invoke-Mimikatz reflective loading), ProcDump for LSASS dumps, and Nirsoft WebBrowserPassView for browser credential extraction. Deploy keyloggers using GetAsyncKeyState at 50ms polling intervals. Emulate OTP/2FA interception where MFA bypass is in scope.
- **C2 via legitimate services (T1102.001, T1102.002, T1071.001, T1567.002).** Use **Sliver** (c2 skill) as primary HTTPS C2, then layer Kimsuky-signature channels: Blogspot/GitHub dead-drop resolvers for configuration retrieval, Dropbox for payload hosting and victim data upload, and DDNS services (FreeDNS/No-IP) for dynamic C2 resolution. Encode C2 traffic with XOR+Base64 to match Kimsuky's HTTPTroy encoding pattern.
- **Persistence & evasion (T1547.001, T1053.005, T1036.004, T1218.005).** Install persistence via registry Run keys with legitimate-sounding names ("WindowsSecurityCheck", "ChromeUpdateTaskMachine", "AhnlabUpdate"). Use **mshta.exe** for HTA-based script execution and **rundll32** for DLL loading. Create scheduled tasks via COM objects. On Linux targets in scope, emulate Gomir's systemd service and cron persistence.
- **Collection & exfiltration (T1005, T1114.002, T1560.001, T1020).** Replicate Kimsuky's collection pattern: scan for HWP/Office/PDF documents with CreateFileList(); collect emails via IMAP using MailFetch-style scripts; stage collected data under %TEMP% or `C:\Program Files\Common Files\System\Ole DB\`; archive with QuickZip or PowerShell `Compress-Archive`, rename archives (init.zip → init.dat); **exfiltrate on 10-minute automated intervals** to cloud services.
- **Anti-analysis & VM detection (T1497.001, T1480.002, T1027).** Implement manufacturer-string checks (VMware/Microsoft/VirtualBox) via `Get-CimInstance` to detect and terminate in virtual environments. Use mutex-based execution guardrails to prevent duplicate instances. Apply junk code insertion and SIMD-based string obfuscation for payload hardening.

## Detection & defense

- **Social engineering / credential phishing (T1598.003, T1566.001/.002, T1684.001):** Implement **DMARC enforcement (p=reject)** on organizational domains; train users to verify sender identity through out-of-band channels for unsolicited policy-related correspondence; deploy phishing-resistant MFA (FIDO2/WebAuthn); flag emails from free email providers impersonating known researchers/journalists; block QR-code-based redirects to unknown domains.
- **ClickFix / copy-paste execution (T1204.004):** Alert on PowerShell execution sourced from clipboard content; deploy endpoint policies blocking encoded PowerShell execution from user-initiated contexts; educate users that legitimate organizations never ask them to paste commands.
- **Malicious browser extensions (T1176.001, T1539):** Enforce Chrome/Edge extension whitelisting via Group Policy; monitor for new extension installations outside managed deployment; alert on extensions requesting broad permissions (cookies, webRequest, tabs); audit Blogspot/GitHub URLs in extension configurations.
- **LNK/CHM/HWP weaponization (T1204.002, T1027.012, T1036.007):** Block execution of .lnk files from ZIP archives via email gateway; alert on .lnk files with padded target fields or double extensions; restrict CHM execution (hh.exe) via AppLocker; monitor HWP postscript/EPS execution chains.
- **Credential dumping (T1003.001, T1555.003):** Enable LSA protection (RunAsPPL) and Credential Guard; alert on LSASS handle access (Sysmon Event 10); monitor for ProcDump targeting lsass.exe; detect Invoke-Mimikatz reflective loading via .NET assembly load events.
- **Web shells (T1505.003):** Monitor web-accessible directories for new PHP files; hunt for "Dinosaur" strings in web shell code (Kimsuky signature); alert on web-server processes spawning cmd.exe/PowerShell.
- **Persistence artifacts (T1547.001, T1053.005):** Monitor registry Run/RunOnce keys for suspicious entries ("WindowsSecurityCheck", "ChromeUpdateTaskMachine"); audit scheduled tasks created via COM objects or named after AV products ("AhnlabUpdate"); detect mshta.exe executing HTA files from temp directories.
- **C2 via legitimate services (T1102, T1567.002):** Monitor and baseline Blogspot, GitHub, and Dropbox traffic; alert on high-frequency API calls to cloud-storage services from non-browser processes; detect DDNS domain resolution (FreeDNS, No-IP) from enterprise hosts.
- **VM/sandbox evasion (T1497.001):** Deploy canary files and processes that mimic virtualization artifacts to trigger early detection; monitor for WMI queries to Win32_ComputerSystem.Manufacturer followed by process termination.
- **Exfiltration (T1041, T1567.002, T1020):** DLP monitoring for renamed archive files (init.dat pattern); alert on periodic (10-minute interval) automated uploads to cloud storage; monitor for QuickZip or Compress-Archive execution in non-standard directories.

## Sources

- https://attack.mitre.org/groups/G0094/
- https://us-cert.cisa.gov/ncas/alerts/aa20-301a
- https://www.ic3.gov/CSA/2026/260108.pdf
- https://services.google.com/fh/files/misc/apt43-report-en.pdf
- https://www.proofpoint.com/us/blog/threat-insight/social-engineering-dmarc-abuse-ta427s-art-information-gathering
- https://www.proofpoint.com/us/blog/threat-insight/around-world-90-days-state-sponsored-actors-try-clickfix
- https://www.microsoft.com/en-us/security/blog/2024/02/14/staying-ahead-of-threat-actors-in-the-age-of-ai/
- https://blog.talosintelligence.com/2021/11/kimsuky-abuses-blogs-delivers-malware.html
- https://www.cybereason.com/blog/back-to-the-future-inside-the-kimsuky-kgh-spyware-suite
- https://blog.malwarebytes.com/threat-analysis/2021/06/kimsuky-apt-continues-to-target-south-korean-government-using-appleseed-backdoor/
- https://securelist.com/the-kimsuky-operation-a-north-korean-apt/57915/
- https://asert.arbornetworks.com/stolen-pencil-campaign-targets-academia/
- https://www.zscaler.com/blogs/security-research/kimsuky-deploys-translatext-target-south-korean-academia
- https://www.security.com/threat-intelligence/springtail-kimsuky-backdoor-espionage
- https://medium.com/s2wblog/kimsuky-disguised-as-a-korean-company-signed-with-a-valid-certificate-to-distribute-troll-stealer-cfa5d54314e2
- https://www.securonix.com/blog/analyzing-deepdrive-north-korean-threat-actors-observed-exploiting-trusted-platforms-for-targeted-attacks/
- https://www.gendigital.com/blog/insights/research/dprk-kimsuky-lazarus-analysis
- https://www.aryaka.com/docs/reports/aryaka-kimsuky-apt-operational-blueprint.pdf
- https://www.enki.co.kr/en/media-center/blog/kimsuky-distributing-malicious-mobile-app-via-qr-code
- https://global.ahnlab.com/global/upload/download/techreport/%5BAnalysis_Report%5DOperation%20Kabar%20Cobra.pdf
- https://threatconnect.com/blog/kimsuky-phishing-operations-putting-in-work/
- https://www.virusbulletin.com/virusbulletin/2020/03/vb2019-paper-kimsuky-group-tracking-king-spearphishing/
- https://go.crowdstrike.com/rs/281-OBQ-266/images/Report2020CrowdStrikeGlobalThreatReport.pdf
