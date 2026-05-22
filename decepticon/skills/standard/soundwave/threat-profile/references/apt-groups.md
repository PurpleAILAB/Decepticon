# Known APT Group Quick Reference

Reference for selecting specific APT groups to emulate. Use this when the client requests simulation of a specific threat actor or when the engagement targets an industry with known adversaries.

## APT29 (Cozy Bear / Nobelium / Midnight Blizzard)

| Field | Detail |
|-------|--------|
| **Attribution** | Russia (SVR) |
| **Targets** | Government, technology, think tanks, diplomatic |
| **Motivation** | Espionage |
| **Sophistication** | Nation-state |
| **Notable** | SolarWinds supply chain (2020), OAuth abuse, cloud targeting |

**Key TTPs:**
| ID | Technique |
|----|-----------|
| T1195.002 | Supply Chain Compromise: Compromise Software Supply Chain |
| T1078.004 | Valid Accounts: Cloud Accounts |
| T1550.001 | Use Alternate Authentication Material: Application Access Token |
| T1098 | Account Manipulation |
| T1071.001 | Application Layer Protocol: Web Protocols |
| T1059.001 | Command and Scripting Interpreter: PowerShell |

---

## APT41 (Winnti / Barium / Wicked Panda)

| Field | Detail |
|-------|--------|
| **Attribution** | China (MSS-linked) |
| **Targets** | Technology, gaming, healthcare, telecom |
| **Motivation** | Dual: espionage + financial |
| **Sophistication** | Nation-state |
| **Notable** | Supply chain attacks, rootkits, dual operations |

**Key TTPs:**
| ID | Technique |
|----|-----------|
| T1195.002 | Supply Chain Compromise |
| T1059.001 | PowerShell |
| T1053.005 | Scheduled Task |
| T1574.001 | DLL Search Order Hijacking |
| T1070.004 | Indicator Removal: File Deletion |
| T1003.001 | OS Credential Dumping: LSASS Memory |

---

## FIN7 (Carbanak / Navigator Group)

| Field | Detail |
|-------|--------|
| **Attribution** | Eastern Europe (cybercriminal) |
| **Targets** | Retail, hospitality, financial services |
| **Motivation** | Financial |
| **Sophistication** | Medium-High |
| **Notable** | Point-of-sale malware, social engineering |

**Key TTPs:**
| ID | Technique |
|----|-----------|
| T1566.001 | Phishing: Spearphishing Attachment |
| T1059.001 | PowerShell |
| T1059.005 | Visual Basic |
| T1053.005 | Scheduled Task |
| T1071.001 | Application Layer Protocol: Web |
| T1005 | Data from Local System |

---

## Lazarus Group (Hidden Cobra / ZINC)

| Field | Detail |
|-------|--------|
| **Attribution** | North Korea (RGB) |
| **Targets** | Financial, cryptocurrency, defense, media |
| **Motivation** | Financial + espionage |
| **Sophistication** | Nation-state |
| **Notable** | Cryptocurrency theft, watering holes, custom malware |

**Key TTPs:**
| ID | Technique |
|----|-----------|
| T1189 | Drive-by Compromise |
| T1566.002 | Phishing: Spearphishing Link |
| T1059.006 | Python |
| T1055 | Process Injection |
| T1071.001 | Application Layer Protocol: Web |
| T1486 | Data Encrypted for Impact |

---

## APT28 (Fancy Bear / Sofacy / Strontium)

| Field | Detail |
|-------|--------|
| **Attribution** | Russia (GRU) |
| **Targets** | Government, military, media, political orgs |
| **Motivation** | Espionage + disruption |
| **Sophistication** | Nation-state |
| **Notable** | 0-day usage, credential harvesting, election interference |

**Key TTPs:**
| ID | Technique |
|----|-----------|
| T1566.001 | Phishing: Spearphishing Attachment |
| T1190 | Exploit Public-Facing Application |
| T1078 | Valid Accounts |
| T1059.001 | PowerShell |
| T1003.001 | LSASS Memory Dump |
| T1048.002 | Exfiltration Over Asymmetric Encrypted Non-C2 Protocol |

---

## Industry → Likely Threat Actors

Quick lookup for engagement scoping:

| Target Industry | Primary Threat | Secondary Threat |
|----------------|---------------|-----------------|
| Financial | FIN7, Lazarus | APT41 |
| Government | APT29, APT28 | Lazarus |
| Technology | APT41, APT29 | FIN7 |
| Healthcare | APT41 | Opportunistic ransomware |
| Defense | APT28, Lazarus | APT29 |
| Retail/Hospitality | FIN7 | Opportunistic |
| Cryptocurrency | Lazarus | Opportunistic |
| Energy/Utilities | APT28 | APT41 |
