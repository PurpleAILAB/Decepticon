# ANY.RUN Free-Tier Threat Intelligence IOC Reference

> Derived from publicly available ANY.RUN TI Lookup results, sandbox community submissions,
> and ANY.RUN blog posts. Free-tier provides 20 TI Lookup investigations with AI-assisted
> search, YARA search, and downloadable TI Reports. All IOCs below are sourced from public
> reporting by ANY.RUN, vendor advisories (Trend Micro, ESET, Fortinet, Kaspersky, Unit 42,
> Deep Instinct, Google GTIG), and government CSAs (CISA/FBI/NSA).
>
> **Last updated:** 2025-06 | **TI Lookup base URL:** `https://intelligence.any.run/`

---

## Query Syntax Quick Reference

ANY.RUN TI Lookup supports 30+ search fields with `AND`, `OR`, `NOT` and wildcard `*`:

```
threatName:"saltTyphoon"
domainName:"example.com" AND filePath:"malware*"
hash.sha256:"<sha256>"
suricataThreatLevel:"malicious" AND threatName:"lazarus"
mitreTechnique:"T1059.001" AND submissionCountry:"us"
commandLine:"powershell*" AND threatName:"muddywater"
```

---

## 1. Salt Typhoon (Earth Estries / GhostEmperor / UNC2286)

**Aliases:** Earth Estries, GhostEmperor, UNC2286, FamousSparrow
**MITRE ATT&CK Group:** Tracked under Earth Estries; overlaps with G1024

### Report Sources
- Trend Micro, "Game of Emperor: Unveiling Long Term Earth Estries Cyber Intrusions" (Nov 2024)
- CISA/FBI/NSA Joint Advisory AA25-239A, "Countering Salt Typhoon" (Aug 2025)
- IMDA Advisory, "Salt Typhoon targeting telecommunications with new backdoor" (2025)

### Key Malware Families
| Family | Role |
|---|---|
| **GhostSpider** | Modular memory-resident backdoor for stealth espionage |
| **DEMODEX** | Rootkit for persistence, anti-analysis |
| **SnappyBee** (SnapyBee) | Modular backdoor shared across Chinese APT groups |
| **CrowDoor** | Espionage backdoor targeting govt/telco |
| **ZINGDOOR** | Backdoor used in multi-stage attack chains |
| **Masol RAT** | Linux backdoor |
| **ShadowPad** | Shared modular backdoor (also used by APT41, others) |

### SHA-256 Hashes (Public Sources)

**SnappyBee samples (Trend Micro, Oct 2024 Campaign Alpha):**
```
6d64643c044fe534dbb2c1158409138fcded757e550c6f79eada15e69a7865bc  # imfsbDll.dll
25b9fdef3061c7dfea744830774ca0e289dba7c14be85f0d4695d382763b409b  # DgApi.dll
```

**GhostSpider samples (PolySwarm):**
```
fc3be6917fd37a083646ed4b97ebd2d45734a1e154e69c9c33ab00b0589a09e5
05840de7fa648c41c60844c4e5d53dbb3bc2a5250dcb158a95b77bc0f68fa870
b2b617e62353a672626c13cc7ad81b27f23f91282aad7a3a0db471d84852a9ac
2fd4a49338d79f4caee4a60024bcd5ecb5008f1d5219263655ef49c54d9acdec
```

**CISA/NSA/FBI YARA-referenced sample:**
```
f2bbba1ea0f34b262f158ff31e00d39d89bbc471d04e8fca60a034cabe18e4f4
```

**ShadowPad-linked SSL certificate hash:**
```
2b5e7b17fc6e684ff026df3241af4a651fc2b55ca62f8f1f7e34ac8303db9a31  # SSL cert
```

### C2 / Network Indicators
- Exploited CVEs for initial access: CVE-2023-46805, CVE-2024-21887 (Ivanti), CVE-2023-48788 (Fortinet), CVE-2023-20198/20273 (Cisco IOS XE), CVE-2022-3236 (Sophos)
- C2 comms use compromised legitimate infrastructure; GhostSpider is memory-resident
- FakeTLS protocol bytes: `0x17 0x03 0x03` (TLSv1.2 spoof) and `0x17 0x03 0x04` (TLSv1.3 spoof)

### TI Lookup Queries
```
threatName:"salt typhoon"
threatName:"earth estries"
threatName:"ghostspider"
hash.sha256:"6d64643c044fe534dbb2c1158409138fcded757e550c6f79eada15e69a7865bc"
mitreTechnique:"T1014" AND threatName:"demodex"
```

