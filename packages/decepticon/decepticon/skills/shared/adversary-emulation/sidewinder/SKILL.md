---
name: sidewinder-rattlesnake
description: "Adversary-emulation profile for SideWinder (G0121 / Rattlesnake / T-APT-04 / Razor Tiger), India's suspected state-sponsored cyber-espionage actor."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "SideWinder, Rattlesnake, T-APT-04, Razor Tiger, G0121, Indian APT espionage emulation, LNK execution chains, HTA JavaScript downloaders, StealerBot, WarHawk, DLL side-loading, CVE-2017-11882 Equation Editor, spearphishing government-themed lures, Pakistan military targeting, South Asian espionage, maritime logistics nuclear targeting"
  tags: sidewinder, rattlesnake, t-apt-04, razor-tiger, india, espionage, nation-state, g0121, adversary-emulation, mitre-attack
  mitre_attack: T1566.001, T1566.002, T1598.002, T1598.003, T1204.001, T1204.002, T1203, T1059.001, T1059.005, T1059.007, T1559.002, T1218.005, T1574.001, T1547.001, T1027.010, T1027.013, T1036.005, T1105, T1071.001, T1119, T1020, T1074.001, T1083, T1057, T1082, T1016, T1033, T1124, T1518, T1518.001
---

# SideWinder (Rattlesnake, T-APT-04, Razor Tiger) — Adversary Emulation Profile

SideWinder (MITRE ATT&CK **G0121**) is a suspected Indian state-sponsored cyber-espionage group active since at least **2012**. It is one of the most prolific APT actors in the South Asian threat landscape, with over 1,000 documented attacks against government organizations in the Asia-Pacific region since April 2020 alone. SideWinder is characterized by rapid malware iteration (generating modified variants in under five hours after detection), heavy reliance on spearphishing with government/military-themed lures, exploitation of the aged CVE-2017-11882 Equation Editor vulnerability, multi-stage JavaScript and .NET infection chains, and custom post-exploitation tooling — most notably the modular **StealerBot** implant discovered in 2024. The group maintains a massive infrastructure footprint (400+ live domains with hundreds of sub-domains mimicking legitimate government sites) and has progressively expanded from its traditional Pakistan-centric targeting to maritime, logistics, nuclear, and diplomatic entities across the Middle East, Africa, and Southeast Asia.

## Attribution & motivation

- **Sponsor / nation:** India (suspected). Multiple threat intelligence vendors (Kaspersky GReAT, Group-IB, AT&T Alien Labs, Trend Micro, Zscaler ThreatLabz) assess SideWinder as an Indian state-sponsored group based on targeting patterns, infrastructure analysis, and victimology aligned with Indian strategic interests.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — military, government, and diplomatic intelligence from neighboring adversary states (especially Pakistan). Secondary interests include monitoring political developments in Nepal, Bangladesh, Sri Lanka, Afghanistan, and China, and — since 2024 — collecting intelligence on maritime logistics, energy, and nuclear power infrastructure.
- **Attribution confidence:** **Moderate-High.** No formal government attribution exists, but consistent and convergent vendor reporting (Kaspersky, Group-IB, Trend Micro, AT&T Alien Labs, Zscaler, Cyble) over a decade, combined with Pakistan government espionage advisories (NTISB 2019), support the Indian nexus assessment.

## Targeting

- **Sectors:** Government and military (primary); diplomatic missions and foreign affairs ministries; defense organizations; central banks and financial institutions; maritime infrastructure and logistics companies; nuclear power agencies; telecommunications; universities; energy and oil trading; media.
- **Regions:** Pakistan (primary, ongoing since 2012), China, Nepal, Bangladesh, Sri Lanka, Afghanistan, Myanmar, Bhutan — expanding to Turkey, Middle East (Saudi Arabia, UAE, Jordan, Egypt), Africa (Djibouti, Morocco, Algeria, Rwanda, Uganda), Southeast Asia (Cambodia, Vietnam, Malaysia, Maldives), and diplomatic entities in Bulgaria and India.
- **Victim profile:** Government officials, military personnel, and diplomatic staff whose documents and communications yield strategic intelligence. Lures are tailored to the victim's nationality and sector — government circulars, defense procurement documents, COVID-19 advisories, HR documents, maritime port briefings, and nuclear regulatory correspondence.

