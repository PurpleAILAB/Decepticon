---
name: wireless-security
description: "Wireless network security reconnaissance — WiFi analysis, Bluetooth assessment, RFID/NFC evaluation, signal capture, protocol analysis, encryption testing, rogue device detection."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "wireless security, WiFi analysis, Bluetooth assessment, RFID, NFC, signal capture, protocol analysis, encryption testing, rogue device detection, wardriving, packet capture"
  tags: wireless, wifi, bluetooth, rfid, nfc, signal-analysis, encryption-testing, wardriving, packet-capture, rogue-device
  mitre_attack: T1584, T1584.001, T1584.002, T1584.003, T1584.004
---

# Wireless Network Security Reconnaissance Knowledge Base

Wireless network security reconnaissance involves identifying, analyzing, and assessing wireless communication protocols and networks for vulnerabilities. This includes WiFi, Bluetooth, RFID/NFC, Zigbee, Z-Wave, LoRaWAN, and other wireless technologies.

## 1. WiFi Network Reconnaissance

### Network Discovery
```bash
# Scan for WiFi networks
airodump-ng wlan0

# Scan specific channel
airodump-ng -c 6 --bssid <BSSID> wlan0

# Scan all channels
wash -i wlan0 -C
```

### Target Identification
```bash
# Identify target network
airolump-ng wlan0

# Get network information
airodump-ng -c <channel> --bssid <BSSID> -w capture wlan0
```

### Client Identification
```bash
# Identify connected clients
airodump-ng -c <channel> --bssid <BSSID> wlan0

# Deauthenticate clients to capture handshakes
aireplay-ng -0 10 -a <BSSID> -c <Client_MAC> wlan0
```

## 2. WiFi Encryption Analysis

### Encryption Type Detection
```bash
# Check encryption type
airodump-ng -c <channel> wlan0 | grep "CH\s*"

# WEP detection (vulnerable)
if [ "$(airodump-ng -c <channel> wlan0 | grep WEP)" ]; then echo "WEP detected - vulnerable!"; fi

# WPA/WPA2 detection
airodump-ng -c <channel> wlan0 | grep -E "WPA|WPA2"

# Open network detection
airodump-ng -c <channel> wlan0 | grep "OPEN"
```

### Vulnerability Assessment
```bash
# WPS vulnerability check
wash -i wlan0 -C
reaver -i wlan0 -b <BSSID> -vv
bully <BSSID> -c <channel> wlan0

# PMKID attack (if WPA2)
hcxpcapngtool -o hash.hc22000 capture.cap --pmkid

# WPA handshake capture
aireplay-ng -0 10 -a <BSSID> wlan0
```

### Key Cracking
```bash
# WEP cracking
airecrack-ng -b <BSSID> capture.cap

# WPA/WPA2 cracking with wordlist
airecrack-ng -w wordlist.txt -b <BSSID> capture.cap

# Use hashcat for GPU acceleration
hcxpcapng2john capture.hc22000 > hash.txt
hashcat -m 22000 hash.txt wordlist.txt
```

## 3. Bluetooth Reconnaissance

### Device Discovery
```bash
# Scan for Bluetooth devices
hcitool scan

# Extended scan with more details
bluetoothctl scan on
bluetoothctl devices
```

### Service Discovery
```bash
# Discover services on device
sdptools browse <device_address>

# RFCOMM scan
rfcomm -a <device_address> list
```

### Connection Attempts
```bash
# Connect to device
bluetoothctl connect <device_address>

# Trust and pair
bluetoothctl trust <device_address>
bluetoothctl pair <device_address>
```

## 4. BLE (Bluetooth Low Energy) Analysis

### BLE Device Discovery
```bash
# Scan for BLE devices
hcitool lescan

# Scan with more details
bluetoothctl scan on
```

### BLE Service Discovery
```bash
# Discover services
gatttool -b <device_address> -p /dev/null connect

# List services
gatttool -b <device_address> -p /dev/null primary

# List characteristics
gatttool -b <device_address> -p /dev/null characteristics
```

### BLE Packet Capture
```bash
# Capture BLE packets
btmon

# Filter BLE traffic
tshark -i bluetooth0 -f "btcommon.address == <device_address>"
```

## 5. RFID and NFC Reconnaissance

### RFID Analysis
```bash
# Use RFID reader
rfidtool --read

# Clone RFID tag (if vulnerable)
rfidtool --clone --source <source_uid> --target <target_uid>

# Proxmark3 commands
proxmark3> hf search
proxmark3> hf mfdump
```

### NFC Analysis
```bash
# NFC tag reading
nfc-list
nfc-poll

# Mifare Classic analysis
mfoc -O mf_dump.bin

# NFC URL extraction
nfc-mfultralight rdump nfc_dump.bin
strings nfc_dump.bin
```

## 6. Signal Analysis and Capture

### Packet Capture
```bash
# WiFi packet capture
tcpdump -i wlan0 -n -w capture.pcap

# Filter for specific protocol
tcpdump -i wlan0 -n port 53 -w dns_capture.pcap

# Airplane mode packet capture
tshark -i wlan0 -w wireless_capture.pcap
```