### YARA References
- CISA/NSA/FBI joint advisory YARA rules (2025): detects Salt Typhoon tooling
- Trend Micro IOC appendix: `https://www.trendmicro.com/content/dam/trendmicro/global/en/research/24/k/earth-estries/IOC-earth-estries.txt`

---

## 2. OilRig / APT34 (Crambus / Helix Kitten / Earth Simnavaz)

**MITRE ATT&CK Group:** G0049

### Report Sources
- Symantec (Broadcom), "Crambus: New Campaign Targets Middle Eastern Government" (Oct 2023)
- Picus Security, "OilRig Exposed: Tools and Techniques of APT34" (Apr 2026)
- Booz Allen, "Researchers Discover New variants of APT34 Malware" (Feb 2026)

### Key Malware Families
| Family | Role |
|---|---|
| **Trojan.Dirps** | File enumeration + PowerShell command execution |
| **Infostealer.Clipog** | Clipboard theft + keylogging |
| **Backdoor.PowerExchange** | Exchange-based backdoor |
| **STEALHOOK** | Data exfiltration backdoor (2024 campaigns) |

### SHA-256 Hashes (Symantec/Broadcom)

**Crambus Middle Eastern Government Campaign (Feb-Sep 2023):**
```
497e1c76ed43bcf334557c64e1a9213976cd7df159d695dcc19c1ca3d421b9bc  # Trojan.Dirps
75878356f2e131cefb8aeb07e777fcc110475f8c92417fcade97e207a94ac372  # Infostealer.Clipog
d884b3178fc97d1077a13d47aadf63081559817f499163c2dc29f6828ee08cae  # Backdoor.PowerExchange
```

### C2 / Network Indicators
- C2 ports: 8080 (fake 404 responses), 8989, 9090, 10443
- Consistent reuse of single SSH fingerprint across infrastructure
- DNS tunneling for data exfiltration
- CVE-2024-30088 (Windows Kernel) used for SYSTEM privilege escalation in 2024 campaigns

### TI Lookup Queries
```
threatName:"oilrig"
threatName:"apt34"
hash.sha256:"497e1c76ed43bcf334557c64e1a9213976cd7df159d695dcc19c1ca3d421b9bc"
commandLine:"powershell*" AND threatName:"oilrig"
destinationPort:"8080" AND threatName:"apt34"
```

### YARA References
- Symantec IOC appendix for Crambus campaign
- Booz Allen Dark Labs APT34 variant detection rules

---

## 3. APT41 (Double Dragon / Wicked Panda / Barium)

**MITRE ATT&CK Group:** G0096

### Report Sources
- Google GTIG, "APT41 Has Arisen From the DUST" (Jul 2024)
- Google GTIG, "Mark Your Calendar: APT41 Innovative Tactics" (May 2025)
- KPMG Cyber Threat Intelligence Advisory, "APT41 – Deploying Sophisticated Tools" (Jul 2024)
- Cisco Talos, "APT41 compromised Taiwanese government-affiliated research institute" (Dec 2024)

### Key Malware Families
| Family | Role |
|---|---|
| **DUSTPAN / DUSTTRAP** | Memory-resident droppers |
| **DEAD EYE / LOWKEY.PASSIVE** | Lightweight in-memory backdoors |
| **TOUGHPROGRESS** | Google Calendar-based C2 backdoor (Oct 2024) |
| **ShadowPad** | Modular backdoor/RAT (shared tool) |
| **PineGrove** | Data exfiltration |
| **SQLULDR2** | Database exfiltration utility |

### SHA-256 Hashes

**ShadowPad sideloading (Cisco Talos, 2024):**
```
3fc4f3ffce6188d3ef676f9825cdfa297903f6ca7f76603f12179b2e4be90134  # BitDefender binary (loader)
```

### C2 Domains (KPMG, Jul 2024)
```
macfee[.]ga
agegamepay[.]com
notped[.]com
ageofwuxia[.]com
paniesx[.]com
ageofwuxia[.]net
dnsgogle[.]com
ageofwuxia[.]org
ns2.akacur[.]tk
time.qnapntp[.]com
```

### C2 Files/Artifacts
- `TSVIPSrv.dll` — malicious DLL
- `texttable.xsl` — malicious file
- TOUGHPROGRESS archive: `出境海關申報清單.zip` (2024-10-23), LNK disguised as PDF

### TI Lookup Queries
```
threatName:"apt41"
threatName:"shadowpad" AND domainName:"*.ga"
threatName:"dustpan" OR threatName:"dusttrap"
domainName:"dnsgogle.com"
filePath:"TSVIPSrv.dll"
```

