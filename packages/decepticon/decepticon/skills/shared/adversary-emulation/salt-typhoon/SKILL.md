---
name: salt-typhoon-earth-estries
description: "Adversary-emulation profile for Salt Typhoon (G1045 / Earth Estries / GhostEmperor / FamousSparrow / UNC2286 / RedMike / OPERATOR PANDA), a PRC state-sponsored cyber-espionage actor targeting telecommunications and critical infrastructure worldwide."
allowed-tools: Bash Read Write
metadata:
  subdomain: adversary-emulation
  when_to_use: "Salt Typhoon, Earth Estries, GhostEmperor, FamousSparrow, UNC2286, UNC5807, RedMike, OPERATOR PANDA, G1045, Chinese MSS espionage emulation, telecom compromise, Cisco IOS XE CVE-2023-20198, edge device exploitation, DEMODEX rootkit, GhostSpider backdoor, SnappyBee, Crowdoor, ZINGDOOR, JumbledPath, network device persistence, GRE tunneling, ISP targeting, critical infrastructure pre-positioning"
  tags: salt-typhoon, earth-estries, ghostemperor, famoussparrow, unc2286, redmike, china, mss, espionage, nation-state, g1045, adversary-emulation, mitre-attack, telecom, critical-infrastructure
  mitre_attack: T1595, T1590.004, T1583.003, T1584.008, T1587.001, T1588.002, T1588.005, T1190, T1199, T1078, T1569, T1609, T1059.001, T1059.005, T1059.006, T1059.008, T1047, T1136, T1136.001, T1098.004, T1543.005, T1505.003, T1053, T1574.002, T1068, T1110.002, T1027, T1027.010, T1036, T1070, T1070.009, T1562.004, T1610, T1599, T1112, T1564.001, T1685.006, T1040, T1556, T1003, T1003.001, T1555.003, T1082, T1016, T1083, T1057, T1518.001, T1021, T1021.004, T1021.002, T1560, T1560.001, T1602.001, T1602.002, T1005, T1074.001, T1090, T1090.003, T1071, T1071.001, T1571, T1572, T1095, T1104, T1105, T1573.001, T1048.003, T1041
---

# Salt Typhoon (Earth Estries, GhostEmperor, FamousSparrow) — Adversary Emulation Profile

Salt Typhoon (MITRE ATT&CK **G1045**) is a People's Republic of China (PRC) state-backed cyber-espionage group that has been active since at least 2019, with operations traced back to 2021 targeting network infrastructure worldwide. The group is best known for its sustained, large-scale compromises of major U.S. and global telecommunications providers and ISPs, exploiting edge network devices — particularly Cisco IOS XE routers — for long-term covert access. Salt Typhoon is characterized by its focus on network-layer operations (router compromise, GRE/IPsec tunneling, traffic interception via SPAN/ERSPAN), heavy use of living-off-the-land techniques on network devices, a broad custom malware arsenal (DEMODEX kernel rootkit, GhostSpider modular backdoor, SnappyBee/Deed RAT, Crowdoor, ZINGDOOR, HemiGate, MASOL RAT), and exploitation of N-day vulnerabilities in edge appliances from Cisco, Ivanti, Fortinet, Sophos, and Palo Alto Networks. The group's operations ultimately enable Chinese intelligence services to identify and track targets' communications and movements globally.

## Attribution & motivation

- **Sponsor / nation:** People's Republic of China — linked to the Ministry of State Security (MSS) and multiple China-based entities including Sichuan Juxinhe Network Technology Co. Ltd., Beijing Huanyu Tianqiong Information Technology Co. Ltd., and Sichuan Zhixin Ruijie Network Technology Co. Ltd. These companies provide cyber-related products and services to the PLA and MSS. The U.S. Treasury sanctioned Sichuan Juxinhe for Salt Typhoon activity in January 2025.
- **Motivation:** Primarily **strategic intelligence collection (espionage)** — interception of telecommunications metadata and content, tracking of intelligence targets' communications and movements. Secondary motivation includes **pre-positioning in critical infrastructure** for potential future disruptive operations, consistent with broader PRC cyber strategy.
- **Attribution confidence:** **High.** Backed by a joint 23-nation CISA/NSA/FBI advisory (AA25-239A, August 2025), U.S. Treasury OFAC sanctions, Cisco Talos technical analysis, and consistent named vendor reporting (Microsoft, Trend Micro, Kaspersky, ESET, Mandiant).

