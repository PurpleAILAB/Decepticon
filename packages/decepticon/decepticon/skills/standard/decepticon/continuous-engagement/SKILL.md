---
name: continuous-engagement
description: "Continuous security engagement lifecycle — persistent purple-team operations with rolling objective cycles, automated re-testing, regression detection, remediation verification, and trend analysis across engagement iterations."
allowed-tools: Bash Read Write
metadata:
  subdomain: orchestration
  when_to_use: "continuous engagement, persistent engagement, rolling assessment, re-test, remediation verification, regression testing, purple team continuous, ongoing assessment, retesting, continuous pentest, breach simulation continuous"
  tags: "continuous, engagement, lifecycle, purple-team, regression, remediation-verification, re-test, trend-analysis"
  upstream_ref: "Decepticon continuous engagement orchestration — lifecycle management, no direct attack technique"
---

# Continuous Engagement Lifecycle

Manage persistent purple-team engagements that run on rolling cycles rather than point-in-time assessments. Each cycle inherits findings, objectives, and coverage data from previous iterations, enabling remediation verification, regression detection, and security posture trending.

## Lifecycle Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Continuous Engagement                      │
│                                                              │
│   Cycle 1          Cycle 2          Cycle 3        ...       │
│  ┌──────┐        ┌──────┐        ┌──────┐                   │
│  │ Plan │───────>│ Plan │───────>│ Plan │                   │
│  │ Exec │ delta  │ Exec │ delta  │ Exec │                   │
│  │ Rep  │───────>│ Rep  │───────>│ Rep  │                   │
│  └──────┘        └──────┘        └──────┘                   │
│     │               │               │                        │
│     └── findings ──>├── verify ────>├── trend ──> dashboard  │
└──────────────────────────────────────────────────────────────┘
```

## 1. Cycle Structure

Each engagement cycle follows the same phases with inherited context:

```json
{
  "engagement_id": "ENG-2025-001",
  "cycle": 3,
  "cycle_start": "2025-03-01",
  "cycle_end": "2025-03-31",
  "inherited_findings": 12,
  "new_objectives": 5,
  "retest_objectives": 8,
  "status": "active",
  "phases": [
    {"name": "planning", "status": "complete"},
    {"name": "retest_remediation", "status": "in_progress"},
    {"name": "new_attack_paths", "status": "pending"},
    {"name": "detection_validation", "status": "pending"},
    {"name": "reporting", "status": "pending"}
  ]
}
```

### Phase 1: Planning (Inherited Context)

```bash
# Load previous cycle results
python3 << 'PYEOF'
import json, os, glob

engagement_dir = '/workspace/engagements'
current_cycle = int(os.environ.get('CYCLE_NUMBER', '1'))

# Load previous cycle findings
prev_findings = []
prev_dir = f'{engagement_dir}/cycle-{current_cycle - 1}'
if os.path.exists(prev_dir):
    for fpath in glob.glob(f'{prev_dir}/findings/*.md'):
        prev_findings.append(fpath)

# Load remediation status
remediation_file = f'{prev_dir}/remediation_status.json'
if os.path.exists(remediation_file):
    with open(remediation_file) as f:
        remediation = json.load(f)
    retest_needed = [f for f in remediation if f['status'] in ('remediated', 'partial')]
    still_open = [f for f in remediation if f['status'] == 'open']
    print(f"[+] Previous cycle: {len(prev_findings)} findings")
    print(f"    Retest needed: {len(retest_needed)}")
    print(f"    Still open:    {len(still_open)}")

# Initialize current cycle
cycle_dir = f'{engagement_dir}/cycle-{current_cycle}'
os.makedirs(f'{cycle_dir}/findings', exist_ok=True)
os.makedirs(f'{cycle_dir}/evidence', exist_ok=True)

print(f"[+] Cycle {current_cycle} initialized → {cycle_dir}")
PYEOF
```

### Phase 2: Remediation Verification

```bash
# Re-test previously reported findings
python3 << 'PYEOF'
import json, os
from datetime import datetime, timezone

engagement_dir = '/workspace/engagements'
current_cycle = int(os.environ.get('CYCLE_NUMBER', '1'))
prev_dir = f'{engagement_dir}/cycle-{current_cycle - 1}'
curr_dir = f'{engagement_dir}/cycle-{current_cycle}'

with open(f'{prev_dir}/remediation_status.json') as f:
    remediation = json.load(f)

