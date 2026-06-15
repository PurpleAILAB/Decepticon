---
name: iot-security
description: "IoT device security reconnaissance — firmware extraction, embedded analysis, protocol identification, default credential checking, vulnerability scanning, device fingerprinting."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "IoT security, firmware analysis, embedded devices, protocol identification, default credentials, vulnerability scan, device fingerprinting, MQTT, CoAP, Modbus"
  tags: iot, embedded, firmware, reverse-engineering, protocol-analysis, default-credentials, vulnerability-scanning, mqtt, coap, modbus
  mitre_attack: T1592, T1592.001, T1592.002
---

# IoT Device Security Reconnaissance Knowledge Base

IoT (Internet of Things) device security reconnaissance focuses on identifying, analyzing, and assessing vulnerabilities in embedded systems and IoT devices. This includes firmware extraction, protocol analysis, default credential verification, and vulnerability identification.

## 1. Device Discovery and Identification

### Network Scanning
```bash
# Discover IoT devices on network
nmap -sn 192.168.1.0/24

# Identify IoT-specific ports and services
nmap -sV --script=iot* -p- <target_ip>

# Shodan search for IoT devices
shodan search "device_type:iot"
```

### Protocol Identification
```bash
# Check common IoT ports
nmap -sV -p 1883,5683,5684,61613,61614,61616,102,502,8080,8443 <target_ip>

# MQTT protocol detection
nc -zv <target_ip> 1883

# CoAP protocol detection
nc -zv -u <target_ip> 5683

# Modbus TCP detection
nc -zv <target_ip> 502
```

### Device Fingerprinting
```bash
# Extract device information from banners
nc <target_ip> 80
curl -I http://<target_ip>

# Use specialized tools
iot-scanner --target <target_ip>
```

## 2. Firmware Extraction

### From Device
```bash
# Extract firmware via UART
screen /dev/ttyUSB0 115200
# In UART console: check for firmware dump commands

# Extract via SPI flash
flashrom -r firmware.bin

# Extract via JTAG
openocd -f interface/cmsis-dap.cfg -f target/stm32f4x.cfg -c "dump_image firmware.bin 0x08000000 0x200000"
```

### From Manufacturer
```bash
# Download from manufacturer website
wget https://manufacturer.com/support/firmware(device_model)_vX.X.X.bin

# Extract from mobile app (if available)
# Often contains firmware update files
```

### Firmware Archive Sources
- Manufacturer websites
- Third-party firmware repositories
- Device backup files
- OTA (Over-The-Air) update packages

## 3. Firmware Analysis

### File System Extraction
```bash
# Identify firmware type
file firmware.bin

# Extract with binwalk
binwalk -e firmware.bin

# Extract squashfs filesystem
unsquashfs squashfs-root

# Mount filesystem
mount -o loop filesystem.ext4 /mnt/firmware
```

### Binary Analysis
```bash
# Check for executable formats
file extracted_binaries/*

# Analyze ARM binaries
readelf -a binary.elf

# Extract strings
strings firmware.bin > strings.txt

# Search for interesting strings
grep -E "(admin|root|password|secret|backdoor|shell|telnet|ssh)" strings.txt
```

## 4. Default Credential Checking

### Common Default Credentials
```bash
# Try common admin credentials
hydra -L common_usernames.txt -P common_passwords.txt <target_ip> http-post-form "/login:user=^USER^&pass=^PASS^:Invalid" -vV

# Common username/password combinations:
# admin/admin, admin/password, admin/123456
# root/admin, root/password, root/12345
# user/user, user/password
# guest/guest, guest/password
# support/support, support/password
```

### Vendor-Specific Credentials
```bash
# Check vendor documentation for default credentials
# Many vendors have well-known defaults

# Search for default credentials in extracted firmware
grep -r "default.*password\|password.*default" extracted_firmware/
```

### Credential Databases
- Use `secrets-collection` from cirt DefaultPasswords
- Use `routerpasswd` for router-specific defaults
- Check CIRCL default password list

## 5. Protocol-Specific Analysis

### MQTT (Message Queuing Telemetry Transport)
```bash
# Connect to MQTT broker
mosquitto_sub -h <target_ip> -t "#" -v

# Publish test message
mosquitto_pub -h <target_ip> -t "test" -m "hello" --will-topic "test" --will-payload "disconnected"

# Check for unauthenticated access
mosquitto_sub -h <target_ip> -t "#" -v --username "" --password ""
```

### CoAP (Constrained Application Protocol)
```bash
# Discover CoAP resources
coap-client -m get "coap://<target_ip>/.well-known/core"

# Check for default resources
coap-client -m get "coap://<target_ip>/"  
coap-client -m get "coap://<target_ip>/status"
```

