// Skillogy v0.2 — Capability-plane overlay for the Decepticon knowledge graph.
// Additive (MERGE-based, idempotent).
// Defines 20 Capability nodes and ~140 edges (PRODUCES, CONSUMES,
// COMPOSES_WITH, SUBSTITUTES, FORBIDDEN_BY) that let the planner reason
// about skill chains, composability, and operational constraints.


// ============================================================
// === Capability nodes =======================================
// ============================================================
// A Capability is an *abstract output class* that one or more Skills
// can produce or consume.  The planner walks PRODUCES → CONSUMES
// edges to discover valid chains.

MERGE (c:Capability {name: 'subdomain-list'})
SET c.description = 'Enumerated set of live subdomains and virtual hosts',
    c.phase       = 'reconnaissance',
    c.artifact    = 'subdomains.txt';

MERGE (c:Capability {name: 'credential-set'})
SET c.description = 'Harvested or cracked username:password / hash pairs',
    c.phase       = 'credential-access',
    c.artifact    = 'creds.json';

MERGE (c:Capability {name: 'phishing-payload'})
SET c.description = 'Weaponised lure ready for delivery (HTML, PDF, QR, macro)',
    c.phase       = 'initial-access',
    c.artifact    = 'payload.zip';

MERGE (c:Capability {name: 'reverse-shell'})
SET c.description = 'Interactive remote command execution channel',
    c.phase       = 'execution',
    c.artifact    = 'session';

MERGE (c:Capability {name: 'c2-channel'})
SET c.description = 'Established command-and-control communication link',
    c.phase       = 'command-and-control',
    c.artifact    = 'beacon';

MERGE (c:Capability {name: 'privilege-escalation-vector'})
SET c.description = 'Path from unprivileged to SYSTEM / root / admin',
    c.phase       = 'privilege-escalation',
    c.artifact    = 'privesc-path.md';

MERGE (c:Capability {name: 'lateral-movement-path'})
SET c.description = 'Validated route to pivot from host A to host B',
    c.phase       = 'lateral-movement',
    c.artifact    = 'pivot.json';

MERGE (c:Capability {name: 'ad-domain-map'})
SET c.description = 'BloodHound-style graph of AD trusts, GPOs, ACLs',
    c.phase       = 'reconnaissance',
    c.artifact    = 'bloodhound.zip';

MERGE (c:Capability {name: 'web-vulnerability-report'})
SET c.description = 'Confirmed web-app vulnerability with PoC',
    c.phase       = 'web-exploitation',
    c.artifact    = 'finding.json';

MERGE (c:Capability {name: 'cloud-identity-token'})
SET c.description = 'Stolen or forged cloud bearer / STS / refresh token',
    c.phase       = 'credential-access',
    c.artifact    = 'token.json';

MERGE (c:Capability {name: 'persistence-implant'})
SET c.description = 'Durable foothold surviving reboot (service, scheduled task, registry)',
    c.phase       = 'persistence',
    c.artifact    = 'implant-manifest.json';

MERGE (c:Capability {name: 'exfil-archive'})
SET c.description = 'Staged data package ready for exfiltration',
    c.phase       = 'exfiltration',
    c.artifact    = 'loot.tar.gz';

MERGE (c:Capability {name: 'wireless-handshake'})
SET c.description = 'Captured WPA/WPA2/WPA3 handshake or PMKID for offline cracking',
    c.phase       = 'credential-access',
    c.artifact    = 'capture.pcapng';

MERGE (c:Capability {name: 'firmware-image'})
SET c.description = 'Extracted firmware blob ready for RE (binwalk / ubi_reader output)',
    c.phase       = 'reverse-engineering',
    c.artifact    = 'firmware.bin';

MERGE (c:Capability {name: 'malware-sample-analysis'})
SET c.description = 'Behavioural + static analysis report for a malware specimen',
    c.phase       = 'reverse-engineering',
    c.artifact    = 'analysis.json';

MERGE (c:Capability {name: 'yara-ruleset'})
SET c.description = 'Detection rules for hunting malware families or IOCs',
    c.phase       = 'detection',
    c.artifact    = 'rules.yar';

