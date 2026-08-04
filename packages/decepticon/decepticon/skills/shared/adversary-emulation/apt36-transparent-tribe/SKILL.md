---
name: apt36-transparent-tribe
description: "Adversary-emulation profile for APT36 (G0134 / Transparent Tribe / Mythic Leopard / ProjectM / COPPER FIELDSTONE), a Pakistan-linked cyber-espionage actor targeting Indian government, defense, and diplomatic entities."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "APT36, Transparent Tribe, Mythic Leopard, ProjectM, COPPER FIELDSTONE, Earth Karkaddan, G0134, Pakistan ISI espionage emulation, CrimsonRAT, ObliqueRAT, CapraRAT, Peppy, Operation C-Major, India military targeting, spearphishing with weaponized Office documents, Android mobile surveillance, honey trap social engineering, USB removable media spreading, watering hole attacks, South Asian cyber espionage"
  tags: apt36, transparent-tribe, mythic-leopard, projectm, copper-fieldstone, pakistan, espionage, nation-state, g0134, adversary-emulation, mitre-attack, crimsonrat, obliquerat, caprarat, south-asia
  mitre_attack: T1583.001, T1584.001, T1587.003, T1608.001, T1608.004, T1566.001, T1566.002, T1189, T1091, T1204.001, T1204.002, T1059.001, T1059.003, T1059.005, T1203, T1106, T1547.001, T1564.001, T1036.005, T1027.002, T1027.003, T1027.004, T1027.013, T1140, T1112, T1070.004, T1497.001, T1497.003, T1555.003, T1056.001, T1083, T1057, T1082, T1033, T1016, T1518.001, T1012, T1120, T1680, T1614, T1124, T1010, T1018, T1021.001, T1005, T1025, T1113, T1125, T1123, T1114.001, T1115, T1074.001, T1071.001, T1095, T1568, T1105, T1571, T1132.001, T1041, T1020, T1030
---

# APT36 (Transparent Tribe, Mythic Leopard, ProjectM, COPPER FIELDSTONE) — Adversary Emulation Profile

APT36 (MITRE ATT&CK **G0134**) is a suspected Pakistan-based cyber-espionage group active since at least **2013**, primarily targeting diplomatic, defense, and research organizations in India and Afghanistan. The group is believed to operate in alignment with Pakistan's Inter-Services Intelligence (ISI) strategic interests, conducting persistent intelligence collection against India's government, military, aerospace, and — more recently — educational and startup sectors. APT36 is characterized by heavy reliance on spearphishing with weaponized Office documents delivering its signature **CrimsonRAT** (.NET implant), Android mobile surveillance via **CapraRAT**, watering hole attacks, social engineering through honey traps and fake personas, and USB-based lateral movement — a pragmatic, high-volume approach tuned for the India-Pakistan geopolitical theater.

## Attribution & motivation

- **Sponsor / nation:** Pakistan — suspected linkage to Inter-Services Intelligence (ISI). Infrastructure analysis has revealed Pakistani Standard Time (`Asia/Karachi`) timezone artifacts embedded in delivered payloads and server configurations.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** aligned with Pakistani state interests — military, diplomatic, defense-industrial, and political intelligence targeting India. Campaigns consistently exploit India-Pakistan geopolitical events (border tensions, terrorist incidents, Kashmir conflict) as lure themes.
- **Attribution confidence:** **Moderate-High.** Based on consistent multi-vendor reporting (Proofpoint, Kaspersky, Cisco Talos, Trend Micro, BlackBerry, Check Point, CrowdStrike, Secureworks), infrastructure analysis showing Pakistan nexus, and operational patterns sustained over a decade. No formal government indictments, but multiple threat intelligence firms converge on Pakistan-state attribution.

## Targeting

