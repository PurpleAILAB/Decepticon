---
name: compliance-mapping
description: "Map engagement findings to compliance frameworks — NIST CSF, NIST 800-53, PCI DSS 4.0, SOC 2, HIPAA, ISO 27001, CIS Controls v8. Generates control-gap matrices, audit-ready evidence tables, and remediation mappings for regulatory reporting."
allowed-tools: Bash Read Write
metadata:
  subdomain: analyst
  when_to_use: "compliance, nist, pci dss, soc 2, hipaa, iso 27001, cis controls, regulatory, audit, control gap, compliance mapping, framework mapping, control assessment, audit evidence"
  tags: "compliance, nist, pci-dss, soc2, hipaa, iso-27001, cis-controls, audit, regulatory, governance"
  mitre_attack: "T1190, T1078, T1059"
---

# Compliance Mapping

Map engagement findings to regulatory and compliance frameworks. Produce control-gap matrices that show which controls failed, what evidence proves it, and what remediation satisfies the control requirement.

## Quick Reference

```bash
# Generate compliance mapping from findings
python3 << 'PYEOF'
import yaml, json, os, glob

findings_dir = '/workspace/findings'
output_dir = '/workspace/compliance'
os.makedirs(output_dir, exist_ok=True)

findings = []
for fpath in glob.glob(f'{findings_dir}/*.md'):
    with open(fpath) as f:
        content = f.read()
        if content.startswith('---'):
            fm = content.split('---', 2)[1]
            finding = yaml.safe_load(fm)
            finding['_file'] = os.path.basename(fpath)
            findings.append(finding)

print(f"[+] Loaded {len(findings)} findings for compliance mapping")

with open(f'{output_dir}/findings_metadata.json', 'w') as f:
    json.dump(findings, f, indent=2, default=str)
PYEOF
```

## 1. Framework Cross-Reference Matrix

### Finding → Control Mapping

```python
# Master mapping: MITRE ATT&CK technique → compliance controls
TECHNIQUE_TO_CONTROLS = {
    'T1190': {  # Exploit Public-Facing Application
        'NIST_CSF': ['PR.IP-12', 'DE.CM-8'],
        'NIST_800_53': ['SI-2', 'SI-5', 'RA-5'],
        'PCI_DSS_4': ['6.3.3', '6.4.1', '11.3.1'],
        'SOC2': ['CC7.1', 'CC8.1'],
        'HIPAA': ['164.312(a)(1)', '164.312(e)(1)'],
        'ISO_27001': ['A.12.6.1', 'A.14.2.1'],
        'CIS_V8': ['7.1', '7.2', '7.4', '16.1'],
    },
    'T1078': {  # Valid Accounts
        'NIST_CSF': ['PR.AC-1', 'PR.AC-4', 'PR.AC-7'],
        'NIST_800_53': ['IA-2', 'IA-5', 'AC-2', 'AC-6'],
        'PCI_DSS_4': ['7.2.1', '7.2.2', '8.3.1', '8.3.6'],
        'SOC2': ['CC6.1', 'CC6.2', 'CC6.3'],
        'HIPAA': ['164.312(a)(1)', '164.312(d)'],
        'ISO_27001': ['A.9.2.1', 'A.9.2.3', 'A.9.4.3'],
        'CIS_V8': ['5.2', '5.3', '5.4', '6.1', '6.2'],
    },
    'T1059': {  # Command and Scripting Interpreter
        'NIST_CSF': ['PR.IP-1', 'DE.CM-5'],
        'NIST_800_53': ['CM-7', 'SI-3', 'SI-4'],
        'PCI_DSS_4': ['5.3.1', '5.3.2', '11.5.1'],
        'SOC2': ['CC6.8', 'CC7.2'],
        'HIPAA': ['164.312(a)(1)', '164.312(e)(2)(ii)'],
        'ISO_27001': ['A.12.2.1', 'A.12.5.1'],
        'CIS_V8': ['2.5', '2.6', '10.1', '10.2'],
    },
    'T1486': {  # Data Encrypted for Impact
        'NIST_CSF': ['PR.DS-1', 'PR.IP-4', 'RC.RP-1'],
        'NIST_800_53': ['CP-9', 'CP-10', 'IR-4', 'SI-4'],
        'PCI_DSS_4': ['3.5.1', '12.10.1'],
        'SOC2': ['CC7.3', 'CC7.4', 'CC7.5'],
        'HIPAA': ['164.308(a)(7)', '164.312(a)(2)(iv)'],
        'ISO_27001': ['A.12.3.1', 'A.17.1.1'],
        'CIS_V8': ['11.1', '11.2', '11.4'],
    },
    'T1071': {  # Application Layer Protocol (C2)
        'NIST_CSF': ['DE.CM-1', 'DE.AE-1'],
        'NIST_800_53': ['SC-7', 'SI-4', 'AC-4'],
        'PCI_DSS_4': ['1.3.1', '1.3.2', '11.4.1'],
        'SOC2': ['CC6.6', 'CC7.2'],
        'HIPAA': ['164.312(e)(1)'],
        'ISO_27001': ['A.13.1.1', 'A.13.1.3'],
        'CIS_V8': ['9.2', '9.3', '13.3', '13.8'],
    },
    'T1053': {  # Scheduled Task/Job
        'NIST_CSF': ['PR.IP-1', 'DE.CM-3'],
        'NIST_800_53': ['CM-7', 'AU-2', 'SI-4'],
        'PCI_DSS_4': ['2.2.5', '10.2.1'],
        'SOC2': ['CC6.1', 'CC7.2'],
        'HIPAA': ['164.312(b)'],
        'ISO_27001': ['A.12.1.2', 'A.12.4.1'],
        'CIS_V8': ['4.1', '8.2', '8.5'],
    },
}
```