## Notable campaigns

- **2012-2018 — Early operations against Pakistan.** SideWinder conducted sustained espionage against Pakistani military and government entities using weaponized documents and custom backdoors. The group evolved its tooling iteratively, establishing the LNK → HTA → JavaScript → .NET downloader chain that would become its signature. (AT&T Alien Labs / HawkEye)
- **2019-02 — Pakistan NTISB espionage advisory.** Pakistan's National Telecom & Information Technology Security Board issued advisory no. 4 warning defense and intelligence organizations of an active SideWinder campaign, marking one of the first government-level acknowledgments of the threat. (AT&T Alien Labs)
- **2019-01 — Android CVE-2019-2215 exploitation.** Trend Micro reported the first active attack exploiting the Android use-after-free vulnerability CVE-2019-2215 found on Google Play, linked to SideWinder — demonstrating mobile targeting capability. (Trend Micro)
- **2020 — COVID-19 themed campaigns.** SideWinder capitalized on the pandemic, sending spearphishing lures themed around COVID-19 online teaching, government advisories, and health updates to target Pakistani government officials, as well as entities in Bangladesh, China, and Nepal. (Rewterz / Trend Micro)
- **2021-06 to 2021-11 — Mass regional campaign (60+ entities).** Group-IB uncovered a systematic spearphishing campaign targeting over 60 government, military, central bank, and media entities across Afghanistan, Bhutan, Myanmar, Nepal, and Sri Lanka. The campaign deployed the SideWinder.AntiBot.Script custom evasion tool to filter non-target visitors from phishing infrastructure. (Group-IB)
- **2022-10 — WarHawk backdoor / NEPRA compromise.** SideWinder compromised the official website of Pakistan's National Electric Power Regulatory Authority (NEPRA) to deliver the **WarHawk** backdoor, which masquerades as legitimate applications (ASUS Update Setup, Realtek HD Audio Manager), validates Pakistan Standard Time zone before executing, and deploys Cobalt Strike with KernelCallBackTable injection. (Zscaler ThreatLabz / The Hacker News)
- **2024-H1 — StealerBot deployment & Middle East/Africa expansion.** Kaspersky GReAT discovered SideWinder deploying the previously unknown **StealerBot** post-exploitation toolkit — a modular, memory-only implant with an Orchestrator core — against government, military, logistics, financial, and telecom targets across Pakistan, Bangladesh, Turkey, Saudi Arabia, UAE, Djibouti, Jordan, Malaysia, Maldives, Myanmar, Nepal, and Sri Lanka. Massive infrastructure expansion (400+ domains) observed. (Kaspersky GReAT)
- **2024-H2 to 2025 — Maritime logistics & nuclear sector targeting.** Kaspersky reported intensified attacks against maritime infrastructure, logistics companies, port authorities, and **nuclear power agencies** in South Asia, Southeast Asia (Cambodia, Vietnam), and Africa. Nuclear-themed lures referenced committee meetings and regulatory matters; maritime lures included HR documents and diplomatic briefings. The group updated its toolset continuously, generating new malware variants within five hours of detection. (Kaspersky GReAT / Securelist)

## TTPs by ATT&CK tactic

### Initial Access
- **T1566.001** — Spearphishing attachment: weaponized OOXML documents (DOCX/XLSX) and ZIP archives containing malicious LNK files, crafted with government/military/sector-specific themes.
- **T1566.002** — Spearphishing link: emails with links to credential-harvesting websites and malicious download pages mimicking government portals.
- **T1598.002** — Spearphishing attachment for credential harvesting: malicious attachments leading victims to fake login portals.
- **T1598.003** — Spearphishing link for credential harvesting: links to lookalike government webmail and portal login pages.
- **T1204.001 / T1204.002** — User execution of malicious links and files: relies on victim interaction with LNK files, weaponized documents, and phishing links.
- **T1203** — Exploitation for client execution: CVE-2017-11882 (Microsoft Office Equation Editor, used across all campaigns since at least 2017) and CVE-2020-0674 (Internet Explorer scripting engine).

