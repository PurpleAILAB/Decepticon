---
name: reverser-rootkit-analysis
description: "Rootkit detection and analysis — UEFI rootkits, kernel-level rootkits, bootkits, DKOM techniques, SSDT/IDT/IRP hooking, hypervisor rootkits, and firmware implant detection using GMER, Volatility, chipsec, and UEFITool."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "rootkit bootkit uefi firmware kernel driver ssdt hook dkom hidden process hypervisor mbr vbr implant bios spi flash ring0 ring-1"
  subdomain: reverser
  tags: "rootkit, UEFI, bootkit, kernel, firmware, Volatility, chipsec"
  mitre_attack: "T1542.001, T1542.003, T1014"
---

# Rootkit Analysis

Detect and analyze rootkits operating at kernel, boot, and firmware levels — from user-mode hiding techniques through UEFI implants and hypervisor-based rootkits.

## Quick Reference

```bash
# Quick kernel rootkit scan (Windows, run as admin)
gmer.exe /scan

# System-wide hidden process / driver detection
volatility3 -f memory.raw windows.pslist vs windows.psscan
# Processes in psscan but NOT in pslist → hidden by DKOM

# UEFI firmware extraction and analysis
chipsec_util.py spi dump firmware.bin
UEFIExtract firmware.bin

# Check for unsigned kernel drivers
sigcheck -u -e C:\Windows\System32\drivers\*.sys

# Scan for SSDT hooks
volatility3 -f memory.raw windows.ssdt
```

## MITRE ATT&CK Mapping

| Technique | ID | How It Appears |
|---|---|---|
| System Firmware | T1542.001 | UEFI rootkit implanted in SPI flash (LoJax, MosaicRegressor, CosmicStrand) |
| Bootkit | T1542.003 | MBR/VBR modification to load malicious code before OS (TDL4, Rovnix, ESPecter) |
| Rootkit | T1014 | Kernel object manipulation to hide processes, files, registry keys |
| Boot or Logon Autostart: Kernel Modules | T1547.006 | Malicious kernel driver loaded at boot via service registry key |
| Exploitation for Defense Evasion | T1211 | Vulnerable driver exploit (BYOVD) to load unsigned kernel code |
| Virtualization/Sandbox Evasion | T1497 | Hypervisor rootkit detecting/evading analysis environment |

## 1. User-Mode Rootkit Detection

Detect rootkits that hook user-mode APIs to hide artifacts.

```bash
# Compare API hook status — IAT/EAT/inline hooks
# Use API Monitor or manually check ntdll.dll integrity

# Volatility: detect IAT hooks in processes
vol3 -f memory.raw windows.iat --pid <PID>

# Check for LD_PRELOAD / dylib injection (Linux/macOS)
# Linux:
cat /proc/<PID>/maps | grep -v "$(ls /lib/ /usr/lib/ 2>/dev/null | tr '\n' '|')"
echo $LD_PRELOAD
cat /etc/ld.so.preload

# Windows: compare loaded DLLs against known-good baseline
vol3 -f memory.raw windows.dlllist --pid <PID>
# Look for: DLLs loaded from temp dirs, DLLs not on disk, unknown publishers

# Cross-view detection: compare user-mode API results vs kernel data
# If FindFirstFile misses files that raw NTFS parsing finds → user-mode hook
python3 << 'EOF'
import os, subprocess
# User-mode listing
user_files = set(os.listdir("C:\\Windows\\System32\\drivers"))
# Raw NTFS listing (bypasses API hooks)
raw = subprocess.check_output(["rawcopy", "/listdir", "C:\\Windows\\System32\\drivers"])
raw_files = set(raw.decode().strip().split('\n'))
hidden = raw_files - user_files
if hidden:
    print(f"[!] Hidden files detected: {hidden}")
EOF
```

## 2. Kernel Rootkit Detection

Detect DKOM, SSDT hooks, and malicious drivers.