### YARA References
- Google Threat Intelligence collection for APT41 IOCs
- Google Cloud blog IOC appendix (May 2025)

---

## 4. Lazarus Group (HIDDEN COBRA / APT38 / Diamond Sleet)

**MITRE ATT&CK Group:** G0032

### Report Sources
- ANY.RUN Blog, "Lazarus Group Attacks in 2025: Overview for SOC Teams" (Sep 2025)
- ANY.RUN Blog, "OtterCookie: Analysis of New Lazarus Group Malware" (Jun 2025)
- ANY.RUN Blog, "Lazarus Mach-O Man Malware" (Apr 2026)
- Kaspersky, "Operation DreamJob Targets Nuclear Sector with CookiePlus" (Dec 2024)
- SecurityScorecard, "Operation Phantom Circuit" (Apr 2026)

### Key Malware Families
| Family | Role |
|---|---|
| **BeaverTail** | JavaScript/Python stealer, initial payload |
| **InvisibleFerret** | Python-based modular RAT, keylogging, screen capture |
| **OtterCookie** | Credential/crypto wallet stealer via hijacked npm packages |
| **CookiePlus** | Modular backdoor disguised as open-source plugin (DreamJob) |
| **TsunamiKit** | Updated InvisibleFerret browser-data stealer module (Nov 2024) |

### C2 / Network Indicators
- C2 active since Sep 2024 for Operation Phantom Circuit
- Primary C2 ports: 8888, 9999
- Known C2 domain: `www.addfriend[.]kr` (IP: `211.239.117[.]117`)
- Delivery: fake job interview platforms, hijacked npm packages

### TI Lookup Queries
```
threatName:"lazarus"
threatName:"invisibleferret"
threatName:"ottercookie"
threatName:"beavertail"
destinationPort:"8888" AND threatName:"lazarus"
commandLine:"node*" AND threatName:"lazarus"
```

### YARA References
- ESET malware-ioc GitHub: `nukesped_lazarus/samples.sha256`
- CISA advisories AA22-108A, AA21-048A
- ANY.RUN sandbox YARA matching via `yaraRule:` search field

---

## 5. Turla (Secret Blizzard / Venomous Bear / Pensive Ursa)

**MITRE ATT&CK Group:** G0010

### Report Sources
- ESET, "Gamaredon X Turla collab" (Sep 2025)
- Hybrid Analysis Blog, "Analyzing the Newest Turla Backdoor" (Sep 2024)
- Palo Alto Unit 42, "Over the Kazuar's Nest" (Jun 2024)
- The Hacker News, "Turla Turns Kazuar Backdoor Into Modular P2P Botnet" (May 2026)

### Key Malware Families
| Family | Role |
|---|---|
| **Kazuar v2** | Modular P2P botnet backdoor (Kernel/Bridge/Worker modules) |
| **Pelmeni Wrapper** | Wrapper/loader for Kazuar |
| **PteroOdd / PteroEffigy / PteroPaste** | Gamaredon PowerShell downloaders delivering Kazuar |

### SHA-256 Hashes (Hybrid Analysis, ESET)

**Kazuar samples (Sep 2024):**
```
7091ce97fb5906680c1b09558bafdf9681a81f5f524677b90fd0f7fc0a05bc00
cac4d4364d20fa343bf681f6544b31995a57d8f69ee606c4675db60be5ae8775
b6abbeab6e000036c6cdffc57c096d796397263e280ea264eba73ac5bab39441
8d6fe8e336e020410753ff15ece5f36bae992f7f234385a23590a11ed734792d
```

### C2 Domains / IPs (2025 campaigns)

**WordPress-hosted C&C (Gamaredon-Turla collaboration, 2025):**
```
abrargeospatial[.]ir
brannenburger-nagelfluh[.]de
pizzeria-mercy[.]de
```

**Additional C2:**
```
eset.ydns[.]eu          # PteroOdd delivery (Apr 2025)
91.231.182[.]187         # PteroPaste delivery (Jun 2025)
```

### Mutex
```
{C916E9A6-EEDF-4648-9A29-9E5713F4E79A}    # Kazuar single-instance mutex
```

### TI Lookup Queries
```
threatName:"turla"
threatName:"kazuar"
hash.sha256:"7091ce97fb5906680c1b09558bafdf9681a81f5f524677b90fd0f7fc0a05bc00"
domainName:"*.ydns.eu" AND commandLine:"powershell*"
mutexName:"C916E9A6*"
```