### Spectrum Analysis
```bash
# Use SDR (Software Defined Radio)
rtl_sdr -f 2412e6 -s 2e6 -g 20 -b 8 -F 0 -l 0 -E deinterleave -E dcblock -E normalized output.raw

# Analyze with gnuradio
# Requires GNU Radio setup
```

### Signal Strength Analysis
```bash
# Monitor signal strength
watch -n 1 "iwconfig wlan0 | grep Signal"

# Create signal heatmap
kismet
```

## 7. Rogue Device Detection

### Rogue Access Point Detection
```bash
# Detect rogue APs
kismet

# Use specialized tools
wifi-pumpkin -i wlan0

# Detect evil twin attacks
airodump-ng -c <channel> wlan0 | grep -E "<known_SSID>|<known_BSSID>"
```

### Rogue Client Detection
```bash
# Detect unauthorized clients
airodump-ng -c <channel> wlan0 | grep -v <authorized_mac_list>

# Detect MAC spoofing
airodump-ng -c <channel> wlan0 | grep -E "<known_MAC_prefixes>"
```

## 8. Wireless Protocol Analysis

### WiFi Protocol Analysis
```bash
# Analyze WiFi management frames
tshark -i wlan0 -Y "wlan.fc.type == 0" -V

# Analyze WiFi control frames
tshark -i wlan0 -Y "wlan.fc.type == 1" -V

# Analyze WiFi data frames
tshark -i wlan0 -Y "wlan.fc.type == 2" -V
```

### Bluetooth Protocol Analysis
```bash
# Analyze Bluetooth packets
tshark -i bluetooth0 -V

# Filter for specific Bluetooth protocol
tshark -i bluetooth0 -Y "btatt" -V
```

## 9. Encryption Testing

### WiFi Encryption Testing
```bash
# Test WEP encryption strength
aireplay-ng -1 0 -e <ESSID> -a <BSSID> -h <My_MAC> wlan0
aireplay-ng -2 -p 0841 -c FF:FF:FF:FF:FF:FF -e <ESSID> -a <BSSID> -h <My_MAC> wlan0

# Test WPA handshake
aircrack-ng -w wordlist.txt -b <BSSID> capture.cap
```

### Bluetooth Encryption Testing
```bash
# Check Bluetooth encryption status
bluetoothctl info <device_address>

# Test encryption strength
# Requires specialized tools
```

## 10. Advanced Wireless Attacks

### Deauthentication Attacks
```bash
# Deauthenticate specific client
aireplay-ng -0 10 -a <BSSID> -c <Client_MAC> wlan0

# Deauthenticate all clients
aireplay-ng -0 10 -a <BSSID> wlan0

# Continuous deauthentication
aireplay-ng -0 0 -a <BSSID> wlan0
```

### MITM Attacks
```bash
# ARP spoofing
arpspoof -i wlan0 -t <target_ip> -r <gateway_ip>

# DNS spoofing
dnsspoof -i wlan0 "tcp port 53 and (udp port 53)"
```

### Evil Twin Attack
```bash
# Create evil twin AP
airbase-ng -e <Fake_SSID> -c <channel> wlan0

# Use hostapd
# Configure /etc/hostapd/hostapd.conf
# Then: hostapd /etc/hostapd/hostapd.conf
```

## 11. Wireless Security Tools

### WiFi Tools
```bash
# Comprehensive WiFi suite
aircrack-ng suite
# - airodump-ng: Packet capture
# - aireplay-ng: Packet injection
# - airtun-ng: Virtual tunnel interface
# - airolump-ng: WEP and WPA PSK key generator

# WPA/WPA2 handshake capture
wifite

# WiFi signal analysis
kismet
```

### Bluetooth Tools
```bash
# Bluetooth scanning and analysis
bluetoothctl

# RFCOMM tool
rfcomm

# SDP tool
sdptools
```

### RFID/NFC Tools
```bash
# RFID analysis
rfidtool

# NFC analysis
libnfc tools

# Proxmark3
proxmark3-client
```

## Tools Summary

| Tool | Purpose | Required |
|------|---------|----------|
| `airodump-ng` | WiFi packet capture | ✅ |
| `aireplay-ng` | WiFi packet injection | ✅ |
| `aircrack-ng` | WiFi encryption cracking | ✅ |
| `wash` | WPS detection | ✅ |
| `reaver` | WPS brute-force attack | ✅ |
| `bully` | WPS brute-force attack | ✅ |
| `hcxpcapngtool` | PMKID extraction | ✅ |
| `hashcat` | Password cracking | ✅ |
| `hcitool` | Bluetooth device scanning | ✅ |
| `bluetoothctl` | Bluetooth device management | ✅ |
| `gatttool` | BLE service discovery | ✅ |
| `rfcomm` | RFCOMM channel access | ✅ |
| `sdptools` | SDP service discovery | ✅ |
| `tcpdump` | Network packet capture | ✅ |
| `tshark` | Command-line protocol analysis | ✅ |
| `kismet` | Wireless network detector | ✅ |
| `rtlsdr` | Software Defined Radio | ❌ |
| `proxmark3` | RFID/NFC analysis | ❌ |
| `wifite` | Automated WiFi attacks | ✅ |