retest_results = []
for finding in remediation:
    if finding['status'] not in ('remediated', 'partial'):
        continue

    result = {
        'finding_id': finding['id'],
        'title': finding['title'],
        'original_severity': finding['severity'],
        'retest_date': datetime.now(timezone.utc).isoformat(),
        'retest_result': None,  # Set after manual/automated retest
        'evidence_path': None,
        'notes': ''
    }
    retest_results.append(result)

with open(f'{curr_dir}/retest_queue.json', 'w') as f:
    json.dump(retest_results, f, indent=2)

print(f"[+] Retest queue: {len(retest_results)} findings to verify")
PYEOF
```

### Retest Result States

| Result | Meaning | Action |
|---|---|---|
| `fixed` | Vulnerability fully remediated | Close finding, update trend |
| `partial` | Risk reduced but not eliminated | Update severity, keep open |
| `regression` | Previously fixed, now broken again | Escalate, flag in report |
| `still_open` | No remediation applied | Re-report with updated evidence |
| `wontfix` | Client accepted risk | Document risk acceptance |

### Phase 3: New Attack Path Exploration

```bash
# Identify coverage gaps from previous cycles
python3 << 'PYEOF'
import json, os

engagement_dir = '/workspace/engagements'
current_cycle = int(os.environ.get('CYCLE_NUMBER', '1'))

# Load cumulative coverage map
coverage_file = f'{engagement_dir}/coverage_map.json'
try:
    with open(coverage_file) as f:
        coverage = json.load(f)
except FileNotFoundError:
    coverage = {'techniques_tested': [], 'assets_tested': [], 'attack_paths': []}

# MITRE ATT&CK techniques NOT yet tested
ALL_RELEVANT_TECHNIQUES = [
    'T1190', 'T1566', 'T1078', 'T1059', 'T1053', 'T1547',
    'T1021', 'T1048', 'T1071', 'T1486', 'T1003', 'T1055',
]
tested = set(coverage.get('techniques_tested', []))
untested = [t for t in ALL_RELEVANT_TECHNIQUES if t not in tested]

print(f"[+] Coverage: {len(tested)}/{len(ALL_RELEVANT_TECHNIQUES)} techniques tested")
print(f"    Untested: {', '.join(untested)}")
print(f"    → Prioritize these in cycle {current_cycle}")
PYEOF
```

### Phase 4: Detection Validation

```bash
# Replay attack techniques and verify detection
python3 << 'PYEOF'
import json, os
from datetime import datetime, timezone

curr_dir = f'/workspace/engagements/cycle-{os.environ.get("CYCLE_NUMBER", "1")}'

detection_tests = []

# For each technique executed this cycle, check if SIEM/EDR detected it
# This is populated during execution phase
test_template = {
    'technique': 'T1059.001',
    'description': 'Encoded PowerShell execution',
    'executed_at': None,
    'detected': None,           # True/False
    'detection_time_seconds': None,
    'detection_source': None,   # 'EDR', 'SIEM', 'NDR', 'manual'
    'alert_id': None,
    'gap': None                 # Description if not detected
}

detection_tests.append(test_template)

with open(f'{curr_dir}/detection_validation.json', 'w') as f:
    json.dump(detection_tests, f, indent=2)

print(f"[+] Detection validation template → {curr_dir}/detection_validation.json")
PYEOF
```

## 2. Trend Analysis

### Cross-Cycle Metrics

```bash
python3 << 'PYEOF'
import json, os, glob

engagement_dir = '/workspace/engagements'
metrics = []

for cycle_dir in sorted(glob.glob(f'{engagement_dir}/cycle-*')):
    cycle_num = int(os.path.basename(cycle_dir).split('-')[1])

    findings_count = len(glob.glob(f'{cycle_dir}/findings/*.md'))

    # Load retest results if available
    retest_file = f'{cycle_dir}/retest_results.json'
    fixed = 0
    regressions = 0
    if os.path.exists(retest_file):
        with open(retest_file) as f:
            retests = json.load(f)
        fixed = sum(1 for r in retests if r.get('retest_result') == 'fixed')
        regressions = sum(1 for r in retests if r.get('retest_result') == 'regression')

    # Load detection validation
    det_file = f'{cycle_dir}/detection_validation.json'
    det_rate = 0.0
    if os.path.exists(det_file):
        with open(det_file) as f:
            det_tests = json.load(f)
        detected = sum(1 for d in det_tests if d.get('detected'))
        det_rate = detected / len(det_tests) if det_tests else 0.0

    metrics.append({
        'cycle': cycle_num,
        'total_findings': findings_count,
        'remediated': fixed,
        'regressions': regressions,
        'detection_rate': round(det_rate * 100, 1),
    })

