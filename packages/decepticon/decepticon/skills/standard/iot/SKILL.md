---
name: iot-overview
description: >
  Use when the engagement target is IoT, embedded Linux, RTOS, or any device
  reachable via UART/JTAG/SWD or by extracting its firmware. Covers firmware
  acquisition, binwalk extraction, filesystem mounting, default-credential
  hunting, bootloader attacks, wireless protocol sidebands (BLE, Zigbee,
  Z-Wave, LoRaWAN, sub-GHz).
metadata:
  subdomain: iot
  when_to_use: "iot embedded linux rtos uart jtag swd firmware binwalk filesystem bootloader ble zigbee z-wave lorawan sub-ghz wireless"
  tags: iot, firmware, embedded, binwalk, uart, jtag, ble, zigbee
  mitre_attack: T1542, T1542.005, T1601, T1499.004
---

# IoT / Embedded Operator Skill Catalog

This catalog covers the surface area between hardware reconnaissance and
runtime exploitation of IoT and embedded targets. Wireless sidebands
(BLE / Zigbee / Z-Wave / LoRaWAN / sub-GHz) live alongside firmware-level
attacks because IoT engagements routinely chain across both.

## Playbooks

| Skill | Use for |
|---|---|
| `/skills/standard/iot/firmware-acquisition/SKILL.md` | Vendor portals, OTA capture, SPI flash dump, eMMC chip-off |
| `/skills/standard/iot/binwalk-extract/SKILL.md` | binwalk + firmware-mod-kit extraction; squashfs / jffs2 mount |
| `/skills/standard/iot/hardcoded-creds/SKILL.md` | Strings, shadow, busybox httpd, telnet logs |
| `/skills/standard/iot/bootloader-uboot/SKILL.md` | U-Boot console interrupt; environment variables; secure-boot bypass |
| `/skills/standard/iot/dev-mem/SKILL.md` | /dev/mem, /dev/kmem, MTD writes on embedded Linux |
| `/skills/standard/iot/ble-gatt/SKILL.md` | GATT enumeration, characteristic read/write without auth, pairing downgrade |
| `/skills/standard/iot/zigbee-touchlink/SKILL.md` | Touchlink commissioning abuse, well-known transport key, ZCL command abuse |
| `/skills/standard/iot/z-wave/SKILL.md` | S0 derivation flaw, S2 ECDH analysis, replay on unauthenticated nodes |
| `/skills/standard/iot/lorawan-otaa/SKILL.md` | OTAA join, frame-counter replay, downlink injection |
| `/skills/standard/iot/sub-ghz/SKILL.md` | 433/868/915 MHz capture + replay (HackRF, Flipper Zero, RTL-SDR) |

## Workflow

1. **Inventory hardware**: photograph PCB; identify SoC, flash, debug pads
   (UART = 4-pin pattern; JTAG = TAP; SWD = 2-pin SWDIO/SWCLK).
2. **Acquire firmware**: vendor update portal first; OTA proxy capture
   second; SPI flash dump third; eMMC chip-off last.
3. **Extract**: `binwalk -eM <fw.bin>`, then mount squashfs / jffs2 / ubifs.
4. **Triage**: search strings for credentials, AWS keys, MQTT topics, hardcoded
   IPs; identify backdoor accounts (busybox /etc/passwd, telnet/SSH stanzas).
5. **Wireless co-channels**: if the device speaks BLE / Zigbee / Z-Wave /
   LoRaWAN, capture commissioning, replay, attempt key extraction.
6. **Cloud-IoT**: if the device backhauls to a vendor cloud, pivot to the
   mobile companion app and the cloud API.

## Hardware bench tools (sandbox tools)

- Logic analyzer: Saleae Pro 8 / Sigrok PulseView.
- Flash interface: ch341a + SOIC clip.
- Debug interface: BusPirate v5, J-Link, Black Magic Probe.
- Glitching: ChipWhisperer-Nano / Pico.
- Wireless: HackRF One, Sonoff Zigbee 3.0 Dongle E, RTL-SDR Blog v4.

## Safety

IoT engagements often touch consumer devices that the operator owns but
that have shared cloud accounts (vendor telemetry). RoE must enumerate
which clouds may be probed. ConOps `blue_team` field should declare the
vendor IR contact when in scope so a fail-safe trip can be reported.
