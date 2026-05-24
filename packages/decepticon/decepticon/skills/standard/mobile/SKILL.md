---
name: mobile-overview
description: "Mobile application red team category — Android (APK) and iOS (IPA) pentest. Routing skill: identifies the platform + attack surface, then loads the matching sub-skill."
allowed-tools: Bash Read Write
metadata:
  subdomain: mobile
  when_to_use: "mobile, android, ios, apk, ipa, app, smartphone, frida, objection, jadx, apktool, mobsf, ssl pinning, root detection, jailbreak, intent, deep link, url scheme, mobile pentest"
  tags: mobile, android, ios, frida, jadx, apktool
  mitre_attack: T1517, T1640, T1418, T1409
---

# Mobile Application Red Team — Category Overview

This is a **routing skill**. Identify the target platform and the relevant attack surface, then load the specialized sub-skill.

## Sub-Skills

| Sub-Skill | Covers | When to Load |
|---|---|---|
| **android** | APK static (apktool/jadx) + dynamic (Frida/Objection), SSL pinning bypass, root detection bypass, intent fuzzing, keystore extraction, exported components | Android `.apk` file in scope, Play-Store target, MDM-managed Android device | `load_skill("/skills/standard/mobile/android/SKILL.md")` |

## Workflow

1. **Acquire** — APK from Play Store (apkpure / apkmirror), MDM extraction (`adb shell pm path <pkg>`), or device pull (`adb pull`)
2. **Static** — Pre-pull strings, manifest, permissions; decompile to Java/Smali
3. **Dynamic** — Frida or Objection on a rooted/emulated device; instrument crypto, network, storage
4. **Network** — Burp / mitmproxy with patched APK or Frida SSL-pin bypass
5. **Backend** — The APK is the door — the API behind it is the real attack surface; pivot to `standard/exploit/web/` once you have endpoints and tokens

## Tooling

| Tool | Use |
|---|---|
| `apktool` | Smali decompile / recompile / re-sign |
| `jadx` | Java pseudocode from DEX |
| `frida` / `frida-tools` | Runtime instrumentation |
| `objection` | Frida wrapper — ready-made bypass scripts |
| `mobsf` | Automated SAST+DAST first-pass triage |
| `drozer` | IPC / exported-component fuzzer |
| `apksigner` / `zipalign` | Re-sign modified APKs for re-install |
| `frida-ssl-pin-bypass` | Universal SSL-pinning patches |
| `nox` / `genymotion` / `android-studio AVD` | Emulators (x86_64 for speed) |

## Decision Notes

- iOS coverage (sub-skill `ios/`) is on the roadmap — for iOS work today, leverage the same dynamic patterns (Frida + Objection) and load `android/SKILL.md` for the methodology since the analytical workflow is platform-agnostic.
- Mobile backend exploitation almost always pivots to web/API testing — after token extraction, load `/skills/standard/exploit/web/SKILL.md`.
