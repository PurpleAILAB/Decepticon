---
name: mobile-overview
description: >
  Use when the engagement target is an Android (APK / AAB) or iOS (IPA)
  application. Covers static analysis (jadx, apktool, class-dump),
  dynamic instrumentation via Frida and Objection, SSL-pinning bypass,
  root/jailbreak detection bypass, deep-link / URL-scheme abuse,
  exported-component attacks, IPC redirection, WebView vulnerabilities,
  and biometric / Face ID / Touch ID bypass.
metadata:
  subdomain: mobile
  when_to_use: "mobile android ios apk aab ipa jadx apktool frida objection ssl pinning bypass root jailbreak detection deep link url scheme exported component ipc webview biometric face id touch id"
  subdomain: mobile
  tags: mobile, android, ios, frida, objection, ssl-pinning, jadx, apktool
  mitre_attack: T1635, T1623, T1517, T1521, T1517.001
---

# Mobile Operator Skill Catalog

Mobile is 40% of modern bug-bounty programs and is conspicuously absent
from Strix and XBOW commercial. This catalog covers both platforms with
shared Frida tooling for runtime work.

## Playbooks — Android

| Skill | Use for |
|---|---|
| `/skills/standard/mobile/android/apk-triage/SKILL.md` | apktool decode + jadx -d for source recovery |
| `/skills/standard/mobile/android/manifest-analysis/SKILL.md` | exported components, permissions, deeplinks |
| `/skills/standard/mobile/android/insecure-storage/SKILL.md` | SharedPreferences / SQLite / external storage scans |
| `/skills/standard/mobile/android/intent-redirection/SKILL.md` | Intent forwarding / pendingIntent abuse |
| `/skills/standard/mobile/android/webview-flaws/SKILL.md` | JavaScriptInterface, file:// access, mixed content |
| `/skills/standard/mobile/android/frida-ssl-pin-bypass/SKILL.md` | OkHttp / TrustKit / Cordova pin-bypass scripts |
| `/skills/standard/mobile/android/root-detect-bypass/SKILL.md` | Common root-detection libraries and their bypasses |

## Playbooks — iOS

| Skill | Use for |
|---|---|
| `/skills/standard/mobile/ios/ipa-triage/SKILL.md` | class-dump-z + Hopper; Mach-O headers; entitlements |
| `/skills/standard/mobile/ios/keychain-acl/SKILL.md` | Keychain ACL misconfigurations; `kSecAccessControl` flags |
| `/skills/standard/mobile/ios/url-scheme-abuse/SKILL.md` | Universal links + URL scheme handler attacks |
| `/skills/standard/mobile/ios/xpc-services/SKILL.md` | XPC interface enumeration; unauthenticated XPC services |
| `/skills/standard/mobile/ios/frida-trust-killer/SKILL.md` | SSL Kill Switch + Frida pin-bypass for iOS apps |
| `/skills/standard/mobile/ios/jailbreak-detect-bypass/SKILL.md` | DTAppJailbreakDetectorSwift, Liberty Lite, common patterns |

## Cross-platform

| Skill | Use for |
|---|---|
| `/skills/standard/mobile/frida-bridge/SKILL.md` | frida-server install on emulator / jailbroken device; basic scripts |
| `/skills/standard/mobile/objection-walkthrough/SKILL.md` | Objection cheatsheet (env, memory, sqlite, classes) |
| `/skills/standard/mobile/firebase-misconfig/SKILL.md` | Firebase /Firestore RLS / Storage / Auth bypasses |
| `/skills/standard/mobile/mobile-api-testing/SKILL.md` | Burp / Caido proxy → mobile API endpoint enumeration |

## Workflow

1. **Triage**: jadx for Android, class-dump for iOS. Search strings for
   API endpoints, Firebase config, AWS keys.
2. **Static**: AndroidManifest.xml exported components; iOS Info.plist
   URL schemes + entitlements.
3. **Dynamic setup**: Frida server on a rooted emulator (Android) or
   jailbroken physical device (iOS); Objection for quick inspection.
4. **SSL pin bypass**: Frida script; verify HTTPS now visible in Burp.
5. **API enumeration**: re-route the app through the proxy; spider
   reachable endpoints; export to Burp project for later web-recon-style
   testing.
6. **Insecure storage**: pull `/data/data/<pkg>/` (Android) or app
   container (iOS); grep for credentials, tokens, PII.
7. **Component-level attacks**: send crafted Intents (`adb shell am
   start ...`) or URL-scheme payloads (`xcrun simctl openurl ...`).

## Tools sandbox

- adb + emulator / physical device.
- jadx, apktool, dex2jar, jd-gui.
- class-dump, Hopper Disassembler, IDA Free (host-side).
- Frida-server (per device), frida (host), objection.
- mitmproxy / Burp Suite Community / Caido (PR #304 lands the LangChain
  Caido tool bundle).
- MobSF (`mobsf` Docker image) for automated triage when speed matters.
