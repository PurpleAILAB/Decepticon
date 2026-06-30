---
name: patchwork-dropping-elephant
description: "Adversary-emulation profile for Patchwork (G0040 / Dropping Elephant / Chinastrats / MONSOON / Hangover Group / Operation Hangover), an India-linked cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Patchwork, Dropping Elephant, Chinastrats, MONSOON, Hangover Group, Operation Hangover, Quilted Tiger, Zinc Emerson, APT-C-09, APT-Q-43, G0040, India espionage emulation, BADNEWS RAT, Ragnatela RAT, QuasarRAT, VajraSpy, DLL side-loading, copy-paste APT, RTF exploits, CVE-2017-11882 Equation Editor, Pakistan government targeting, South Asian espionage TTPs"
  tags: patchwork, dropping-elephant, chinastrats, monsoon, hangover-group, india, espionage, nation-state, g0040, adversary-emulation, mitre-attack, south-asia, badnews, ragnatela
  mitre_attack: T1548.002, T1560, T1119, T1197, T1547.001, T1059.001, T1059.003, T1059.005, T1555.003, T1132.001, T1005, T1074.001, T1587.002, T1189, T1203, T1083, T1574.001, T1070.004, T1105, T1559.002, T1680, T1036.005, T1112, T1027.001, T1027.002, T1027.005, T1027.010, T1588.002, T1566.001, T1566.002, T1598.003, T1055.012, T1021.001, T1053.005, T1518.001, T1553.002, T1082, T1033, T1204.001, T1204.002, T1102.001, T1056.001, T1113, T1025, T1039, T1573.001, T1071.001, T1102.002, T1106, T1564.001, T1564.003, T1137.001, T1016, T1120, T1020, T1036.001, T1140, T1125, T1614, T1571, T1095, T1090
---

# Patchwork (Dropping Elephant, Chinastrats, MONSOON, Hangover Group) — Adversary Emulation Profile

Patchwork (MITRE ATT&CK **G0040**) is a cyber-espionage group believed to operate from India, active since at least **2009** and first publicly documented in December 2015. The group earned its name because much of the code used in its tooling is **copied and pasted from online forums and public repositories** — a "patchwork" of borrowed exploit code and open-source RATs stitched together with custom malware. Despite this low-sophistication approach, Patchwork compensates with **high-quality social engineering** and aggressive targeting of diplomatic, government, defense, and research organizations primarily across South Asia — with heavy emphasis on **Pakistan** and **China's foreign relations apparatus**. The group's malware arsenal includes the custom BADNEWS RAT (and its Ragnatela variant), the public QuasarRAT, BackConfig, VajraSpy (Android), and multiple document exploit chains leveraging CVE-2017-11882, CVE-2017-0199, CVE-2012-0158, and EPS vulnerabilities.

## Attribution & motivation

- **Sponsor / nation:** India (suspected state-sponsored). Circumstantial evidence — Indian keyboard layouts, IP geolocation, infrastructure registration patterns, and targeting profile — consistently points to a pro-Indian or Indian state entity. Norman Shark's 2013 Operation Hangover report traced infrastructure ownership to Indian firms. No formal government attribution has been issued, but multiple vendors (Kaspersky, Symantec, Palo Alto Unit 42, Trend Micro, Malwarebytes, ESET, Cymmetria, Forcepoint, Volexity) converge on an Indian nexus.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — military, diplomatic, and political intelligence relevant to Indian national security interests. Targets align with Indian geopolitical priorities: Pakistani military/defense/nuclear programs, Chinese diplomatic activities, and Western think tanks covering South Asian policy.
- **Attribution confidence:** **Medium-High.** No government indictments or formal attributions, but consistent vendor consensus plus the 2022 self-compromise (the actor infected their own machine with Ragnatela, revealing Indian keyboard layouts and development environment) significantly reinforce the India attribution.

## Targeting

- **Sectors:** Government and diplomatic bodies; defense and military organizations; nuclear/atomic energy agencies; think tanks and policy research institutes; universities and scientific research (molecular medicine, biological sciences); telecommunications; media and journalists covering South Asian affairs.
- **Regions:** Primary focus on **Pakistan** (military, government, defense, atomic energy, universities), **China** (diplomatic and government entities, foreign affairs), **Bangladesh**, **Sri Lanka**, **Nepal**, and **Southeast Asia**. Secondary targets include **United States** (think tanks — e.g., US-based foreign policy organizations), **United Kingdom**, **Australia**, and Western nations with diplomatic ties to South Asia.
- **Victim profile:** Individuals and organizations whose documents, communications, and credentials yield intelligence on Pakistani military capabilities, Chinese foreign policy, and South Asian regional security dynamics. Frequently targets webmail users and personnel who handle sensitive policy/defense documents.

