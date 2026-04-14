"""Defense brief schemas — structured feedback documents for inter-agent communication.

These models define the data contract between the offensive recon agent and the
defensive response agent (Offensive Vaccine). The flow is:

  Offensive agent → DefenseBrief → Defense agent → VerificationResult → Ralph loop

Each DefenseBrief maps one-to-one with a finding (FIND-NNN) and carries the
structured information a defense agent needs to apply mitigations and then
re-verify via a controlled re-attack.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────


class DefenseActionType(StrEnum):
    """Discrete defensive action categories the defense agent can execute.

    Each value maps to a concrete remediation primitive the sandbox or
    target host can perform. The defense agent selects one or more per finding.
    """

    BLOCK_PORT = "block_port"
    ADD_FIREWALL_RULE = "add_firewall_rule"
    DISABLE_SERVICE = "disable_service"
    RESTART_SERVICE = "restart_service"
    UPDATE_CONFIG = "update_config"
    KILL_PROCESS = "kill_process"
    REVOKE_CREDENTIAL = "revoke_credential"


class ReAttackOutcome(StrEnum):
    """Outcome of re-running the original attack after defensive actions were applied.

    Used to determine whether a defense was effective, partial, or failed.
    """

    BLOCKED = "blocked"  # Attack was fully mitigated — finding is closed
    PASSED = "passed"  # Attack still succeeds — defense was ineffective
    PARTIAL = "partial"  # Attack partially mitigated — follow-up needed
    ERROR = "error"  # Re-attack could not complete (infra/tooling issue)


# ── Models ─────────────────────────────────────────────────────────────


class DefenseRecommendation(BaseModel):
    """A single recommended defensive action from the offensive agent.

    The offensive agent populates these inside a DefenseBrief. The defense
    agent reads them and decides which to execute, in which order.
    """

    action_type: DefenseActionType = Field(description="Category of defensive action to take")
    target: str = Field(
        description=(
            "What to act on — port notation (e.g. 'tcp/8080'), service name "
            "(e.g. 'sshd'), IP/hostname (e.g. '10.0.0.5'), or credential ID"
        )
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Action-specific key/value parameters (e.g. {'rule': 'DROP', 'chain': 'INPUT'})",
    )
    priority: int = Field(
        default=1,
        description="Execution priority: 1 = highest. Lower numbers run first.",
    )
    rationale: str = Field(
        description="Why this action is recommended — links back to the attack vector"
    )


class DefenseBrief(BaseModel):
    """Structured feedback document passed from the offensive agent to the defense agent.

    One DefenseBrief is generated per finding. It carries everything the defense
    agent needs to understand the vulnerability and apply targeted mitigations
    without needing to re-read raw findings files.
    """

    finding_ref: str = Field(description="Reference to the source finding, e.g. 'FIND-001'")
    finding_title: str = Field(description="Human-readable title matching the finding document")
    severity: str = Field(
        description=(
            "Finding severity using FindingSeverity values: "
            "critical, high, medium, low, informational"
        )
    )
    attack_vector: str = Field(
        description="Description of how the attack worked — what was exploited and how"
    )
    affected_assets: list[str] = Field(
        default_factory=list,
        description="IPs, hostnames, and service identifiers affected by this finding",
    )
    recommended_actions: list[DefenseRecommendation] = Field(
        default_factory=list,
        description="Ordered list of defensive actions the defense agent should consider",
    )
    evidence_summary: str = Field(
        default="",
        description="Brief summary of exploitation evidence from the offensive run",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this brief was generated (UTC)",
    )


class DefenseActionResult(BaseModel):
    """Result of executing a single defensive action on the target.

    Populated by the defense agent after attempting each action from a
    DefenseRecommendation. Collected into a VerificationResult.
    """

    action_type: DefenseActionType = Field(
        description="The type of defensive action that was executed"
    )
    target: str = Field(description="The specific target the action was applied to")
    success: bool = Field(description="Whether the action was applied successfully")
    message: str = Field(
        description="Human-readable result message — include error detail on failure"
    )
    rollback_command: str | None = Field(
        default=None,
        description="Shell command to undo this action if needed during deconfliction",
    )
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the action was executed (UTC)",
    )


class VerificationResult(BaseModel):
    """Result of re-attack verification after defensive actions were applied.

    The defense agent populates this after executing all actions from a
    DefenseBrief and performing a controlled re-attack. The ralph loop reads
    this to determine whether to close the finding or escalate.
    """

    finding_ref: str = Field(description="Reference to the finding being verified, e.g. 'FIND-001'")
    defense_actions_applied: list[DefenseActionResult] = Field(
        default_factory=list,
        description="Results for every defensive action that was attempted",
    )
    re_attack_outcome: ReAttackOutcome = Field(
        description="Whether the re-attack was blocked, passed, partial, or errored"
    )
    re_attack_details: str = Field(
        default="",
        description="What happened during the re-attack — tool output, observations, conclusions",
    )
    verified_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when re-attack verification completed (UTC)",
    )