## Targeting

- **Sectors:** Telecommunications providers and ISPs (primary); government agencies; transportation; lodging/hospitality; military infrastructure; defense; technology and consulting firms; chemical industry; NGOs.
- **Regions:** Global — heavy focus on the **United States**, Southeast Asia (Philippines, Thailand, Malaysia, Indonesia, Vietnam, India, Taiwan), Africa (South Africa, Eswatini), Middle East (Afghanistan), South America (Brazil), and allied Five Eyes nations (Australia, Canada, New Zealand, United Kingdom). Operations confirmed across 13+ countries.
- **Victim profile:** Large backbone routers at major telecom providers, provider edge (PE) and customer edge (CE) routers, ISP infrastructure, Exchange servers, VPN appliances, and firewalls. The group targets both high-value strategic organizations and opportunistic edge devices that serve as pivot points into target networks. Over 20 organizations compromised across multiple sectors according to Trend Micro.

## Notable campaigns

- **2019-present — Long-term telecom provider compromises.** Sustained, multi-year intrusions into major U.S. and global telecommunications providers, leveraging Cisco router exploitation for persistent access to backbone infrastructure. Discovered in late 2024 and publicly attributed. (CISA AA25-239A / U.S. Treasury)
- **2023-10 — Cisco IOS XE mass exploitation (CVE-2023-20198 / CVE-2023-20273).** Widespread exploitation of Cisco IOS XE web UI authentication bypass and privilege escalation vulnerabilities, creating unauthorized admin accounts on internet-exposed routers globally. Chained for root-level code execution. (Cisco Talos / CISA)
- **2023-2024 — Earth Estries Southeast Asia telecom campaign.** Trend Micro documented Earth Estries targeting telecom companies in Southeast Asia with the previously undisclosed GhostSpider backdoor, DEMODEX rootkit, and SnappyBee. Over 20 organizations compromised using two distinct attack chains. (Trend Micro, November 2024)
- **2023-2024 — Ivanti Connect Secure exploitation (CVE-2023-46805 / CVE-2024-21887).** Exploitation of Ivanti VPN authentication bypass chained with command injection for initial access into government and enterprise networks. (CISA / multiple vendors)
- **2024 — Cisco NX-OS exploitation (CVE-2024-20399).** Exploitation of Cisco NX-OS CLI command injection vulnerability to execute commands on underlying Linux OS from authenticated admin sessions. (Cisco / Sygnia)
- **2023-2024 — Exchange server and web management tool exploitation.** Earth Estries campaigns exploiting ProxyLogon (CVE-2021-26855), Sophos Firewall (CVE-2022-3236), and Fortinet FortiClient EMS (CVE-2023-48788) for initial access, deploying ChinaChopper web shells, Cobalt Strike, and custom backdoors. (Trend Micro)
- **2025-06 — Canadian telecom targeting via CVE-2023-20198.** Salt Typhoon operators exploited Cisco Smart Install (CVE-2018-0171) and IOS XE web UI vulnerabilities to compromise Canadian ISP infrastructure. (Eclypsium)
- **2025-08 — Joint 23-nation advisory (CISA AA25-239A).** NSA, CISA, FBI, and 20 international partner agencies released comprehensive advisory detailing Salt Typhoon TTPs, IOCs, and mitigations for global network infrastructure targeting. (CISA)

## TTPs by ATT&CK tactic

