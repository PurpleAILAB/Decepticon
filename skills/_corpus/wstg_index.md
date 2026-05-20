# OWASP Web Security Testing Guide — Index

Vendored at `skills/_corpus/wstg/` (submodule, OWASP/wstg, CC-BY-SA 4.0).

The WSTG is the canonical web-app pentest methodology. **142 test cases**
across 13 categories, each with a unique `WSTG-XXX-NN` identifier and
structured sections: Summary / Test Objectives / How to Test / Remediation /
References.

Decepticon agents cite WSTG test IDs when reporting findings — gives
report consumers (bug-bounty triagers, internal security reviewers) a
shared methodology vocabulary.

## Category map

| Category | Prefix | Path |
|---|---|---|
| Information Gathering | WSTG-INFO | `wstg/document/4-Web_Application_Security_Testing/01-Information_Gathering/` |
| Configuration & Deployment Mgmt | WSTG-CONF | `02-Configuration_and_Deployment_Management_Testing/` |
| Identity Management | WSTG-IDNT | `03-Identity_Management_Testing/` |
| Authentication | WSTG-ATHN | `04-Authentication_Testing/` |
| Authorization | WSTG-ATHZ | `05-Authorization_Testing/` |
| Session Management | WSTG-SESS | `06-Session_Management_Testing/` |
| Input Validation | WSTG-INPV | `07-Input_Validation_Testing/` |
| Error Handling | WSTG-ERRH | `08-Testing_for_Error_Handling/` |
| Weak Cryptography | WSTG-CRYP | `09-Testing_for_Weak_Cryptography/` |
| Business Logic | WSTG-BUSL | `10-Business_Logic_Testing/` |
| Client-side | WSTG-CLNT | `11-Client-side_Testing/` |
| API Testing | WSTG-APIT | `12-API_Testing/` |

## High-frequency cross-references to Decepticon skills

| WSTG-ID | Skill |
|---|---|
| WSTG-ATHN-01..10 | `skills/exploit/web/oauth/`, `skills/exploit/web/jwt/`, `skills/exploit/web/saml/` |
| WSTG-ATHZ-01..05 | `skills/_corpus/payloads/Account Takeover/` + `skills/exploit/web/ato-methodology/` |
| WSTG-SESS-01..09 | `skills/exploit/web/oauth/`, `skills/exploit/web/jwt/` |
| WSTG-INPV-01..19 | `skills/exploit/web/xss.md`, `sqli.md`, `ssrf.md`, `ssti.md`, `xxe.md`, `lfi.md`, `nosqli/`, `ldapi/`, `xpath-xslt/`, `crlf.md`, `command-injection.md` |
| WSTG-CRYP-01..04 | `skills/exploit/crypto/SKILL.md`, `skills/exploit/web/jwt/` |
| WSTG-BUSL-01..09 | `skills/analyst/bounty-hunting/`, `skills/analyst/auth-bypass/` |
| WSTG-CLNT-01..15 | `skills/exploit/web/xss.md`, `dom-clobbering/`, `xs-leaks/`, `open-redirect/` |
| WSTG-APIT-01..04 | `skills/exploit/web/graphql.md`, `skills/exploit/web/mass-assignment/` |

## Usage protocol

1. Agent identifies a vuln class during exploit phase
2. Map class → WSTG-XXX-NN via the cross-reference table or by reading
   the WSTG document directly via `load_skill("/skills/_corpus/wstg/document/.../WSTG-XXX-NN.md")`
3. Cite the WSTG-ID in the finding report:
   > Maps to **WSTG-INPV-05 — Testing for SQL Injection** (OWASP WSTG v4.2)
4. Use WSTG's "How to Test" steps as a methodology checklist if the
   Decepticon skill is insufficiently detailed

## Refresh

```bash
git submodule update --remote skills/_corpus/wstg
```

WSTG is on its v5.0 development cycle; current master pin is v4.2-stable
content. Reasonable refresh cadence: quarterly.

## License

CC-BY-SA 4.0. Attribution preserved in the submodule's `LICENSE.md` +
`CITATION.cff`. Decepticon may redistribute + adapt with attribution.
Added to `THIRD_PARTY_LICENSES.md` (when PR #242 merges).