## 2. NIST Cybersecurity Framework (CSF) Mapping

### Output Format

```markdown
## NIST CSF Control Gap Analysis

| CSF Function | Category | Subcategory | Finding | Gap | Remediation |
|---|---|---|---|---|---|
| PROTECT | Access Control | PR.AC-1 | Weak password policy | MFA not enforced on VPN | Deploy MFA for all remote access |
| PROTECT | Info Protection | PR.IP-12 | Unpatched Apache | CVE-2024-XXXX exploited | Patch within 30 days, deploy WAF |
| DETECT | Anomalies | DE.AE-1 | No C2 detection | Beacon traffic undetected for 72h | Deploy network detection rules |
| DETECT | Monitoring | DE.CM-1 | No egress filtering | Data exfiltration via DNS | Implement DNS monitoring and filtering |
```

### CSF Function Descriptions

| Function | Purpose | Relevant Finding Types |
|---|---|---|
| **IDENTIFY** (ID) | Asset management, risk assessment | Scope, asset inventory gaps |
| **PROTECT** (PR) | Access control, awareness, data security | Auth bypass, missing encryption, unpatched |
| **DETECT** (DE) | Anomaly detection, monitoring | Undetected C2, missing alerts, blind spots |
| **RESPOND** (RS) | Response planning, communications | IR process gaps, no playbooks |
| **RECOVER** (RC) | Recovery planning, improvements | Backup gaps, no DR testing |

## 3. PCI DSS 4.0 Mapping

```markdown
## PCI DSS 4.0 Control Gap Analysis

| Requirement | Control | Finding | Status | Evidence | Remediation |
|---|---|---|---|---|---|
| 1.3.1 | Restrict inbound traffic | No DMZ segmentation | FAIL | Network diagram + scan results | Implement proper network segmentation |
| 6.3.3 | Patch critical vulns in 30 days | CVE-2024-XXXX unpatched | FAIL | Vulnerability scan dated [date] | Apply patch, verify with rescan |
| 8.3.6 | MFA for all admin access | Admin portal lacks MFA | FAIL | Screenshot of login page | Implement TOTP/FIDO2 MFA |
| 10.2.1 | Log all access to cardholder data | Incomplete logging | FAIL | Audit log review | Enable comprehensive audit logging |
| 11.3.1 | Internal vulnerability scanning | No regular scanning | FAIL | Interview with IT team | Deploy authenticated vulnerability scanning |
```

### PCI DSS Penalty Context

```python
PENALTY_CONTEXT = {
    'non_compliance_fines': '$5,000 - $100,000 per month',
    'breach_cost_avg': '$4.45M (IBM 2023 Cost of Data Breach)',
    'card_brand_penalties': {
        'Visa': 'VFIP: $25,000-$500,000 per incident',
        'Mastercard': 'SDC: varies by merchant level',
    },
    'loss_of_processing': 'Card brands may revoke processing ability',
}
```

## 4. SOC 2 (Trust Service Criteria) Mapping