## Notable campaigns

- **2009-2013 — Operation Hangover.** Disclosed by Norman Shark in May 2013, this espionage network had infrastructure roughly four years old, designed to spy on Pakistani national security targets and private-sector companies. Victims spanned over a dozen countries including Pakistan, the United States (Chicago Mercantile Exchange, law firms), Norway (Telenor), the UK, and Austria (Porsche). Used weaponized Word documents exploiting Java and Office vulnerabilities. (Norman Shark / Security Affairs / SC Media)
- **2015-11 to 2016-06 — Dropping Elephant / Chinastrats.** Kaspersky documented an aggressive campaign profiling hundreds to thousands of targets worldwide, focused on Chinese government and diplomatic entities and their international partners. Victims located in China, Pakistan, Sri Lanka, Bangladesh, Taiwan, Australia, the US, and Uruguay. Used watering-hole sites disguised as political news portals serving malicious PPS/PPT slides, exploiting CVE-2012-0158 and CVE-2014-6352. (Kaspersky GReAT)
- **2016-08 — MONSOON campaign.** Forcepoint documented a spearphishing campaign delivering BADNEWS, TINYTYPHON, and Unknown Logger malware via weaponized Office documents. Linked Patchwork to the same actor behind Operation Hangover. Targeted government and military organizations across South Asia. (Forcepoint Security Labs)
- **2016-07 — Patchwork expansion.** Symantec documented the group expanding its target list from government entities to a wide range of industries including aviation, energy, and financial sectors. (Symantec)
- **2017-2018 — BADNEWS evolution / EPS exploits.** Trend Micro and Palo Alto Unit 42 documented continued delivery of BADNEWS RAT via spearphishing with weaponized documents exploiting CVE-2017-11882 (Equation Editor), CVE-2017-0199, CVE-2017-8570, CVE-2015-2545, and CVE-2017-0261 (EPS). Lures impersonated Pakistani military promotions, Pakistan Atomic Energy Commission, and Ministry of the Interior documents. (Trend Micro / Unit 42)
- **2018-03/06 — US think tank targeting.** Volexity documented Patchwork targeting US-based think tanks with spearphishing emails and watering-hole attacks, deploying QuasarRAT and BADNEWS. Used web bugs (tracking pixels) for recipient profiling. Dropped QuasarRAT binaries masquerading as `microsoft_network.exe` and `crome.exe`. (Volexity)
- **2020 — BackConfig campaign.** Unit 42 documented updated BackConfig malware targeting government and military organizations in South Asia, distributed via spearphishing links with self-signed code-signing certificates from fictitious companies, using BITS jobs for payload delivery. (Unit 42)
- **2021-11 to 2022-01 — Ragnatela self-compromise.** Malwarebytes documented Patchwork deploying a new BADNEWS variant dubbed Ragnatela ("spider web") via malicious RTF files exploiting the Equation Editor. Targets included Pakistan's Ministry of Defense, National Defense University of Islamabad, UVAS University (Lahore), and the International Center for Chemical and Biological Sciences. The actor accidentally infected their own development machine, revealing their Indian keyboard layouts, VirtualBox/VMware development environment, and operational details. (Malwarebytes / Security Affairs)
- **2023-2024 — VajraSpy Android espionage.** ESET documented twelve Android apps bundled with VajraSpy RAT, six distributed via Google Play (1,400+ installs) and six in the wild. Apps disguised as messaging tools (Privee Talk, MeetMe, Let's Chat, etc.) used honey-trap romance scams to target users primarily in Pakistan. Capable of stealing contacts, call logs, SMS, WhatsApp/Signal messages, recording calls, and camera capture. 148 compromised devices geolocated in Pakistan and India. (ESET)

## TTPs by ATT&CK tactic

### Resource Development
- **T1587.002** — Develop capabilities — code signing certificates: created self-signed certificates from fictitious and spoofed legitimate software companies to sign malware (BackConfig campaign).
- **T1588.002** — Obtain capabilities — tool: obtained and used open-source tools such as QuasarRAT, PowerSploit, and Meterpreter; extensively copy-pasted exploit code from public forums.

### Initial Access
- **T1566.001** — Spearphishing attachment: primary initial access vector — weaponized Office documents (RTF, DOC, PPS/PPT) exploiting CVE-2017-11882, CVE-2017-0199, CVE-2017-8570, CVE-2012-1856, CVE-2014-4114, CVE-2015-1641, CVE-2012-0158, and EPS vulnerabilities (CVE-2015-2545, CVE-2017-0261). Lures impersonate Pakistani government/military documents.
- **T1566.002** — Spearphishing link: emails with links to malicious downloads hosted on actor-controlled infrastructure; used in BackConfig campaign and US think tank targeting.
- **T1598.003** — Spearphishing link for information: embedded image tags (web bugs / tracking pixels) with unique per-recipient tracking links to profile which recipients opened messages before delivering payloads.
- **T1189** — Drive-by compromise: watering-hole attacks using fake political news portals (focused on China's external affairs) serving malicious PPS files with embedded exploits.
- **T1204.001** — User execution — malicious link: spearphishing emails with links to malicious downloads; lured victims into clicking links to actor-controlled infrastructure.
- **T1204.002** — User execution — malicious file: embedded malicious macros in Word documents and lured victims to click icons to execute malware; weaponized RTF/DOC/PPS attachments.

### Execution
- **T1059.001** — PowerShell: used PowerSploit to download payloads, run reverse shells, and execute malware on victim machines.
- **T1059.003** — Windows Command Shell: ran reverse shells with Meterpreter; executed JavaScript code and .SCT files on victim machines.
- **T1059.005** — Visual Basic: used VBS scripts for execution on victim machines; macro-laden Office documents.
- **T1203** — Exploitation for client execution: core technique — exploits CVE-2017-11882 (Equation Editor), CVE-2017-0199 (OLE), CVE-2017-8570, CVE-2012-1856, CVE-2014-4114, CVE-2015-1641 in weaponized documents.
- **T1559.002** — Dynamic Data Exchange: leveraged DDE protocol in documents to deliver malware.
- **T1106** — Native API: BADNEWS and BackConfig use Windows native APIs for execution and system interaction.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: added second-stage malware to the startup folder (masquerading as "Baidu Software Update" and "Net Monitor"); file stealers persisted via Registry Run keys.
- **T1053.005** — Scheduled Task: file stealer uses TaskScheduler DLL to add persistence; BADNEWS and BackConfig use scheduled tasks.
- **T1137.001** — Office template macros: BackConfig used Office template macros for persistence.

### Privilege Escalation
- **T1548.002** — Bypass User Account Control: bypassed UAC using process hollowing through svchost.exe.
- **T1055.012** — Process hollowing: payload uses process hollowing to hide UAC bypass exploitation inside svchost.exe.

### Defense Evasion
- **T1027.001** — Binary padding: altered NDiskMonitor samples by adding four bytes of random letters to change file hashes.
- **T1027.002** — Software packing: payloads packed with UPX.
- **T1027.005** — Indicator removal from tools: modified malware samples to alter hash signatures.
- **T1027.010** — Command obfuscation: obfuscated scripts with Crypto Obfuscator.
- **T1036.005** — Match legitimate resource name or location: installed payloads masquerading as legitimate software ("Baidu Software Update", "Net Monitor"); dropped QuasarRAT as `microsoft_network.exe` and `crome.exe`.
- **T1036.001** — Invalid code signature: BADNEWS used invalid code signatures to appear legitimate.
- **T1070.004** — File deletion: removed and replaced certain files to prevent forensic retrieval.
- **T1112** — Modify Registry: deleted Microsoft Office Resiliency Registry keys to suppress crash dialogs and trick users.
- **T1553.002** — Code signing: signed malware with self-signed certificates from fictitious and spoofed companies.
- **T1140** — Deobfuscate/decode files: BackConfig deobfuscated encoded payloads at runtime.
- **T1564.001** — Hidden files and directories: BackConfig and QuasarRAT used hidden files.
- **T1564.003** — Hidden window: QuasarRAT ran with hidden windows to avoid user detection.
- **T1574.001** — DLL search order hijacking / DLL side-loading: BADNEWS DLL loaded and executed via DLL side-loading through legitimate applications.

### Credential Access
- **T1555.003** — Credentials from web browsers: dumped Chrome login data from `\AppData\Local\Google\Chrome\User Data\Default\Login Data`.
- **T1056.001** — Keylogging: BADNEWS/Ragnatela and Unknown Logger capture keystrokes.

### Discovery
- **T1083** — File and directory discovery: payloads search all fixed drives for files matching specified extension lists (documents, spreadsheets, databases).
- **T1680** — Local storage discovery: enumerated all available drives on the victim's machine.
- **T1518.001** — Security software discovery: scanned "Program Files" for "Total Security" (360 Total Security antivirus) installation path.
- **T1082** — System information discovery: collected computer name, OS version, and architecture type for C2 registration.
- **T1033** — System owner/user discovery: collected username and admin-privilege status.
- **T1016** — System network configuration discovery: Unknown Logger collected network configuration data.
- **T1120** — Peripheral device discovery: BADNEWS enumerated peripheral devices.
- **T1614** — System location discovery: QuasarRAT performed system location discovery.

### Lateral Movement
- **T1021.001** — Remote Desktop Protocol: attempted to use RDP for lateral movement within compromised networks.

### Collection
- **T1005** — Data from local system: collected and exfiltrated files from infected systems.
- **T1039** — Data from network shared drive: BADNEWS collected data from network shares.
- **T1025** — Data from removable media: BADNEWS collected data from removable media.
- **T1119** — Automated collection: developed file stealers to search C:\ and collect files with specified extensions; enumerated all drives, stored lists, and uploaded generated files to C2.
- **T1074.001** — Local data staging: copied all targeted files to a directory called "index" for eventual upload to C2.
- **T1113** — Screen capture: BADNEWS/Ragnatela captured screenshots of the victim's desktop.
- **T1125** — Video capture: QuasarRAT and VajraSpy capable of video/camera capture.
- **T1560** — Archive collected data: encrypted collected file paths with AES, then base64-encoded them before exfiltration.

### Command & Control
- **T1071.001** — Web protocols: BADNEWS and BackConfig communicate with C2 servers over HTTP/HTTPS.
- **T1132.001** — Standard encoding: used Base64 to encode C2 traffic.
- **T1573.001** — Symmetric cryptography: BADNEWS and NDiskMonitor use symmetric encryption for C2 communications.
- **T1102.001** — Dead drop resolver: hid base64-encoded and encrypted C2 server locations in comments on legitimate websites (blogs, forums).
- **T1102.002** — Bidirectional communication: BADNEWS used web services for bidirectional C2 communication.
- **T1105** — Ingress tool transfer: payloads download additional files and tools from C2 servers.
- **T1571** — Non-standard port: QuasarRAT used non-standard ports for C2.
- **T1095** — Non-application layer protocol: QuasarRAT used raw TCP for C2.
- **T1090** — Proxy: QuasarRAT used proxy capabilities for C2.
- **T1197** — BITS jobs: used Background Intelligent Transfer Service jobs to download malicious payloads, blending with legitimate Windows update traffic.

### Exfiltration
- **T1020** — Automated exfiltration: TINYTYPHON and file stealers automatically exfiltrated collected documents.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| BADNEWS | S0128 | Windows RAT — keylogging, screen capture, file collection, C2 via dead-drop resolvers | Custom |
| Ragnatela | (variant of S0128) | Updated BADNEWS variant — enhanced RAT with command execution, file upload, screenshot, keylogging | Custom |
| BackConfig | S0475 | Modular Windows backdoor — C2 over HTTP, scheduled tasks, DDE delivery | Custom |
| NDiskMonitor | S0272 | Windows backdoor — file discovery, system recon, encrypted C2 | Custom |
| TINYTYPHON | S0131 | Lightweight file exfiltration tool — automated document theft | Custom |
| Unknown Logger | S0130 | Keylogger and credential stealer — browser credentials, USB replication | Custom |
| AutoIt backdoor | S0129 | AutoIt-compiled backdoor — UAC bypass, PowerShell execution | Custom |
| VajraSpy | S9006 | Android RAT — contacts/SMS/call-log theft, WhatsApp/Signal interception, camera/mic capture, honey-trap distribution | Custom |
| QuasarRAT | S0262 | Open-source .NET RAT — RDP, keylogging, screen/video capture, credential theft | Public |
| PowerSploit | S0194 | PowerShell post-exploitation framework — credential dumping, code execution | Public |
| Meterpreter | (Metasploit) | Reverse shell / post-exploitation agent | Public |
| UPX | — | Executable packer | Public |
| Crypto Obfuscator | — | .NET obfuscation tool | Public |

> Note: Patchwork's defining characteristic is heavy reuse of publicly available code — exploit code from forums, open-source RATs (QuasarRAT), and public post-exploitation frameworks (PowerSploit, Meterpreter). Custom tools like BADNEWS are themselves built with significant copy-pasted components.

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Patchwork's techniques are relatively low-sophistication but high-impact through social engineering — emulate the full kill chain, not just the tooling.

Map Patchwork's signature plays to Decepticon's own capabilities:

- **Initial access — weaponized documents (T1566.001, T1566.002, T1203, T1204.002).** Use the payload-builder skill to craft **Office documents with embedded exploits** — prioritize Equation Editor (CVE-2017-11882) and OLE object (CVE-2017-0199) exploit chains, as these are Patchwork's most-used vectors. Build RTF and DOC lures impersonating target-relevant government/military documents (defense policy papers, personnel announcements, conference invitations). Stage tracking pixels (T1598.003) in initial phishing emails to profile which targets open messages before sending armed payloads.
- **Watering holes (T1189).** With the web-infrastructure skill, stand up a **fake news portal** mirroring Patchwork's Chinastrats-style sites — political news focused on the target's regional interests. Serve malicious PPS/PPSX files with embedded exploits to visitors. Use this as a secondary access vector alongside spearphishing.
- **DLL side-loading (T1574.001).** Emulate BADNEWS delivery by **side-loading a malicious DLL through a legitimate, signed application**. Identify a suitable LOLBin or vendor application in the target environment for the side-load. This is Patchwork's signature persistence and evasion mechanism.
- **Execution — scripting chain (T1059.001, T1059.003, T1059.005).** Mirror Patchwork's multi-stage execution: initial macro/exploit drops a VBS or JavaScript downloader, which invokes PowerShell (via PowerSploit) to fetch and execute the main implant. Use `powershell -ExecutionPolicy Bypass -WindowStyle Hidden` patterns consistent with the actor's tradecraft.
- **C2 — dead-drop resolvers and public RATs (T1102.001, T1071.001, T1132.001).** Deploy **QuasarRAT or Sliver** (c2 skill) as the primary implant over HTTPS. Implement a **dead-drop resolver** pattern: embed base64-encoded, encrypted C2 addresses in comments on legitimate websites (blogs, forums, social media) — this is BADNEWS's defining C2 mechanism. Encode C2 traffic with Base64 to match the actor's signature.
- **Collection — automated file theft (T1119, T1083, T1074.001, T1560).** Script an **automated file stealer** that enumerates all fixed drives, searches for documents by extension (`.doc`, `.docx`, `.xls`, `.xlsx`, `.pdf`, `.ppt`), stages them to a local directory, encrypts file paths with AES, base64-encodes the manifest, and uploads to C2. This directly replicates Patchwork's documented collection tradecraft.
- **Credential harvesting (T1555.003, T1056.001).** Deploy a keylogger module and **dump Chrome stored credentials** from `Login Data` — both are core BADNEWS/Unknown Logger capabilities. Use PowerSploit's credential modules for additional coverage.
- **Defense evasion (T1548.002, T1055.012, T1036.005).** Emulate the UAC bypass via **process hollowing into svchost.exe**, and masquerade payloads as legitimate software updates ("Baidu Software Update", "Net Monitor") in the Startup folder.
- **Android targeting (VajraSpy pattern).** If mobile is in scope, emulate the **honey-trap romance-scam delivery** of trojanized messaging apps. Build a convincing messaging-app shell that exfiltrates contacts, SMS, call logs, and messaging-app databases — mirroring VajraSpy's capabilities.
- **OPSEC note — copy-paste tradecraft.** Patchwork's weakness is poor operational security — they reuse infrastructure, borrow detectable public code, and once infected their own machine. When emulating, deliberately introduce some of these "sloppy" indicators (reused domains, known QuasarRAT signatures) to test whether the target's detection stack catches low-sophistication but persistent actors.

## Detection & defense

- **Document exploit chains (T1203 / CVE-2017-11882, CVE-2017-0199):** Patch Microsoft Office, especially the Equation Editor (EQNEDT32.EXE — remove or disable it entirely); enable Attack Surface Reduction (ASR) rules blocking Office child processes, macro execution from the internet, and OLE/DDE exploitation; monitor for `EQNEDT32.EXE` spawning child processes.
- **DLL side-loading (T1574.001):** Monitor for DLLs loaded from unusual paths by signed executables; baseline legitimate DLL load locations for common applications; alert on unsigned DLLs in application directories; use application whitelisting.
- **Spearphishing / social engineering (T1566.001, T1566.002):** Deploy email gateway filtering for weaponized Office attachments (RTF, DOC, PPS); strip or sandbox macros; block tracking pixels from unknown senders; train high-value personnel on spearphishing recognition, particularly lures themed around defense/military/government topics.
- **PowerShell abuse (T1059.001):** Enable PowerShell ScriptBlock and Module logging; constrain execution policies; alert on `powershell.exe` with `-ExecutionPolicy Bypass`, `-WindowStyle Hidden`, or downloading cradles (`IEX`, `Invoke-Expression`, `DownloadString`); monitor for PowerSploit module loads.
- **Dead-drop resolver C2 (T1102.001):** Monitor for beaconing to blog/social-media comment sections from endpoints that don't normally access those services; inspect HTTP responses from blog platforms for base64-encoded strings in comment fields; baseline and alert on anomalous outbound web traffic patterns.
- **Process hollowing / UAC bypass (T1055.012, T1548.002):** Monitor for `svchost.exe` instances not spawned by `services.exe`; enable Sysmon Event ID 25 (process tampering); alert on UAC bypass techniques via EventID 1 with suspicious parent-child relationships.
- **Automated file collection (T1119, T1083):** Alert on processes performing rapid sequential file enumeration across multiple drives; monitor for creation of staging directories with aggregated document files; DLP rules for bulk document access by non-standard processes.
- **Credential theft (T1555.003):** Monitor access to Chrome `Login Data` SQLite database; alert on processes reading browser credential stores outside of browser executables; protect credential stores with endpoint security tooling.
- **Masquerading (T1036.005):** Audit Startup folder and Run keys for entries with names mimicking legitimate software ("Baidu Software Update", "Net Monitor", "microsoft_network.exe"); alert on executables in startup locations with names that don't match signed vendor binaries.
- **BITS abuse (T1197):** Monitor for unusual BITS job creation via `bitsadmin` or COM interfaces; alert on BITS transfers to/from uncommon domains; log BITS job creation events.
- **Mobile / VajraSpy (Android):** Enforce MDM policies restricting sideloaded apps; monitor for apps requesting excessive permissions (SMS, call log, camera, microphone, contacts); review enterprise app stores for messaging-app clones.

## Sources

- https://attack.mitre.org/groups/G0040/
- https://web.archive.org/web/20180825085952/https://s3-us-west-2.amazonaws.com/cymmetria-blog/public/Unveiling_Patchwork.pdf
- https://securelist.com/the-dropping-elephant-actor/75328/
- http://www.symantec.com/connect/blogs/patchwork-cyberespionage-group-expands-targets-governments-wide-range-industries
- https://documents.trendmicro.com/assets/tech-brief-untangling-the-patchwork-cyberespionage-group.pdf
- https://www.volexity.com/blog/2018/06/07/patchwork-apt-group-targets-us-think-tanks/
- https://researchcenter.paloaltonetworks.com/2018/03/unit42-patchwork-continues-deliver-badnews-indian-subcontinent/
- https://unit42.paloaltonetworks.com/updated-backconfig-malware-targeting-government-and-military-organizations/
- https://www.forcepoint.com/sites/default/files/resources/files/forcepoint-security-labs-monsoon-analysis-report.pdf
- https://web.archive.org/web/20140424084220/http://enterprise-manage.norman.c.bitbit.net/resources/files/Unveiling_an_Indian_Cyberattack_Infrastructure.pdf
- https://blog.malwarebytes.com/threat-intelligence/2022/01/patchwork-apt-caught-in-its-own-web/
- https://securityaffairs.co/wordpress/126524/apt/patchwork-apt-ragnatela-rat.html
- https://www.welivesecurity.com/en/eset-research/vajraspy-patchwork-espionage-apps/
- https://socradar.io/dark-web-profile-patchwork-apt/
