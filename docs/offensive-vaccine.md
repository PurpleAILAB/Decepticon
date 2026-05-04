# Offensive Vaccine

## The Core Idea

This is a planned product direction, not an active implementation in the current codebase.

Most offensive security tools treat the attack as the destination. Find a vulnerability, write a report, close the ticket.

Decepticon treats the attack as Step 1.

The **Offensive Vaccine** is intended to become a closed feedback loop: attack → defend → verify. Every vulnerability discovered should become a test case for the defense system. A future defense component applies a mitigation, then the attacker verifies the defense actually holds. If it doesn't, the loop continues.

The name is intentional. A biological vaccine works by exposing the immune system to controlled doses of a pathogen, training it to respond. Decepticon does the same thing to your infrastructure — relentless, structured exposure builds real immunity.

---

## Why This Matters

Traditional security operates in two separate, disconnected lanes: Red Team attacks, Blue Team defends. The feedback between them is slow — a report written weeks after an engagement, reviewed in a meeting, turned into tickets, maybe patched. By the time a defense is actually applied, the threat landscape has moved on.

The Offensive Vaccine is intended to collapse that timeline. The same platform that finds vulnerabilities should eventually drive the remediation loop, verify the fix, and record the result within a single engagement.

This shifts the value proposition from *"here's a list of what's broken"* to *"here's a system that got broken, got fixed, and got verified — and will do it again tomorrow."*

That's the real goal: not a better attack tool, but a **better defense system** that emerges from surviving continuous attack.

---

## The Loop

```
For each finding:

  1. ATTACK
     Agent discovers vulnerability → writes FIND-NNN.md → updates KG

  2. BRIEF GENERATION
     A future vaccine component generates a remediation brief from the finding:
     - What was exploited
     - Recommended mitigations (firewall rule, patch, config change)
     - Priority: immediate / short-term / long-term

  3. DEFENSE
     A future defense component receives the brief → executes mitigations:
     - Applies firewall rules
     - Patches service configuration
     - Disables vulnerable endpoint
     Records mitigation evidence in the knowledge graph

  4. VERIFICATION
     Re-attack: the same exploit vector is run again
     → BLOCKED = defense holds ✓
     → PASSED  = defense failed, loop continues

  5. RECORD
     Result recorded in KG with verification timestamp
     Finding status updated: mitigated / partially-mitigated / failed
```

---

## Future Defense Component

The previous Defender graph and Docker defense backend have been removed. A future implementation should be rebuilt around the current OPPLAN middleware and a dedicated vaccine concept instead of the legacy loop.

| Backend | Use case |
|---------|---------|
| Docker | Modify sandbox container (firewall rules, service config, file patches) |
| Cloud | Apply security group rules, IAM policy changes, bucket policies |
| Host OS | System-level hardening (for authorized host-level engagements) |

The concrete schemas, tools, backend APIs, knowledge-graph relationships, and verification flow are intentionally left for that future implementation.

---

## The Bigger Picture

Three steps toward a self-hardening infrastructure:

**Step 1 — Autonomous Offensive Agent**
Build a world-class hacking agent that executes realistic Red Team operations. *We are here.*

**Step 2 — Infinite Offensive Feedback**
Deploy the agent to generate continuous, diverse attack scenarios — an endless stream of real-world threat simulation.

**Step 3 — Defensive Evolution**
Channel that feedback into Blue Team capabilities — detection rules, response playbooks, hardening strategies. The defense evolves because the offense never stops.

The Offensive Vaccine is the planned bridge between Step 1 and Step 3. It is the mechanism that should eventually turn attack findings into defense improvements.
