---
name: web-auth-mapping
description: "Authentication surface — login endpoints, JWT/OAuth/SAML/SSO/API-key mechanism identification."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "auth surface, login endpoints, JWT, OAuth, SAML, SSO, API key, authentication mechanism"
  tags: auth-mapping
  mitre_attack: T1589.001
---

# Authentication Surface Mapping

Map every authentication mechanism the target exposes. Exploit downstream needs to know exactly how to hold a session (cookie, JWT, API key) and where to attack auth (token theft, race-condition on bcrypt, SSO redirect chain).

## 1. Login Endpoint Discovery

```bash
# Common auth paths
for path in login signin auth authenticate oauth/authorize \
    api/auth api/login admin/login wp-login.php; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://<target>/$path")
    [ "$code" != "404" ] && echo "$code https://<target>/$path"
done
```

## 2. Auth Mechanism Identification

| Mechanism | Signal |
|-----------|--------|
| Cookie-based | `Set-Cookie` headers after login (often `session=`, `JSESSIONID=`, `PHPSESSID=`) |
| JWT | `Authorization: Bearer eyJ...` patterns; three base64 segments separated by `.` |
| OAuth 2.0 | `/oauth/authorize`, `/oauth/token` endpoints; `state`/`code`/`redirect_uri` params |
| API Key | `X-API-Key` header accepted; `Authorization: ApiKey <token>` |
| SAML/SSO | Redirects to IdP (Okta, Azure AD, Auth0); `SAMLRequest` form param |
| Session row + slow KDF | Login latency >50ms on wrong password (bcrypt/Argon2) — flag for race-condition recon |

## 3. Output for Handoff

Record per mechanism: endpoint, success/fail signals (status code, cookie set, JSON shape), credentials used, observed latency. This feeds the **Required session state** line in the recon → exploit handoff.
