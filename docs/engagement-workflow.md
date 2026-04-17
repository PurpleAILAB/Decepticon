# Engagement Workflow

A Decepticon engagement runs in two phases: **Planning** (operator + Soundwave) and **Execution** (autonomous loop). Here's the complete flow from first launch to final report.

---

## Phase 1: Planning

### 1. Define the target

When you start a new engagement, Soundwave asks for the target. Five input types are supported:

| Type | Example |
|------|---------|
| IP range | `192.168.1.0/24`, `10.0.0.1-10.0.0.50` |
| Web URL | `https://app.example.com` |
| Git repository | `https://github.com/org/repo` |
| File upload | Upload a binary, archive, or source tree |
| Local path | `/path/to/target/app` |

### 2. Soundwave interview

Soundwave conducts a structured interview to understand the engagement:

- **Threat actor profile** — Who are we emulating? Nation-state, financially motivated, insider threat?
- **Authorized scope** — What systems, networks, and actions are in scope?
- **Exclusions** — What must not be touched (production databases, critical services)?
- **Testing window** — When is testing authorized?
- **Acceptance criteria** — What does a successful engagement look like?
- **OPSEC requirements** — Noise level, detection avoidance, logging preferences

The interview streams in real time — you respond to each question.

### 3. Document generation

From the interview, Soundwave generates four documents:

| Document | Contents |
|----------|----------|
| **RoE** (Rules of Engagement) | Authorized scope, exclusions, testing window, escalation contacts, legal authorization |
| **ConOps** (Concept of Operations) | Threat actor profile, initial access TTPs, attack methodology, objectives |
| **Deconfliction Plan** | Source IPs, user-agents, time windows, and a shared code for real-time deconfliction calls with the SOC |
| **OPPLAN** (Operations Plan) | Full mission plan: objectives by phase, dependencies, acceptance criteria, MITRE ATT&CK mapping |

### 4. OPPLAN structure

Each OPPLAN objective carries:

```
OBJ-001
  title: "Port scan and service enumeration"
  phase: recon
  opsec_level: standard
  mitre: [T1595, T1046]
  depends_on: []
  acceptance_criteria: "All open ports identified with service versions"
  status: pending
```

OPSEC levels: `loud` → `standard` → `careful` → `quiet` → `silent`

Phases: `recon` → `initial-access` → `post-exploit` → `c2` → `exfiltration`

### 5. Operator review

You review the generated documents. If anything is wrong — scope is too broad, wrong threat actor, missing exclusions — you can edit the documents or ask Soundwave to regenerate sections before approving.

---

## Phase 2: Execution

Once the OPPLAN is approved, the autonomous loop begins.

### The orchestration loop

```
while objectives remain pending:
    obj = next_pending_objective_with_dependencies_met()
    agent = spawn_specialist_agent(obj.phase)
    result = agent.execute(obj, roe, findings_so_far)
    update_opplan_status(obj, result.status)
    append_findings_to_disk(result.findings)
    update_knowledge_graph(result.findings)
```

**Key properties:**
- Each agent starts with a **fresh context window** — no accumulated noise
- Agents read prior findings from disk, not from conversation history
- The orchestrator enforces RoE every iteration before dispatching an agent
- Dependencies are checked before an objective starts (e.g., exploitation waits for recon)

### Agent dispatch by phase

| Phase | Primary agents | Specialists (if applicable) |
|-------|---------------|---------------------------|
| `recon` | Recon, Scanner | — |
| `initial-access` | Exploit, Verifier, Exploiter | AD Operator, Cloud Hunter |
| `post-exploit` | Post-Exploit | AD Operator, Reverser |
| `c2` | Post-Exploit | — |
| `exfiltration` | Post-Exploit, Analyst | — |

### Objective status transitions

```
pending → in-progress → completed
                     ↘ blocked
                     ↘ cancelled
```

`blocked` means the agent could not complete the objective (patch applied, service unavailable, out of scope). The orchestrator records the reason and moves on.

### Findings format

Each finding is written to `workspace/findings/FIND-NNN.md`:

```markdown
# FIND-001: vsftpd 2.3.4 Backdoor (CVE-2011-2523)

**Severity**: CRITICAL (CVSS 10.0)
**Host**: 192.168.1.100
**Service**: FTP (port 21)
**CWE**: CWE-78 (OS Command Injection)
**MITRE**: T1190 (Exploit Public-Facing Application)

## Description
...

## Evidence
[command output, screenshots]

## Remediation
Upgrade vsftpd to 2.3.5 or later.
```

---

## Phase 3: Offensive Vaccine (optional)

After the attack phase, Decepticon can run the defense feedback loop. See [Offensive Vaccine](offensive-vaccine.md).

---

## Outputs

At engagement end, the `workspace/` directory contains:

| Path | Contents |
|------|----------|
| `workspace/findings/FIND-NNN.md` | Individual vulnerability findings |
| `workspace/docs/roe.md` | Rules of Engagement |
| `workspace/docs/conops.md` | Concept of Operations |
| `workspace/docs/deconfliction.md` | Deconfliction Plan |
| `workspace/docs/opplan.md` | Operations Plan |
| `workspace/docs/executive-summary.md` | Executive summary (generated by Analyst) |
| `workspace/docs/technical-report.md` | Full technical report |
| `workspace/loot/` | Credentials, hashes, sensitive data discovered |
| `workspace/.scratch/` | Raw tool output (nmap, nuclei, etc.) |

The knowledge graph retains the full attack graph for post-engagement analysis via Neo4j Browser (`http://localhost:7474`).
