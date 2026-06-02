---
name: anti-debug-bypass
description: Detect and neutralize anti-debug / anti-VM checks — IsDebuggerPresent, ptrace, NtGlobalFlag, timing, hardware-breakpoint detection.
metadata:
  subdomain: reverse-engineering
  when_to_use: "anti debug bypass ptrace isdebuggerpresent debugger detection ntglobalflag timing hardware breakpoint"
  mitre_attack:
    - T1622
---

# Anti-Debug Bypass Playbook

Malware and protected commercial software check for debuggers and
sandboxes before running real logic. Bypassing these checks is required
to dynamically analyze them. Each check has a known counter.

## 1. Enumerate anti-debug techniques in the binary

### Static signature scan
```bash
# Windows API calls
strings /tmp/sample | grep -iE 'IsDebuggerPresent|NtQuery|CheckRemoteDebugger|OutputDebugString'

# Linux ptrace check
strings /tmp/sample | grep -iE 'ptrace|/proc/self/status|TracerPid'

# CPUID hypervisor check
strings /tmp/sample | grep -iE 'vmware|VirtualBox|qemu|xen'

# Detect via YARA rules
yara -r /opt/yara-rules/anti_debug.yar /tmp/sample
```

Decepticon helper:
```
bin_anti_debug_scan("/tmp/sample")
```

## 2. Common checks + bypasses

### Windows checks

| Check | What it does | Bypass |
|---|---|---|
| `IsDebuggerPresent()` | reads PEB.BeingDebugged byte | Set PEB.BeingDebugged = 0 in debugger; ScyllaHide handles |
| `CheckRemoteDebuggerPresent()` | calls NtQueryInformationProcess(ProcessDebugPort) | Patch return to FALSE; ScyllaHide hooks the syscall |
| `NtQueryInformationProcess(ProcessDebugPort)` | returns nonzero if debugger attached | Hook + return 0 |
| `NtQueryInformationProcess(ProcessDebugFlags)` | returns 0 if debugger, 1 if not | Force return 1 |
| `NtQueryInformationProcess(ProcessDebugObjectHandle)` | nonzero handle if attached | Force NULL |
| `PEB.NtGlobalFlag` | 0x70 if heap debugging | Set to 0 |
| `PEB.HeapFlags` & `PEB.ForceFlags` | non-default if debugger | Reset to defaults |
| `NtSetInformationThread(ThreadHideFromDebugger)` | unhook debugger from thread | Hook NtSetInformationThread |
| `INT 2D / INT 3` exception handling | normal flow if no debugger | Set exception handler in debugger |
| `Hardware breakpoint detection` (GetThreadContext check) | reads DR0-3, fails if BPs set | Use software BPs, or zero DRs before check |

ScyllaHide (x64dbg/x32dbg/IDA plugin) handles essentially all of these
automatically.

### Linux checks

| Check | What it does | Bypass |
|---|---|---|
| `ptrace(PTRACE_TRACEME)` | fails if already traced | Run w/o `ptrace`, or use `LD_PRELOAD` to hook |
| Read `/proc/self/status` `TracerPid:` | nonzero if debugger | LD_PRELOAD hook reading; or modify /proc on a fork |
| `prctl(PR_SET_DUMPABLE, 0)` | prevents `gdb attach` | Patch out the prctl |
| `getppid()` parent process name | if it's gdb/strace | rename gdb binary, or LD_PRELOAD getppid |
| Timing checks via `rdtsc` | measures execution time | Use gdb's `set $rax = ...` to fake; or patch rdtsc out |

### LD_PRELOAD bypass example
```c
// bypass.c
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <sys/ptrace.h>
#include <string.h>

long ptrace(int request, int pid, void *addr, void *data) {
    return 0;  // pretend it always succeeds
}

FILE *fopen(const char *path, const char *mode) {
    static FILE *(*orig)(const char *, const char *) = NULL;
    if (!orig) orig = dlsym(RTLD_NEXT, "fopen");
    if (strstr(path, "/proc/self/status") || strstr(path, "/proc/self/stat")) {
        // Return a doctored file
        FILE *tmp = tmpfile();
        fprintf(tmp, "TracerPid:\t0\n");
        rewind(tmp);
        return tmp;
    }
    return orig(path, mode);
}
```
```bash
gcc -shared -fPIC bypass.c -o bypass.so -ldl
LD_PRELOAD=./bypass.so gdb /tmp/sample
```

