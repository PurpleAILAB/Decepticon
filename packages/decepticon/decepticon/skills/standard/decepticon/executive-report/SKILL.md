---
name: executive-report
description: "Executive-level engagement report — translates technical findings into business-risk language for C-suite and board audiences. Covers risk scoring, business impact quantification, remediation prioritization, and presentation-ready output."
allowed-tools: Read Write
metadata:
  subdomain: orchestration
  when_to_use: "executive report, executive summary, board report, ciso report, business risk, risk score, business impact, c-suite report, non-technical report, management report, risk quantification"
  tags: "executive, report, business-risk, c-suite, board, remediation, risk-quantification"
  upstream_ref: "Decepticon executive report template — business-risk translation, no direct attack technique"
---

# Executive Report Generation

Generate executive-level engagement reports that translate technical findings into business-risk language. The audience is C-suite, board members, and non-technical stakeholders who need to understand impact and make resource allocation decisions.

## Report Generation Workflow

```
1. Read all findings/*.md            (parse YAML frontmatter)
2. Read plan/roe.json                (engagement scope and constraints)
3. Read plan/conops.json             (engagement concept of operations)
4. Read plan/opplan.json             (objective status)
5. Score each finding by business risk
6. Generate report/executive-report.md
7. Generate report/executive-slides.md  (presentation-ready format)
```

### Step 1: Initialize Output

```
bash(command="mkdir -p /workspace/report")
```

## 1. Report Structure

```markdown
# Security Assessment — Executive Report

**Client**: [Organization Name]
**Assessment Period**: [Start Date] — [End Date]
**Classification**: [TLP:RED / TLP:AMBER / Client Confidential]
**Report Date**: [YYYY-MM-DD]
**Prepared By**: [Assessment Team]

---

## Overall Risk Rating

[CRITICAL / HIGH / MODERATE / LOW]

[1-paragraph summary: what was tested, what was found, what it means for the business]

---

## Key Findings Summary

| # | Finding | Business Risk | Likelihood | Impact | Priority |
|---|---------|---------------|------------|--------|----------|
| 1 | [Title] | Critical | High | Critical | Immediate |
| 2 | [Title] | High | Medium | High | 30 days |
| 3 | [Title] | Medium | Medium | Medium | 90 days |

---

## Business Impact Analysis

### Finding 1: [Title]

**What happened**: [Plain-language description — no jargon]
**Business impact**: [Revenue, reputation, regulatory, operational]
**Who is affected**: [Customers, employees, partners, regulators]
**Remediation**: [Action, owner, timeline]
**Investment required**: [Estimated effort: hours/days, cost tier]

---

## Attack Path Narrative

[Tell the story of how an attacker could move from initial access
to the crown jewels. Use business language — "customer database"
not "PostgreSQL instance on 10.0.3.42".]

---

## Remediation Roadmap

### Immediate (0–30 days)
- [ ] [Action item with owner]

### Short-term (30–90 days)
- [ ] [Action item with owner]

### Strategic (90+ days)
- [ ] [Action item with owner]

---

## Metrics

| Metric | Value |
|--------|-------|
| Total findings | N |
| Critical | N |
| High | N |
| Medium | N |
| Low | N |
| Mean time to initial access | X hours |
| Systems compromised | N of M tested |
| Data access achieved | [Description] |
```

## 2. Business Risk Scoring

### Risk Matrix

```
              │ Negligible │   Minor   │  Moderate  │   Major   │  Severe   │
              │  Impact    │  Impact   │  Impact    │  Impact   │  Impact   │
─────────────┼────────────┼───────────┼────────────┼───────────┼───────────┤
Almost       │   Medium   │   High    │  Critical  │ Critical  │ Critical  │
Certain      │            │           │            │           │           │
─────────────┼────────────┼───────────┼────────────┼───────────┼───────────┤
Likely       │    Low     │  Medium   │    High    │ Critical  │ Critical  │
─────────────┼────────────┼───────────┼────────────┼───────────┼───────────┤
Possible     │    Low     │   Low     │  Medium    │   High    │ Critical  │
─────────────┼────────────┼───────────┼────────────┼───────────┼───────────┤
Unlikely     │    Info    │   Low     │    Low     │  Medium   │   High    │
─────────────┼────────────┼───────────┼────────────┼───────────┼───────────┤
Rare         │    Info    │   Info    │    Low     │   Low     │  Medium   │
─────────────┴────────────┴───────────┴────────────┴───────────┴───────────┘
```