### Reconnaissance
- **T1595** — Active scanning: scanning for open ports, services, and SPAN/RSPAN mirroring capabilities on target network infrastructure.
- **T1590.004** — Gather victim network information (network topology): leveraging configuration files from exploited network devices to discover upstream and downstream network segments, MPLS configurations, and BGP routing tables.

### Resource Development
- **T1583.003** — Acquire infrastructure (VPS): leveraging virtual private servers as operational infrastructure for C2 and pivoting, not attributable to a publicly known botnet.
- **T1584.008** — Compromise infrastructure (network devices): compromising intermediate routers as relay infrastructure for targeting downstream telecom and ISP networks.
- **T1587.001** — Develop capabilities (malware): custom tooling including JumbledPath (S1206), GhostSpider, DEMODEX, ZINGDOOR, HemiGate, Crowdoor, and custom SFTP exfiltration clients (cmd1, cmd3, new2, sft — Golang-based).
- **T1588.002** — Obtain capabilities (tool): using publicly available tooling such as Cobalt Strike, Mimikatz, PlugX, PsExec, STOWAWAY (multi-hop proxy), siet.py (Cisco Smart Install exploit), TCLproxy.tcl, and map.tcl.
- **T1588.005** — Obtain capabilities (exploits): utilizing publicly available exploit code from GitHub repositories to exploit edge device vulnerabilities.

### Initial Access
- **T1190** — Exploit public-facing application: primary initial access vector. Exploited CVEs include: **CVE-2023-20198** (Cisco IOS XE web UI auth bypass), **CVE-2023-20273** (Cisco IOS XE command injection, chained with 20198), **CVE-2018-0171** (Cisco Smart Install RCE), **CVE-2023-46805** (Ivanti Connect Secure auth bypass), **CVE-2024-21887** (Ivanti command injection), **CVE-2023-48788** (Fortinet FortiClient EMS SQLi), **CVE-2022-3236** (Sophos Firewall RCE), **CVE-2024-20399** (Cisco NX-OS CLI injection), **CVE-2024-3400** (PAN-OS GlobalProtect RCE), and **CVE-2021-26855** (Exchange ProxyLogon). Zero-day exploitation has not been observed — all are N-day vulnerabilities.
- **T1199** — Trusted relationship: leveraging compromised devices and trusted private interconnections (provider-to-provider, provider-to-customer links) to pivot into downstream target networks.
- **T1078** — Valid accounts: reusing credentials obtained from configuration file dumps and TACACS+/RADIUS capture, including weak default credentials (e.g., "cisco/cisco").

### Execution
- **T1059.008** — Network device CLI: primary execution method — using built-in CLI commands on Cisco IOS/IOS XE/NX-OS/IOS XR devices to execute native commands, configure PCAP, modify routing, and manage Guest Shell.
- **T1059.006** — Python: running Python scripts (e.g., siet.py for Smart Install exploitation) within Guest Shell containers on Cisco devices.
- **T1059.001** — PowerShell: encoded PowerShell scripts for deploying backdoors (DEMODEX rootkit installation chain), lateral movement, and reconnaissance on Windows enterprise targets.
- **T1059.005** — Visual Basic: VBScript execution via cscript.exe in enterprise environment operations.
- **T1047** — Windows Management Instrumentation (WMI): WMIC.exe for lateral movement and remote execution in enterprise environments (Earth Estries attack chain 1).
- **T1569** — System services: executing commands via SNMP on network devices.
- **T1609** — Container administration command: using Cisco Guest Shell (Linux LXC container) to load open-source tools, parse collected artifacts, and as a jump point for reconnaissance and lateral movement. On IOS XE via `guestshell run bash`; on NX-OS via `run guestshell` and `dohost` for host CLI actions.