- **Sectors:** Government and diplomatic bodies; defense, military, and aerospace (including Department of Defense Production and state-owned defense electronics firms); research and academic institutions (Indian universities and students since 2022); startups and technology firms (since 2025); NGOs and social activists.
- **Regions:** Heavily focused on **India** — the primary target across all campaigns. Secondary targeting of **Afghanistan** and other South Asian nations. Occasional activity against Pakistani dissidents and social activists.
- **Victim profile:** High-value government and military personnel whose documents, credentials, communications, and device data yield strategic intelligence. Frequently targets individuals via spearphishing with defense/government-themed lures, fake Kavach MFA installer downloads, and honey-trap social media profiles aimed at military personnel.

## Notable campaigns

- **2013-2016 — Operation Transparent Tribe / Operation C-Major.** Proofpoint documented the group's initial campaigns using spearphishing with weaponized RTF/Office documents exploiting CVE-2012-0158 and CVE-2010-3333, delivering CrimsonRAT and other payloads to Indian diplomatic and military targets. Infrastructure mimicked government and defense file-sharing sites. (Proofpoint)
- **2016-2018 — Indian military and government spearphishing waves.** Sustained spearphishing campaigns targeting Indian military and governmental organizations with malicious documents themed around defense operations and fake job offers. Expanded use of CrimsonRAT variants and DarkComet/njRAT as secondary tools. (Unit 42 / Trend Micro)
- **2019-2020 — COVID-19 themed lures and Kavach impersonation.** APT36 exploited the pandemic with COVID-19 health advisory decoy documents targeting Indian government employees. Concurrently began distributing fake Kavach MFA application installers — Kavach is widely used by government/military personnel to access Indian government IT resources. (Cisco Talos)
- **2020-2022 — Mobile surveillance via CapraRAT.** Trend Micro and SentinelLabs documented APT36 deploying CapraRAT (modified AndroRAT) disguised as YouTube and messaging apps, targeting Indian military and government personnel's Android devices for SMS theft, call recording, location tracking, and contact exfiltration. (Trend Micro / SentinelLabs)
- **2021-2022 — Campaign C0011: Indian education sector.** Cisco Talos documented a campaign (MITRE C0011, December 2021 – July 2022) targeting Indian students and educational institutions with updated CrimsonRAT delivered via malicious VBA macros and spearphishing links from typo-squatted education-themed domains with SSL certificates. (Cisco Talos)
- **2023-2024 — ElizaRAT and cross-platform expansion.** Check Point Research documented the evolution of ElizaRAT, a newer Windows RAT initiated via CPL files distributed through Google Storage links. The group expanded to cross-platform tooling using Python, Golang, and Rust, and began abusing cloud services (Telegram, Discord, Slack, Google Drive) for C2. BlackBerry observed targeting of Indian aerospace and defense production stakeholders. (Check Point / BlackBerry)
- **2025 — Pahalgam Terror Attack lure.** APT36 weaponized a fabricated report about the Pahalgam Terror Attack in Jammu & Kashmir to deliver CrimsonRAT to Indian defense personnel, demonstrating continued exploitation of real-world geopolitical events. (D09r / CYFIRMA)
- **2025-2026 — Weaponized LNK and startup targeting.** The group evolved delivery to oversized LNK shortcut files (>2MB, embedding full PDF decoys) with HTA-based fileless execution, and expanded targeting to India's startup ecosystem alongside traditional government/defense targets. (Acronis / Cyberwarzone)

## TTPs by ATT&CK tactic

### Resource Development
- **T1583.001** — Acquire Infrastructure: Domains: registered domains mimicking file-sharing, government, defense, and educational websites for use in phishing and watering hole campaigns.
- **T1584.001** — Compromise Infrastructure: Domains: compromised legitimate domains to host malicious payloads and redirect targets.
- **T1587.003** — Develop Capabilities: Digital Certificates: established SSL certificates on typo-squatted domains (e.g., education-themed domains in C0011).
- **T1608.001** — Stage Capabilities: Upload Malware: hosted malicious documents and payloads on attacker-registered and compromised domains.
- **T1608.004** — Stage Capabilities: Drive-by Target: set up websites with malicious hyperlinks and iframes to deliver Crimson, njRAT, and other tools via watering hole attacks.

