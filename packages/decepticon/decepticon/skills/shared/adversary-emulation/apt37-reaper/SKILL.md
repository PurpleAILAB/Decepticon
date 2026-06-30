---
name: apt37-reaper
description: "Adversary-emulation profile for APT37 (G0067 / Reaper / ScarCruft / Ricochet Chollima / InkySquid / Group123), North Korea's RGB cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "APT37, Reaper, ScarCruft, Ricochet Chollima, InkySquid, Group123, TEMP.Reaper, G0067, North Korean RGB espionage emulation, RoKRAT, BLUELIGHT, Chinotto, Konni, DOGCALL, HWP spearphishing, Flash/IE zero-day, watering hole, strategic web compromise, Bluetooth harvesting, NK defector surveillance, South Korea targeting"
  tags: apt37, reaper, scarcruft, ricochet-chollima, inkysquid, group123, north-korea, rgb, espionage, nation-state, g0067, adversary-emulation, mitre-attack
  mitre_attack: T1548.002, T1071.001, T1071.003, T1123, T1547.001, T1059, T1059.003, T1059.005, T1059.006, T1555.003, T1555.004, T1005, T1561.002, T1189, T1203, T1105, T1559.002, T1036.001, T1106, T1027, T1027.003, T1027.013, T1120, T1566.001, T1057, T1055, T1053.005, T1082, T1033, T1529, T1204.002, T1102.002, T1113, T1115, T1056.001, T1539, T1070.004, T1140, T1480.001, T1497.001, T1622, T1010, T1012, T1016, T1083, T1124, T1518.001, T1560, T1560.001, T1560.003, T1074.001, T1041, T1048.003, T1567.002, T1112
---

# APT37 (Reaper, ScarCruft, Ricochet Chollima, InkySquid) — Adversary Emulation Profile

APT37 (MITRE ATT&CK **G0067**) is a North Korean state-sponsored cyber-espionage group active since at least 2012. Tracked as ScarCruft (Kaspersky), Reaper (FireEye), InkySquid (Volexity), Group123 (Cisco Talos), TEMP.Reaper, and Ricochet Chollima (CrowdStrike), APT37 primarily targets South Korean government, military, media, and defector communities, with expanding operations into Japan, Vietnam, the Middle East, and Europe. The group is characterized by aggressive exploitation of zero-day vulnerabilities in Adobe Flash Player, Internet Explorer, and Microsoft Edge; heavy use of weaponized Hangul Word Processor (HWP) documents; strategic web compromises (watering holes); a diverse custom malware arsenal (RoKRAT, BLUELIGHT, Chinotto, Dolphin, DOGCALL); and C2 over legitimate cloud services (Dropbox, pCloud, Yandex, Box, Google Drive). Unlike the higher-profile Lazarus Group, APT37 focuses on targeted intelligence collection and defector surveillance rather than financial theft or destructive operations.

## Attribution & motivation

- **Sponsor / nation:** Democratic People's Republic of Korea (North Korea) — Reconnaissance General Bureau (RGB). FireEye's 2018 report assessed APT37 as a North Korean state-sponsored group with "high confidence," based on malware compilation timestamps aligned with Pyongyang working hours (UTC+8:30/+9), Korean-language resources in binaries, targeting patterns consistent with DPRK state interests, and overlapping infrastructure with other attributed DPRK operations.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — surveillance of North Korean defectors, journalists covering DPRK affairs, and human-rights activists; collection of South Korean military, government, and diplomatic intelligence. Secondary missions include **pre-positioning for destructive operations** (MBR-wiping malware capability) and **technology/defense intelligence collection** from aerospace, chemicals, electronics, and manufacturing sectors.
- **Attribution confidence:** **High.** FireEye's 2018 "APT37: The Overlooked North Korean Actor" report, Kaspersky's ScarCruft tracking (Operation Daybreak, Bluetooth harvester), Cisco Talos "Korea in the Crosshairs," Volexity's InkySquid browser-exploit research, and consistent multi-vendor reporting over a decade.

## Targeting