### YARA References
- ESET GitHub: `https://github.com/eset/malware-ioc` (Gamaredon-Turla collab IOCs)
- Unit 42 Kazuar analysis IOC appendix

---

## 6. MuddyWater (Boggy Serpens / Mercury / Mango Sandstorm)

**MITRE ATT&CK Group:** G0069

### Report Sources
- Deep Instinct, "PhonyC2: Revealing a New Malicious C2 Framework" (Jun 2023)
- Fortinet FortiGuard Labs, "UDPGangster Campaigns Target Multiple Countries" (Dec 2025)
- Deep Instinct, "DarkBeatC2: The Latest MuddyWater Attack Framework" (Apr 2024)
- ANY.RUN TI Report, "ShadowAgent and UDPGangster" (Dec 2025)

### Key Malware Families
| Family | Role |
|---|---|
| **PhonyC2** | Custom Python C2 framework (in dev since 2021) |
| **UDPGangster** | UDP-based backdoor for exfil, cmd exec, payload deployment |
| **DarkBeatC2** | Latest C2 framework iteration |
| **MuddyC2Go** | Go-based C2 framework |

### SHA-256 Hashes

**UDPGangster (PolySwarm):**
```
7ea4b307e84c8b32c0220eca13155a4cf66617241f96b8af26ce2db8115e3d53
```

**UDPGangster Turkey campaign (Malwation):**
```
dd267575e2f6835f8a8a0e65e9dbc763ca9229b55af7d212da38b949051ae296  # karel.com.tr MSI
```

### C2 / Network Indicators
- UDPGangster C2: `157.20.182[.]75` (UDP port 1269)
- UDPGangster commands: `0x04` heartbeat, `0x0A` cmd.exe, `0x14` file exfil, `0x1E` payload drop, `0x63` C2 update
- PhonyC2 archive: `PhonyC2_v6.zip` (config: IP, port, random UUIDs for URL tracking)
- PhonyC2 source code: Deep Instinct GitHub
- Delivery: phishing emails mimicking Turkish Republic of Northern Cyprus Ministry of Foreign Affairs

### TI Lookup Queries
```
threatName:"muddywater"
threatName:"udpgangster"
threatName:"phonyc2"
hash.sha256:"7ea4b307e84c8b32c0220eca13155a4cf66617241f96b8af26ce2db8115e3d53"
destinationPort:"1269" AND protocol:"udp"
commandLine:"msiexec*" AND threatName:"muddywater"
```

### YARA References
- Deep Instinct PhonyC2 GitHub IOCs
- Fortinet FortiGuard UDPGangster detection signatures
- ANY.RUN TI Report Dec 2025 (UDPGangster YARA rules)

---

## 7. Mustang Panda (Bronze President / Hive0154 / TA416)

**MITRE ATT&CK Group:** G0129

### Report Sources
- Intezer, "Frankenstein Variant of the ToneShell Backdoor Targeting Myanmar" (Dec 2025)
- IBM X-Force, "Hive0154 drops updated Toneshell and novel SnakeDisk USB worm" (Nov 2025)
- Zscaler ThreatLabz, "Mustang Panda: ToneShell and StarProxy" (Apr 2026)
- Kaspersky, "Mustang Panda Uses Signed Kernel-Mode Rootkit to Load TONESHELL" (Dec 2025)

### Key Malware Families
| Family | Role |
|---|---|
| **TONESHELL** (v7-v9) | Primary backdoor with FakeTLS C2 protocol |
| **PlugX** | Long-running modular RAT |
| **SnakeDisk** | USB worm for air-gapped network propagation |
| **StarProxy** | Network proxy/tunnel tool |
| **LOTUSLITE** | Loader component |

### SHA-256 Hashes (Intezer, IBM)

**ToneShell Frankenstein variant (Dec 2025):**
```
543024edc9f160cc1cedcffc3de52bfa656daa0ec9ed351331d97faaa67d0d99  # update.zip archive
1272a0853651069ed4dc505007e8525f99e1454f9e033bcc2e58d60fdafa4f0   # SkinH.dll (compiled 2025-07-14)
e7b29611c789a6225aebbc9fee3710a57b51537693cb2ec16e2177c22392b546
a58868b3d50b775de99278eeb14da8b7409b165aa45313c6d9fa35ac30d2cda2
```