### Execution
- **T1059.001** — PowerShell: used to drop and execute malware loaders in multi-stage infection chains.
- **T1059.005** — VBScript: used to drop and execute malware loaders.
- **T1059.007** — JavaScript: central to the infection chain — HTA files execute JavaScript that downloads subsequent stages; JavaScript downloaders fetch .NET payloads.
- **T1559.002** — Dynamic Data Exchange (DDE): ActiveXObject utility used to create OLE objects for execution through Internet Explorer.
- **T1218.005** — Mshta: `mshta.exe` used to execute malicious HTA payloads containing JavaScript, a signature SideWinder technique.
- **T1203** — Exploitation for client execution: Office Equation Editor (CVE-2017-11882) triggers remote template injection chains.

### Persistence
- **T1547.001** — Registry Run keys / Startup folder: Registry paths to malicious executables added for autostart persistence.

### Privilege Escalation
- **T1574.001** — DLL search-order hijacking / side-loading: legitimate Windows applications (notably `rekeywiz.exe`) hijacked to side-load malicious DLLs — a signature SideWinder persistence and evasion technique.

### Defense Evasion
- **T1027.010** — Command obfuscation: base64 encoding applied to scripts and commands throughout the infection chain.
- **T1027.013** — Encrypted/encoded files: payloads encrypted with ECDH-P256 and encoded with base64; StealerBot modules loaded only in memory, never written to disk.
- **T1036.005** — Match legitimate resource name or location: malicious files named after legitimate Windows executables (e.g., `rekeywiz.exe`); WarHawk masquerades as ASUS Update Setup and Realtek HD Audio Manager.
- **T1574.001** — DLL side-loading: legitimate signed binaries abused to load malicious DLLs, bypassing application whitelisting and signature checks.
- **T1218.005** — Mshta: system binary proxy execution via `mshta.exe` to run unsigned HTA/JavaScript payloads.

### Credential Access
- **StealerBot credential modules** — Steals passwords from browsers, intercepts RDP credentials by injecting into `mstsc.exe` processes, and captures keystrokes. (Not yet assigned individual ATT&CK technique IDs for all modules, but aligns with T1555.003, T1056.001, T1557-adjacent RDP interception.)

### Discovery
- **T1083** — File and directory discovery: malware enumerates files and directories across drives for collection.
- **T1057** — Process discovery: tools identify running processes on the victim machine; StealerBot monitors for `mstsc.exe` creation events.
- **T1082** — System information discovery: collects computer name, OS version, installed hotfixes, memory, and processor details.
- **T1016** — System network configuration discovery: collects network interface information including MAC addresses.
- **T1033** — System owner/user discovery: identifies the user of the compromised host.
- **T1124** — System time discovery: obtains current system time (WarHawk validates Pakistan Standard Time zone).
- **T1518** — Software discovery: enumerates installed software on the host.
- **T1518.001** — Security software discovery: queries `winmgmts:\.\root\SecurityCenter2` to enumerate installed antivirus products.

### Lateral Movement
- WarHawk's Cobalt Strike deployment enables standard lateral movement (RDP, SMB, pass-the-hash) post-compromise, though SideWinder's primary documented focus is initial access and data exfiltration rather than extensive lateral movement.

### Collection
- **T1074.001** — Local data staging: stolen files collected in temporary folders before exfiltration.
- **T1119** — Automated collection: tools automatically collect system and network configuration information.
- **T1113 (StealerBot)** — Screen capture: StealerBot captures screenshots.
- **T1056.001 (StealerBot)** — Keylogging: StealerBot logs keystrokes.
- **T1005 (StealerBot)** — Data from local system: StealerBot's file manager module recursively enumerates and exfiltrates files across drives.

### Command & Control
- **T1071.001** — Web protocols: HTTP/HTTPS used for C2 communications across all documented campaigns.
- **T1105** — Ingress tool transfer: LNK files and JavaScript downloaders fetch remote payloads; multi-stage chain downloads .NET loaders and StealerBot modules from attacker infrastructure.
- **Custom C2 infrastructure** — 400+ live domains with sub-domains crafted to mimic legitimate government and corporate websites (e.g., `mofa-gov-sa.direct888[.]net`), disguising malicious traffic as legitimate.