### Persistence
- **T1098.004** — Account manipulation (SSH authorized keys): adding SSH authorized_keys under root or other users at the Linux level on compromised network devices for persistent re-entry.
- **T1136 / T1136.001** — Create account (local account): creating local users on network devices via router configuration modification and on IOS XR via `/etc/shadow` and `/etc/passwd` modification, with sudo privileges granted via `/etc/sudoers`.
- **T1543.005** — Container service: leveraging Linux-based Guest Shell containers natively supported on Cisco IOS XE and NX-OS for persistent, concealed access. Systemd-managed services enable long-running components inside Guest Shell.
- **T1505.003** — Web shell: deploying ChinaChopper and other web shells on compromised Exchange/IIS servers for persistent access in enterprise environment operations.
- **T1574.002** — DLL side-loading: heavily used by Earth Estries to load encrypted backdoor payloads via legitimate AV software (Norton, Bkav, IObit) — custom loader DLLs decrypt and execute DEMODEX, GhostSpider, SnappyBee, Crowdoor, and Cobalt Strike.
- **T1053** — Scheduled task/job: scheduled tasks for persistence of backdoor payloads in enterprise environment operations.

### Privilege Escalation
- **T1068** — Exploitation for privilege escalation: exploiting CVE-2023-20273 (Cisco IOS XE post-auth command injection) chained with CVE-2023-20198 to achieve root-level execution; CVE-2024-20399 (NX-OS CLI injection to underlying Linux OS). On IOS XR, granting sudo privileges to created local accounts.
- **T1110.002** — Brute force (password cracking): cracking passwords with weak encryption (Cisco Type 5 MD5, Type 7 reversible encoding) obtained from dumped network device configuration files.

### Defense Evasion
- **T1027** — Obfuscated files or information: obfuscating source IP addresses in system logs by tunneling through local interfaces; using encrypted payloads for all custom backdoors loaded via DLL side-loading.
- **T1027.010** — Command obfuscation: double-encoding URL paths (e.g., `/%2577eb%2575i_%2577sma_Http`) when exploiting CVE-2023-20198 WSMA endpoints to evade detection.
- **T1036** — Masquerading: naming ACLs with common numbering schemes ("access-list 20/50/10") to blend with normal configurations; using legitimate AV software binaries for DLL side-loading.
- **T1562.004** — Impair defenses (disable or modify system firewall): modifying ACLs to add actor-controlled IP addresses, bypassing security policies and permitting unauthorized traffic.
- **T1610** — Deploy container: deploying Guest Shell virtual containers on network infrastructure to persist and evade monitoring, as activities within containers are not closely monitored by standard network security tools.
- **T1070** — Indicator removal: deleting and clearing logs, disabling log forwarding to central servers, stopping/starting event logging on network devices; clearing `.bash_history`, `auth.log`, `lastlog`, `wtmp`, and `btmp`.
- **T1070.009** — Clear persistence: using `guestshell disable` and `guestshell destroy` to deactivate and remove Guest Shell containers, returning resources to the system and removing forensic artifacts.
- **T1599** — Network boundary bridging: abusing peering connections (direct interconnections between ISP networks) to facilitate exfiltration across network boundaries that lack policy restraints.
- **T1112** — Modify registry: registry manipulation for persistence and defense evasion in enterprise environment operations.
- **T1564.001** — Hidden files and directories: hiding tool files and artifacts on device storage.
- **T1685.006** — Disable or modify tools (clear Linux/Mac system logs): clearing system logs on compromised Linux-based network devices.

### Credential Access
- **T1040** — Network sniffing: primary credential access technique — using native PCAP capabilities (Cisco Embedded Packet Capture, SPAN/RSPAN/ERSPAN) on compromised routers to capture TACACS+ (TCP/49) and RADIUS authentication traffic containing cleartext or weakly protected credentials. JumbledPath tool also used for packet capture.
- **T1556** — Modify authentication process: modifying router TACACS+ server configuration to point to actor-controlled IP addresses, capturing authentication attempts; adjusting AAA configurations to force less secure authentication methods.
- **T1003** — OS credential dumping: collecting router configurations containing weak Cisco Type 5/7 hashed passwords; in enterprise environments, LSASS memory dumping via Mimikatz.
- **T1003.001** — LSASS memory: Mimikatz for credential extraction from Windows enterprise targets.
- **T1555.003** — Credentials from web browsers: Trillclient tool for harvesting credentials stored in browser caches (Earth Estries enterprise operations).