### Initial Access
- **T1566.001** — Spearphishing Attachment: primary initial access vector — weaponized Office documents (RTF, DOCX with VBA macros, XLSX), ZIP archives containing malicious LNK files, and PDF-embedded executables delivered via email.
- **T1566.002** — Spearphishing Link: embedded links to malicious downloads (fake Kavach installers, Google Storage-hosted CPL files) in spearphishing emails.
- **T1189** — Drive-by Compromise: maintained websites with malicious iframes and hyperlinks to infect visitors with CrimsonRAT and njRAT.

### Execution
- **T1204.001 / T1204.002** — User Execution: Malicious Link / Malicious File: relies on targets opening weaponized documents, clicking malicious links, or executing disguised payloads (fake Kavach installers, oversized LNK files).
- **T1059.005** — Visual Basic: crafts VBS-based malicious documents; VBA macros in Office lures are the primary CrimsonRAT delivery mechanism.
- **T1059.003** — Windows Command Shell: CrimsonRAT, Peppy, DarkComet, and njRAT execute commands via `cmd.exe` / COMSPEC.
- **T1059.001** — PowerShell: njRAT leverages PowerShell for execution.
- **T1203** — Exploitation for Client Execution: exploited CVE-2012-0158 and CVE-2010-3333 in Office documents for code execution.
- **T1106** — Native API: njRAT uses native Windows APIs for execution and system interaction.

### Persistence
- **T1547.001** — Registry Run Keys / Startup Folder: CrimsonRAT, ObliqueRAT, DarkComet, and njRAT all establish persistence via registry Run keys and Startup folder entries.

### Defense Evasion
- **T1027.013** — Encrypted/Encoded File: drops encoded executables on compromised hosts; njRAT uses encoded payloads.
- **T1027.002** — Software Packing: DarkComet uses software packing for evasion.
- **T1027.003** — Steganography: ObliqueRAT hides payloads in image files using steganography.
- **T1027.004** — Compile After Delivery: njRAT compiles payloads post-delivery to evade static detection.
- **T1140** — Deobfuscate/Decode Files or Information: CrimsonRAT decodes its encoded PE payload prior to execution.
- **T1036.005** — Match Legitimate Resource Name or Location: mimics legitimate Windows directories using identical icons and folder names; oversized LNK files embed real PDF documents to appear legitimate.
- **T1564.001** — Hidden Files and Directories: hides legitimate directories and replaces them with malicious copies of the same name.
- **T1112** — Modify Registry: CrimsonRAT and njRAT modify registry keys for persistence tracking and configuration storage.
- **T1070.004** — File Deletion: CrimsonRAT and njRAT delete files to remove indicators from compromised hosts.
- **T1497.001** — System Checks: ObliqueRAT performs system-environment checks to detect sandboxes/VMs.
- **T1497.003** — Time Based Checks: CrimsonRAT waits at least 15 days after installation before downloading the final payload to evade sandbox analysis.

### Credential Access
- **T1555.003** — Credentials from Web Browsers: CrimsonRAT and njRAT steal saved credentials from web browsers.
- **T1056.001** — Keylogging: CrimsonRAT, Peppy, DarkComet, and njRAT all include dedicated keylogging modules.

### Discovery
- **T1083** — File and Directory Discovery: CrimsonRAT, ObliqueRAT, and Peppy enumerate files/directories and search for files matching target extensions (documents, spreadsheets, PDFs).
- **T1057** — Process Discovery: CrimsonRAT, ObliqueRAT, DarkComet, and njRAT list running processes.
- **T1082** — System Information Discovery: all primary tools collect host name, OS version, and system configuration.
- **T1033** — System Owner/User Discovery: CrimsonRAT, ObliqueRAT, DarkComet, and njRAT identify the current user.
- **T1016** — System Network Configuration Discovery: CrimsonRAT collects MAC address and LAN IP.
- **T1518.001** — Security Software Discovery: CrimsonRAT collects information about installed antivirus products; malware adapts persistence strategy based on detected AV.
- **T1012** — Query Registry: CrimsonRAT and njRAT query registry for installation timestamps and configuration.
- **T1120** — Peripheral Device Discovery: CrimsonRAT and ObliqueRAT discover pluggable/removable drives for data collection and spreading.
- **T1680** — Local Storage Discovery: CrimsonRAT collects disk drive information.
- **T1614** — System Location Discovery: CrimsonRAT identifies the geographical location of victim hosts.
- **T1124** — System Time Discovery: CrimsonRAT determines the date and time on compromised hosts.
- **T1010** — Application Window Discovery: njRAT enumerates visible application windows.
- **T1018** — Remote System Discovery: njRAT discovers remote systems on the network.

