---
name: dark-caracal
description: "Adversary-emulation profile for Dark Caracal (G0070), a Lebanese state-linked cyber-espionage and surveillance actor attributed to the General Directorate of General Security (GDGS), operating since at least 2012."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Dark Caracal, G0070, Lebanese GDGS, General Directorate of General Security, Bandook RAT, CrossRAT, Pallas, Poco RAT, Operation Manul, Lebanon espionage, mobile surveillance, Android trojan, multi-platform RAT, Latin America targeting, watering hole, trojanized apps, Facebook WhatsApp phishing, mercenary hacking"
  tags: dark-caracal, g0070, lebanon, gdgs, espionage, surveillance, nation-state, adversary-emulation, mitre-attack, bandook, crossrat, pallas, poco-rat, mobile, android, multi-platform
  mitre_attack: T1189, T1566.001, T1566.003, T1204.002, T1059, T1059.001, T1059.003, T1059.005, T1059.006, T1106, T1547.001, T1547.013, T1543.001, T1543.003, T1548.002, T1134.001, T1055.012, T1027, T1027.002, T1027.003, T1027.013, T1036.005, T1070.004, T1140, T1218.001, T1497.001, T1553.002, T1056.001, T1056.004, T1012, T1016, T1057, T1082, T1083, T1120, T1518.001, T1680, T1005, T1113, T1123, T1125, T1071.001, T1095, T1105, T1573.001, T1041, T1437.001, T1417.002, T1418, T1421, T1426, T1429, T1430, T1406, T1409, T1512, T1636.002, T1636.003, T1636.004, T1646, T1630.002
---

# Dark Caracal — Adversary Emulation Profile

Dark Caracal (MITRE ATT&CK **G0070**) is a cyber-espionage and surveillance group attributed to Lebanon's **General Directorate of General Security (GDGS)**, operating since at least 2012. The group is best characterized by its **mobile-first surveillance** approach — deploying trojanized Android messaging apps (Pallas) to harvest SMS, call logs, contacts, photos, and real-time audio/video — combined with cross-platform desktop RATs (Bandook, CrossRAT) and the commercial spyware FinFisher. Dark Caracal relies on relatively simple social engineering — phishing via Facebook and WhatsApp, watering holes, and trojanized applications masquerading as popular software — rather than advanced zero-day exploitation. Despite this simplicity, the group has compromised thousands of victims across 20+ countries, exfiltrating hundreds of thousands of files and text messages. Evidence suggests the group may also operate as a **cyber-mercenary / hack-for-hire** entity, conducting campaigns on behalf of other governments (notably Kazakhstan in Operation Manul).

## Attribution & motivation

- **Sponsor / nation:** Republic of Lebanon — **General Directorate of General Security (GDGS)**, the country's primary intelligence agency. The 2018 EFF/Lookout investigation traced C2 infrastructure to a building adjacent to GDGS headquarters in Beirut, with test devices physically located in the same building.
- **Motivation:** Primarily **espionage and surveillance** — long-term intelligence collection against individuals (journalists, activists, dissidents, lawyers, military personnel) rather than organizations. Secondary motivation includes **hack-for-hire / mercenary operations** for foreign governments (Kazakhstan in Operation Manul).
- **Attribution confidence:** **High.** Backed by the joint EFF/Lookout 2018 investigation tracing infrastructure to GDGS premises, corroborated by shared infrastructure with Operation Manul (2016 EFF report), and consistent vendor reporting (Check Point, ESET, Positive Technologies, Cofense).

## Targeting

- **Sectors:** Government and military; defense; journalists and media; political activists, dissidents, and NGOs; lawyers and legal professionals; education; healthcare; financial institutions; energy; IT and technology firms.
- **Regions:** Middle East (Lebanon, Syria, Saudi Arabia, Jordan), Latin America (Venezuela, Dominican Republic, Chile, Colombia, Ecuador), Southeast Asia (Singapore, Indonesia), Europe (Germany, Switzerland, Cyprus, Italy), North America, Kazakhstan and Central Asia. Heavy recent focus on **Latin American Spanish-speaking enterprises** (2023-2025).
- **Victim profile:** High-value individuals whose personal communications, contacts, photos, and documents yield intelligence — activists, journalists, lawyers, military personnel, and their families and associates. In recent campaigns, broader targeting of government and enterprise employees via financial-themed phishing (fake invoices).

## Notable campaigns

