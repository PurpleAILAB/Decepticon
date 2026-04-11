"""Red team engagement document schemas.

Defines the machine-readable document set for planning and executing
red team engagements. These map to the military-style planning hierarchy:

  RoE     → legal scope & boundaries       (guard rail, checked every iteration)
  CONOPS  → operational concept & threat    (strategic context)
  OPPLAN  → tactical objectives & status    (ralph loop task tracker)

The OPPLAN is the direct analogue of ralph's prd.json — it drives the
autonomous loop, with each objective checked off as it passes validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────


class EngagementType(StrEnum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    HYBRID = "hybrid"
    ASSUMED_BREACH = "assumed-breach"
    PHYSICAL = "physical"


class ObjectivePhase(StrEnum):
    """Kill chain phases for objective ordering.

    Practical 5-phase model aligned with sub-agent routing:
      recon          → recon agent       (TA0043 Reconnaissance)
      initial-access → exploit agent     (TA0001 Initial Access + TA0002 Execution)
      post-exploit   → postexploit agent (TA0003-TA0009: Persistence thru Collection)
      c2             → postexploit agent (TA0011 Command and Control)
      exfiltration   → postexploit agent (TA0010 Exfiltration + Actions on Objectives)
    """

    RECON = "recon"
    INITIAL_ACCESS = "initial-access"
    POST_EXPLOIT = "post-exploit"
    C2 = "c2"
    EXFILTRATION = "exfiltration"


class OpsecLevel(StrEnum):
    """OPSEC posture for an objective.

    Determines C2 tier selection, tool choices, and detection avoidance rigor.
    Based on Red Team Maturity Model levels and C2 tier mapping.
    See docs/red-team/opplan-domain-knowledge.md for details.
    """

    LOUD = "loud"  # No evasion; testing detection capability
    STANDARD = "standard"  # Basic OPSEC; modify default signatures
    CAREFUL = "careful"  # Active evasion; avoid known signatures
    QUIET = "quiet"  # Minimal footprint; blend with normal traffic
    SILENT = "silent"  # Zero detection tolerance; abort if burned


class C2Tier(StrEnum):
    """C2 infrastructure tier for objective execution."""

    INTERACTIVE = "interactive"  # Direct operator control, seconds callback
    SHORT_HAUL = "short-haul"  # Reliable access, minutes-hours callback
    LONG_HAUL = "long-haul"  # Persistent fallback, hours-days callback


class ObjectiveStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class FindingSeverity(StrEnum):
    """CVSS-aligned severity levels for individual findings."""

    CRITICAL = "critical"  # CVSS 9.0-10.0
    HIGH = "high"  # CVSS 7.0-8.9
    MEDIUM = "medium"  # CVSS 4.0-6.9
    LOW = "low"  # CVSS 0.1-3.9
    INFORMATIONAL = "informational"  # CVSS 0.0 — observation only


class FindingConfidence(StrEnum):
    """Confidence level for a finding — drives verification requirements."""

    VERIFIED = "verified"  # Confirmed with 2+ methods (required for CRITICAL/HIGH)
    PROBABLE = "probable"  # Strong indicators, single method
    UNVERIFIED = "unverified"  # Initial observation, needs confirmation


class RemediationPriority(StrEnum):
    """Remediation urgency aligned with PTES/CREST reporting standards."""

    IMMEDIATE = "immediate"  # 0-7 days: patch, config change
    SHORT_TERM = "short-term"  # 30 days: detection rules, SIEM update
    LONG_TERM = "long-term"  # 90+ days: architecture improvement


# ── Finding / Evidence / Attack Path ─────────────────────────────────


class Evidence(BaseModel):
    """Artifact reference attached to a finding.

    Each piece of evidence points to a file in the engagement workspace
    (e.g., scan output, HTTP request/response, terminal log, pcap).
    SHA-256 hash provides chain-of-custody integrity verification.
    """

    type: str = Field(
        description=(
            "Evidence type: screenshot, http-request, terminal-log, pcap, artifact, scan-output"
        )
    )
    path: str = Field(description="Relative path within engagement workspace")
    description: str = ""
    sha256: str = Field(default="", description="SHA-256 hash for integrity verification")
    collected_at: str = Field(default="", description="ISO 8601 timestamp of collection")


class Finding(BaseModel):
    """Individual vulnerability or security finding -- one Markdown file per finding.

    Follows bug bounty report structure (HackerOne/Bugcrowd) enriched with
    red team metadata (detection gaps, ATT&CK mapping, agent provenance).
    CVSS v4.0 is the primary scoring system per FIRST 2023 recommendation.
    On-disk format: YAML frontmatter + Markdown body.

    File naming: findings/FIND-001.md, findings/FIND-002.md, ...
    """

    id: str = Field(description="Auto-generated ID: FIND-001, FIND-002, ...")
    title: str = Field(description="Bug bounty format: '[Type] in [Target] allows [Impact]'")
    severity: FindingSeverity
    cvss_score: float | None = Field(default=None, description="Numeric CVSS score (0.0-10.0)")
    cvss_vector: str = Field(
        default="", description="Full CVSS vector string, e.g. CVSS:4.0/AV:N/AC:L/..."
    )
    cvss_version: str = Field(default="4.0", description="CVSS version used (4.0 primary)")
    cwe: list[str] = Field(default_factory=list, description="CWE IDs, e.g. ['CWE-89']")
    mitre: list[str] = Field(
        default_factory=list, description="MITRE ATT&CK technique IDs, e.g. ['T1190']"
    )

    # Where
    affected_target: str = Field(description="IP, hostname, or URL of affected system")
    affected_component: str = Field(
        default="", description="Specific service, endpoint, port, or parameter"
    )

    # What
    description: str = Field(description="Technical description of the vulnerability")
    steps_to_reproduce: list[str] = Field(
        default_factory=list, description="Ordered reproduction steps"
    )
    impact: str = Field(default="", description="Business and technical impact assessment")

    # Evidence
    evidence: list[Evidence] = Field(default_factory=list)

    # Detection gap tracking (Purple Team / TIBER-EU)
    detected: bool | None = Field(
        default=None, description="Whether Blue Team detected this activity"
    )
    detection_notes: str = Field(
        default="", description="Which detection mechanisms fired or failed"
    )

    # Remediation (PTES/CREST report structure)
    remediation: str = Field(default="", description="Specific fix recommendation")
    remediation_priority: RemediationPriority | None = Field(
        default=None, description="Urgency: immediate, short-term, long-term"
    )

    # AI Agent metadata
    objective_id: str = Field(default="", description="OPPLAN objective that found this (OBJ-xxx)")
    phase: ObjectivePhase | None = None
    agent: str = Field(
        default="", description="Agent that discovered this: recon/exploit/postexploit"
    )
    iteration: int = Field(default=0, description="Ralph loop iteration number")
    confidence: FindingConfidence = FindingConfidence.VERIFIED
    discovered_at: str = Field(default="", description="ISO 8601 discovery timestamp")
    verified_methods: list[str] = Field(
        default_factory=list,
        description="Methods used to verify (e.g. ['nmap', 'manual curl'])",
    )


class AttackPathStep(BaseModel):
    """Single hop in a kill chain attack path."""

    order: int = Field(description="Step sequence number (1-based)")
    phase: ObjectivePhase
    technique: str = Field(description="ATT&CK technique name")
    mitre: str = Field(description="ATT&CK technique ID, e.g. T1190")
    source: str = Field(description="Origin host/service for this hop")
    target: str = Field(description="Destination host/service")
    tool: str = Field(default="", description="Tool used for this step")
    detected: bool | None = Field(default=None, description="Whether this step was detected")
    finding_id: str = Field(default="", description="Related finding ID (FIND-xxx)")


class AttackPath(BaseModel):
    """Kill chain traversal path -- connects findings into an attack narrative.

    Documents the complete chain from initial access to objective completion,
    mapping each hop to ATT&CK techniques. Combined severity may exceed
    individual finding scores when chained (e.g., Medium + Medium = Critical).

    File naming: findings/attack-paths/PATH-001.md
    """

    id: str = Field(description="Auto-generated ID: PATH-001, PATH-002, ...")
    name: str = Field(description="Descriptive name, e.g. 'External to DB Admin via SSRF Chain'")
    description: str = Field(default="", description="Narrative description of the attack path")
    steps: list[AttackPathStep] = Field(default_factory=list)
    combined_severity: FindingSeverity = FindingSeverity.CRITICAL
    finding_ids: list[str] = Field(
        default_factory=list, description="All FIND-xxx IDs in this path"
    )


# ── RoE (Rules of Engagement) ────────────────────────────────────────


class ScopeEntry(BaseModel):
    """A single in-scope or out-of-scope target."""

    target: str = Field(description="Domain, IP range (CIDR), or asset identifier")
    type: str = Field(description="domain, ip-range, cloud-resource, physical, etc.")
    notes: str = ""


class EscalationContact(BaseModel):
    """Emergency or escalation contact."""

    name: str
    role: str
    channel: str = Field(description="Phone, email, Slack, etc.")
    available: str = Field(default="24/7", description="Availability window")


class RoE(BaseModel):
    """Rules of Engagement — legally binding scope and boundaries.

    Checked at the start of every ralph loop iteration as a guard rail.
    """

    engagement_name: str
    client: str
    start_date: str
    end_date: str
    engagement_type: EngagementType
    testing_window: str = Field(
        description="Authorized testing hours, e.g. 'Mon-Fri 09:00-18:00 KST'"
    )

    # Scope
    in_scope: list[ScopeEntry] = Field(default_factory=list)
    out_of_scope: list[ScopeEntry] = Field(default_factory=list)

    # Boundaries
    prohibited_actions: list[str] = Field(
        default_factory=lambda: [
            "Denial of Service (DoS/DDoS)",
            "Social engineering of employees (unless authorized)",
            "Physical access attempts (unless authorized)",
            "Data exfiltration of real customer data",
            "Modification or deletion of production data",
        ]
    )
    permitted_actions: list[str] = Field(default_factory=list)

    # Escalation
    escalation_contacts: list[EscalationContact] = Field(default_factory=list)
    incident_procedure: str = Field(
        default="Stop immediately, document the incident, notify engagement lead within 15 minutes."
    )

    # Legal
    authorization_reference: str = Field(
        default="", description="Reference to signed authorization letter or contract"
    )

    # Operational limits
    data_handling: str = Field(
        default="",
        description="How discovered PII, credentials, and client data must be handled",
    )
    cleanup_required: bool = Field(
        default=True,
        description="Whether red team must remove tools/artifacts after engagement",
    )

    # Metadata
    version: str = "1.0"
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── CONOPS (Concept of Operations) ───────────────────────────────────


class ThreatActor(BaseModel):
    """Threat actor profile to emulate."""

    name: str = Field(description="Actor name or archetype, e.g. 'APT29', 'Opportunistic External'")
    sophistication: str = Field(description="low, medium, high, nation-state")
    motivation: str = Field(description="financial, espionage, disruption, hacktivism")
    initial_access: list[str] = Field(
        default_factory=list, description="Expected initial access techniques (MITRE IDs)"
    )
    ttps: list[str] = Field(
        default_factory=list, description="Key MITRE ATT&CK technique IDs this actor uses"
    )


class KillChainPhase(BaseModel):
    """A phase in the engagement kill chain."""

    phase: ObjectivePhase
    description: str
    success_criteria: str = ""
    tools: list[str] = Field(default_factory=list)


class CONOPS(BaseModel):
    """Concept of Operations — strategic engagement overview.

    Readable by both technical operators and non-technical stakeholders.
    """

    engagement_name: str
    executive_summary: str = Field(description="2-3 sentence overview a CEO could understand")

    # Threat model
    threat_actors: list[ThreatActor] = Field(default_factory=list)
    attack_narrative: str = Field(
        default="", description="Story-form description of the simulated attack scenario"
    )

    # Kill chain
    kill_chain: list[KillChainPhase] = Field(default_factory=list)

    # Operational
    methodology: str = Field(default="PTES + MITRE ATT&CK framework")
    communication_plan: str = Field(
        default="", description="How red cell communicates with client and internally"
    )

    # Timeline
    phases_timeline: dict[str, str] = Field(
        default_factory=dict, description="Phase name → date range mapping"
    )

    # Success criteria
    success_criteria: list[str] = Field(default_factory=list)


# ── Deconfliction Plan ───────────────────────────────────────────────


class DeconflictionEntry(BaseModel):
    """A deconfliction identifier for red team activity."""

    type: str = Field(description="source-ip, user-agent, tool-hash, time-window, etc.")
    value: str
    description: str = ""


class DeconflictionPlan(BaseModel):
    """Deconfliction plan — separating red team activity from real threats."""

    engagement_name: str
    identifiers: list[DeconflictionEntry] = Field(default_factory=list)
    notification_procedure: str = Field(
        default="Red team lead notifies SOC 30 minutes before active scanning begins."
    )
    soc_contact: str = ""
    deconfliction_code: str = Field(
        default="", description="Shared secret code for real-time deconfliction calls"
    )


# ── OPPLAN (Operations Plan) — the ralph loop driver ─────────────────


class Objective(BaseModel):
    """A single engagement objective — analogous to ralph's user story.

    Each objective must be completable in ONE agent context window.
    The ralph loop picks the highest-priority objective where status != 'passed'.
    """

    id: str = Field(description="Unique ID, e.g. OBJ-001")
    phase: ObjectivePhase
    title: str
    description: str
    acceptance_criteria: list[str] = Field(
        description="Verifiable criteria — each must be checkable"
    )
    priority: int = Field(
        description="Execution order (1 = first). Respects kill chain dependencies."
    )
    status: ObjectiveStatus = ObjectiveStatus.PENDING
    """pending → in-progress → completed/blocked. blocked → in-progress (retry) or completed (abandon)."""
    mitre: list[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK technique IDs (e.g. ['T1190', 'T1059.004'])",
    )

    # Red team-specific fields (not found in pentest planning)
    opsec: OpsecLevel = Field(
        default=OpsecLevel.STANDARD,
        description="OPSEC posture — drives tool selection and detection avoidance rigor",
    )
    opsec_notes: str = Field(
        default="", description="Specific OPSEC constraints for this objective"
    )
    c2_tier: C2Tier = Field(
        default=C2Tier.INTERACTIVE,
        description="C2 tier: interactive (seconds), short-haul (minutes), long-haul (hours)",
    )
    concessions: list[str] = Field(
        default_factory=list,
        description="Pre-authorized assists if objective is blocked (TIBER/CORIE concept)",
    )

    notes: str = ""
    blocked_by: list[str] = Field(
        default_factory=list, description="Objective IDs that must complete first"
    )
    owner: str = Field(default="", description="Sub-agent currently executing this objective")
    parent_id: str | None = Field(
        default=None,
        description=(
            "Optional parent objective ID. When set, this objective is a "
            "sub-task of the parent — the parent cannot move to COMPLETED "
            "until every child is COMPLETED or CANCELLED. Inspired by "
            "PentestGPT's Pentesting Task Tree (PTT)."
        ),
    )


class OPPLAN(BaseModel):
    """Operations Plan — the tactical task tracker for the ralph loop.

    Direct analogue of ralph's prd.json. The autonomous loop reads this
    file each iteration, picks the next objective, executes it, and
    updates the status.

    Hierarchical mode: any objective with ``parent_id`` set becomes a
    child of that parent. Trees are arbitrary depth — but real plans
    rarely need more than two levels in practice. The flat-list code
    paths still work when no hierarchy is set.
    """

    engagement_name: str
    threat_profile: str = Field(
        description="Short threat actor summary for context injection each iteration"
    )
    objectives: list[Objective] = Field(default_factory=list)

    # ── Hierarchy helpers ──────────────────────────────────────────────

    def by_id(self, objective_id: str) -> Objective | None:
        for obj in self.objectives:
            if obj.id == objective_id:
                return obj
        return None

    def children_of(self, parent_id: str) -> list[Objective]:
        """Direct children of ``parent_id`` (single level)."""
        return [o for o in self.objectives if o.parent_id == parent_id]

    def descendants_of(self, parent_id: str) -> list[Objective]:
        """Every descendant of ``parent_id`` (depth-first)."""
        out: list[Objective] = []
        stack = list(self.children_of(parent_id))
        while stack:
            obj = stack.pop()
            out.append(obj)
            stack.extend(self.children_of(obj.id))
        return out

    def root_objectives(self) -> list[Objective]:
        """Top-level objectives (no parent)."""
        return [o for o in self.objectives if not o.parent_id]

    def has_hierarchy(self) -> bool:
        return any(o.parent_id for o in self.objectives)

    def detect_cycle(self, objective_id: str, parent_id: str) -> bool:
        """Return True if attaching ``objective_id`` under ``parent_id``
        would create a cycle. Walks the proposed parent chain upward."""
        if objective_id == parent_id:
            return True
        cur = self.by_id(parent_id)
        seen: set[str] = set()
        while cur is not None:
            if cur.id in seen:
                return True
            seen.add(cur.id)
            if cur.id == objective_id:
                return True
            if not cur.parent_id:
                return False
            cur = self.by_id(cur.parent_id)
        return False

    def tree(self) -> list[dict[str, object]]:
        """Return the objective list as a nested ``[{...children: []}]`` dict."""

        def _build(parent_id: str | None) -> list[dict[str, object]]:
            return [
                {
                    "id": o.id,
                    "title": o.title,
                    "phase": o.phase.value if hasattr(o.phase, "value") else str(o.phase),
                    "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                    "priority": o.priority,
                    "children": _build(o.id),
                }
                for o in sorted(
                    [x for x in self.objectives if x.parent_id == parent_id],
                    key=lambda x: x.priority,
                )
            ]

        return _build(None)


# ── Engagement Bundle ─────────────────────────────────────────────────


class EngagementBundle(BaseModel):
    """Complete engagement document set.

    The planning agent generates all four documents as a unit.
    The ralph loop reads roe + opplan each iteration.
    """

    roe: RoE
    conops: CONOPS
    opplan: OPPLAN
    deconfliction: DeconflictionPlan

    def save(self, engagement_dir: str) -> dict[str, str]:
        """Save all documents to an engagement workspace directory.

        Layout:
          <engagement_dir>/plan/roe.json, conops.json, opplan.json, deconfliction.json
          <engagement_dir>/findings/             (per-finding reports: FIND-001.md, ...)
          <engagement_dir>/findings/attack-paths/ (attack path JSON files)
          <engagement_dir>/findings/evidence/    (evidence artifacts)
          <engagement_dir>/timeline.jsonl        (activity timeline)
          <engagement_dir>/report/               (final report output)
          <engagement_dir>/recon/  exploit/  post-exploit/

        Returns a mapping of document type → file path.
        """
        import json
        from pathlib import Path

        root = Path(engagement_dir)
        plan_dir = root / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)

        # Create execution subdirectories
        for subdir in (
            "recon",
            "exploit",
            "post-exploit",
            "findings",
            "findings/attack-paths",
            "findings/evidence",
            "report",
        ):
            (root / subdir).mkdir(parents=True, exist_ok=True)

        files = {}
        for name, doc in [
            ("roe", self.roe),
            ("conops", self.conops),
            ("opplan", self.opplan),
            ("deconfliction", self.deconfliction),
        ]:
            path = plan_dir / f"{name}.json"
            path.write_text(
                json.dumps(doc.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            files[name] = str(path)

        # Initialize findings directory README (replaces legacy findings.md)
        findings_readme = root / "findings" / "README.md"
        if not findings_readme.exists():
            findings_readme.write_text(
                f"# Findings — {self.roe.engagement_name}\n\n"
                f"Started: {datetime.now().isoformat()}\n\n"
                "Each finding is a separate file: `FIND-001.md`, `FIND-002.md`, ...\n"
                "Attack paths: `attack-paths/PATH-001.md`, ...\n"
                "Evidence artifacts: `evidence/`\n",
                encoding="utf-8",
            )
            files["findings"] = str(root / "findings")

        # Initialize empty timeline.jsonl (activity log)
        timeline_path = root / "timeline.jsonl"
        if not timeline_path.exists():
            timeline_path.write_text("", encoding="utf-8")
            files["timeline"] = str(timeline_path)

        return files