### Exfiltration
- **T1020** — Automated exfiltration: tools automatically transmit collected files to attacker-controlled servers.
- **T1041 (implied)** — Exfiltration over C2 channel: WarHawk and StealerBot exfiltrate data over the same HTTP/HTTPS C2 channel.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| StealerBot | (no ATT&CK software ID assigned) | Modular memory-only post-exploitation framework (Orchestrator + modules for screencap, keylog, credential theft, file exfil, RDP interception) | Custom |
| WarHawk | (no ATT&CK software ID assigned) | Backdoor with Cobalt Strike loader, command execution, file manager, upload modules; validates PKT timezone | Custom |
| SideWinder.AntiBot.Script | (no ATT&CK software ID assigned) | Server-side phishing evasion script filtering non-target visitors | Custom |
| ModuleInstaller | (no ATT&CK software ID assigned) | .NET downloader / second-stage loader for StealerBot | Custom |
| Custom JavaScript downloaders | (no ATT&CK software ID assigned) | Multi-stage JS loaders executed via HTA/mshta, fetching .NET payloads | Custom |
| Custom LNK loaders | (no ATT&CK software ID assigned) | Weaponized shortcut files initiating the infection chain | Custom |
| Koadic | S0250 | Post-exploitation framework (COM-based) | Public |
| Cobalt Strike | S0154 | Post-exploitation framework (deployed via WarHawk) | Public (commercial) |

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. SideWinder's techniques are designed for stealth and persistence — ensure all implant infrastructure is properly scoped and can be decommissioned cleanly.

Map SideWinder's signature plays to Decepticon's own capabilities:

- **Initial access — spearphishing with themed lures (T1566.001, T1566.002, T1598.002, T1598.003).** Use the phishing skill to craft government/military-themed OOXML documents and ZIP archives containing malicious LNK files. Lures should mimic real government circulars, defense procurement notices, or sector-specific documents (maritime port briefings, nuclear regulatory correspondence). Stand up lookalike government portal login pages on domains with sub-domains mimicking target-country ministry websites (e.g., `mofa-gov-[cc].domain[.]net`).
- **Execution — LNK → HTA → JavaScript → .NET chain (T1204.002, T1059.007, T1218.005, T1203).** Replicate SideWinder's signature multi-stage chain: LNK file triggers `mshta.exe` to execute an HTA containing JavaScript; the JavaScript performs remote template injection to fetch an RTF exploiting CVE-2017-11882 (Equation Editor); the exploit launches additional JavaScript that downloads a .NET loader (ModuleInstaller analog). Use the payload-builder skill for each stage, keeping payloads as close to SideWinder's documented chain as possible.
- **Defense evasion — DLL side-loading & memory-only payloads (T1574.001, T1027.013, T1036.005).** Use a legitimate signed Windows binary (e.g., `rekeywiz.exe`) to side-load a malicious DLL. Ensure the final implant (StealerBot analog) loads modules only into memory — no disk artifacts for the post-exploitation payload. Apply base64 and ECDH-P256 (or equivalent asymmetric) encryption to all staged payloads.
- **Credential access — browser, RDP, and keylogging (T1555.003, T1056.001).** Deploy StealerBot-style modules that extract browser stored credentials, inject into `mstsc.exe` to intercept RDP credentials via named pipes, and log keystrokes. Monitor for process creation events matching target process names.
- **Discovery & collection (T1082, T1083, T1057, T1518.001, T1119).** Automate system profiling (OS version, hostname, user, network config, installed AV via WMI SecurityCenter2 query) and recursive file enumeration across drives. Stage collected files to a temporary folder before exfiltration.
- **C2 — mimicry infrastructure (T1071.001, T1105).** Set up HTTPS C2 using Sliver or custom infrastructure with domain fronting. Register domains with sub-domains impersonating legitimate government websites. Rotate infrastructure aggressively — SideWinder's operational model generates new malware variants within five hours of detection, so emulate rapid C2 rotation and payload re-staging.
- **Exfiltration — automated upload (T1020, T1041).** Configure automated file exfiltration over the C2 HTTPS channel. Emulate WarHawk's upload module pattern: system metadata sent first, then targeted file uploads.
- **WarHawk variant (optional advanced scenario).** For engagements testing watering-hole defenses: compromise an in-scope web application to host a WarHawk-style backdoor that masquerades as a legitimate software update (ASUS/Realtek), validates the target timezone before executing, and deploys a Cobalt Strike beacon with KernelCallBackTable injection.

