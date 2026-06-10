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
  tags: mobile, android, ios, frida, objection, ssl-pinning, jadx, apktool
  mitre_attack: T1635, T1623, T1517, T1521, T1517.001
---

# Mobile Operator Skill Catalog

Mobile is 40% of modern bug-bounty programs and is conspicuously absent
from Strix and XBOW commercial. This catalog covers both platforms with
shared Frida tooling for runtime work.

## Playbooks

| Skill | Use for |
|---|---|
| `/skills/standard/mobile/android/SKILL.md` | Android APK workflow: apktool/jadx static, Frida dynamic, SSL-pin + root-detection bypass, intent fuzzing, keystore extraction |
| `/skills/standard/mobile/android/il2cpp/SKILL.md` | Unity IL2CPP reversing: Il2CppDumper metadata recovery, Frida method hooks, IAP/license bypass |
| `/skills/standard/mobile/flutter/SKILL.md` | Flutter reversing: reFlutter Dart-AOT patching, BoringSSL pin bypass, libapp.so analysis |
| `/skills/standard/mobile/ios/dynamic/SKILL.md` | iOS dynamic work on a jailbroken device: Frida/Objection, SSL Kill Switch, keychain dump, biometric bypass |

Per-technique splits (manifest-analysis, webview-flaws, keychain-acl,
url-scheme-abuse, firebase-misconfig, …) are planned but NOT yet
authored — `load_skill` only the paths in the table above; for
everything else follow the workflow below directly.

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