## 3. Anti-VM / sandbox detection

| Check | Bypass |
|---|---|
| CPUID leaf 0x40000000 (hypervisor bit) | Mask CPUID via KVM `-cpu host,-hypervisor` or VMM config |
| VMware backdoor `0x564D5868` magic via IN/OUT | Patch the magic number check |
| MAC address vendor (00:0C:29 = VMware) | Spoof MAC in VM config |
| Disk size < 50GB | Allocate larger disk for the analysis VM |
| RAM < 2GB | Provision more RAM |
| Username `sandbox`, `vagrant`, `virtual` | Change username in analysis env |
| Recent file count low | Pre-populate Documents folder before run |
| Mouse cursor never moves | Use `xdotool` to inject mouse jitter |
| Process count, uptime, kernel objects | Boot the VM a while before analysis |

## 4. Dynamic bypass via debugger

### x64dbg / x32dbg (Windows)
1. Install **ScyllaHide** plugin
2. In the plugin, enable all checks (PEB patches, NtSetInformation hooks, etc)
3. Open the binary, set BP at entry → continue
4. ScyllaHide neutralizes most checks transparently

### IDA Pro
- Built-in remote debugger + IDAStealth plugin
- For step-tracing through anti-debug: `Debugger options → Suspend on library load/unload = no`

### radare2 / r2dbg
```bash
r2 -d /tmp/sample
> e dbg.aslr = false
> dc                  # continue, see where it dies
> dbt                 # backtrace at SIGSEGV / exit
```

### gdb / pwndbg
For Linux:
```bash
gdb /tmp/sample
> set follow-fork-mode parent
> set detach-on-fork off
> catch syscall ptrace
> run
# When hit, override
> return 0
> continue
```

## 5. Patching for static-replay analysis

If you only need to analyze the unpacked / decrypted state, sometimes
easier to patch the anti-debug checks to no-ops:

```bash
# Find the check
r2 -A /tmp/sample
> afl ~ debug
> s sym.imp.IsDebuggerPresent
> /c call sym.imp.IsDebuggerPresent
> # for each hit, patch w/ "xor eax,eax; ret"
> wx 31c0c3 @ <addr>
```

Caution: patching may break self-checksums. Run static-validation YARA
post-patch to ensure binary still loads.

## 6. Promote
```
kg_add_node(kind="observation", label="anti-debug: <check-name>",
            props={"sample":"<sha256>","check":"<name>","bypassed":<bool>})
kg_add_edge(src=<sample>, dst=<observation>, kind="exhibits")
```

## OPSEC (for malware analysis)
- Run in isolated VM w/ NO connectivity to your network — many anti-VM
  checks involve DNS / HTTP probes
- Snapshot before run, revert after
- Don't analyze on host w/ persistent creds in browsers
- For commercial protected SW (legitimate analysis), document
  authorization to bypass DRM-adjacent protections

## Tool cheat sheet

| Tool | Use for |
|---|---|
| ScyllaHide | x64dbg/IDA plugin, neutralizes Windows checks |
| HideDebugger | Older but still useful x32dbg plugin |
| Phant0m | OllyDbg-era plugin |
| `gdb-peda` / `pwndbg` / `gef` | gdb plugins w/ anti-debug awareness |
| `ltrace` / `strace` | observe library / syscall use |
| `frida` | runtime hooking, can no-op checks dynamically |
| `MalwareAnalysisSandbox` / Cuckoo | full automated detonation w/ anti-anti-VM |
| `unpac.me` | community unpack service (engagement-permitting) |

## Known exemplars
- Stuxnet: multiple anti-VM checks (Siemens PLC env detection)
- Conti / Ryuk: PEB checks, sleep timer skipping, mouse-cursor check
- Most banking trojans (Trickbot, Emotet): full Anti-Debug + anti-sandbox + anti-emul
- Cobalt Strike beacons: lighter anti-debug, more anti-AV focus
- iOS / Android packers: ptrace + frida-detect (objection bypasses most)