### Discovery
- **T1082** — System information discovery: running CLI commands on network devices via SNMP, SSH, and HTTP GET/POST requests targeting privileged execution paths (e.g., `/level/15/exec/-/*`) to display configurations, BGP routes, VRF instances, and system information.
- **T1016** — System network configuration discovery: SNMP enumeration (SNMPwalk GET/WALK) to discover device interfaces, VRFs, routing tables, ACLs, and SNMP community group memberships; enumerating MPLS configuration information.
- **T1083** — File and directory discovery: scanning device storage (flash, NVRAM) for configuration files and artifacts.
- **T1057** — Process discovery: discovering running processes and services on compromised hosts.
- **T1518.001** — Security software discovery: identifying installed security monitoring tools to adapt evasion techniques.

### Lateral Movement
- **T1021** — Remote services: enumerating and altering SNMP configurations for other devices in the same community group; using service/automation credentials (e.g., RANCID configuration-archival credentials) to access additional network devices.
- **T1021.004** — SSH: enabling SSH servers on non-default high ports (port numbering scheme `22x22` or `xxx22`) on network devices; modifying loopback addresses on compromised switches to use them as SSH sources, bypassing ACLs. On IOS XR, enabling `sshd_operns` on TCP/57722 for direct Linux shell access.
- **T1021.002** — SMB/Windows admin shares: PsExec for lateral movement in enterprise environments (Earth Estries attack chain 1).

### Collection
- **T1005** — Data from local system: passively collecting PCAP from specific ISP customer networks; capturing subscriber information, user content, customer records, network diagrams, device configurations, and vendor lists from provider-held data stores.
- **T1560 / T1560.001** — Archive collected data: compiling configurations and packet captures; archiving collected data into password-protected RAR archives before exfiltration. Using tar/openssl on Linux devices for encrypted archival.
- **T1602.001** — Data from configuration repository (SNMP/MIB dump): targeting MIBs to collect network information via SNMP.
- **T1602.002** — Data from configuration repository (network device configuration dump): dumping network device configurations to acquire credentials and map network topology; exfiltrating configs via TFTP and FTP.
- **T1074.001** — Data staged (local data staging): staging PCAP files and configuration dumps on device storage (bootflash:) prior to exfiltration.

### Command & Control
- **T1572** — Protocol tunneling: creating GRE, multipoint GRE (mGRE), and IPsec tunnels on network devices for covert, persistent C2 channels that blend with normal network traffic. Some tunnels used to move data back to China via MPLS tunnels.
- **T1090** — Proxy: using VPS infrastructure for C2; configuring compromised routers as proxy/relay points.
- **T1090.003** — Multi-hop proxy: leveraging STOWAWAY open-source multi-hop pivoting tool to build chained relays for C2 and operator access, including interactive shells, file transfer, SOCKS5/HTTP proxying, and local/remote port mapping with encrypted node-to-node links.
- **T1071 / T1071.001** — Application layer protocol (web protocols): HTTP/HTTPS for C2; enabling/abusing built-in HTTP/HTTPS management servers on network devices, sometimes reconfigured to non-default high ports (18xxx pattern). GhostSpider uses custom protocol over TLS.
- **T1571** — Non-standard port: utilizing non-standard ports for SSH (22x22, xxx22 patterns), HTTPS (18xxx pattern), and other management services to evade monitoring focused on standard ports.
- **T1095** — Non-application layer protocol: using GRE/IPsec for C2 transport over non-application layer protocols.
- **T1104** — Multi-stage channels: JumbledPath (S1206) uses multi-stage channels for PCAP collection and exfiltration.
- **T1105** — Ingress tool transfer: downloading additional tools and payloads via cURL, custom SFTP clients, and C2 channels.
- **T1573.001** — Encrypted channel (symmetric cryptography): AES encryption used in custom SFTP exfiltration clients; encrypted node-to-node links in STOWAWAY relay chains.