- **Sectors:** Government and diplomatic bodies; military and defense; media and journalism (specifically reporters covering North Korea); **North Korean defectors, refugees, and human-rights organizations**; chemicals, electronics, manufacturing, aerospace, automotive, and healthcare; academic and research institutions.
- **Regions:** Primary focus on **South Korea**; expanded since 2017 to **Japan, Vietnam, Middle East (Kuwait, other Gulf states), Russia (NPO Mashinostroyeniya breach), India, Nepal, Romania, Czech Republic, and Poland**.
- **Victim profile:** Individuals and organizations with intelligence value to the DPRK regime — defectors and their support networks, journalists and NGOs reporting on North Korean affairs, ROK military and government officials, and sector-specific targets for technology acquisition. Frequently targets users of Hangul Word Processor (HWP), the dominant office suite in South Korean government and organizations.

## Notable campaigns

- **2016-03 — Operation Daybreak.** Kaspersky documented a watering-hole campaign exploiting a zero-day Adobe Flash Player vulnerability (CVE-2016-4171) to deliver malware. The RICECURRY JavaScript profiler fingerprinted visitors to filter and deliver exploits only to relevant targets. High-profile victims in South Korea. (securelist.com)
- **2017 — Operation Erebus.** Watering-hole campaign exploiting CVE-2016-4117 (Adobe Flash) against a broader set of South Korean business targets. Delivered malware through compromised websites frequented by targets of interest. Ran concurrently with continued targeted operations. (FireEye / thesecmaster.com)
- **2016-2018 — Golden Time, Evil New Year, FreeMilk, Are you Happy?, North Korean Human Rights, Evil New Year 2018.** Series of campaigns documented by FireEye and Cisco Talos targeting South Korean entities with spearphishing (weaponized HWP and Office documents), delivering RoKRAT, DOGCALL, NavRAT, and other implants. "Are you Happy?" included destructive MBR-wiping capability. (FireEye APT37 report / Cisco Talos)
- **2017 — Expansion beyond the Korean peninsula.** APT37 broadened targeting to Japan, Vietnam, and the Middle East, including chemicals, electronics, manufacturing, aerospace, automotive, and healthcare verticals. (FireEye)
- **2019 — Bluetooth harvester / ScarCruft evolution.** Kaspersky identified APT37 deploying a Bluetooth device harvester using Windows Bluetooth APIs to enumerate connected devices, alongside multi-stage downloaders with UAC bypass and steganography delivery. Targeted NK defectors and human-rights activists. (securelist.com)
- **2021 — Chinotto multi-platform campaign.** Kaspersky documented APT37 targeting South Korean journalists, defectors, and human-rights activists via watering holes, spearphishing, and smishing, delivering the Chinotto malware family on both Windows and Android. Operators maintained persistence for months before deploying the final payload. (Kaspersky / bleepingcomputer.com)
- **2021 — InkySquid browser exploits (IE/Edge zero-days).** Volexity documented APT37 compromising a South Korean news site to deliver exploits for Internet Explorer (CVE-2020-1380) and Microsoft Edge (CVE-2021-26411), deploying BLUELIGHT and Cobalt Strike. (Volexity)
- **2021-2022 — NPO Mashinostroyeniya breach.** ScarCruft compromised Russia's leading missile manufacturer NPO Mash, maintaining access from late 2021 through May 2022 for intelligence collection on missile technology. (SentinelLabs / socradar.io)
- **2022-2023 — Oversized LNK pivot and GOLDBACKDOOR.** APT37 shifted delivery from malicious documents to oversized LNK files, deploying GOLDBACKDOOR against South Korean journalists (Stairwell, 2022) and continuing with ROKRAT delivery chains via LNK lures (Check Point, 2023).
- **2023 — M2RAT and FadeStealer.** New malware families deployed: M2RAT for Windows/mobile data theft bypassing AV/IDS (AhnLab), and FadeStealer for comprehensive surveillance including audio recording, keylogging, screenshot capture, and device monitoring with RAR-based exfiltration. (AhnLab / Zscaler)
- **2025 — KoSpy Android spyware.** Lookout attributed (medium confidence) mobile spyware KoSpy to ScarCruft, first observed March 2022 and active through 2025, collecting SMS, call logs, location, audio, and screenshots from Android devices via dynamically loaded plugins. (Lookout)