```bash
# GMER scan (Windows — gold standard for kernel rootkit detection)
# Run gmer.exe as Administrator
# Checks: SSDT hooks, IDT hooks, IRP hooks, inline hooks,
#          hidden processes, hidden drivers, hidden files, hidden registry

# Volatility cross-view process detection
vol3 -f memory.raw windows.pslist > pslist.txt
vol3 -f memory.raw windows.psscan > psscan.txt
# Diff: processes in psscan but not pslist are DKOM-hidden
comm -23 <(sort psscan.txt) <(sort pslist.txt)

# SSDT hook detection
vol3 -f memory.raw windows.ssdt
# All entries should point to ntoskrnl.exe or win32k.sys
# Entries pointing elsewhere → hooked

# Driver analysis
vol3 -f memory.raw windows.drvscan
vol3 -f memory.raw windows.modules
# Look for:
# - Drivers not on disk (loaded from memory only)
# - Drivers loaded from unusual paths (temp, appdata)
# - Drivers with no digital signature

# IRP hook detection — malicious drivers hooking filesystem IRPs
vol3 -f memory.raw windows.driverirp
# NTFS driver IRP_MJ_DIRECTORY_CONTROL hooked → file hiding
# NTFS driver IRP_MJ_CREATE hooked → file access interception

# Linux kernel rootkit detection
# Check loaded kernel modules
lsmod
cat /proc/modules
# Verify module signature
modinfo <MODULE_NAME> | grep sig

# Check syscall table integrity (requires kernel symbol access)
cat /proc/kallsyms | grep sys_call_table
# Compare function addresses against known-good System.map

# chkrootkit / rkhunter (automated Linux rootkit scanners)
chkrootkit
rkhunter --check --skip-keypress
```

## 3. BYOVD (Bring Your Own Vulnerable Driver) Analysis

```bash
# Attackers load a signed-but-vulnerable driver to gain kernel access
# Then use the driver's read/write primitives to disable security

# Known vulnerable drivers database: loldrivers.io
# Common BYOVD targets:
# - RTCore64.sys (MSI Afterburner) — arbitrary physical memory R/W
# - dbutil_2_3.sys (Dell) — arbitrary memory R/W
# - gdrv.sys (GIGABYTE) — physical memory R/W
# - capcom.sys — disables SMEP, executes user-mode code in ring 0

# Detect BYOVD: check for known vulnerable driver hashes
python3 << 'EOF'
import hashlib, os, json

# LOLDrivers hash list (download from loldrivers.io)
vuln_hashes = set()  # Populate from loldrivers.io API or CSV

drivers_dir = r"C:\Windows\System32\drivers"
for f in os.listdir(drivers_dir):
    path = os.path.join(drivers_dir, f)
    if os.path.isfile(path) and f.endswith('.sys'):
        h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if h in vuln_hashes:
            print(f"[!] VULNERABLE DRIVER: {f} — {h}")
EOF

# Check driver signature status
sigcheck.exe -u -e C:\Windows\System32\drivers\*.sys
# -u shows unsigned drivers; -e scans executables only

# Volatility: find recently loaded drivers
vol3 -f memory.raw windows.drvscan | sort -k3 -t'|'
```

## 4. Bootkit Analysis

Detect and analyze MBR/VBR/ESP modifications.

```bash
# Dump MBR (first 512 bytes of disk)
dd if=/dev/sda bs=512 count=1 of=mbr.bin 2>/dev/null
# On Windows: use FTK Imager or dd for Windows

# Analyze MBR
python3 << 'EOF'
data = open("mbr.bin", "rb").read()
# Check boot signature
if data[510:512] != b'\x55\xAA':
    print("[!] Invalid MBR signature — corrupted or wiped")
else:
    print("[+] MBR signature valid")

# Check for known bootkit signatures
known_sigs = {
    b'\xEB\x5A\x90': "Standard Windows MBR",
    b'\xEB\x63\x90': "GRUB MBR",
}
sig = data[:3]
print(f"Boot code signature: {sig.hex()}")
print(f"Identified: {known_sigs.get(sig, 'UNKNOWN — possible bootkit')}")

# Dump partition table
import struct
for i in range(4):
    entry = data[446 + i*16 : 446 + (i+1)*16]
    status, ptype = entry[0], entry[4]
    lba = struct.unpack('<I', entry[8:12])[0]
    size = struct.unpack('<I', entry[12:16])[0]
    if ptype != 0:
        print(f"  Partition {i}: type=0x{ptype:02x} status=0x{status:02x} LBA={lba} sectors={size}")
EOF

# Dump VBR (Volume Boot Record — first sector of each partition)
dd if=/dev/sda1 bs=512 count=1 of=vbr.bin 2>/dev/null

# UEFI boot analysis — check ESP (EFI System Partition)
# Mount ESP and inspect bootloaders
mountvol S: /s
dir S:\EFI\
# Verify bootloader integrity
sigcheck.exe S:\EFI\Microsoft\Boot\bootmgfw.efi
sigcheck.exe S:\EFI\Boot\bootx64.efi
# ESPecter bootkit replaces bootmgfw.efi with a patched version

# Compare against known-good bootloader hash
sha256sum S:\EFI\Microsoft\Boot\bootmgfw.efi
# Cross-reference with Microsoft's signed bootloader hashes
```