### Exfiltration
- **T1048.003** — Exfiltration over alternative protocol (unencrypted non-C2 protocol): exfiltrating configuration files over FTP and TFTP from compromised network devices; using GRE/IPsec tunnels for data exfiltration.
- **T1041** — Exfiltration over C2 channel: exfiltrating stolen archives via C2 channels; using cURL to upload files to anonymized file-sharing services.

## Signature tooling & malware

| Name | ATT&CK ID | Type | Public/Custom |
|---|---|---|---|
| JumbledPath | S1206 | ELF utility for PCAP capture, multi-hop relay, and log clearing on network devices | Custom |
| GhostSpider | (no ATT&CK software ID) | Modular multi-layer backdoor with TLS-encrypted custom protocol C2; targets telecom networks | Custom |
| DEMODEX | (no ATT&CK software ID) | Windows kernel rootkit for long-term stealth persistence; newer variant uses CAB-bundled registry payloads | Custom |
| SnappyBee / Deed RAT | (no ATT&CK software ID) | Shared modular backdoor (likely MaaS-sourced); encrypted payloads loaded via DLL side-loading | Shared/Custom |
| Crowdoor | (no ATT&CK software ID) | Custom backdoor deployed after exploiting web management tool vulnerabilities (ShadowPad variant) | Custom |
| ZINGDOOR | (no ATT&CK software ID) | HTTP-tunneling backdoor deployed in Exchange server attack chains | Custom |
| HemiGate | (no ATT&CK software ID) | Multi-instance backdoor supporting file management, keylogging, screen capture, and process control | Custom |
| MASOL RAT | (no ATT&CK software ID) | Cross-platform (Linux) backdoor targeting Southeast Asian government Linux servers | Custom |
| Trillclient | (no ATT&CK software ID) | Browser credential harvester targeting cached credentials | Custom |
| cmd1 / cmd3 / new2 / sft | (no ATT&CK software ID) | Custom Golang SFTP exfiltration clients with AES-encrypted config; cmd1 includes PCAP collection capability | Custom |
| Cobalt Strike | S0154 | Post-exploitation framework; encrypted payloads loaded via DLL side-loading | Public |
| PlugX | S0013 | RAT; encrypted payloads via custom loaders | Public (shared among Chinese APTs) |
| Mimikatz | S0002 | Credential dumping | Public |
| ChinaChopper | S0020 | Web shell for Exchange/IIS persistence | Public |
| PsExec | S0029 | Remote execution for lateral movement | Public |
| STOWAWAY | (no ATT&CK software ID) | Open-source multi-hop proxy/relay framework | Public |
| siet.py | (no ATT&CK software ID) | Cisco Smart Install exploitation tool (CVE-2018-0171) | Public |
| cURL / WMIC / netsh / reg | Built-in | LOLBins for download, lateral movement, ACL modification, and registry operations | Built-in |

> Note: Trend Micro states they do not have sufficient evidence to attribute DEMODEX and GhostSpider as proprietary to Earth Estries — these tools may be shared across multiple Chinese APT groups or sourced from third-party malware developers.

## Emulation guidance (Decepticon)

> **Authorized-use caveat:** Execute the following ONLY within the documented rules of engagement, target scope, and time window of an authorized engagement. Salt Typhoon's operations involve network infrastructure (routers, switches, firewalls) — emulation on production network devices requires explicit written authorization and coordination with network operations teams. Never modify production routing tables or SPAN configurations outside an explicitly sanctioned, isolated lab.

Map Salt Typhoon's signature plays to Decepticon's own capabilities:

- **Initial access — edge device exploitation (T1190, CVE-2023-20198/20273/2018-0171).** Where Cisco IOS XE devices are in scope, emulate the CVE-2023-20198 web UI auth bypass chain: craft WSMA endpoint requests to `/webui_wsma_Http` with double-encoded paths (`/%2577eb%2575i_%2577sma_Http`) to create unauthorized admin accounts, then chain CVE-2023-20273 for root privilege escalation. For older devices, emulate CVE-2018-0171 Smart Install exploitation using siet.py from within the sandbox. Use the payload-builder to stage Ivanti Connect Secure (CVE-2023-46805 + CVE-2024-21887) and Fortinet (CVE-2023-48788) exploit chains for broader edge device coverage.
- **Network device persistence & C2 (T1098.004, T1136.001, T1572, T1543.005).** After gaining access to network devices, emulate Salt Typhoon's persistence pattern: create local accounts with `privilege 15`, add SSH authorized_keys for persistent re-entry on non-default high ports (22x22 pattern), and configure GRE/IPsec tunnels for covert C2 channels. If Guest Shell (IOS XE/NX-OS) is available in the lab, enable it (`guestshell enable`) and demonstrate tool staging, Python script execution, and lateral movement from within the container — this is Salt Typhoon's defining evasion technique.
- **Traffic interception & credential capture (T1040, T1556, T1602).** On compromised lab routers, configure native PCAP (`monitor capture mycap interface ... match ipv4 protocol tcp any any eq 49`) to capture TACACS+ authentication traffic. Demonstrate TACACS+ server redirection by modifying the router's AAA configuration to point at an attacker-controlled server. Dump device configurations via SNMP and crack Type 5/7 passwords offline — this mirrors the group's primary lateral movement enabler.
- **Enterprise operations — DLL side-loading (T1574.002).** Use the payload-builder to create DLL side-loading packages mimicking Earth Estries' technique: bundle a legitimate signed AV binary (Norton, IObit) with a malicious loader DLL that decrypts and executes an encrypted Cobalt Strike / **Sliver** beacon payload. Deploy via cURL download or CAB file extraction to emulate both Earth Estries attack chains.
- **Lateral movement (T1021.004, T1021.002, T1047).** Use **Sliver** (c2 skill) pivots to emulate SSH-based lateral movement from compromised network devices using modified loopback addresses to bypass ACLs. In enterprise environments, use PsExec/WMIC for lateral movement matching Earth Estries attack chain 1. Deploy Mimikatz for credential harvesting to fuel additional pivots.
- **C2 (T1572, T1090.003, T1071.001, T1571).** Use **Sliver** over HTTPS as the primary C2 channel, configured on non-standard high ports (matching the 18xxx HTTP pattern or 22x22 SSH pattern) to emulate Salt Typhoon's port-selection tradecraft. Layer multi-hop relaying with STOWAWAY or Sliver's built-in pivoting to emulate the chained-relay architecture. For network device operations, configure GRE tunnels as C2 transport to replicate the group's infrastructure-level C2.
- **Collection & exfiltration (T1560.001, T1048.003, T1602.002).** Stage collected data (PCAP files, device configs, credential dumps) on device storage (`bootflash:`), archive into password-protected compressed files, and exfiltrate via FTP/TFTP to a staging server, then via encrypted SFTP to a final collection point — replicating the group's multi-stage exfiltration pattern. Use `copy bootflash:tac.pcap ftp://...` syntax to match observed commands.
- **Web shell & Exchange operations (T1505.003, T1190).** Where Exchange or web servers are in scope, deploy ChinaChopper-style web shells to emulate Earth Estries' secondary access vector. Use the web-shell as a pivot point for deploying additional backdoors via cURL download.

## Detection & defense