## TTPs by ATT&CK tactic

### Initial Access
- **T1566.001** — Spearphishing attachments: weaponized HWP (Hangul Word Processor) documents and Microsoft Office files with malicious macros/VBA/OLE, the group's signature delivery vector.
- **T1189** — Drive-by compromise: strategic web compromises (watering holes) of South Korean websites, including news sites, with RICECURRY JavaScript profiling to selectively deliver Flash/IE/Edge exploits.
- **T1204.002** — User execution of malicious files: relies on victims opening spearphishing attachments (HWP, DOC, XLS, LNK files).
- **T1559.002** — Dynamic Data Exchange (DDE): used in Operation Daybreak-era lures to execute commands via Word DDE fields.

### Execution
- **T1203** — Exploitation for client execution: zero-day and N-day exploitation of Adobe Flash Player (CVE-2016-4117, CVE-2016-4171, CVE-2018-4878), Microsoft Word (CVE-2017-0199), Internet Explorer (CVE-2020-1380), and Microsoft Edge (CVE-2021-26411).
- **T1059 / .003 / .005 / .006** — Command and scripting interpreter: Windows Command Shell for post-compromise commands, VBScript/VBA for macro-based execution and shellcode decoding, Python and Ruby scripts for payload execution (InkySquid campaigns).
- **T1106** — Native API: direct use of Windows APIs (VirtualAlloc, WriteProcessMemory, CreateRemoteThread) for process injection and payload staging.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: persistence via `HKCU\Software\Microsoft\CurrentVersion\Run\` registry keys.
- **T1053.005** — Scheduled tasks: creation of scheduled tasks to run malicious scripts on compromised hosts (BLUELIGHT delivery).

### Privilege Escalation
- **T1548.002** — UAC bypass: initial dropper includes functionality to bypass Windows User Account Control for higher-privilege payload execution.
- **T1055** — Process injection: injects malware (RoKRAT) into `cmd.exe` using VirtualAlloc/WriteProcessMemory/CreateRemoteThread for execution in a legitimate process context.

### Defense Evasion
- **T1027 / .003 / .013** — Obfuscation: string and payload obfuscation; **steganography** (shellcode embedded in images delivered to victims); encrypted/encoded files (BLUELIGHT, DOGCALL payloads).
- **T1036.001** — Invalid code signature: malware signed with fraudulent certificates listed as "Tencent Technology (Shenzhen) Company Limited."
- **T1070.004** — File deletion: BLUELIGHT and RoKRAT delete artifacts post-execution to remove forensic evidence.
- **T1140** — Deobfuscate/decode files: RoKRAT and Final1stspy decode Base64 and decrypt payloads at runtime.
- **T1480.001** — Execution guardrails / environmental keying: RoKRAT checks execution environment before running payloads.
- **T1497.001** — Virtualization/sandbox evasion via system checks: BLUELIGHT and RoKRAT detect VM/sandbox environments.
- **T1622** — Debugger evasion: RoKRAT employs anti-debugging techniques.
- **T1112** — Registry modification: RoKRAT modifies registry values for configuration and evasion.

### Credential Access
- **T1555.003 / .004** — Credentials from password stores: ZUMKONG harvests usernames and passwords from web browsers; RoKRAT steals browser credentials and Windows Credential Manager entries.
- **T1056.001** — Keylogging: RoKRAT, NavRAT, and DOGCALL capture keystrokes.
- **T1539** — Steal web session cookies: BLUELIGHT extracts browser session cookies.

### Discovery
- **T1082** — System information discovery: malware collects computer name, BIOS model, OS version, and execution path.
- **T1033** — System owner/user discovery: identifies victim username.
- **T1057** — Process discovery: Freenki and other implants enumerate running processes via Windows API.
- **T1083** — File and directory discovery: BLUELIGHT, CORALDECK, POORAIM, and RoKRAT enumerate files for collection.
- **T1120** — Peripheral device discovery: **Bluetooth device harvester** using Windows Bluetooth APIs to enumerate connected Bluetooth devices — a distinctive APT37 capability.
- **T1010** — Application window discovery: RoKRAT enumerates open application windows.
- **T1012** — Query registry: RoKRAT queries registry for system/configuration information.
- **T1016** — System network configuration discovery: BLUELIGHT enumerates network adapters and configuration.
- **T1124** — System time discovery: BLUELIGHT queries system time.
- **T1518.001** — Security software discovery: BLUELIGHT identifies installed security products.

### Collection
- **T1005** — Data from local system: broad collection of files from victim machines.
- **T1113** — Screen capture: RoKRAT, BLUELIGHT, DOGCALL, POORAIM, and SHUTTERSPEED capture screenshots.
- **T1123** — Audio capture: SOUNDWAVE utility captures microphone input; RoKRAT and DOGCALL record audio.
- **T1115** — Clipboard data: RoKRAT monitors and exfiltrates clipboard contents.
- **T1056.001** — Keylogging: keystroke capture for intelligence collection (RoKRAT, NavRAT, DOGCALL).
- **T1560 / .001 / .003** — Archive collected data: BLUELIGHT uses custom archiving; CORALDECK uses standard archive utilities for exfiltration staging.
- **T1074.001** — Local data staging: NavRAT stages collected data locally before exfiltration.

### Command & Control
- **T1071.001** — Web protocols: HTTPS-based C2 communications.
- **T1071.003** — Mail protocols: NavRAT uses email-based C2 (Naver email service).
- **T1102.002** — Bidirectional C2 over web services: extensive use of legitimate cloud platforms — **AOL, Twitter/X, Yandex, Mediafire, pCloud, Dropbox, Box, Google Drive** — for C2 communication and payload hosting. This is APT37's signature C2 pattern.
- **T1105** — Ingress tool transfer: downloads second-stage malware from compromised websites and cloud services.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: BLUELIGHT and RoKRAT exfiltrate data over their HTTPS/cloud C2 channels.
- **T1048.003** — Exfiltration over unencrypted non-C2 protocol: CORALDECK exfiltrates via alternative HTTP channels.
- **T1567.002** — Exfiltration to cloud storage: RoKRAT exfiltrates collected data to cloud storage services (Dropbox, pCloud, Yandex, Box).

### Impact
- **T1561.002** — Disk structure wipe: APT37 has access to destructive malware capable of overwriting the Master Boot Record (MBR), used in the "Are you Happy?" campaign.
- **T1529** — System shutdown/reboot: malware issues `shutdown /r /t 1` to reboot systems after MBR wipe.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| ROKRAT | S0240 | Modular RAT; cloud-service C2 (Dropbox/pCloud/Yandex/Box); screen/audio/keylog/clipboard | Custom |
| BLUELIGHT | S0657 | Multi-function backdoor; Microsoft Graph API (OneDrive/Outlook) for C2 | Custom |
| DOGCALL | S0213 | Backdoor with audio/keylog/screen capture; cloud C2 | Custom |
| CORALDECK | S0212 | Exfiltration tool; archives and uploads files | Custom |
| HAPPYWORK | S0214 | Downloader for second-stage payloads | Custom |
| KARAE | S0215 | Backdoor distributed via torrent sites; cloud C2 | Custom |
| POORAIM | S0216 | Backdoor with screen capture; AOL IM C2 | Custom |
| SHUTTERSPEED | S0217 | Screenshot capture utility | Custom |
| SLOWDRIFT | S0218 | Cloud-based backdoor/downloader | Custom |
| WINERACK | S0219 | Backdoor with reverse shell; process/file enumeration | Custom |
| NavRAT | S0247 | RAT using Naver email for C2; keylogging | Custom |
| Final1stspy | S0355 | Reconnaissance downloader | Custom |
| KONNI | S0356 | RAT delivered via phishing; batch/PS/VBS multi-stage; credential theft | Custom (possibly shared) |
| Chinotto | (no ATT&CK software ID) | Multi-platform (Windows + Android) surveillance implant | Custom |
| GOLDBACKDOOR | (no ATT&CK software ID) | Backdoor delivered via LNK lures; targeted journalists | Custom |
| M2RAT | (no ATT&CK software ID) | RAT with AV evasion; Windows/mobile data theft | Custom |
| FadeStealer | (no ATT&CK software ID) | Surveillance tool: keylog, screenshot, audio, device monitor; RAR exfil | Custom |
| Dolphin | (no ATT&CK software ID) | Backdoor with Google Drive C2; broad collection capability | Custom |
| KoSpy | (no ATT&CK software ID) | Android spyware; SMS/call/location/audio/screenshot collection | Custom |
| SOUNDWAVE | (no ATT&CK software ID) | Audio capture utility (microphone recording) | Custom |
| RICECURRY | (no ATT&CK software ID) | JavaScript browser profiler for watering-hole victim filtering | Custom |
| ZUMKONG | (no ATT&CK software ID) | Browser credential stealer | Custom |
| Cobalt Strike | S0154 | Post-exploitation framework (deployed via InkySquid browser exploits) | Public |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never run destructive (T1561/T1529 MBR wipe) actions outside an explicitly sanctioned, isolated lab.

Map APT37's signature plays to Decepticon's own capabilities:

- **Initial access — HWP/Office spearphishing (T1566.001, T1204.002, T1559.002).** Use the phishing/payload-builder skill to craft weaponized HWP or Office lures with embedded macros/VBA/DDE. APT37 heavily targets Korean-language users with HWP documents — reproduce this with `.hwp`-themed lures or macro-laden `.doc` files relevant to defector/journalist/government themes. Stage delivery with spearphishing pretexts tied to North Korea news, human-rights reports, or ROK government topics.
- **Initial access — watering hole / strategic web compromise (T1189, T1203).** With the web-compromise skill, emulate RICECURRY-style browser profiling: stand up a compromised page with JavaScript fingerprinting that selectively delivers exploits only to browsers matching the target profile (IE/Edge/Flash). In a lab, reproduce CVE-2020-1380 (IE) or CVE-2021-26411 (Edge) exploitation chains to deliver BLUELIGHT/Cobalt Strike payloads, mirroring the InkySquid campaign pattern.
- **Execution — client-side exploitation (T1203, T1059.005, T1106).** Emulate APT37's zero-day exploitation history: Flash Player (CVE-2016-4171, CVE-2018-4878), Word (CVE-2017-0199), IE/Edge exploits. Use VBA macro execution with shellcode decoding, and direct Windows API calls (VirtualAlloc → WriteProcessMemory → CreateRemoteThread) for process injection into `cmd.exe`.
- **Persistence & privilege escalation (T1547.001, T1053.005, T1548.002, T1055).** Set Registry Run key persistence (`HKCU\...\Run`); create scheduled tasks for script-based persistence; implement UAC bypass in the dropper chain; inject into legitimate processes (RoKRAT → cmd.exe pattern).
- **Defense evasion (T1027.003, T1036.001, T1497.001, T1622).** Use **steganography** to embed shellcode in images — APT37's distinctive evasion technique. Sign payloads with invalid/stolen certificates. Implement sandbox/VM detection and debugger-evasion checks before payload execution. Delete artifacts post-execution.
- **C2 — cloud service abuse (T1102.002, T1071.001).** This is APT37's defining C2 pattern. Use **Sliver or a custom implant** (c2 skill) with cloud-service C2 profiles emulating RoKRAT's use of Dropbox, pCloud, Yandex, and Box APIs. Stand up bidirectional C2 over legitimate cloud APIs to blend with normal user traffic. Supplement with HTTPS-based channels as fallback.
- **Collection — full surveillance (T1113, T1123, T1115, T1056.001, T1120).** Deploy a SOUNDWAVE-equivalent audio capture module; implement screen capture, clipboard monitoring, and keylogging. Where Bluetooth-enabled targets are in scope, emulate the **Bluetooth device harvester** using Windows Bluetooth APIs — this is a rare and distinctive APT37 capability.
- **Credential access (T1555.003, T1555.004, T1539).** Harvest browser-stored credentials (Chrome/Firefox/Edge) and Windows Credential Manager entries; extract session cookies. Emulate ZUMKONG-style browser credential theft.
- **Exfiltration (T1560.001, T1567.002, T1041).** Archive collected data and exfiltrate to cloud storage (Dropbox/pCloud) over the same C2 channel, reproducing APT37's signature cloud-exfil pattern. Use password-protected RAR archives where FadeStealer-style exfil is being emulated.
- **Destructive capability (T1561.002, T1529) — lab only.** In an isolated lab environment, emulate the "Are you Happy?" MBR-wipe capability followed by forced reboot (`shutdown /r /t 1`). This demonstrates APT37's destructive potential without operational risk.

## Detection & defense

- **Spearphishing / HWP lures (T1566.001, T1204.002):** Block or sandbox HWP file attachments at the mail gateway; implement attachment sandboxing for macro-enabled Office documents; train users on Korean-language lure themes (defector stories, ROK government notices); alert on HWP/Office processes spawning cmd.exe/PowerShell/scripting interpreters.
- **Watering-hole / browser exploits (T1189, T1203):** Patch browser engines (IE, Edge, Chrome) and retire Flash Player; deploy exploit-mitigation features (EMET/Windows Defender Exploit Guard); monitor for anomalous JavaScript profiling patterns on controlled web assets; hunt for injected `<script>` tags on high-value Korean-language sites.
- **Process injection (T1055, T1106):** Monitor for VirtualAlloc/WriteProcessMemory/CreateRemoteThread call chains from Office or script host processes; alert on `cmd.exe` spawning with suspicious parent processes (HWP, Word); deploy endpoint-level API monitoring.
- **Cloud-service C2 (T1102.002):** Monitor for anomalous API calls to Dropbox, pCloud, Yandex, Box, Google Drive, and OneDrive from endpoint processes that don't normally use them; inspect HTTPS traffic to cloud-storage domains from non-browser processes; baseline legitimate cloud usage and alert on deviations.
- **Registry persistence (T1547.001):** Monitor `HKCU\Software\Microsoft\CurrentVersion\Run` and startup folder modifications; alert on registry changes from script interpreters or unsigned binaries.
- **Steganography (T1027.003):** Deploy content-inspection systems that can detect anomalous entropy in image files; hunt for processes downloading and parsing images outside of normal browsing patterns.
- **Bluetooth harvesting (T1120):** Monitor for unusual access to Windows Bluetooth APIs (BluetoothFindFirstDevice, etc.) from non-standard processes; alert on Bluetooth enumeration from processes without legitimate Bluetooth use cases.
- **Browser credential theft (T1555.003, T1539):** Deploy browser credential-store protections; monitor for file reads of Chrome/Firefox credential databases and cookie stores by non-browser processes.
- **MBR wipe / destructive actions (T1561.002, T1529):** Monitor for direct disk-write access to `\\.\PhysicalDrive0`; alert on `shutdown /r /t 1` from non-administrative contexts; deploy MBR integrity monitoring.
- **Audio/screen/clipboard surveillance (T1123, T1113, T1115):** Alert on processes accessing microphone APIs, repeated screen-capture API calls, or clipboard monitoring from unsigned or unexpected processes; monitor for known SOUNDWAVE and FadeStealer behavioral patterns.

## Sources

- https://attack.mitre.org/groups/G0067/
- https://services.google.com/fh/files/misc/apt37-reaper-the-overlooked-north-korean-actor.pdf
- https://securelist.com/operation-daybreak/75100/
- https://securelist.com/scarcruft-continues-to-evolve-introduces-bluetooth-harvester/90729/
- https://blog.talosintelligence.com/2018/01/korea-in-crosshairs.html
- https://www.volexity.com/blog/2021/08/17/north-korean-apt-inkysquid-infects-victims-using-browser-exploits/
- https://www.volexity.com/blog/2021/08/24/north-korean-bluelight-special-inkysquid-deploys-rokrat/
- https://www.bleepingcomputer.com/news/security/apt37-targets-journalists-with-chinotto-multi-platform-malware/
- https://research.checkpoint.com/2023/chain-reaction-rokrats-missing-link/
- https://www.lookout.com/threat-intelligence/article/lookout-discovers-new-spyware-by-north-korean-apt37
- https://www.zscaler.com/blogs/security-research/unintentional-leak-glimpse-attack-vectors-apt37
- https://www.crowdstrike.com/adversaries/ricochet-chollima/
- https://attack.mitre.org/software/S0240/
- https://attack.mitre.org/software/S0657/
- https://socradar.io/blog/threat-actor-profile-scarcruft-apt37/