## 5. UEFI Firmware Analysis

Detect firmware-level implants that survive OS reinstallation.

```bash
# Dump SPI flash firmware using chipsec
python chipsec_util.py spi dump firmware.bin
# Alternative: use hardware programmer (CH341A) for offline dump

# Check UEFI write protection
python chipsec_main.py -m common.bios_wp
# BIOS Write Protect (BIOSWE) should be LOCKED
# If unlocked → firmware can be modified from OS (implant vector)

# Check SPI flash lock
python chipsec_main.py -m common.spi_lock
# SPI Protected Ranges should cover full flash region

# Check Secure Boot status
python chipsec_main.py -m common.secureboot.variables
# Secure Boot should be ENABLED with valid PK/KEK/db

# Extract and analyze firmware volumes
UEFIExtract firmware.bin
# Inspect extracted DXE drivers and runtime services

# Search for known UEFI rootkit indicators
python3 << 'EOF'
import os
extracted_dir = "firmware.bin.dump"
suspicious = []
for root, dirs, files in os.walk(extracted_dir):
    for f in files:
        path = os.path.join(root, f)
        try:
            data = open(path, 'rb').read()
            # Known UEFI implant indicators
            if b'LoJax' in data or b'SedUploader' in data:
                suspicious.append((path, "LoJax indicator"))
            if b'MosaicRegressor' in data or b'IntelUpdate' in data:
                suspicious.append((path, "MosaicRegressor indicator"))
            if b'CosmicStrand' in data:
                suspicious.append((path, "CosmicStrand indicator"))
            # Generic: look for HTTP URLs in firmware modules (unusual)
            import re
            urls = re.findall(rb'https?://[^\x00\s]{8,}', data)
            if urls:
                suspicious.append((path, f"URLs found: {urls[:3]}"))
        except: pass
for path, reason in suspicious:
    print(f"[!] {reason}: {path}")
EOF

# Firmware integrity verification against vendor baseline
# Download original firmware from vendor site → binary diff
python3 -c "
a=open('firmware_original.bin','rb').read()
b=open('firmware.bin','rb').read()
diffs=[(i,a[i],b[i]) for i in range(min(len(a),len(b))) if a[i]!=b[i]]
print(f'Differences: {len(diffs)} bytes')
for off,orig,mod in diffs[:20]:
    print(f'  0x{off:08x}: {orig:02x} → {mod:02x}')
"
```

## 6. Hypervisor / Ring -1 Rootkit Detection

```bash
# Hypervisor rootkits (Blue Pill concept) run below the OS
# Detection is inherently difficult — timing-based side channels

# Check if running under unexpected hypervisor
# CPUID leaf 0x1: ECX bit 31 = hypervisor present
python3 << 'EOF'
import struct, ctypes
# Check CPUID for hypervisor bit
# This requires native code execution or WMI
import subprocess
result = subprocess.check_output(
    ["powershell", "-c",
     "Get-WmiObject -Class Win32_ComputerSystem | Select-Object HypervisorPresent,Model"],
    text=True
)
print(result)
# If HypervisorPresent=True but no known hypervisor installed → suspicious
EOF

# Timing-based detection (RDTSC anomalies)
# Hypervisor causes VM exits that add measurable latency
# CPUID instruction under hypervisor takes ~1000+ cycles vs ~100 native

# Check for known hypervisor rootkit artifacts
vol3 -f memory.raw windows.modules | grep -iE "vbox\|vmware\|hv\|hyperv"
# But a true ring-1 rootkit may not appear in module lists

# Physical memory access test (blocked by hypervisor)
# chipsec can detect unexpected EPT (Extended Page Tables)
python chipsec_main.py -m common.cpu.cpu_info
```

## 7. Linux Kernel Rootkit Analysis