### Lateral Movement
- **T1091** — Replication Through Removable Media: CrimsonRAT spreads across systems by infecting removable media (USB drives) — a key capability for reaching air-gapped military networks.
- **T1021.001** — Remote Desktop Protocol: DarkComet and njRAT provide RDP-based remote access capabilities.

### Collection
- **T1005** — Data from Local System: CrimsonRAT and njRAT collect files and information from compromised hosts.
- **T1025** — Data from Removable Media: CrimsonRAT and ObliqueRAT contain modules to search and collect data from USB/removable drives.
- **T1113** — Screen Capture: CrimsonRAT, ObliqueRAT, and Peppy capture screenshots.
- **T1125** — Video Capture: CrimsonRAT, ObliqueRAT, DarkComet, and njRAT capture webcam video.
- **T1123** — Audio Capture: CrimsonRAT and DarkComet perform audio surveillance using microphones.
- **T1056.001** — Keylogging: keystroke capture for intelligence collection (see Credential Access).
- **T1114.001** — Local Email Collection: CrimsonRAT contains a command to collect and exfiltrate emails from Outlook.
- **T1115** — Clipboard Data: DarkComet captures clipboard contents.
- **T1074.001** — Local Data Staging: ObliqueRAT stages collected data locally before exfiltration.

### Command & Control
- **T1071.001** — Web Protocols: CrimsonRAT, Peppy, DarkComet, and njRAT use HTTP/HTTPS for C2 communications and payload downloads.
- **T1095** — Non-Application Layer Protocol: CrimsonRAT uses a custom TCP protocol for C2.
- **T1568** — Dynamic Resolution: uses dynamic DNS services for C2 infrastructure.
- **T1105** — Ingress Tool Transfer: CrimsonRAT, Peppy, DarkComet, and njRAT retrieve additional tools and payloads from C2 servers.
- **T1571** — Non-Standard Port: njRAT communicates over non-standard ports.
- **T1132.001** — Standard Encoding: njRAT uses base64 and other standard encoding for data in transit.

### Exfiltration
- **T1041** — Exfiltration Over C2 Channel: CrimsonRAT and njRAT exfiltrate stolen data over their primary C2 channels.
- **T1020** — Automated Exfiltration: Peppy automatically exfiltrates collected files to C2.
- **T1030** — Data Transfer Size Limits: ObliqueRAT limits data transfer sizes during exfiltration.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| Crimson / CrimsonRAT | S0115 | .NET Windows RAT — flagship implant (keylogging, screen/video/audio capture, USB spreading, email collection) | Custom |
| ObliqueRAT | S0644 | Windows RAT with steganography delivery, USB data collection, sandbox evasion | Custom |
| Peppy | S0643 | Python-based Windows RAT — keylogging, screen capture, automated file exfiltration | Custom |
| CapraRAT | (no ATT&CK software ID) | Android RAT (modified AndroRAT) — SMS/call/contact theft, location tracking, audio recording; disguised as YouTube/messaging apps | Custom |
| ElizaRAT | (no ATT&CK software ID) | Windows RAT — CPL-initiated, Google Storage distribution, evolving C2 (Telegram/Slack/Google Drive) | Custom |
| Limepad | (no ATT&CK software ID) | Windows stealer companion to ElizaRAT | Custom |
| DarkComet | S0334 | Windows RAT with RDP, keylogging, video/audio capture | Public |
| njRAT | S0385 | Windows RAT with RDP, keylogging, USB spreading, browser credential theft | Public |