## Detection & defense

- **CVE-2017-11882 (Equation Editor):** Patch Office or disable the Equation Editor component entirely (`eqnedt32.exe`); monitor for `EQNEDT32.EXE` spawning child processes — any child process is anomalous. This single CVE has been SideWinder's most persistent exploitation vector across all campaigns.
- **LNK-based execution (T1204.002, T1218.005):** Monitor for `mshta.exe` execution with URL or file arguments, especially from user profile directories (`Downloads`, `Desktop`, `Temp`); alert on LNK files in email attachments and ZIP archives; watch for `mshta.exe` → `wscript.exe` / `cscript.exe` → `powershell.exe` process chains.
- **DLL side-loading (T1574.001):** Monitor for legitimate signed binaries (`rekeywiz.exe`, `credwiz.exe`) executing from unusual paths (user `%TEMP%`, `%APPDATA%`); alert on DLL loads from non-standard directories by known side-loading targets; maintain a baseline of expected DLL paths for commonly abused binaries.
- **JavaScript/HTA execution chains (T1059.007):** Restrict or monitor `mshta.exe`, `wscript.exe`, and `cscript.exe` execution via AppLocker/WDAC; alert on script interpreters making outbound HTTP connections; monitor for base64-encoded content in script arguments.
- **StealerBot memory-only implants (T1027.013):** Deploy EDR with in-memory scanning capability; monitor for process injection into `mstsc.exe`; alert on creation of named pipes matching patterns used by StealerBot (e.g., static pipe names like `c63hh148d7c9437caa0f5850256ad32c`); monitor for anomalous RDP credential access patterns.
- **Infrastructure detection:** SideWinder uses domains with sub-domains mimicking government websites — monitor DNS for newly registered domains resembling ministry/government hostnames; implement DNS sinkholing for known SideWinder C2 patterns; alert on HTTP connections to domains with government-impersonating sub-domain structures.
- **Persistence (T1547.001):** Monitor Registry Run key modifications and Startup folder additions, especially entries pointing to binaries in user-writable directories or with names matching legitimate Windows utilities.
- **Automated collection & exfiltration (T1119, T1020):** Monitor for automated file enumeration patterns (recursive directory walks across all drives); alert on bulk file staging to temporary folders followed by HTTP/HTTPS uploads; implement DLP controls on outbound transfers of document collections.
- **Anti-analysis evasion:** SideWinder's AntiBot.Script filters non-target visitors from phishing infrastructure — security teams testing suspected SideWinder phishing pages should use client fingerprints matching the target population (geo-IP, language, user-agent) to avoid being filtered out.

## Sources

- https://attack.mitre.org/groups/G0121/
- https://securelist.com/sidewinder-apt/114089/
- https://securelist.com/sidewinder-apt-updates-its-toolset-and-targets-nuclear-sector/115847/
- https://cdn-cybersecurity.att.com/docs/global-perspective-of-the-sidewinder-apt.pdf
- https://www.kaspersky.com/about/press-releases/kaspersky-identifies-sidewinder-apt-expanding-attacks-with-new-espionage-tool
- https://www.kaspersky.com/about/press-releases/kaspersky-great-uncovers-sidewinder-apts-pivot-to-nuclear-infrastructure-targets
- https://www.zscaler.com/blogs/security-research/warhawk-new-backdoor-arsenal-sidewinder-apt-group
- https://www.group-ib.com/resources/research-hub/sidewinder-apt/
- https://thehackernews.com/2024/10/sidewinder-apt-strikes-middle-east-and.html
- https://thehackernews.com/2025/03/sidewinder-apt-targets-maritime-nuclear.html
- https://cybleinc.com/2020/09/26/sidewinder-apt-targets-with-futuristic-tactics-and-techniques/
- https://www.rewterz.com/articles/analysis-on-sidewinder-apt-group-covid-19
- https://www.darkreading.com/cyberattacks-data-breaches/sidewinder-intensifies-attacks-maritime-sector
- https://www.picussecurity.com/resource/blog/sidewinder-threat-group