### Modbus
```bash
# Read Modbus registers
modbus-read --ip=<target_ip> --port=502 --slave=1 --count=10 --register=0

# Check for common Modbus configurations
nmap --script modbus-discover <target_ip>
```

### HTTP/REST APIs
```bash
# Check for web interface
curl -k https://<target_ip>

# Check common API endpoints
curl -k https://<target_ip>/api
curl -k https://<target_ip>/cgi-bin/

# Check for authentication bypass
curl -k -H "Authorization: Basic $(echo -n 'admin:admin' | base64)" https://<target_ip>
```

### UPnP
```bash
# Discover UPnP devices
upnp-discover

# Check for UPnP vulnerabilities
searchsploit upnp | grep -i iot
```

## 6. Vulnerability Scanning

### Common IoT Vulnerabilities
- Default/weak credentials
- Hardcoded backdoors
- Unauthenticated access
- Command injection
- Buffer overflow
- Memory corruption
- Firmware update vulnerabilities
- Insecure communication (cleartext protocols)

### Automated Scanning
```bash
# Use IoT-specific vulnerability scanners
iot-vuln-scanner --target <target_ip>

# Check for known CVEs
searchsploit --nmap <nmap_xml_output.xml> -t iot

# Use Metasploit modules
msfconsole -q -x "use auxiliary/scanner/iot/*; set RHOSTS <target_ip>; run"
```

### Manual Verification
```bash
# Check for shell access via Telnet
nc <target_ip> 23

# Check for shell access via SSH
ssh admin@<target_ip>

# Check for FTP
ftp <target_ip>

# Check for TFTP
atftp <target_ip>
```

## 7. Wireless IoT Analysis

### Zigbee
```bash
# Zigbee network scanning
zigbee-scan --interface /dev/ttyACM0 --channel 11-26

# Zigbee packet capture
zigbee-capture --interface /dev/ttyACM0 --output zigbee.pcap
```

### Z-Wave
```bash
# Z-Wave network discovery
zwave-scan --device /dev/ttyACM0

# Z-Wave node enumeration
zwave-nodes --device /dev/ttyACM0
```

### BLE (Bluetooth Low Energy)
```bash
# BLE device discovery
hcitool lescan

# BLE service discovery
bluetoothctl scan on
bluetoothctl info <device_mac>

# Connect to BLE device
bluetoothctl connect <device_mac>
```

## 8. Cloud IoT Analysis

### AWS IoT
```bash
# List IoT things (requires AWS credentials)
aws iot list-things

# Get thing details
aws iot describe-thing --thing-name <thing_name>

# List IoT policies
aws iot list-policies
```

### Azure IoT Hub
```bash
# List IoT devices (requires Azure credentials)
az iot hub device list --hub-name <hub_name> -g <resource_group>
```

## 9. Security Hardening Checks

### Password Complexity
- Check if device enforces strong passwords
- Check for password recovery mechanisms
- Check for password change requirements

### Network Segmentation
- Check if IoT devices are on isolated VLAN
- Check for firewall rules protecting IoT devices
- Check for network access controls

### Update Mechanism
- Check for secure firmware update process
- Check for signed updates
- Check for update verification

### Logging and Monitoring
- Check if device logs security events
- Check if logs are accessible
- Check for remote logging capabilities

## 10. Exploitation and Post-Exploitation

### Note: Only perform with explicit authorization

### Gaining Access
```bash
# If default credentials work
ssh admin@<target_ip>  # with default password

# If vulnerable to command injection
curl -k "https://<target_ip>/cgi-bin/;id"

# If vulnerable to buffer overflow
# Use Metasploit or custom exploit
```

### Privilege Escalation
- Check for root shell access
- Check for sudo/su configuration
- Check for setuid binaries

### Persistence
- Add SSH keys
- Modify startup scripts
- Install backdoors

### Lateral Movement
- Pivot to other devices on the same network
- Access cloud management interfaces
- Exfiltrate data to external servers

## Tools Summary

| Tool | Purpose | Required |
|------|---------|----------|
| `nmap` | Network scanning and service detection | ✅ |
| `binwalk` | Firmware extraction and analysis | ✅ |
| `strings` | String extraction from binaries | ✅ |
| `hydra` | Brute-force credential attacks | ✅ |
| `mosquitto_sub` | MQTT client for testing | ✅ |
| `coap-client` | CoAP protocol testing | ✅ |
| `screen` | Serial terminal emulation | ✅ |
| `flashrom` | SPI flash memory reading | ❌ |
| `openocd` | JTAG debugging | ❌ |
| `wireshark` | Network traffic analysis | ✅ |
| `tshark` | Command-line packet capture | ✅ |
| `searchsploit` | Vulnerability database search | ✅ |
| `metasploit` | Exploitation framework | ❌ |
| `iot-scanner` | IoT-specific scanner | ❌ |