> Note: CapraRAT, ElizaRAT, and Limepad are well-documented custom APT36 tools but do not yet have assigned MITRE ATT&CK software IDs. CrimsonRAT (S0115) is the group's signature implant used continuously since at least 2016.

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Mobile (CapraRAT-style) emulation requires explicit mobile-device scope authorization.

Map APT36's signature plays to Decepticon's own capabilities:

- **Initial access — spearphishing with weaponized documents (T1566.001, T1566.002, T1204.002).** Use the phishing skill to craft **government/defense-themed lure documents** (defense advisories, HR circulars, Kavach MFA installer downloads, current-event exploitation). Build macro-laden DOCX/XLSX delivering a .NET payload (CrimsonRAT analog) or LNK-in-ZIP with embedded PDF decoy triggering an HTA downloader via `mshta.exe`. Register typo-squatted domains mimicking government file-sharing or education portals; stage payloads on attacker infrastructure with SSL certificates.
- **Watering hole (T1189, T1608.004).** With the web-attack skill, stand up cloned government/defense/research websites with malicious iframes or injected download links delivering the RAT payload — reproducing APT36's documented watering hole pattern.
- **Execution — VBA macro chain (T1059.005, T1203).** Weaponize Office documents with VBA macros that decode and drop the implant. For legacy emulation, craft RTF documents exploiting CVE-2012-0158 (Equation Editor) in lab environments. For modern emulation, use the LNK + HTA + `mshta.exe` chain with fileless in-memory payload loading.
- **Persistence (T1547.001).** The implant should establish persistence via registry Run keys (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) and/or Startup folder — mirroring CrimsonRAT's documented persistence mechanism. Adapt persistence strategy based on detected AV product (APT36's 2025-2026 pattern).
- **Defense evasion (T1027.003, T1027.013, T1497.003).** Implement a **15-day sleep timer** before deploying the final payload (CrimsonRAT's sandbox evasion). Use steganography to embed payloads in images (ObliqueRAT pattern). Encode/encrypt dropped executables and decode at runtime. Use oversized LNK files with embedded legitimate PDFs to evade heuristic scanning.
- **Collection & surveillance (T1113, T1125, T1123, T1056.001, T1025).** The RAT emulation should include **screen capture, webcam capture, audio recording, keylogging, and USB drive enumeration/collection** — the full CrimsonRAT surveillance suite. Include Outlook email collection (T1114.001) for high-value targets. Search for documents matching defense/government file patterns (.pdf, .doc, .xls, .ppt).
- **USB spreading (T1091, T1025).** Emulate CrimsonRAT's removable-media spreading: monitor for USB insertion, copy the implant to removable drives with autorun or masqueraded filenames, and collect documents from connected media — critical for simulating air-gap bridging attacks against military targets.
- **C2 (T1071.001, T1095, T1568).** Use a **.NET-based custom TCP C2** as the primary channel (CrimsonRAT signature), with HTTP/HTTPS fallback. Register dynamic DNS domains for C2 resolution. For ElizaRAT emulation, add a secondary C2 channel over **Telegram, Slack, or Google Drive** API — reproducing the 2023-2024 cloud-service abuse pattern.
- **Mobile emulation (CapraRAT).** Where Android devices are in scope, deploy a test APK mimicking a legitimate app (YouTube, messaging) that performs SMS/contact/call-log exfiltration, location tracking, and ambient audio recording — reproducing CapraRAT's documented capabilities against military personnel's personal devices.
- **Exfiltration (T1041, T1020, T1030).** Exfiltrate collected intelligence over the C2 channel. Implement size-limited transfers (ObliqueRAT pattern) and automated file exfiltration (Peppy pattern) to reproduce the group's operational tempo.

## Detection & defense

- **Spearphishing / Office macro delivery (T1566.001, T1204.002, T1059.005):** Disable Office macros for external documents (or enforce macro signing); deploy email gateway filtering for malicious attachments (RTF, DOCX with OLE objects, ZIP-wrapped LNK files); alert on `mshta.exe` execution from email-sourced paths; user awareness training on government/defense-themed lure recognition.
- **Watering hole / drive-by (T1189, T1608.004):** Web proxy filtering and URL reputation scoring for government/defense cloned sites; monitor for iframe injection on organizational web properties; browser isolation for high-risk users.
- **CrimsonRAT persistence (T1547.001):** Monitor registry Run keys and Startup folder for new entries with suspicious .NET executables; alert on new scheduled tasks or registry modifications by recently-dropped binaries; behavioral detection for the 15-day delayed-execution pattern (T1497.003).
- **USB spreading / removable media (T1091, T1025):** Enforce USB device control policies (whitelist authorized devices); disable AutoRun/AutoPlay; monitor for new executables written to removable drives; DLP monitoring for sensitive document types copied to USB.
- **Keylogging and surveillance (T1056.001, T1113, T1125, T1123):** EDR alerting on processes accessing webcam/microphone APIs, screen-capture APIs, and low-level keyboard hooks; monitor for newly-dropped DLLs or executables in user-writable paths that register input hooks.
- **CrimsonRAT C2 (T1095, T1071.001, T1568):** Network detection for CrimsonRAT's custom TCP protocol signatures; monitor for dynamic DNS resolution to known APT36 infrastructure patterns; TLS inspection for C2 beacons to recently-registered domains; alert on processes making HTTP requests to domains matching government/defense typo-squatting patterns.
- **Cloud-service C2 abuse (ElizaRAT pattern):** Monitor for anomalous Telegram Bot API, Slack webhook, or Google Drive API usage from endpoint processes that are not sanctioned applications; alert on CPL file execution from Google Storage download paths.
- **Mobile device targeting (CapraRAT):** Mobile device management (MDM) enforcement preventing sideloaded APKs; Google Play Protect / mobile threat defense for RAT detection; educate military/government personnel on fake app distribution via social engineering and honey-trap profiles.
- **Credential theft (T1555.003):** Browser credential monitoring; enforce credential manager protections; alert on bulk browser database access by non-browser processes.
- **Exfiltration (T1041, T1020):** DLP/egress monitoring for bulk document exfiltration over HTTP/TCP channels; baseline network traffic for endpoints and alert on sustained upload patterns to dynamic DNS destinations or cloud storage services.

## Sources

- https://attack.mitre.org/groups/G0134/
- https://attack.mitre.org/software/S0115/
- https://attack.mitre.org/software/S0644/
- https://attack.mitre.org/software/S0643/
- https://www.proofpoint.com/sites/default/files/proofpoint-operation-transparent-tribe-threat-insight-en.pdf
- https://securelist.com/transparent-tribe-part-1/98127/
- https://blog.talosintelligence.com/2021/05/transparent-tribe-infra-and-targeting.html
- https://blog.talosintelligence.com/2022/07/transparent-tribe-targets-education.html
- https://blog.talosintelligence.com/2021/02/obliquerat-new-campaign.html
- https://blog.talosintelligence.com/transparent-tribe-new-campaign/
- https://www.trendmicro.com/en_us/research/22/a/investigating-apt36-or-earth-karkaddans-attack-chain-and-malware.html
- https://research.checkpoint.com/2024/the-evolution-of-transparent-tribes-new-malware/
- https://blogs.blackberry.com/en/2024/05/transparent-tribe-targets-indian-government-defense-and-aerospace-sectors
- https://unit42.paloaltonetworks.com/unit42-projectm-link-found-between-pakistani-actor-and-operation-transparent-tribe/
- https://www.secureworks.com/research/threat-profiles/copper-fieldstone
- https://www.cyfirma.com/research/apt-profile-transparent-tribe-aka-apt36/
- https://socradar.io/blog/dark-web-profile-apt36/
- https://www.acronis.com/en/tru/posts/new-year-new-sector-transparent-tribe-targets-indias-startup-ecosystem/