- **2012-2016 — Early surveillance operations.** Dark Caracal deployed Pallas trojanized Android apps and Bandook RAT, collecting data from thousands of victims across 20+ countries. Lookout later determined the group had been active since at least 2012. (Lookout/EFF 2018 report)
- **2016-08 — Operation Manul.** EFF documented a phishing and malware campaign targeting journalists, political dissidents, lawyers, and their families who had spoken out against Kazakhstan's government. Bandook RAT and FinFisher were delivered via spearphishing. Infrastructure was later linked to Dark Caracal's GDGS-connected servers, revealing the group operated as a hack-for-hire for the Kazakh government. (EFF "I Got a Letter from the Government" report / BlackHat US 2016)
- **2018-01 — EFF/Lookout public exposure.** Joint Lookout-EFF report "Dark Caracal: Cyber-espionage at a Global Scale" publicly attributed the group, documenting 486,766 intercepted text messages, 264,535 stolen files, Pallas Android trojan, CrossRAT (cross-platform Java RAT), Bandook, and FinFisher usage. C2 servers traced to a building co-located with GDGS headquarters in Beirut. (Lookout / EFF)
- **2020-11 — Bandook resurgence ("Signed & Delivered").** Check Point documented a new Bandook campaign signed with legitimate Certum code-signing certificates, targeting government, financial, energy, healthcare, education, IT, and legal institutions across Singapore, Cyprus, Chile, Italy, USA, Turkey, Switzerland, Indonesia, and Germany. (Check Point Research)
- **2020-12 — EFF "You Missed a Spot" follow-up.** EFF reported Dark Caracal was still operational, using the same infrastructure patterns, with updated Bandook samples featuring new code-signing certificates. (EFF)
- **2023-02 — "Uncle Sow" — Dark Caracal in Latin America.** EFF documented Bandook infections across 700+ computers in Central and South America, primarily the Dominican Republic and Venezuela. Spanish-language phishing lures and decoy documents targeted government and enterprise victims. (EFF)
- **2024-2025 — Poco RAT campaigns.** Positive Technologies detected 483 samples of Poco RAT (a new Delphi-based credential-harvesting RAT) across Venezuela, Dominican Republic, Chile, Colombia, and Ecuador, superseding the 355 Bandook samples from 2023-2024. Financial-themed phishing with blurred PDF decoys, .rev archive containers, and delivery via Google Drive/Dropbox link shorteners. (Positive Technologies / Cofense / The Hacker News)

## TTPs by ATT&CK tactic

### Initial Access
- **T1566.003** — Spearphishing via service: Dark Caracal distributes malicious links and trojanized app downloads via **Facebook and WhatsApp** messages to targeted individuals.
- **T1566.001** — Spearphishing attachment: Bandook is delivered via malicious Word documents containing macros inside zip archives; recent campaigns use PDF decoys with blurred content inside .rev (WinRAR recovery volume) archives.
- **T1204.002** — User execution — malicious file: malware is disguised as Flash Player, Office, or PDF documents to entice user interaction; trojanized Android messaging apps (Signal, WhatsApp, Threema clones) are distributed to targets.
- **T1189** — Drive-by compromise: Dark Caracal leveraged watering hole sites to serve malicious code to visiting targets.

### Execution
- **T1059.003** — Windows Command Shell: Bandook spawns `cmd.exe` for post-compromise command execution; Word document macros invoke the shell to download second-stage payloads.
- **T1059.001** — PowerShell: Bandook uses PowerShell loaders as part of its execution chain.
- **T1059.005** — Visual Basic: Bandook campaigns deliver malicious VBA macros in Office documents to trigger payload execution.
- **T1059.006** — Python: Bandook supports commands to execute Python-based payloads.
- **T1059** — Command and Scripting Interpreter: Bandook supports Java-based payload execution (CrossRAT is itself a cross-platform Java RAT).
- **T1106** — Native API: Bandook calls `ShellExecuteW()` and other Win32 APIs directly for execution.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: Bandook adds a registry key to `HKEY_USERS\Software\Microsoft\Windows\CurrentVersion\Run` for persistence; CrossRAT and FinFisher also use Run keys.
- **T1547.013** — XDG Autostart entries: CrossRAT establishes persistence on Linux via XDG Autostart entries.
- **T1543.001** — Launch Agent: CrossRAT creates a macOS Launch Agent (`/Library/LaunchAgents/`) for persistence across reboots.
- **T1543.003** — Windows Service: FinFisher (used by Dark Caracal) persists as a Windows service.

### Privilege Escalation
- **T1055.012** — Process hollowing: Bandook creates a suspended `iexplore.exe` process and injects its payload via process hollowing — the group's signature injection technique.
- **T1548.002** — Bypass UAC: FinFisher (deployed by Dark Caracal) bypasses User Account Control.
- **T1134.001** — Token impersonation/theft: FinFisher performs access token manipulation for privilege escalation.