```bash
# Check for LKM (Loadable Kernel Module) rootkits
lsmod | sort
cat /proc/modules | sort
# Compare: hidden modules appear in /proc but not lsmod, or vice versa

# Verify syscall table integrity
cat /proc/kallsyms | grep -E "sys_(read|write|open|getdents|kill)"
# Compare addresses against clean System.map

# Check for /dev anomalies (rootkits often create hidden devices)
ls -la /dev/ | grep -vE "^[bcdlps]"

# Detect hidden files via direct inode enumeration
debugfs -R "ls -l /" /dev/sda1 2>/dev/null

# Check for process hiding
ls /proc/ | grep -E "^[0-9]+$" | sort -n > proc_pids.txt
ps -eo pid --no-headers | sort -n > ps_pids.txt
comm -23 proc_pids.txt ps_pids.txt   # In /proc but not ps → suspicious
comm -13 proc_pids.txt ps_pids.txt   # In ps but not /proc → rootkit hiding

# Network socket hiding detection
ss -tulnp > ss_output.txt
cat /proc/net/tcp /proc/net/tcp6 > proc_net.txt
# Compare: hidden connections appear in /proc/net but not ss

# Volatility for Linux memory images
vol3 -f memory.lime linux.bash
vol3 -f memory.lime linux.check_modules
vol3 -f memory.lime linux.hidden_modules
vol3 -f memory.lime linux.check_syscall
```

## Tools & Resources

| Tool | Purpose | Install |
|---|---|---|
| GMER | Windows kernel rootkit scanner (GUI) | gmer.net |
| Volatility 3 | Memory forensics framework | github.com/volatilityfoundation/volatility3 |
| chipsec | UEFI/firmware security assessment | github.com/chipsec/chipsec |
| UEFITool | UEFI firmware image parser/editor | github.com/LongSoft/UEFITool |
| UEFIExtract | CLI firmware volume extractor | github.com/LongSoft/UEFITool |
| Sigcheck | Authenticode signature verification | Sysinternals |
| rkhunter | Linux rootkit scanner | rkhunter.sourceforge.net |
| chkrootkit | Linux rootkit checker | chkrootkit.org |
| LOLDrivers | Vulnerable driver database | loldrivers.io |
| ESET UEFI scanner | UEFI module whitelist checker | eset.com |

## Detection Signatures

| Indicator | Description | Detection |
|---|---|---|
| SSDT entry pointing outside ntoskrnl | Kernel function hook | Volatility windows.ssdt |
| Process in psscan but not pslist | DKOM process hiding | Volatility cross-view comparison |
| Driver loaded from \Temp or \AppData | Suspicious kernel driver | Volatility windows.drvscan + path check |
| BIOSWE bit unlocked | Firmware writable from OS | chipsec common.bios_wp |
| SPI region not locked | Flash can be modified | chipsec common.spi_lock |
| ESP bootloader hash mismatch | Modified bootloader (bootkit) | Hash comparison with vendor baseline |
| Unsigned .sys file in drivers directory | Potentially malicious driver | Sigcheck -u scan |
| Known BYOVD driver hash | Vulnerable driver exploitation | LOLDrivers hash comparison |

## Error Handling & Edge Cases

| Issue | Resolution |
|---|---|
| GMER crashes or hangs | Rootkit actively fighting scanner; try from WinPE/safe mode boot |
| chipsec requires kernel driver | Run on Linux live USB; Windows needs admin + test signing |
| Firmware dump size mismatch | SPI flash layout varies; use `chipsec_util spi info` for correct regions |
| Hypervisor rootkit undetectable | Physical hardware analysis required; use JTAG/SPI programmer for firmware dump |
| UEFI Secure Boot prevents chipsec | Boot Linux with Secure Boot disabled or MOK-signed chipsec driver |
| Memory image too large | Use targeted Volatility plugins; filter by PID or address range |
| Rootkit patches Volatility output | Use multiple analysis tools; cross-reference with raw memory search |
| Anti-forensics: cleared event logs | Carve deleted entries from raw disk; check alternate log locations |

## Decision Gate

```
IF suspicious hidden processes/files/network connections:
  → Capture full memory dump
  → Run Volatility cross-view detection (pslist vs psscan)
  → Check SSDT/IDT/IRP hooks
  → Scan for known vulnerable drivers (BYOVD)
IF boot-level persistence suspected:
  → Dump and verify MBR/VBR integrity
  → Mount ESP and hash-verify bootloaders
  → Check Secure Boot configuration
IF firmware implant suspected:
  → Dump SPI flash with chipsec
  → Extract and analyze UEFI volumes
  → Compare against vendor baseline firmware
  → Check BIOS write protect and SPI lock status
IF Linux system:
  → Run chkrootkit + rkhunter
  → Compare /proc PIDs vs ps output
  → Verify syscall table addresses
  → Check for hidden kernel modules
ELSE:
  → Start with GMER quick scan (Windows) or rkhunter (Linux)
  → Escalate to memory forensics if scanner detects anomalies
```
