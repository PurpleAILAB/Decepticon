---
name: reverser-ios-static
description: "iOS IPA static analysis — class-dump-z / class-dump-ng, Hopper / IDA / Ghidra for Mach-O ARM64, Objective-C runtime introspection, Swift demangling, App Transport Security check, plist analysis, embedded provisioning profile parse. For dynamic Frida/Objection see mobile/SKILL.md."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "ios ipa ios app mach-o arm64 class-dump objective-c swift hopper ghidra plist provisioning profile entitlements"
  subdomain: reverser
  tags: ios, mach-o, mobile, static-analysis
  mitre_attack: T1518.001
---

# iOS IPA Static Analysis

## Acquire the IPA

```bash
# Option 1: App Store (encrypted FairPlay — needs decryption from a jailbroken device)
# Option 2: ipatool — pulls IPAs from your Apple ID
ipatool download -b com.target.app

# Option 3: Frida-iOS-Dump (jailbroken device required)
# Pulls a decrypted IPA from the device's memory
frida-ios-dump -o app.ipa "<bundle-id>"
```

## Unpack the IPA

```bash
unzip app.ipa -d app/
# Structure:
#   app/Payload/<AppName>.app/
#     <AppName>                  — Mach-O binary
#     Info.plist                  — metadata
#     embedded.mobileprovision    — provisioning profile
#     en.lproj/, Frameworks/, ...
```

## Quick triage

```bash
# 1. Info.plist — capabilities, URL schemes, ATS exceptions
plutil -p app/Payload/Foo.app/Info.plist
# Look for:
#   CFBundleURLTypes           — custom URL schemes (deep links)
#   LSApplicationQueriesSchemes — schemes the app probes
#   NSAppTransportSecurity      — ATS exceptions (HTTP allowed?)
#   UIBackgroundModes          — long-running capabilities
#   com.apple.developer.*       — entitlements

# 2. Embedded provisioning profile — entitlements + cert chain
security cms -D -i app/Payload/Foo.app/embedded.mobileprovision | plutil -p -
# Look for:
#   Entitlements (push, keychain access, app groups, network extension)
#   Developer team ID (Apple-issued vs Enterprise)

# 3. Mach-O architecture + protection flags
file app/Payload/Foo.app/Foo
otool -hV app/Payload/Foo.app/Foo
# Flags: PIE (always on for iOS), STACK_PROTECT, MH_NO_HEAP_EXECUTION

# 4. Check encryption status
otool -l app/Payload/Foo.app/Foo | grep -A4 LC_ENCRYPTION_INFO
# cryptid 1 = encrypted (decrypt via frida-ios-dump first)
# cryptid 0 = ready to analyze
```

## Class-dump (Objective-C metadata)

```bash
# class-dump-z, class-dump-ng — extract Objective-C interface
class-dump-z -H app/Payload/Foo.app/Foo -o headers/
# Output: one .h file per class. Reveals method names, ivars, properties.

# class-dump (newer):
class-dump --arch arm64 -H app/Payload/Foo.app/Foo -o headers/

# For Swift symbols: swift-demangle
nm app/Payload/Foo.app/Foo | swift-demangle | head
```

Headers tell you:
- Class hierarchy (subclasses of NSObject, UIViewController, etc.)
- Method signatures (often reveal business logic intent)
- Properties (often reveal stored data)
- Use of `NSURLSession` / `NSURLConnection` (network) / `Security.framework` (crypto)

## Disassembly

```bash
# Hopper Disassembler — UI-focused, decent Obj-C support
# IDA Pro — best Objective-C / Swift but $$$
# Ghidra — free, growing iOS support
# rizin / radare2 — CLI:
r2 -A app/Payload/Foo.app/Foo
> afl                                  # function list
> s sym._-[FooViewController login:]   # navigate to a method
> pdf                                   # disassemble + decompile (Cutter UI helps)
```

## Things to look for

### Hardcoded secrets
```bash
strings app/Payload/Foo.app/Foo | grep -iE 'api[._-]?key|secret|token|password|bearer'
strings app/Payload/Foo.app/Foo | grep -iE '^[A-Za-z0-9+/]{40,}={0,2}$'   # base64 candidates
strings app/Payload/Foo.app/Foo | grep -iE 'sk_live|pk_live|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}'  # AWS, Stripe, GCP
```

### URLs / Endpoints
```bash
strings app/Payload/Foo.app/Foo | grep -iE 'https?://' | sort -u
```

### Backend / firebase config
```bash
find app/Payload/Foo.app -name '*.plist' -exec plutil -p {} \; 2>/dev/null | grep -iE 'google|firebase|amazon|azure|api'
find app/Payload/Foo.app -name 'GoogleService-Info.plist'   # Firebase config
```

### Insecure ATS exceptions
```bash
plutil -p app/Payload/Foo.app/Info.plist | grep -A20 NSAppTransportSecurity
# NSAllowsArbitraryLoads = true → app allows HTTP. Why?
# NSExceptionDomains → list of allowed-HTTP domains
```

### Insecure file storage
Search the binary for:
- `NSUserDefaults`-stored secrets (no encryption)
- `kSecAttrAccessibleAlways` (keychain item accessible always — no device-lock requirement)
- `NSFileProtectionNone` (file readable when device locked)

### URL scheme handlers
```bash
plutil -p app/Payload/Foo.app/Info.plist | grep -A4 CFBundleURLSchemes
# Each scheme is a potential entry point. Check what method handles it
# in headers/ — `application:openURL:` or `scene:openURLContexts:`.
```

### Embedded JS bridge (WebView, React Native, Cordova)
```bash
find app/Payload/Foo.app -name '*.bundle' -o -name 'main.jsbundle'   # React Native
find app/Payload/Foo.app -name 'cordova.js'                          # Cordova
# These are JavaScript — easier to RE; check for eval, postMessage handlers
```

## For dynamic analysis

See `/skills/standard/mobile/SKILL.md` (or `/skills/standard/mobile/android/` for the Android counterpart). Use Frida + Objection on a jailbroken device for runtime hooking, SSL pinning bypass, jailbreak detection bypass.

## OPSEC

- Static analysis is invisible to the target — analyze offline on a clean VM.
- App Store-acquired IPAs are FairPlay-encrypted — decryption requires a jailbroken device, which leaves an Apple-side fingerprint (don't use your personal Apple ID).
- Symbolicated dSYM files are sometimes shipped to App Store Connect — request from the vendor if you have a bug-bounty relationship.

## References

- "iOS Application Security" — David Thiel (NCC Group book)
- OWASP MSTG (Mobile Security Testing Guide) — iOS chapter
- "The Mobile Application Hacker's Handbook"
- iphone-dev-wiki Mach-O / Objective-C runtime references
