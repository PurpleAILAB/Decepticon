---
name: engagement-lifecycle
description: "Red team engagement lifecycle management — initiation, phase transitions, go/no-go gates, deconfliction, emergency procedures, completion."
allowed-tools: Read
metadata:
  subdomain: orchestration
  when_to_use: "start engagement, new engagement, engagement status, phase transition, go/no-go, deconfliction, emergency stop, engagement complete, wrap up"
  tags: engagement, lifecycle, planning, phase-transition, deconfliction, emergency, completion
  mitre_attack: []
---

# Engagement Lifecycle Management

## Engagement Initiation

### Pre-Flight Checklist
Before starting any engagement, verify:

1. **Documents exist and are valid**:
   - [ ] `roe.json` — Rules of Engagement with scope, restrictions, contacts
   - [ ] `conops.json` — Concept of Operations with threat profile and kill chain phases
   - [ ] `deconfliction.json` — Deconfliction identifiers and procedures
   - [ ] `opplan.json` — Operational Plan with sequenced, acceptance-gated objectives
   - [ ] All documents cross-reference consistently

2. **Infrastructure ready**:
   - [ ] Docker sandbox running with required tools
   - [ ] C2 server reachable if post-exploitation is in scope: `nc -z c2-sliver 31337` (gRPC port)
   - [ ] Operator config exists: `/workspace/.sliver-configs/decepticon.cfg`
   - [ ] Output directories created (`<engagement>/recon/`, `<engagement>/exploit/`, etc.)

3. **If any document is missing**: Delegate to `soundwave` sub-agent first.

All paths below are relative to the engagement working directory (set via `cd` before commands run).

### Engagement Types and Implications

| Type | Starting Phase | Sub-Agents Used | Key Consideration |
|------|---------------|-----------------|-------------------|
| Full Scope | Planning → Recon | All (soundwave, recon, exploit, postexploit) | Longest duration, most OPSEC-sensitive |
| Assumed Breach | Exploitation | exploit, postexploit | Skip recon, start from provided foothold |
| Recon Only | Recon | recon only | No exploitation, intelligence gathering only |
| Objective-Based | Varies | Targeted subset | Focus on specific crown jewels |

Read `roe.json` to determine engagement type and adjust phase ordering accordingly.

## Phase Transitions

### Gate Checks (Go/No-Go Decisions)

Before transitioning between phases, verify the gate criteria from the `workflow` skill:

```
Planning → Recon:    roe.json + conops.json + deconfliction.json + opplan.json exist and validated
Recon → Exploit:     Attack surface identified, targets prioritized, vulns catalogued
Exploit → PostExploit: Initial foothold established, access type documented
PostExploit → Report: All OPPLAN objectives resolved (passed or blocked)
```

### Phase Transition Protocol
1. Read current phase objectives from opplan.json
2. Check: are all current-phase objectives resolved?
3. Check: does the next phase have pending objectives?
4. Verify gate criteria (consult `workflow` skill for phase-specific gates)
5. If gate passes → proceed. If not → identify what's missing and address it.

### Handling Cross-Phase Dependencies
Some objectives may uncover new targets or invalidate assumptions:
- **New targets discovered during recon** → Update opplan.json with new objectives
- **Exploit fails, need more recon** → Return to recon phase for that specific target
- **PostExploit reveals new network segments** → May need additional recon/exploit cycles

## Deconfliction

### Blue Team Coordination
If `roe.json` specifies deconfliction contacts:
- Record all major actions with timestamps in findings.md
- If blue team detects and responds, note this as a data point (MTTD measurement)
- Never reveal TTPs to blue team during active engagement unless ROE requires it

### Emergency Stop Procedure
If engagement must be halted:
1. Immediately stop all active sub-agent tasks
2. Document current state: which objectives in-progress, what's deployed
3. Record in findings.md with `[EMERGENCY STOP]` prefix
4. Save opplan.json with current status for potential resumption

## Engagement Metrics

Track these throughout the engagement for the final report:

| Metric | Description | Source |
|--------|-------------|--------|
| MTTD | Mean Time to Detect (per objective) | Blue team detection timestamps |
| Dwell Time | Time from foothold to detection | findings.md timestamps |
| Objectives Completed | Passed / Total | opplan.json status counts |
| Attack Path Depth | Number of hops from initial access | lateral movement log |
| Credential Exposure | Unique credentials captured | post-exploit/creds/ |

## Engagement Completion

### Final Reporting Checklist
When all objectives are resolved:

1. **Attack Path Documentation**:
   - Every hop from initial recon to final objective
   - Credentials used at each step
   - Privilege levels achieved on each host

2. **Findings Synthesis**:
   - Read all `<engagement>/findings.md` entries
   - Group by severity: Critical, High, Medium, Low
   - Map each finding to MITRE ATT&CK technique

3. **Remediation Recommendations**:
   - For each successful attack path, suggest defensive controls
   - Prioritize by: quick wins vs. strategic improvements
   - Reference where in the kill chain the control would interrupt the attack

4. **Evidence Preservation**:
   - All scan outputs in `<engagement>/recon/`
   - All exploit artifacts in `<engagement>/exploit/`
   - All post-exploit evidence in `<engagement>/post-exploit/`
   - Credential inventory (encrypted)

5. **Cleanup**:
   - List all artifacts deployed on target systems
   - Document persistence mechanisms that need removal
   - Verify no active implants remain (if applicable)