### Defense Evasion
- **T1027.002** — Software packing: Dark Caracal packs Bandook with UPX; FinFisher also uses software packing.
- **T1027.013** — Encrypted/encoded file: Bandook strings are base64-encoded then encrypted; Poco RAT uses Twofish encryption with unique per-build keys derived from Ripemd-160 hashes.
- **T1027.003** — Steganography: Bandook uses .PNG images within zip files to construct the executable payload.
- **T1027** — Obfuscated files or information: FinFisher employs multiple obfuscation layers; Bandook and Poco RAT droppers use dynamic API resolution to hinder analysis.
- **T1140** — Deobfuscate/decode files or information: Bandook decodes its PowerShell loader at runtime; FinFisher performs similar runtime deobfuscation.
- **T1218.001** — Compiled HTML file: Dark Caracal used a compiled HTML (.chm) file containing a command to download and execute a payload.
- **T1553.002** — Code signing: Bandook was signed with legitimate Certum code-signing certificates (2019-2020), allowing execution without Windows warnings.
- **T1036.005** — Masquerading — match legitimate name or location: FinFisher masquerades as legitimate software; Dark Caracal disguises malware as Flash Player, Office, and PDF viewers; Poco RAT metadata impersonates Disney, Lockheed Martin, and Morgan Stanley.
- **T1055.012** — Process hollowing: (also defense evasion) Bandook and Poco RAT inject into `iexplore.exe` via process hollowing to evade detection.
- **T1070.004** — File deletion: Bandook can delete files from compromised systems to remove evidence.
- **T1497.001** — Virtualization/sandbox evasion — system checks: FinFisher performs VM/sandbox environment checks before executing.

### Credential Access
- **T1056.001** — Keylogging: Bandook contains keylogging modules for capturing credentials and keystrokes.
- **T1056.004** — Credential API hooking: FinFisher hooks credential APIs to intercept authentication data.

### Discovery
- **T1083** — File and directory discovery: Dark Caracal collects file listings of all default Windows directories; Bandook and CrossRAT enumerate files and directories.
- **T1082** — System information discovery: FinFisher gathers comprehensive system information.
- **T1016** — System network configuration discovery: Bandook retrieves the public IP address and network configuration from compromised systems.
- **T1057** — Process discovery: FinFisher enumerates running processes.
- **T1012** — Query registry: FinFisher queries the Windows registry for configuration and installed software.
- **T1518.001** — Security software discovery: FinFisher identifies installed security products.
- **T1120** — Peripheral device discovery: Bandook detects connected USB devices.
- **T1680** — Local storage discovery: Bandook collects information about available drives on the system.

### Collection
- **T1005** — Data from local system: Dark Caracal collects complete contents of the Pictures folder and other user directories from compromised Windows systems; Bandook collects arbitrary local files.
- **T1113** — Screen capture: Dark Caracal takes screenshots via Bandook, CrossRAT, and FinFisher.
- **T1123** — Audio capture: Bandook captures audio from the device microphone.
- **T1125** — Video capture: Bandook captures video from the victim's webcam.
- **T1056.001** — Keylogging (collection): Bandook logs keystrokes for intelligence collection.

### Command and Control
- **T1071.001** — Web protocols: Bandook communicates with C2 servers over HTTP using TCP, with payloads Base64-encoded and suffixed with the string `&&&`.
- **T1573.001** — Symmetric cryptography: Bandook uses AES encryption for C2 communications.
- **T1095** — Non-application layer protocol: Bandook supports raw TCP socket connections for C2.
- **T1105** — Ingress tool transfer: Bandook downloads additional files and payloads to compromised systems.

### Exfiltration
- **T1041** — Exfiltration over C2 channel: Bandook uploads collected files from the victim's machine over the same C2 channel.