### C2 / Network Indicators
- TONESHELL FakeTLS headers: `0x17 0x03 0x03` (TLSv1.2) → `0x17 0x03 0x04` (TLSv1.3 spoof in newer variants)
- C2 domain: `coastallasercompany[.]com` (HTTPS)
- C2 infrastructure erected Sep 2024, campaigns commenced Feb 2025
- Sideloading: `USBSRService.exe` → `EasyFuncs.dll` (ToneShell), export `FS_RegActiveX`
- Toneshell9: proxy-aware C2, two parallel reverse shells

### TI Lookup Queries
```
threatName:"mustang panda"
threatName:"toneshell"
threatName:"plugx" AND submissionCountry:"mm"
hash.sha256:"543024edc9f160cc1cedcffc3de52bfa656daa0ec9ed351331d97faaa67d0d99"
filePath:"SkinH.dll"
domainName:"coastallasercompany.com"
```

### YARA References
- IBM X-Force Hive0154 IOC appendix
- Intezer Frankenstein ToneShell analysis IOCs
- Zscaler ThreatLabz detection rules

---

## 8. Dark Caracal (Bandook / Poco RAT)

**MITRE ATT&CK:** No dedicated group ID; attributed by Lookout/EFF, tracked by ESET, PT Security

### Report Sources
- Positive Technologies, "The evolution of Dark Caracal tools: Poco RAT campaign" (May 2025)
- Fortinet FortiGuard Labs, "Bandook - A Persistent Threat That Keeps Evolving" (Dec 2023)
- ESET malware-ioc GitHub: bandook samples
- Malware-Traffic-Analysis.net, Bandook infection analysis (Aug 2023)

### Key Malware Families
| Family | Role |
|---|---|
| **Bandook** | Full-featured RAT (139+ commands), persistent evolution |
| **Poco RAT** | Newer backdoor, likely Bandook evolution/replacement |

### SHA-256 Hashes

**Bandook sample (Malware-Traffic-Analysis, Aug 2023):**
```
2804b45d46b093cc804ec8a8626375e90d495979b0108c480c78a5751a74bda2  # C988563.7z
```

### C2 / Network Indicators
- Bandook C2: `185.10.68[.]52:6591` (initial), `vrunabo[.]su` on `185.10.68[.]127:6591` (follow-up)
- C2 encryption: AES-CFB with hardcoded IV `0123456789123456`
- Domain registrars: Porkbun, NameSilo
- Delivery: password-protected .7z via shortened URLs in PDF lures
- Injection target: `msinfo32.exe`
- 483 Poco RAT samples identified Jun 2024 – Feb 2025 (Positive Technologies)
- Geographic focus: Venezuela, Dominican Republic, Chile, Colombia

### TI Lookup Queries
```
threatName:"bandook"
threatName:"poco rat"
threatName:"dark caracal"
hash.sha256:"2804b45d46b093cc804ec8a8626375e90d495979b0108c480c78a5751a74bda2"
destinationIP:"185.10.68.52"
filePath:"msinfo32.exe" AND threatName:"bandook"
```

### YARA References
- ESET GitHub: `https://github.com/eset/malware-ioc/tree/master/bandook`
- Fortinet FortiGuard Bandook detection signatures
- Check Point Research Bandook report IOCs

---

## Cross-Reference: ANY.RUN TI Report Schedule

| Month | Threats Covered | Free Access |
|---|---|---|
| Dec 2025 (Part 1) | GuLoader, Albiriox, OctoRAT | Yes |
| Dec 2025 (Part 2) | **ShadowAgent, UDPGangster (MuddyWater)** | Yes |
| Nov 2025 | Sturnus, ShinySpider, Tsundere | Yes |
| Jan 2026 | Retro-C2, Scarface, Santastealer | Yes |

Reports include: pre-built TI Lookup queries, YARA signatures, IOCs, behavioral TTPs.
Access at: `https://intelligence.any.run/reports`

---

## Appendix: General TI Lookup Query Templates

```bash
# By threat actor name
threatName:"<actor_name>"

# By file hash
hash.sha256:"<sha256>"
hash.md5:"<md5>"

# By network indicator
domainName:"<domain>" AND filePath:"<pattern>*"
destinationIP:"<ip>" AND destinationPort:"<port>"

# By MITRE technique
mitreTechnique:"T1059.001"   # PowerShell
mitreTechnique:"T1055"       # Process Injection
mitreTechnique:"T1071.001"   # Web Protocols C2

# By Suricata rule severity
suricataThreatLevel:"malicious" AND threatName:"<malware>"

# By submission country
submissionCountry:"<iso2>" AND threatName:"<actor>"

# Combined hunting
threatName:"lazarus" AND mitreTechnique:"T1566.001"
```