- **Edge device patching (T1190):** Prioritize patching CVE-2023-20198/20273 on Cisco IOS XE; CVE-2018-0171 (disable Smart Install with `no vstack`); CVE-2023-46805/CVE-2024-21887 on Ivanti; CVE-2023-48788 on Fortinet; CVE-2022-3236 on Sophos; CVE-2024-3400 on PAN-OS. Disable web UI on Cisco devices when not required (`no ip http server`, `no ip http secure-server`).
- **Network device integrity (T1136.001, T1098.004):** Implement out-of-band management networks isolated from data-plane traffic. Regularly diff running configurations against approved baselines; alert on new local accounts, SSH authorized_keys additions, ACL modifications (watch "access-list 20/50/10"), TACACS+ server changes, and SPAN/ERSPAN session creation. Audit for `sshd_operns` (TCP/57722) on IOS XR.
- **Guest Shell / container abuse (T1610, T1543.005):** Disable Guest Shell where not operationally required (`guestshell disable`; `no iox` on IOS XE). Where used, forward container logs (journald/systemd) to SIEM; restrict Guest Shell VRF egress to only required destinations; alert on `guestshell enable`, `guestshell run bash`, `guestshell destroy`, `chvrf`, and `dohost` commands. Periodically inventory `bootflash:` for unexpected files.
- **Traffic interception detection (T1040, T1556):** Alert on creation of on-box packet captures (`monitor capture ... start`), SPAN/RSPAN/ERSPAN session definitions, and TACACS+ traffic (TCP/49) to non-approved destinations. Watch for PCAP naming patterns: `mycap`, `tac.pcap`, `1.pcap`. Monitor for unauthorized FTP/TFTP transfers from network devices.
- **Tunneling & non-standard ports (T1572, T1571):** Hunt for unexpected GRE/IPsec tunnels, especially with foreign infrastructure or across ASN boundaries. Alert on SSH services on non-default ports matching `22x22`/`xxx22` patterns; HTTPS on `18xxx` ports. Monitor for STOWAWAY relay traffic patterns.
- **SNMP hardening (T1021, T1602):** Enforce SNMPv3 with authPriv; replace all default/weak community strings ("public", "private"); restrict SNMP access to management VLANs; monitor SNMP SET operations that modify AAA, HTTP/HTTPS, tunnel, SPAN/ERSPAN, routing, or ACL configurations.
- **Credential protection (T1003, T1110.002):** Store Cisco credentials using Type 8 (PBKDF2-SHA-256) — eliminate Type 7 and transition from Type 5 (MD5). Implement TACACS+ with strong shared secrets stored using Type 6 (AES) encryption. Enforce key-based authentication for administrative access.
- **DLL side-loading detection (T1574.002):** Monitor for execution of legitimate AV binaries (Norton, Bkav, IObit) from unexpected paths loading unsigned/mismatched DLLs. Alert on CAB file extraction followed by process execution from temporary directories. Hunt for abnormal PowerShell base64-encoded commands, suspicious cURL downloads, and WMIC remote execution.
- **Log integrity (T1070, T1685.006):** Forward all device logs to a centralized, immutable logging server via encrypted channels. Set trap/buffer logging to at least informational level (6). Alert on log clearing events, disabled log forwarding, `.bash_history` truncation, and `auth.log`/`wtmp`/`btmp` deletion on Linux-based network OS.

## Sources

- https://attack.mitre.org/groups/G1045/
- https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
- https://blog.talosintelligence.com/salt-typhoon-analysis/
- https://home.treasury.gov/news/press-releases/jy2792
- https://www.trendmicro.com/en_us/research/24/k/earth-estries.html
- https://www.trendmicro.com/en_us/research/24/k/breaking-down-earth-estries-persistent-ttps-in-prolonged-cyber-o.html
- https://www.welivesecurity.com/en/eset-research/you-will-always-remember-this-as-the-day-you-finally-caught-famoussparrow/
- https://www.picussecurity.com/resource/blog/salt-typhoon-telecommunications-threat
- https://www.attackiq.com/2025/03/19/emulating-salt-typhoon/
- https://attack.mitre.org/software/S1206/