MERGE (c:Capability {name: 'osint-dossier'})
SET c.description = 'Aggregated open-source intelligence profile on target',
    c.phase       = 'reconnaissance',
    c.artifact    = 'dossier.md';

MERGE (c:Capability {name: 'supply-chain-vector'})
SET c.description = 'Identified dependency-confusion, typosquat, or CI/CD injection path',
    c.phase       = 'initial-access',
    c.artifact    = 'supply-chain-finding.json';

MERGE (c:Capability {name: 'ai-model-exploit'})
SET c.description = 'Working prompt-injection, jailbreak, or model-extraction PoC',
    c.phase       = 'ai-security',
    c.artifact    = 'ai-exploit.json';

MERGE (c:Capability {name: 'threat-intel-report'})
SET c.description = 'Structured threat intelligence product (TTP map, IOC bundle, campaign summary)',
    c.phase       = 'intelligence',
    c.artifact    = 'ti-report.json';


// ============================================================
// === PRODUCES edges (Skill → Capability) ====================
// === A skill *produces* a capability when it can generate    =
// === that artifact class as a primary output.                =
// ============================================================

// --- Reconnaissance / OSINT producers ---
MATCH (s:Skill {name: 'passive-recon'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'passive-recon'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'osint'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'osint'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'web-recon'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'web-recon'}), (c:Capability {name: 'web-vulnerability-report'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'open-web'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'wireless-security'}), (c:Capability {name: 'wireless-handshake'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Credential-access producers ---
MATCH (s:Skill {name: 'credential-access'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'ad-domain-map'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Phishing producers ---
MATCH (s:Skill {name: 'html-smuggling-lure'}), (c:Capability {name: 'phishing-payload'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'pdf-credential-harvest'}), (c:Capability {name: 'phishing-payload'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'quishing'}), (c:Capability {name: 'phishing-payload'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'mfa-fatigue-social'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'pdf-credential-harvest'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Exploitation / shell producers ---
MATCH (s:Skill {name: 'web'}), (c:Capability {name: 'web-vulnerability-report'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'web'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'command-injection'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'edge-device-exploitation'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'rmm-tool-abuse'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- C2 producers ---
MATCH (s:Skill {name: 'c2'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'c2-cobalt-strike'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'c2-domain-fronting'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'c2-alternative-channels'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Privilege-escalation / lateral-movement producers ---
MATCH (s:Skill {name: 'lateral-movement'}), (c:Capability {name: 'lateral-movement-path'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'lateral-movement-path'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'privilege-escalation-vector'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Cloud producers ---
MATCH (s:Skill {name: 'gcp-org-escalation'}), (c:Capability {name: 'cloud-identity-token'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'gcp-org-escalation'}), (c:Capability {name: 'privilege-escalation-vector'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (c:Capability {name: 'cloud-identity-token'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (c:Capability {name: 'exfil-archive'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Persistence producers ---
MATCH (s:Skill {name: 'persistence'}), (c:Capability {name: 'persistence-implant'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'c2-cobalt-strike'}), (c:Capability {name: 'persistence-implant'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Reverse-engineering producers ---
MATCH (s:Skill {name: 'triage'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'malware-triage'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'deep-analysis'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ghidra'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'firmware'}), (c:Capability {name: 'firmware-image'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'packer-unpacking'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'yara-hunting'}), (c:Capability {name: 'yara-ruleset'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ti-yara-hunting'}), (c:Capability {name: 'yara-ruleset'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Wireless producers ---
MATCH (s:Skill {name: 'wpa2-psk'}), (c:Capability {name: 'wireless-handshake'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'wpa2-psk'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'wpa3-sae'}), (c:Capability {name: 'wireless-handshake'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'wpa-enterprise-eap'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'evil-twin-karma'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Supply-chain producers ---
MATCH (s:Skill {name: 'supply-chain'}), (c:Capability {name: 'supply-chain-vector'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Threat-intel producers ---
MATCH (s:Skill {name: 'ti-ioc-extraction'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

MATCH (s:Skill {name: 'ti-anyrun-lookup'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

MATCH (s:Skill {name: 'threat-profile'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- AI-security producers ---
MATCH (s:Skill {name: 'ai-red-team'}), (c:Capability {name: 'ai-model-exploit'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Exfiltration producers ---
MATCH (s:Skill {name: 'exfiltration'}), (c:Capability {name: 'exfil-archive'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Fuzzing producers ---
MATCH (s:Skill {name: 'fuzzing'}), (c:Capability {name: 'web-vulnerability-report'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- ROP producers ---
MATCH (s:Skill {name: 'rop-chain'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);


// ============================================================
// === CONSUMES edges (Skill → Capability) ====================
// === A skill *consumes* a capability when it requires that   =
// === artifact class as a prerequisite input.                 =
// ============================================================

// --- Exploitation consumes recon output ---
MATCH (s:Skill {name: 'web'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'command-injection'}), (c:Capability {name: 'web-vulnerability-report'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'edge-device-exploitation'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Credential use consumes credential-set ---
MATCH (s:Skill {name: 'lateral-movement'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (c:Capability {name: 'cloud-identity-token'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'gcp-org-escalation'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'gcp-org-escalation'}), (c:Capability {name: 'cloud-identity-token'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- C2 consumes shells ---
MATCH (s:Skill {name: 'c2'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'c2-cobalt-strike'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'c2-domain-fronting'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'c2-alternative-channels'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

// --- Persistence consumes C2 or shell ---
MATCH (s:Skill {name: 'persistence'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'persistence'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

// --- Privilege escalation consumes shell ---
MATCH (s:Skill {name: 'ad'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Lateral movement consumes paths ---
MATCH (s:Skill {name: 'lateral-movement'}), (c:Capability {name: 'ad-domain-map'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Exfiltration consumes C2 ---
MATCH (s:Skill {name: 'exfiltration'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

// --- Phishing consumes OSINT ---
MATCH (s:Skill {name: 'html-smuggling-lure'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'pdf-credential-harvest'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'quishing'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'mfa-fatigue-social'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

// --- RE consumes firmware / samples ---
MATCH (s:Skill {name: 'deep-analysis'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'ghidra'}), (c:Capability {name: 'firmware-image'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'packer-unpacking'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'yara-hunting'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

MATCH (s:Skill {name: 'ti-yara-hunting'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Wireless consumes handshake for cracking ---
MATCH (s:Skill {name: 'wpa2-psk'}), (c:Capability {name: 'wireless-handshake'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'wpa3-sae'}), (c:Capability {name: 'wireless-handshake'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- TI consumes threat intel ---
MATCH (s:Skill {name: 'ti-ioc-extraction'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'ti-anyrun-lookup'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Supply-chain consumes recon ---
MATCH (s:Skill {name: 'supply-chain'}), (c:Capability {name: 'subdomain-list'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

MATCH (s:Skill {name: 'supply-chain'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- RMM abuse consumes credentials ---
MATCH (s:Skill {name: 'rmm-tool-abuse'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:CONSUMES {required: true}]->(c);

// --- ROP consumes binary analysis ---
MATCH (s:Skill {name: 'rop-chain'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);


// ============================================================
// === COMPOSES_WITH edges (Skill ↔ Skill) ====================
// === Bidirectional composability: two skills can be chained  =
// === or used in parallel within the same engagement phase.   =
// ============================================================

// --- Recon composition ---
MATCH (a:Skill {name: 'passive-recon'}), (b:Skill {name: 'web-recon'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reconnaissance', note: 'passive first, then active probing'}]->(b);

MATCH (a:Skill {name: 'passive-recon'}), (b:Skill {name: 'osint'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reconnaissance', note: 'complementary OSINT enrichment'}]->(b);

MATCH (a:Skill {name: 'web-recon'}), (b:Skill {name: 'open-web'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reconnaissance', note: 'web fingerprint + content discovery'}]->(b);

MATCH (a:Skill {name: 'osint'}), (b:Skill {name: 'open-web'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reconnaissance', note: 'OSINT targets fed to open-web scanner'}]->(b);

// --- Phishing composition ---
MATCH (a:Skill {name: 'html-smuggling-lure'}), (b:Skill {name: 'pdf-credential-harvest'})
MERGE (a)-[:COMPOSES_WITH {phase: 'initial-access', note: 'dual-format phishing campaign'}]->(b);

MATCH (a:Skill {name: 'html-smuggling-lure'}), (b:Skill {name: 'quishing'})
MERGE (a)-[:COMPOSES_WITH {phase: 'initial-access', note: 'email + QR phishing'}]->(b);

MATCH (a:Skill {name: 'mfa-fatigue-social'}), (b:Skill {name: 'pdf-credential-harvest'})
MERGE (a)-[:COMPOSES_WITH {phase: 'initial-access', note: 'credential harvest then MFA push abuse'}]->(b);

// --- C2 composition ---
MATCH (a:Skill {name: 'c2-cobalt-strike'}), (b:Skill {name: 'c2-domain-fronting'})
MERGE (a)-[:COMPOSES_WITH {phase: 'command-and-control', note: 'CS beacon with domain-fronting transport'}]->(b);

MATCH (a:Skill {name: 'c2-cobalt-strike'}), (b:Skill {name: 'c2-alternative-channels'})
MERGE (a)-[:COMPOSES_WITH {phase: 'command-and-control', note: 'CS with DNS/ICMP exfil channel'}]->(b);

MATCH (a:Skill {name: 'c2-domain-fronting'}), (b:Skill {name: 'c2-alternative-channels'})
MERGE (a)-[:COMPOSES_WITH {phase: 'command-and-control', note: 'layered covert channels'}]->(b);

// --- AD + lateral movement composition ---
MATCH (a:Skill {name: 'ad'}), (b:Skill {name: 'lateral-movement'})
MERGE (a)-[:COMPOSES_WITH {phase: 'post-exploitation', note: 'AD enum feeds lateral movement'}]->(b);

MATCH (a:Skill {name: 'ad'}), (b:Skill {name: 'credential-access'})
MERGE (a)-[:COMPOSES_WITH {phase: 'post-exploitation', note: 'Kerberoast + DCSync chain'}]->(b);

MATCH (a:Skill {name: 'lateral-movement'}), (b:Skill {name: 'persistence'})
MERGE (a)-[:COMPOSES_WITH {phase: 'post-exploitation', note: 'pivot then persist on new host'}]->(b);

// --- Exploitation composition ---
MATCH (a:Skill {name: 'web'}), (b:Skill {name: 'command-injection'})
MERGE (a)-[:COMPOSES_WITH {phase: 'web-exploitation', note: 'web vuln → RCE chain'}]->(b);

MATCH (a:Skill {name: 'web'}), (b:Skill {name: 'edge-device-exploitation'})
MERGE (a)-[:COMPOSES_WITH {phase: 'exploitation', note: 'web app vuln on edge appliance'}]->(b);

MATCH (a:Skill {name: 'command-injection'}), (b:Skill {name: 'c2'})
MERGE (a)-[:COMPOSES_WITH {phase: 'exploitation', note: 'RCE → C2 implant'}]->(b);

// --- RE composition ---
MATCH (a:Skill {name: 'triage'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'quick triage then deep dive'}]->(b);

MATCH (a:Skill {name: 'malware-triage'}), (b:Skill {name: 'ghidra'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'behavioural triage then static RE'}]->(b);

MATCH (a:Skill {name: 'packer-unpacking'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'unpack then analyse'}]->(b);

MATCH (a:Skill {name: 'yara-hunting'}), (b:Skill {name: 'ti-ioc-extraction'})
MERGE (a)-[:COMPOSES_WITH {phase: 'detection', note: 'YARA rules + IOC correlation'}]->(b);

MATCH (a:Skill {name: 'firmware'}), (b:Skill {name: 'ghidra'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'firmware extraction then Ghidra RE'}]->(b);

// --- Wireless composition ---
MATCH (a:Skill {name: 'wpa2-psk'}), (b:Skill {name: 'evil-twin-karma'})
MERGE (a)-[:COMPOSES_WITH {phase: 'wireless', note: 'handshake capture + evil twin'}]->(b);

MATCH (a:Skill {name: 'deauth-pmf'}), (b:Skill {name: 'wpa2-psk'})
MERGE (a)-[:COMPOSES_WITH {phase: 'wireless', note: 'deauth forces reconnect for handshake'}]->(b);

MATCH (a:Skill {name: 'deauth-pmf'}), (b:Skill {name: 'evil-twin-karma'})
MERGE (a)-[:COMPOSES_WITH {phase: 'wireless', note: 'deauth clients onto rogue AP'}]->(b);

MATCH (a:Skill {name: 'wpa-enterprise-eap'}), (b:Skill {name: 'evil-twin-karma'})
MERGE (a)-[:COMPOSES_WITH {phase: 'wireless', note: 'EAP relay via evil twin'}]->(b);

MATCH (a:Skill {name: 'krack-fragattacks'}), (b:Skill {name: 'wpa2-psk'})
MERGE (a)-[:COMPOSES_WITH {phase: 'wireless', note: 'protocol vuln + handshake attack'}]->(b);

// --- Cloud composition ---
MATCH (a:Skill {name: 'gcp-org-escalation'}), (b:Skill {name: 'm365-mailbox-compromise'})
MERGE (a)-[:COMPOSES_WITH {phase: 'cloud', note: 'cross-cloud token abuse'}]->(b);

// --- Supply-chain + recon ---
MATCH (a:Skill {name: 'supply-chain'}), (b:Skill {name: 'osint'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reconnaissance', note: 'OSINT identifies dependency targets'}]->(b);

// --- TI composition ---
MATCH (a:Skill {name: 'ti-ioc-extraction'}), (b:Skill {name: 'ti-anyrun-lookup'})
MERGE (a)-[:COMPOSES_WITH {phase: 'intelligence', note: 'extract IOCs then enrich via ANY.RUN'}]->(b);

MATCH (a:Skill {name: 'threat-profile'}), (b:Skill {name: 'adversary-emulation'})
MERGE (a)-[:COMPOSES_WITH {phase: 'intelligence', note: 'profile actor then emulate TTPs'}]->(b);


// ============================================================
// === SUBSTITUTES edges (Skill → Skill) ======================
// === Skill A can replace Skill B in the same capability     =
// === slot with stated tradeoffs.                            =
// ============================================================

// --- Recon substitutions ---
MATCH (a:Skill {name: 'osint'}), (b:Skill {name: 'passive-recon'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'osint broader but less infra-focused'}]->(b);

MATCH (a:Skill {name: 'open-web'}), (b:Skill {name: 'web-recon'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'open-web is lighter, fewer checks'}]->(b);

// --- Phishing substitutions ---
MATCH (a:Skill {name: 'html-smuggling-lure'}), (b:Skill {name: 'pdf-credential-harvest'})
MERGE (a)-[:SUBSTITUTES {direction: 'full', tradeoff: 'HTML avoids PDF AV detection but needs JS'}]->(b);

MATCH (a:Skill {name: 'quishing'}), (b:Skill {name: 'html-smuggling-lure'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'QR avoids email link scanning but needs camera'}]->(b);

MATCH (a:Skill {name: 'quishing'}), (b:Skill {name: 'pdf-credential-harvest'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'QR delivery vs PDF attachment'}]->(b);

// --- C2 substitutions ---
MATCH (a:Skill {name: 'c2-domain-fronting'}), (b:Skill {name: 'c2-cobalt-strike'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'domain-fronting is transport, CS is framework; overlap in evasion'}]->(b);

MATCH (a:Skill {name: 'c2-alternative-channels'}), (b:Skill {name: 'c2-domain-fronting'})
MERGE (a)-[:SUBSTITUTES {direction: 'full', tradeoff: 'DNS/ICMP tunnels vs CDN fronting; different detection surface'}]->(b);

// --- RE substitutions ---
MATCH (a:Skill {name: 'malware-triage'}), (b:Skill {name: 'triage'})
MERGE (a)-[:SUBSTITUTES {direction: 'full', tradeoff: 'malware-triage is specialised; triage is generic'}]->(b);

MATCH (a:Skill {name: 'deep-analysis'}), (b:Skill {name: 'ghidra'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'deep-analysis is methodology; ghidra is tool-specific'}]->(b);

// --- Wireless substitutions ---
MATCH (a:Skill {name: 'wpa3-sae'}), (b:Skill {name: 'wpa2-psk'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'WPA3 side-channel vs WPA2 brute-force; different target requirements'}]->(b);

MATCH (a:Skill {name: 'evil-twin-karma'}), (b:Skill {name: 'wpa2-psk'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'rogue AP captures creds without handshake cracking'}]->(b);

MATCH (a:Skill {name: 'wps-pixie-dust'}), (b:Skill {name: 'wpa2-psk'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'WPS PIN recovery avoids 4-way handshake but only works if WPS enabled'}]->(b);

// --- Cloud substitutions ---
MATCH (a:Skill {name: 'gcp-org-escalation'}), (b:Skill {name: 'm365-mailbox-compromise'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'different cloud platforms; token type differs'}]->(b);

// --- Credential substitutions ---
MATCH (a:Skill {name: 'evil-twin-karma'}), (b:Skill {name: 'credential-access'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'wireless cred capture vs host-based dumping'}]->(b);

// --- Exploitation substitutions ---
MATCH (a:Skill {name: 'rmm-tool-abuse'}), (b:Skill {name: 'edge-device-exploitation'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'RMM provides shell via legitimate tooling vs vuln exploitation'}]->(b);


// ============================================================
// === FORBIDDEN_BY edges (Skill → RoE constraint) ============
// === Operational guardrails — the planner MUST NOT suggest   =
// === a skill when the engagement RoE forbids it.            =
// ============================================================

MERGE (roe:RoEConstraint {name: 'no-social-engineering'})
SET roe.description = 'Social engineering / phishing is out of scope',
    roe.category    = 'scope-exclusion';

MERGE (roe:RoEConstraint {name: 'no-denial-of-service'})
SET roe.description = 'DoS / availability impact is prohibited',
    roe.category    = 'impact-limit';

MERGE (roe:RoEConstraint {name: 'no-wireless'})
SET roe.description = 'Wireless testing is out of scope',
    roe.category    = 'scope-exclusion';

MERGE (roe:RoEConstraint {name: 'no-physical'})
SET roe.description = 'Physical access / USB drop is prohibited',
    roe.category    = 'scope-exclusion';

MERGE (roe:RoEConstraint {name: 'no-exfiltration'})
SET roe.description = 'Real data exfiltration is prohibited; proof-of-concept only',
    roe.category    = 'impact-limit';

MERGE (roe:RoEConstraint {name: 'no-supply-chain'})
SET roe.description = 'Supply-chain attacks against production deps are out of scope',
    roe.category    = 'scope-exclusion';

MERGE (roe:RoEConstraint {name: 'no-destructive'})
SET roe.description = 'Destructive actions (wipe, encrypt, brick) are prohibited',
    roe.category    = 'impact-limit';

MERGE (roe:RoEConstraint {name: 'internal-only'})
SET roe.description = 'Only internal network testing; no external attack surface',
    roe.category    = 'network-scope';

MERGE (roe:RoEConstraint {name: 'no-cloud-prod'})
SET roe.description = 'Production cloud accounts are out of scope',
    roe.category    = 'scope-exclusion';

MERGE (roe:RoEConstraint {name: 'no-ai-attacks'})
SET roe.description = 'AI/ML model attacks are out of scope',
    roe.category    = 'scope-exclusion';

// --- Phishing skills forbidden by no-social-engineering ---
MATCH (s:Skill {name: 'html-smuggling-lure'}), (roe:RoEConstraint {name: 'no-social-engineering'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'pdf-credential-harvest'}), (roe:RoEConstraint {name: 'no-social-engineering'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'quishing'}), (roe:RoEConstraint {name: 'no-social-engineering'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'mfa-fatigue-social'}), (roe:RoEConstraint {name: 'no-social-engineering'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Wireless skills forbidden by no-wireless ---
MATCH (s:Skill {name: 'wpa2-psk'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'wpa3-sae'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'wpa-enterprise-eap'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'evil-twin-karma'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'deauth-pmf'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'krack-fragattacks'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'wps-pixie-dust'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'wireless-security'}), (roe:RoEConstraint {name: 'no-wireless'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Deauth / DoS ---
MATCH (s:Skill {name: 'deauth-pmf'}), (roe:RoEConstraint {name: 'no-denial-of-service'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Exfiltration ---
MATCH (s:Skill {name: 'exfiltration'}), (roe:RoEConstraint {name: 'no-exfiltration'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Supply-chain ---
MATCH (s:Skill {name: 'supply-chain'}), (roe:RoEConstraint {name: 'no-supply-chain'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Cloud prod ---
MATCH (s:Skill {name: 'gcp-org-escalation'}), (roe:RoEConstraint {name: 'no-cloud-prod'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (roe:RoEConstraint {name: 'no-cloud-prod'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Internal-only scope forbids external recon ---
MATCH (s:Skill {name: 'passive-recon'}), (roe:RoEConstraint {name: 'internal-only'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'osint'}), (roe:RoEConstraint {name: 'internal-only'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

MATCH (s:Skill {name: 'open-web'}), (roe:RoEConstraint {name: 'internal-only'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- AI attacks ---
MATCH (s:Skill {name: 'ai-red-team'}), (roe:RoEConstraint {name: 'no-ai-attacks'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- Destructive ---
MATCH (s:Skill {name: 'ransomware-analysis'}), (roe:RoEConstraint {name: 'no-destructive'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);


// ============================================================
// === Additional PRODUCES edges ==============================
// ============================================================

// --- Defense-evasion skills producing persistence ---
MATCH (s:Skill {name: 'defense-evasion'}), (c:Capability {name: 'persistence-implant'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Adversary-emulation produces threat intel ---
MATCH (s:Skill {name: 'adversary-emulation'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Wireless-security produces OSINT ---
MATCH (s:Skill {name: 'wireless-security'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:PRODUCES {confidence: 'low'}]->(c);

// --- Web-recon produces osint-dossier ---
MATCH (s:Skill {name: 'web-recon'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Edge device exploitation produces persistence ---
MATCH (s:Skill {name: 'edge-device-exploitation'}), (c:Capability {name: 'persistence-implant'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- RMM abuse produces persistence ---
MATCH (s:Skill {name: 'rmm-tool-abuse'}), (c:Capability {name: 'persistence-implant'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- RMM abuse produces C2 channel ---
MATCH (s:Skill {name: 'rmm-tool-abuse'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Lateral movement produces credential-set (pass-the-hash) ---
MATCH (s:Skill {name: 'lateral-movement'}), (c:Capability {name: 'credential-set'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Supply-chain produces reverse-shell ---
MATCH (s:Skill {name: 'supply-chain'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Credential-access produces cloud tokens ---
MATCH (s:Skill {name: 'credential-access'}), (c:Capability {name: 'cloud-identity-token'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);

// --- Fileless malware analysis ---
MATCH (s:Skill {name: 'fileless-malware'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Dotnet malware analysis ---
MATCH (s:Skill {name: 'dotnet-malware'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Rootkit analysis ---
MATCH (s:Skill {name: 'rootkit-analysis'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Ransomware analysis ---
MATCH (s:Skill {name: 'ransomware-analysis'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- Android malware analysis ---
MATCH (s:Skill {name: 'android-malware'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'high'}]->(c);

// --- CTF triage produces analysis ---
MATCH (s:Skill {name: 'ctf-triage'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:PRODUCES {confidence: 'medium'}]->(c);


// ============================================================
// === Additional CONSUMES edges ==============================
// ============================================================

// --- Defense-evasion consumes C2 channel ---
MATCH (s:Skill {name: 'defense-evasion'}), (c:Capability {name: 'c2-channel'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Adversary-emulation consumes osint-dossier ---
MATCH (s:Skill {name: 'adversary-emulation'}), (c:Capability {name: 'osint-dossier'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Adversary-emulation consumes threat-intel ---
MATCH (s:Skill {name: 'adversary-emulation'}), (c:Capability {name: 'threat-intel-report'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Edge device exploitation consumes web vuln report ---
MATCH (s:Skill {name: 'edge-device-exploitation'}), (c:Capability {name: 'web-vulnerability-report'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Fileless malware consumes prior analysis ---
MATCH (s:Skill {name: 'fileless-malware'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Rootkit analysis consumes firmware ---
MATCH (s:Skill {name: 'rootkit-analysis'}), (c:Capability {name: 'firmware-image'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Android malware consumes prior triage ---
MATCH (s:Skill {name: 'android-malware'}), (c:Capability {name: 'malware-sample-analysis'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- ROP chain consumes malware analysis ---
MATCH (s:Skill {name: 'rop-chain'}), (c:Capability {name: 'firmware-image'})
MERGE (s)-[:CONSUMES {required: false}]->(c);

// --- Credential-access consumes reverse-shell ---
MATCH (s:Skill {name: 'credential-access'}), (c:Capability {name: 'reverse-shell'})
MERGE (s)-[:CONSUMES {required: false}]->(c);


// ============================================================
// === Additional COMPOSES_WITH edges =========================
// ============================================================

// --- RE specialisation composition ---
MATCH (a:Skill {name: 'dotnet-malware'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: '.NET decompile then deep behavioural analysis'}]->(b);

MATCH (a:Skill {name: 'fileless-malware'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'in-memory triage then deep analysis'}]->(b);

MATCH (a:Skill {name: 'rootkit-analysis'}), (b:Skill {name: 'ghidra'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'rootkit identification then Ghidra disassembly'}]->(b);

MATCH (a:Skill {name: 'ransomware-analysis'}), (b:Skill {name: 'yara-hunting'})
MERGE (a)-[:COMPOSES_WITH {phase: 'detection', note: 'analyse ransomware then write hunting rules'}]->(b);

MATCH (a:Skill {name: 'android-malware'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reverse-engineering', note: 'APK triage then deep analysis'}]->(b);

// --- Reporting / OPPLAN composition ---
MATCH (a:Skill {name: 'reporting'}), (b:Skill {name: 'adversary-emulation'})
MERGE (a)-[:COMPOSES_WITH {phase: 'reporting', note: 'emulation findings feed report generation'}]->(b);

// --- Cloud + credential composition ---
MATCH (a:Skill {name: 'credential-access'}), (b:Skill {name: 'gcp-org-escalation'})
MERGE (a)-[:COMPOSES_WITH {phase: 'cloud', note: 'dumped creds used for cloud escalation'}]->(b);

MATCH (a:Skill {name: 'credential-access'}), (b:Skill {name: 'm365-mailbox-compromise'})
MERGE (a)-[:COMPOSES_WITH {phase: 'cloud', note: 'harvested creds pivot to M365'}]->(b);


// ============================================================
// === Additional SUBSTITUTES edges ===========================
// ============================================================

// --- RE tool substitutions ---
MATCH (a:Skill {name: 'dotnet-malware'}), (b:Skill {name: 'deep-analysis'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: '.NET-specific analysis replaces generic deep analysis for managed code'}]->(b);

MATCH (a:Skill {name: 'fileless-malware'}), (b:Skill {name: 'malware-triage'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'fileless-specific replaces generic triage for in-memory threats'}]->(b);

MATCH (a:Skill {name: 'ransomware-analysis'}), (b:Skill {name: 'malware-triage'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'ransomware-specific replaces generic triage for encryption-based threats'}]->(b);

// --- RMM substitutes C2 ---
MATCH (a:Skill {name: 'rmm-tool-abuse'}), (b:Skill {name: 'c2-cobalt-strike'})
MERGE (a)-[:SUBSTITUTES {direction: 'partial', tradeoff: 'legitimate RMM tool avoids CS detection signatures'}]->(b);


// ============================================================
// === Additional FORBIDDEN_BY edges ==========================
// ============================================================

// --- No-physical forbids wireless-adjacent skills ---
MATCH (s:Skill {name: 'evil-twin-karma'}), (roe:RoEConstraint {name: 'no-physical'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- No-destructive forbids edge-device exploitation (bricking risk) ---
MATCH (s:Skill {name: 'edge-device-exploitation'}), (roe:RoEConstraint {name: 'no-destructive'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- No-social-engineering also covers MFA fatigue callback ---
MATCH (s:Skill {name: 'evil-twin-karma'}), (roe:RoEConstraint {name: 'no-social-engineering'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);

// --- No-denial-of-service forbids deauth on enterprise ---
MATCH (s:Skill {name: 'krack-fragattacks'}), (roe:RoEConstraint {name: 'no-denial-of-service'})
MERGE (s)-[:FORBIDDEN_BY]->(roe);
