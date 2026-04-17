# Offensive Vaccine

## The Core Idea

Most offensive security tools treat the attack as the destination. Find a vulnerability, write a report, close the ticket.

Decepticon treats the attack as Step 1.

The **Offensive Vaccine** is a closed feedback loop: attack → defend → verify. Every vulnerability discovered doesn't just become a finding — it becomes a test case for the defense system. The defender applies a mitigation, then the attacker verifies the defense actually holds. If it doesn't, the loop continues.

The name is intentional. A biological vaccine works by exposing the immune system to controlled doses of a pathogen, training it to respond. Decepticon does the same thing to your infrastructure — relentless, structured exposure builds real immunity.

---

## Why This Matters

Traditional security operates in two separate, disconnected lanes: Red Team attacks, Blue Team defends. The feedback between them is slow — a report written weeks after an engagement, reviewed in a meeting, turned into tickets, maybe patched. By the time a defense is actually applied, the threat landscape has moved on.

The Offensive Vaccine collapses that timeline. The same platform that finds vulnerabilities also drives the remediation loop, verifies the fix, and records the result — all autonomously, all within a single engagement.

This shifts the value proposition from *"here's a list of what's broken"* to *"here's a system that got broken, got fixed, and got verified — and will do it again tomorrow."*

That's the real goal: not a better attack tool, but a **better defense system** that emerges from surviving continuous attack.

---

## The Loop

```
For each finding:

  1. ATTACK
     Agent discovers vulnerability → writes FIND-NNN.md → updates KG

  2. BRIEF GENERATION
     Orchestrator generates a Defense Brief from the finding:
     - What was exploited
     - Recommended mitigations (firewall rule, patch, config change)
     - Priority: immediate / short-term / long-term

  3. DEFENSE
     Defender agent receives the brief → executes mitigations:
     - Applies firewall rules
     - Patches service configuration
     - Disables vulnerable endpoint
     Records DefenseAction node in Neo4j with MITIGATES relationship

  4. VERIFICATION
     Re-attack: the same exploit vector is run again
     → BLOCKED = defense holds ✓
     → PASSED  = defense failed, loop continues

  5. RECORD
     Result recorded in KG with verification timestamp
     Finding status updated: mitigated / partially-mitigated / failed
```

---

## Defense Agent

The **Defender** agent executes against a pluggable backend:

| Backend | Use case |
|---------|---------|
| Docker | Modify sandbox container (firewall rules, service config, file patches) |
| Cloud | Apply security group rules, IAM policy changes, bucket policies |
| Host OS | System-level hardening (for authorized host-level engagements) |

Defense actions are tracked as `DefenseAction` nodes in the knowledge graph:

```
(DefenseAction) -[:MITIGATES]->  (Vulnerability)
(DefenseAction) -[:DEFENDS]->    (Service)
(DefenseAction) -[:RESPONDS_TO]-> (Attack)
```

This makes the defense history queryable — you can see exactly what was applied, when, and whether it was verified.

---

## Knowledge Graph Integration

The Offensive Vaccine loop produces a complete, auditable trail in Neo4j:

```cypher
-- See all defense actions and their verification status
MATCH (d:DefenseAction)-[:MITIGATES]->(v:Vulnerability)
RETURN v.cve_id, d.action_type, d.description, d.status
ORDER BY d.applied_at DESC
```

```cypher
-- Find vulnerabilities where defense failed verification
MATCH (d:DefenseAction {status: "failed"})-[:MITIGATES]->(v:Vulnerability)
RETURN v.cve_id, v.severity, d.action_type
```

---

## Enabling the Vaccine Loop

The Vaccine phase runs automatically after the attack phase completes, if configured in the OPPLAN. You can also trigger it manually from the Orchestrator.

The loop runs up to `max_iterations` times per finding. If a defense cannot be verified within the iteration limit, the finding is marked `partially-mitigated` and escalated for human review.

---

## The Bigger Picture

Three steps toward a self-hardening infrastructure:

**Step 1 — Autonomous Offensive Agent**
Build a world-class hacking agent that executes realistic Red Team operations. *We are here.*

**Step 2 — Infinite Offensive Feedback**
Deploy the agent to generate continuous, diverse attack scenarios — an endless stream of real-world threat simulation.

**Step 3 — Defensive Evolution**
Channel that feedback into Blue Team capabilities — detection rules, response playbooks, hardening strategies. The defense evolves because the offense never stops.

The Offensive Vaccine is the bridge between Step 1 and Step 3. It's the mechanism that turns attack findings into defense improvements, automatically, at machine speed.