# Output trend report
print("=" * 65)
print(f"{'Cycle':>6} {'Findings':>10} {'Fixed':>8} {'Regress':>9} {'Det Rate':>10}")
print("-" * 65)
for m in metrics:
    print(f"{m['cycle']:>6} {m['total_findings']:>10} {m['remediated']:>8} "
          f"{m['regressions']:>9} {m['detection_rate']:>9}%")
print("=" * 65)

with open(f'{engagement_dir}/trend_report.json', 'w') as f:
    json.dump(metrics, f, indent=2)
PYEOF
```

### Key Performance Indicators

| KPI | Target | Measurement |
|---|---|---|
| Mean time to remediate (MTTR) | < 30 days for Critical | Days from report → verified fix |
| Remediation rate | > 80% per cycle | Fixed findings / total reported |
| Regression rate | < 5% | Re-broken / previously fixed |
| Detection coverage | > 70% | Detected techniques / executed |
| Mean time to detect (MTTD) | < 1 hour | Alert time − execution time |
| Attack surface reduction | Trending down | New unique findings per cycle |

## 3. Regression Detection

```bash
# Automated regression check — re-run previous finding test cases
python3 << 'PYEOF'
import json, os

engagement_dir = '/workspace/engagements'
current_cycle = int(os.environ.get('CYCLE_NUMBER', '1'))

# Load all "fixed" findings from all previous cycles
fixed_findings = []
for i in range(1, current_cycle):
    retest_file = f'{engagement_dir}/cycle-{i}/retest_results.json'
    if os.path.exists(retest_file):
        with open(retest_file) as f:
            retests = json.load(f)
        for r in retests:
            if r.get('retest_result') == 'fixed':
                fixed_findings.append(r)

print(f"[+] {len(fixed_findings)} previously fixed findings to regression-check")

# Generate regression test queue
regression_queue = []
for finding in fixed_findings:
    regression_queue.append({
        'finding_id': finding['finding_id'],
        'title': finding['title'],
        'originally_fixed_in': f"cycle-{finding.get('cycle', 'unknown')}",
        'regression_test_result': None,  # Fill during execution
    })

curr_dir = f'{engagement_dir}/cycle-{current_cycle}'
with open(f'{curr_dir}/regression_queue.json', 'w') as f:
    json.dump(regression_queue, f, indent=2)

print(f"[+] Regression queue → {curr_dir}/regression_queue.json")
PYEOF
```

## 4. Engagement State Persistence

```json
{
  "engagement_id": "ENG-2025-001",
  "client": "Acme Corp",
  "start_date": "2025-01-01",
  "cadence": "monthly",
  "current_cycle": 3,
  "total_unique_findings": 47,
  "findings_fixed": 31,
  "findings_open": 12,
  "findings_accepted_risk": 4,
  "regressions_detected": 3,
  "coverage": {
    "techniques_tested": 18,
    "techniques_total": 25,
    "assets_tested": 142,
    "assets_total": 210
  },
  "next_cycle_focus": [
    "Cloud infrastructure (AWS)",
    "API security (new microservices)",
    "Retest 4 open critical findings"
  ]
}
```

## 5. Cycle Handoff Report

Each cycle produces a delta report showing what changed:

```markdown
# Cycle N → Cycle N+1 Handoff

## Remediation Status
- **Fixed this cycle**: N findings
- **Still open**: N findings (list with owners)
- **Regressions detected**: N (ESCALATE)
- **New findings**: N

## Coverage Delta
- **New techniques tested**: T1053, T1547
- **New assets in scope**: [list]
- **Remaining coverage gaps**: [list]

## Detection Improvements
- **Detection rate**: X% → Y% (Δ +Z%)
- **New rules deployed**: N Sigma rules
- **Mean detection time**: Xh → Yh

## Recommendations for Next Cycle
1. [Specific focus area]
2. [Specific focus area]
3. [Retest priorities]
```

## 6. Quality Checklist

- [ ] Previous cycle findings imported and tracked
- [ ] All "remediated" findings have retest evidence
- [ ] Regressions flagged and escalated
- [ ] Detection validation results recorded with timestamps
- [ ] Coverage map updated with techniques tested this cycle
- [ ] Trend metrics computed and compared to previous cycles
- [ ] Handoff report generated for next cycle

## References

- PTES (Penetration Testing Execution Standard) — http://www.pentest-standard.org/
- NIST SP 800-115 — Technical Guide to Information Security Testing
- OWASP Testing Guide — https://owasp.org/www-project-web-security-testing-guide/
