---
name: mobile-security
description: "Mobile application security reconnaissance — APK/IPA analysis, permission enumeration, certificate validation, hardcoded secret detection, insecure storage identification, network security analysis."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "mobile security, APK analysis, IPA analysis, Android manifest, iOS Info.plist, certificate validation, hardcoded secrets, insecure storage, network security config, WebView security"
  tags: mobile, android, ios, apk, ipa, reverse-engineering, static-analysis, certificate-validation, secret-detection
  mitre_attack: T1589.001, T1589.002
---

# Mobile Application Security Reconnaissance Knowledge Base

Mobile application security reconnaissance involves static analysis of APK and IPA files to identify vulnerabilities, misconfigurations, and security weaknesses without executing the application. This skill enables autonomous agents to analyze mobile applications for security issues.

## 1. APK Analysis

### Package Information Extraction
```bash
# Extract APK package information
aapt dump badging {apk_path}

# Extract full APK details
aapt dump all {apk_path}
```

### Decompilation
```bash
# Decompile APK with apktool
apktool d {apk_path} -o output_dir

# Decompile with jadx (to Java source)
jadx {apk_path} -d output_dir

# Convert DEX to JAR for Java analysis
dex2jar {apk_path} -o output.jar
```

### Resource Extraction
```bash
# Extract resources from APK
unzip -l {apk_path}
unzip -d output_dir {apk_path}

# View AndroidManifest.xml
aapt dump xmltree {apk_path} AndroidManifest.xml
```

## 2. iOS IPA Analysis

### Package Information
```bash
# Extract IPA metadata
unzip -l {ipa_path}

# View Info.plist
plutil -p {ipa_path}/Payload/*.app/Info.plist
```

### Binary Analysis
```bash
# Extract binary information
otool -lv {binary_path}

# View strings in binary
strings {binary_path}

# Check entitlements
jtool --ent {ipa_path}/Payload/*.app/embedded.mobileprovision
```

## 3. Certificate and Signature Validation

### Android
```bash
# View certificate information
keytool -printcert -jarfile {apk_path}

# Verify APK signature
jarsigner -verify -verbose -certs {apk_path}
```

### iOS
```bash
# Check code signing
codesign -v --deep --strict {app_path}

# View provisioning profile
security cms -D -i {embedded.mobileprovision_path}
```

## 4. Hardcoded Secret Detection

### String Extraction
```bash
# Extract all strings from binary
strings {binary_path} > strings_output.txt

# Search for API keys and secrets
grep -E "(API_KEY|api_key|SECRET|secret|PASSWORD|password|TOKEN|token)" strings_output.txt

# Search for AWS credentials
grep -E "(AKIA|ASIA)[0-9A-Z]{16,}" strings_output.txt
```

### Common Secret Patterns
- AWS Access Keys: `AKIA...` or `ASIA...` (20 characters)
- GitHub Tokens: `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`
- Generic API Keys: Various formats depending on service
- Private Keys: `-----BEGIN PRIVATE KEY-----`
- JWT Tokens: Three base64-encoded parts separated by dots

## 5. Insecure Storage Identification

### Android
```bash
# Check for SharedPreferences usage
grep -r "SharedPreferences" smali/ 2>/dev/null

# Check for file-based storage
grep -r "FileOutputStream\|FileInputStream\|openFileOutput\|openFileInput" smali/ 2>/dev/null

# Check for SQLite database
grep -r "SQLiteDatabase\|SQLiteOpenHelper" smali/ 2>/dev/null
```

### iOS
```bash
# Check for UserDefaults
strings {binary_path} | grep -i "UserDefaults"

# Check for Keychain usage
strings {binary_path} | grep -i "Keychain"

# Check for plist storage
find {app_path} -name "*.plist" -type f
```

## 6. Network Security Configuration Analysis

### Android
```bash
# Check for cleartext traffic
grep -r "android:usesCleartextTraffic" AndroidManifest.xml

# Check for network security config
cat app/src/main/res/xml/network_security_config.xml 2>/dev/null
```

### iOS
```bash
# Check ATS (App Transport Security) settings
plutil -p {app_path}/Info.plist | grep -A 10 "NSAppTransportSecurity"
```

## 7. Third-Party Library Vulnerability Scanning

### Library Identification
```bash
# List all JAR files in APK
unzip -l {apk_path} | grep "\.jar$"

# Check for known vulnerable libraries
grep -r "org.apache.commons\|com.google.gson\|com.fasterxml.jackson" smali/ 2>/dev/null
```

### Version Checking
- Use OWASP Dependency-Check for vulnerability scanning
- Use mobsfscan for mobile-specific vulnerability detection
- Check CVE databases for known vulnerabilities

## 8. WebView Security Checks

### Android
```bash
# Check for JavaScript enabled
grep -r "setJavaScriptEnabled(true)" smali/ 2>/dev/null

# Check for DOM storage enabled
grep -r "setDomStorageEnabled(true)" smali/ 2>/dev/null

# Check for addJavascriptInterface
grep -r "addJavascriptInterface" smali/ 2>/dev/null
```

## 9. Deep Link Analysis

### Android
```bash
# Check for intent filters in manifest
grep -A 5 "intent-filter" AndroidManifest.xml

# Check for deep link schemes
grep -o '<data android:scheme="[^"]*"' AndroidManifest.xml
```

### iOS
```bash
# Check for URL schemes in Info.plist
plutil -p Info.plist | grep -A 5 "CFBundleURLTypes\|URL Schemes"
```

## 10. Mobile-Specific Security Checks

### Android
- Check for `android:debuggable="true"` in manifest
- Check for `android:allowBackup="true"`
- Check for exported components (activities, services, receivers, providers)
- Check for insufficient permissions on content providers

### iOS
- Check for jailbreak detection bypass
- Check for debug mode enabled
- Check for iTunes backup prevention
- Check for sensitive data in logs

## Tools Summary

| Tool | Purpose | Required |
|------|---------|----------|
| `apktool` | APK decompilation and resource extraction | ✅ |
| `dex2jar` | DEX to JAR conversion for Java analysis | ✅ |
| `jadx` | APK decompilation to Java source | ✅ |
| `aapt` | Android Asset Packaging Tool | ✅ |
| `keytool` | Keystore and certificate analysis | ✅ |
| `jarsigner` | JAR signature verification | ✅ |
| `strings` | Binary string extraction | ✅ |
| `grep` | Pattern matching | ✅ |
| `openssl` | Cryptographic operations | ✅ |
| `yara` | Pattern matching for malware detection | ❌ |
| `mobsf` | Mobile Security Framework | ❌ |
| `frida` | Dynamic instrumentation | ❌ |
| `objection` | Runtime mobile exploration | ❌ |