```markdown
## SOC 2 Control Gap Analysis

| Criteria | Control | Finding | Test Result | Gap Description |
|---|---|---|---|---|
| CC6.1 | Logical access security | Default credentials on admin panel | FAIL | Default admin:admin on management interface |
| CC6.3 | Access removal for terminated users | Ex-employee VPN access active | FAIL | Account active 6 months post-termination |
| CC7.1 | Detection of unauthorized changes | No file integrity monitoring | FAIL | Webshell persisted undetected for 48h |
| CC7.2 | Monitoring system components | No IDS/IPS on internal network | FAIL | Lateral movement undetected |
| CC8.1 | Change management | Patches not tested before deployment | FAIL | No staging environment for patches |
```

## 5. HIPAA Mapping (Healthcare)

```markdown
## HIPAA Security Rule Control Gap Analysis

| Rule Section | Standard | Finding | Status | PHI Risk |
|---|---|---|---|---|
| 164.312(a)(1) | Access Control | SQL injection to patient DB | FAIL | Direct PHI exposure |
| 164.312(d) | Person Authentication | No MFA on EHR system | FAIL | Unauthorized PHI access |
| 164.312(e)(1) | Transmission Security | Unencrypted API transmitting PHI | FAIL | PHI interception risk |
| 164.308(a)(7) | Contingency Plan | No tested backup for EHR DB | FAIL | PHI availability risk |
| 164.312(b) | Audit Controls | Insufficient access logging | FAIL | Cannot detect unauthorized access |
```

## 6. Automated Gap Matrix Generation

```bash
python3 << 'PYEOF'
import json, yaml, glob, os

FRAMEWORK_MAP = {
    'T1190': {'NIST_800_53': ['SI-2','RA-5'], 'PCI_DSS_4': ['6.3.3','11.3.1'], 'CIS_V8': ['7.1','7.4']},
    'T1078': {'NIST_800_53': ['IA-2','AC-2','AC-6'], 'PCI_DSS_4': ['7.2.1','8.3.1','8.3.6'], 'CIS_V8': ['5.2','6.1']},
    'T1059': {'NIST_800_53': ['CM-7','SI-3'], 'PCI_DSS_4': ['5.3.1','11.5.1'], 'CIS_V8': ['2.5','10.1']},
}

findings = []
for fpath in glob.glob('/workspace/findings/*.md'):
    with open(fpath) as f:
        content = f.read()
        if content.startswith('---'):
            fm = content.split('---', 2)[1]
            findings.append(yaml.safe_load(fm))

gap_matrix = []
for finding in findings:
    techniques = finding.get('mitre_attack', [])
    if isinstance(techniques, str):
        techniques = [t.strip() for t in techniques.split(',')]

    for tech in techniques:
        controls = FRAMEWORK_MAP.get(tech, {})
        for framework, control_ids in controls.items():
            for ctrl in control_ids:
                gap_matrix.append({
                    'finding': finding.get('title', 'Unknown'),
                    'severity': finding.get('severity', 'medium'),
                    'mitre_technique': tech,
                    'framework': framework,
                    'control_id': ctrl,
                    'status': 'FAIL',
                })

os.makedirs('/workspace/compliance', exist_ok=True)
with open('/workspace/compliance/gap_matrix.json', 'w') as f:
    json.dump(gap_matrix, f, indent=2)

# Generate CSV for spreadsheet import
import csv
with open('/workspace/compliance/gap_matrix.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['finding','severity','mitre_technique','framework','control_id','status'])
    writer.writeheader()
    writer.writerows(gap_matrix)

print(f"[+] Generated gap matrix: {len(gap_matrix)} control gaps across {len(findings)} findings")
print(f"    → /workspace/compliance/gap_matrix.json")
print(f"    → /workspace/compliance/gap_matrix.csv")
PYEOF
```

## 7. Quality Checklist

- [ ] Every finding maps to at least one compliance framework control
- [ ] Control IDs are correct for the framework version cited
- [ ] Gap descriptions are specific (not "non-compliant" — say what's wrong)
- [ ] Remediation actions map back to specific control requirements
- [ ] Evidence references point to actual engagement artifacts
- [ ] Framework version noted (PCI DSS **4.0**, NIST 800-53 **Rev 5**, CIS **v8**)

## References

- NIST CSF — https://www.nist.gov/cyberframework
- NIST SP 800-53 Rev 5 — https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
- PCI DSS 4.0 — https://www.pcisecuritystandards.org/document_library/
- SOC 2 Trust Service Criteria — https://www.aicpa.org/
- HIPAA Security Rule — https://www.hhs.gov/hipaa/
- ISO/IEC 27001:2022 — https://www.iso.org/standard/27001
- CIS Controls v8 — https://www.cisecurity.org/controls/v8