### Mobile (Pallas — Android)
- **T1437.001** — Application layer protocol — web protocols: Dark Caracal controls Pallas implants using standard HTTP communication.
- **T1429** — Audio capture: Pallas records audio from the device microphone.
- **T1512** — Video capture: Pallas takes pictures via front and rear cameras.
- **T1430** — Location tracking: Pallas tracks GPS latitude/longitude coordinates.
- **T1636.002 / .003 / .004** — Protected user data — call log, contact list, SMS messages: Pallas exfiltrates complete call logs, contacts, and all SMS messages (including real-time capture of incoming messages).
- **T1417.002** — GUI input capture: Pallas uses phishing popups to harvest user credentials on the device.
- **T1409** — Stored application data: Pallas retrieves messages and decryption keys for popular messaging apps (WhatsApp, Signal, Telegram).
- **T1418** — Software discovery: Pallas enumerates all installed applications on the device.
- **T1426** — System information discovery: Pallas queries device metadata (device ID, OS version, camera count).
- **T1421** — System network connections discovery: Pallas enumerates nearby Wi-Fi access points.
- **T1406** — Obfuscated files or information: Pallas stores domain/URL configuration as AES-encrypted, base64-encoded hardcoded strings.
- **T1630.002** — Indicator removal on host — file deletion: Pallas deletes attacker-specified files from compromised devices.
- **T1646** — Exfiltration over C2 channel: Pallas exfiltrates collected data via HTTP.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| Bandook | S0234 | Windows RAT (Delphi/C++, process hollowing, keylogger, screen/audio/video capture) | Custom (origin: commercial RAT by Lebanese dev "PrinceAli", 2007; heavily customized) |
| CrossRAT | S0235 | Cross-platform Java RAT (Windows/macOS/Linux, screenshots, file manipulation) | Custom |
| Pallas | S0399 | Android mobile surveillance trojan (trojanized messaging apps) | Custom |
| FinFisher | S0182 | Commercial Windows/mobile spyware (full-spectrum surveillance) | Commercial (Gamma International) |
| Poco RAT | (no ATT&CK software ID assigned) | Delphi-based Windows RAT (credential harvesting, screen capture, command execution) | Custom (attributed 2024-2025) |

> Note: Bandook originated as a commercially available RAT circa 2007 but has been extensively modified by Dark Caracal with custom loaders, code-signing, steganography-based payload construction, and Twofish-encrypted variants. Poco RAT shares dropper architecture with Bandook (process hollowing into `iexplore.exe`, dynamic API resolution) and is assessed as Bandook's successor.

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Never deploy mobile surveillance implants or trojanized messaging apps outside an explicitly sanctioned, isolated lab.

Map Dark Caracal's signature plays to Decepticon's own capabilities:

- **Initial access — social engineering (T1566.003, T1566.001, T1204.002).** Use the phishing/social-engineering skill to craft **spearphishing messages via messaging platforms** (simulating Facebook/WhatsApp delivery) with links to trojanized application downloads. Stage macro-enabled Word documents inside zip archives as email attachments. For Latin America-themed campaigns, prepare Spanish-language financial lures (fake invoices) with blurred PDF decoys linking to cloud-hosted payloads via link shorteners — this is the group's 2024-2025 signature play.
- **Watering hole (T1189).** With the web-attack skill, stand up a watering hole page serving malicious content to profiled visitors. Dark Caracal uses simple drive-by techniques rather than exploit kits — redirect to a trojanized download that masquerades as a legitimate software update.
- **Payload delivery and evasion (T1027.002, T1027.003, T1553.002, T1055.012).** Use the payload-builder skill to create a Delphi-style dropper that: (1) unpacks from a `.rev` (WinRAR recovery volume) archive to evade AV, (2) uses steganography (payload hidden in PNG images within a zip), (3) employs process hollowing into `iexplore.exe` for injection, and (4) is signed with a valid code-signing certificate. This chain reproduces the Bandook/Poco RAT delivery exactly.
- **Multi-platform persistence (T1547.001, T1547.013, T1543.001).** Emulate CrossRAT's cross-platform persistence: **Windows** — Registry Run key (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`); **Linux** — XDG Autostart entry in `~/.config/autostart/`; **macOS** — Launch Agent plist in `~/Library/LaunchAgents/`. Deploy all three to demonstrate the group's multi-OS capability.
- **Defense evasion (T1218.001, T1036.005, T1140).** Use a compiled HTML (.chm) file as an initial execution vector; masquerade payloads as Flash Player or PDF reader installers; include runtime deobfuscation of encrypted strings (AES/Twofish + Base64, unique key per build) and dynamic API resolution to frustrate analysis.
- **Collection & surveillance (T1005, T1113, T1123, T1125, T1056.001).** Drive the collection skill to replicate Dark Caracal's signature data theft: enumerate and collect the entire `Pictures` folder and default user directories, take periodic screenshots, activate webcam and microphone capture, and log keystrokes. This comprehensive surveillance is the group's defining operational pattern.
- **Mobile (Pallas emulation — T1429, T1430, T1636.*, T1409).** In a sanctioned mobile-testing lab, deploy a trojanized messaging app (imitating Signal/WhatsApp) that: intercepts SMS messages, exfiltrates call logs and contacts, tracks GPS location, captures audio/video via device cameras, and retrieves stored messaging app data. Use HTTP-based C2. This replicates Pallas — Dark Caracal's most operationally successful tool.
- **C2 (T1071.001, T1573.001, T1095).** Configure Sliver or a custom HTTP-based C2 channel that Base64-encodes payloads and appends the `&&&` suffix marker (Bandook's signature C2 pattern). Use AES-encrypted communications and support a raw TCP socket fallback channel.
- **Cloud-assisted delivery (recent TTPs).** Host payloads on Google Drive/Dropbox and distribute via URL shorteners (bit.ly, is.gd, Rebrandly) — Dark Caracal's 2024-2025 delivery infrastructure pattern. Only 7% of decoy documents triggered AV alerts using this approach.

## Detection & defense

- **Trojanized messaging apps (Pallas, T1636.*):** Enforce Android device management policies; block sideloading (unknown sources); deploy mobile threat defense (MTD) solutions; monitor for apps requesting unusual permission combinations (SMS + camera + microphone + location + contacts); verify messaging app signatures against official store versions.
- **Spearphishing via social media (T1566.003):** Train users on social-engineering attacks via Facebook/WhatsApp; deploy URL reputation filtering on messaging platforms where possible; monitor for shortened URLs (bit.ly, is.gd) in corporate messaging channels.
- **Macro-based delivery (T1566.001, T1059.005):** Enforce Office macro execution policies (disable macros from internet-sourced documents); deploy ASR (Attack Surface Reduction) rules blocking Office child process creation; alert on `WINWORD.EXE` spawning `cmd.exe` or `powershell.exe`.
- **Process hollowing / Bandook injection (T1055.012):** Monitor for `iexplore.exe` spawned by non-standard parents (Word, PowerShell, cmd.exe); alert on suspended process creation followed by `NtUnmapViewOfSection`/`WriteProcessMemory` API calls; deploy behavioral endpoint detection for process hollowing patterns.
- **Compiled HTML abuse (T1218.001):** Monitor `hh.exe` execution and its child processes; block `.chm` files at the email gateway; alert on `hh.exe` spawning network connections or downloading executables.
- **Code-signed malware (T1553.002):** Monitor for signed executables with certificates from unexpected CAs (Certum was abused); implement certificate reputation checks; alert on newly-signed executables from uncommon signers executing in user directories.
- **UPX packing & steganography (T1027.002, T1027.003):** Deploy YARA rules for UPX-packed binaries in user-writable directories; alert on executables extracted from PNG images or `.rev` (WinRAR recovery volume) archives.
- **C2 pattern (T1071.001):** Monitor outbound HTTP traffic for Base64-encoded payloads with the `&&&` suffix marker; detect beaconing patterns over TCP to known-bad IPs; alert on raw TCP socket connections from user processes.
- **CrossRAT persistence (T1547.013, T1543.001):** Monitor XDG Autostart directory modifications on Linux; audit Launch Agent plist creation on macOS; baseline legitimate autostart entries and alert on additions by non-package-manager processes.
- **Cloud delivery infrastructure:** Monitor for downloads from Google Drive/Dropbox triggered by shortened URLs; inspect `.rev` file downloads (uncommon extension in enterprise environments); alert on `WinRAR` recovery volume files being extracted and executed.

## Sources

- https://attack.mitre.org/groups/G0070/
- https://attack.mitre.org/software/S0234/
- https://attack.mitre.org/software/S0235/
- https://attack.mitre.org/software/S0399/
- https://attack.mitre.org/software/S0182/
- https://info.lookout.com/rs/051-ESQ-475/images/Lookout_Dark-Caracal_srr_20180118_us_v.1.0.pdf
- https://www.eff.org/files/2016/08/03/i-got-a-letter-from-the-government.pdf
- https://www.eff.org/deeplinks/2020/12/dark-caracal-you-missed-spot
- https://www.eff.org/deeplinks/2023/02/uncle-sow-dark-caracal-latin-america
- https://research.checkpoint.com/2020/bandook-signed-delivered/
- https://global.ptsecurity.com/en/research/pt-esc-threat-intelligence/the-evolution-of-dark-caracal-tools-analysis-of-a-campaign-featuring-poco-rat/
- https://thehackernews.com/2025/03/dark-caracal-uses-poco-rat-to-target.html
- https://therecord.media/dark-caracal-hackers-poco-rat-bandook
- https://www.blackhat.com/docs/us-16/materials/us-16-Quintin-When-Governments-Attack-State-Sponsored-Malware-Attacks-Against-Activists-Lawyers-And-Journalists.pdf