### Scoring Algorithm

```python
def score_business_risk(finding: dict) -> dict:
    """Score a finding for executive reporting."""
    severity = finding.get('severity', 'medium').lower()
    exploitability = finding.get('exploitability', 'medium').lower()

    impact_map = {'critical': 5, 'high': 4, 'medium': 3, 'low': 2, 'info': 1}
    likelihood_map = {'confirmed': 5, 'high': 4, 'medium': 3, 'low': 2, 'theoretical': 1}

    impact = impact_map.get(severity, 3)
    likelihood = likelihood_map.get(exploitability, 3)
    risk_score = impact * likelihood

    if risk_score >= 20:
        rating = 'Critical'
        timeline = 'Immediate (0-7 days)'
    elif risk_score >= 12:
        rating = 'High'
        timeline = 'Urgent (7-30 days)'
    elif risk_score >= 6:
        rating = 'Medium'
        timeline = 'Planned (30-90 days)'
    else:
        rating = 'Low'
        timeline = 'Strategic (90+ days)'

    return {
        'risk_score': risk_score,
        'rating': rating,
        'remediation_timeline': timeline,
        'impact': impact,
        'likelihood': likelihood
    }
```

## 3. Language Translation Guide

Technical jargon alienates executive audiences. Translate consistently:

| Technical Term | Executive Language |
|---|---|
| SQL injection | Unauthorized database access |
| Remote code execution | Full system takeover |
| Privilege escalation | Gaining administrator access |
| Lateral movement | Spreading across internal systems |
| Data exfiltration | Unauthorized data theft |
| C2 beacon | Persistent attacker communication channel |
| Credential stuffing | Automated account takeover using stolen passwords |
| Zero-day | Previously unknown vulnerability with no available fix |
| SSRF | Internal system access from external-facing application |
| XSS | Ability to impersonate users through the website |
| Misconfigured S3 bucket | Publicly accessible cloud storage |
| Unpatched CVE | Known vulnerability without applied security update |
| Webshell | Persistent backdoor in the web application |
| Pass-the-hash | Authentication bypass using stolen credentials |

## 4. Business Impact Categories

### Revenue Impact
- Service disruption (downtime cost per hour)
- Customer churn from data breach
- Lost deals from reputation damage
- Ransomware payment or recovery cost

### Regulatory Impact
- GDPR fines (up to 4% annual global revenue)
- PCI DSS non-compliance (fines, loss of processing ability)
- HIPAA penalties ($100–$50,000 per violation)
- SEC disclosure requirements

### Operational Impact
- IT team diversion (incident response hours)
- Business process disruption
- Third-party/supply-chain notification costs
- Forensics and legal fees

### Reputational Impact
- Media coverage probability
- Customer notification requirements
- Stock price impact (public companies)
- Partner/vendor trust erosion

## 5. Presentation-Ready Format

```markdown
# Slide 1: Title
## Security Assessment Results
**[Organization] | [Date]**
Classification: [TLP]

# Slide 2: Bottom Line Up Front
- Overall risk: **[RATING]**
- [N] critical findings requiring immediate action
- Estimated business exposure: **$[X]M**
- Recommended investment: **$[Y]K** over [Z] months

# Slide 3: What We Tested
[Scope diagram — systems, applications, networks]

# Slide 4: What We Found
[Risk matrix heat map with findings plotted]

# Slide 5–N: Top Findings
[One slide per critical/high finding:
 - What: plain-language description
 - So what: business impact
 - Now what: remediation action + owner + timeline]

# Slide N+1: Remediation Roadmap
[Timeline visualization: immediate / 30-day / 90-day / strategic]

# Slide N+2: Investment Summary
[Cost-benefit: remediation cost vs. potential loss]
```

## 6. Quality Checklist

- [ ] No unexplained technical jargon
- [ ] Every finding has business impact stated
- [ ] Remediation items have owners and timelines
- [ ] Risk ratings use consistent methodology
- [ ] Report classification (TLP) on every page
- [ ] Attack narrative tells a coherent story
- [ ] Metrics section includes engagement scope numbers
- [ ] Findings sorted by business risk, not technical severity

## References

- NIST Cybersecurity Framework — https://www.nist.gov/cyberframework
- FAIR (Factor Analysis of Information Risk) — https://www.fairinstitute.org/
- OWASP Risk Rating Methodology — https://owasp.org/www-community/OWASP_Risk_Rating_Methodology
