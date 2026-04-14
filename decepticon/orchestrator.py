"""Vaccine Orchestrator — attack↔defend↔verify feedback loop.

Sits above the existing Ralph offensive loop. For each finding discovered
by the offensive agent, the orchestrator:

1. Generates a defense-brief from the finding
2. Invokes the defense agent to apply remediation
3. Re-runs the same attack vector to verify the defense holds
4. Records the verification result

The loop continues until all findings are processed or max_iterations
is reached.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from decepticon.core.logging import get_logger
from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseBrief,
    DefenseRecommendation,
    ReAttackOutcome,
    VerificationResult,
)

log = get_logger("orchestrator")


# ── Enums ──────────────────────────────────────────────────────────────────────


class OrchestratorPhase(StrEnum):
    """Current phase of the vaccine orchestration loop."""

    ATTACK = "attack"
    BRIEF_GENERATION = "brief_generation"
    DEFENSE = "defense"
    VERIFICATION = "verification"
    COMPLETE = "complete"


# ── State model ────────────────────────────────────────────────────────────────


class OrchestratorState(BaseModel):
    """Persisted state for the vaccine orchestration loop.

    Written to ``workspace/.vaccine-state.json`` after each iteration so the
    loop can be resumed after an interruption.
    """

    phase: OrchestratorPhase = OrchestratorPhase.ATTACK
    iteration: int = 0
    max_iterations: int = 10
    findings_discovered: list[str] = Field(default_factory=list)
    findings_processed: list[str] = Field(default_factory=list)
    defenses_applied: list[DefenseActionResult] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Orchestrator ───────────────────────────────────────────────────────────────


class VaccineOrchestrator:
    """Coordinates the attack↔defend↔verify feedback loop.

    The orchestrator does not directly invoke the defense agent — it prepares
    the defense brief on disk and reads back verification results that the
    defense agent writes after executing its actions.  This keeps the
    orchestrator decoupled from agent implementation details.

    Typical external integration::

        orchestrator = VaccineOrchestrator(workspace)
        state = await orchestrator.run()
    """

    def __init__(self, workspace: Path, state: OrchestratorState | None = None) -> None:
        self.workspace = workspace
        self.state: OrchestratorState = state if state is not None else OrchestratorState()
        self._state_path = workspace / ".vaccine-state.json"

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run(self) -> OrchestratorState:
        """Run the vaccine loop until all findings are processed or max_iterations reached.

        Returns the final :class:`OrchestratorState`.
        """
        state = self.state

        while state.iteration < state.max_iterations:
            state.iteration += 1
            log.info(
                "Vaccine iteration %d/%d",
                state.iteration,
                state.max_iterations,
            )

            # Phase 1: Discover new findings
            state.phase = OrchestratorPhase.ATTACK
            new_findings = self._scan_findings()
            state.findings_discovered = new_findings
            unprocessed = [f for f in new_findings if f not in state.findings_processed]

            if not unprocessed:
                log.info("No unprocessed findings remaining — loop complete")
                break

            log.info(
                "Found %d unprocessed finding(s): %s",
                len(unprocessed),
                ", ".join(unprocessed),
            )

            for finding_ref in unprocessed:
                # Phase 2: Generate defense brief
                state.phase = OrchestratorPhase.BRIEF_GENERATION
                log.info("Generating defense brief for %s", finding_ref)
                brief = self._generate_brief(finding_ref)
                if brief is None:
                    log.warning("Could not generate brief for %s — skipping", finding_ref)
                    continue
                self._save_brief(brief)
                log.info(
                    "Defense brief written for %s (%d recommended action(s))",
                    finding_ref,
                    len(brief.recommended_actions),
                )

                # Phase 3: Defense
                # The actual defense agent invocation happens externally.
                # The orchestrator writes the brief; the defense agent reads it,
                # executes actions, and writes back a verification result.
                state.phase = OrchestratorPhase.DEFENSE
                log.info(
                    "Waiting for defense agent to process %s (brief at %s)",
                    finding_ref,
                    self.workspace / "defense-brief.json",
                )

                # Phase 4: Verification
                state.phase = OrchestratorPhase.VERIFICATION
                result = self._load_verification_result(finding_ref)
                if result is not None:
                    state.verification_results.append(result)
                    if result.re_attack_outcome == ReAttackOutcome.BLOCKED:
                        log.info("Defense VERIFIED for %s", finding_ref)
                    else:
                        log.warning(
                            "Defense FAILED for %s: outcome=%s",
                            finding_ref,
                            result.re_attack_outcome,
                        )
                else:
                    log.warning(
                        "No verification result found for %s — defense agent may not have run",
                        finding_ref,
                    )

                state.findings_processed.append(finding_ref)

            self._save_state()

        state.phase = OrchestratorPhase.COMPLETE
        self._save_state()
        log.info(
            "Vaccine loop complete — %d finding(s) processed, %d verified",
            len(state.findings_processed),
            sum(
                1
                for r in state.verification_results
                if r.re_attack_outcome == ReAttackOutcome.BLOCKED
            ),
        )
        return state

    @property
    def summary(self) -> dict[str, object]:
        """Return a summary dict with counts and current status."""
        state = self.state
        verified = sum(
            1 for r in state.verification_results if r.re_attack_outcome == ReAttackOutcome.BLOCKED
        )
        failed = sum(
            1 for r in state.verification_results if r.re_attack_outcome != ReAttackOutcome.BLOCKED
        )
        return {
            "phase": state.phase,
            "iteration": state.iteration,
            "max_iterations": state.max_iterations,
            "findings_discovered": len(state.findings_discovered),
            "findings_processed": len(state.findings_processed),
            "verified": verified,
            "failed": failed,
            "started_at": state.started_at.isoformat(),
        }

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _scan_findings(self) -> list[str]:
        """Scan ``workspace/findings/`` for FIND-*.md files.

        Returns a sorted list of finding refs (e.g. ``["FIND-001", "FIND-002"]``).
        """
        findings_dir = self.workspace / "findings"
        if not findings_dir.is_dir():
            log.debug("Findings directory does not exist: %s", findings_dir)
            return []

        refs: list[str] = []
        for path in sorted(findings_dir.glob("FIND-*.md")):
            # Strip the ``.md`` suffix to get the bare ref (FIND-001)
            refs.append(path.stem)

        log.debug("Scanned %d finding(s) from %s", len(refs), findings_dir)
        return refs

    def _generate_brief(self, finding_ref: str) -> DefenseBrief | None:
        """Read a finding markdown file and produce a :class:`DefenseBrief`.

        Parses key fields from the frontmatter-style header lines present in
        Decepticon finding documents (``# Title``, ``**Severity**:``, etc.).
        Falls back to safe defaults when fields are absent so that a brief is
        always emitted for any readable finding.

        Returns ``None`` only when the finding file cannot be read.
        """
        finding_path = self.workspace / "findings" / f"{finding_ref}.md"
        if not finding_path.exists():
            log.warning("Finding file not found: %s", finding_path)
            return None

        try:
            content = finding_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.error("Could not read finding %s: %s", finding_path, exc)
            return None

        title, severity, attack_vector, affected_assets, evidence_summary = self._parse_finding(
            content
        )

        recommended_actions = self._infer_recommendations(attack_vector, severity)

        return DefenseBrief(
            finding_ref=finding_ref,
            finding_title=title,
            severity=severity,
            attack_vector=attack_vector,
            affected_assets=affected_assets,
            recommended_actions=recommended_actions,
            evidence_summary=evidence_summary,
        )

    def _parse_finding(self, content: str) -> tuple[str, str, str, list[str], str]:
        """Extract structured fields from a finding markdown document.

        Returns ``(title, severity, attack_vector, affected_assets, evidence_summary)``.
        """
        lines = content.splitlines()
        title = "Unknown Finding"
        severity = "medium"
        attack_vector = ""
        affected_assets: list[str] = []
        evidence_summary = ""

        # Title: first H1 heading
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        # Severity: line containing "**Severity**:" or "Severity:"
        for line in lines:
            lower = line.lower()
            if "severity" in lower and ":" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    candidate = parts[1].strip().strip("*").strip().lower()
                    if candidate in {"critical", "high", "medium", "low", "informational"}:
                        severity = candidate
                        break

        # Attack vector: line containing "**Attack Vector**:" or section header
        capture_vector = False
        vector_lines: list[str] = []
        for line in lines:
            lower = line.lower()
            if "attack vector" in lower and ":" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[1].strip():
                    vector_lines = [parts[1].strip()]
                    break
                capture_vector = True
                continue
            if capture_vector:
                stripped = line.strip()
                if stripped.startswith("#") or (stripped.startswith("**") and ":" in stripped):
                    break
                if stripped:
                    vector_lines.append(stripped)
                    if len(vector_lines) >= 3:
                        break
        if vector_lines:
            attack_vector = " ".join(vector_lines)

        # Affected assets: lines under "**Affected**:" or "**Assets**:"
        capture_assets = False
        for line in lines:
            lower = line.lower()
            if ("affected" in lower or "assets" in lower) and ":" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[1].strip():
                    for asset in parts[1].split(","):
                        asset = asset.strip()
                        if asset:
                            affected_assets.append(asset)
                    break
                capture_assets = True
                continue
            if capture_assets:
                stripped = line.strip()
                if stripped.startswith("#") or (stripped.startswith("**") and ":" in stripped):
                    break
                if stripped.startswith("-") or stripped.startswith("*"):
                    asset = stripped.lstrip("-* ").strip()
                    if asset:
                        affected_assets.append(asset)

        # Evidence summary: first non-empty paragraph after "## Evidence" heading
        capture_evidence = False
        for line in lines:
            stripped = line.strip()
            if stripped.lower() in {"## evidence", "### evidence"}:
                capture_evidence = True
                continue
            if capture_evidence:
                if stripped.startswith("#"):
                    break
                if stripped:
                    evidence_summary = stripped
                    break

        return title, severity, attack_vector, affected_assets, evidence_summary

    def _infer_recommendations(
        self, attack_vector: str, severity: str
    ) -> list[DefenseRecommendation]:
        """Infer a minimal set of defensive recommendations from the attack vector text.

        Uses keyword matching to produce actionable :class:`DefenseRecommendation`
        objects.  The defense agent is expected to refine these based on the full
        brief context.
        """
        lower = attack_vector.lower()
        recommendations: list[DefenseRecommendation] = []
        priority = 1

        if any(kw in lower for kw in ("port", "tcp", "udp", "service", "listen")):
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.BLOCK_PORT,
                    target="affected-port",
                    priority=priority,
                    rationale=(
                        "Attack vector references a network port or listening service — "
                        "block inbound access as an immediate containment measure"
                    ),
                )
            )
            priority += 1

        if any(kw in lower for kw in ("ssh", "ftp", "telnet", "smb", "rdp", "vnc")):
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.DISABLE_SERVICE,
                    target="affected-service",
                    priority=priority,
                    rationale=(
                        "Attack vector references a remote-access protocol — "
                        "disable or harden the service to remove the attack surface"
                    ),
                )
            )
            priority += 1

        if any(kw in lower for kw in ("credential", "password", "token", "key", "secret", "auth")):
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.REVOKE_CREDENTIAL,
                    target="compromised-credential",
                    priority=priority,
                    rationale=(
                        "Attack vector involves credentials or authentication — "
                        "revoke and rotate affected credentials immediately"
                    ),
                )
            )
            priority += 1

        if any(kw in lower for kw in ("config", "misconfigur", "permission", "acl", "setting")):
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.UPDATE_CONFIG,
                    target="affected-config",
                    priority=priority,
                    rationale=(
                        "Attack vector references a misconfiguration — "
                        "update the relevant configuration to enforce secure defaults"
                    ),
                )
            )
            priority += 1

        if any(kw in lower for kw in ("process", "pid", "daemon", "spawn", "exec")):
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.KILL_PROCESS,
                    target="affected-process",
                    priority=priority,
                    rationale=(
                        "Attack vector involves a running process — "
                        "terminate the process to halt active exploitation"
                    ),
                )
            )
            priority += 1

        # Always recommend a firewall rule for critical/high findings with no other actions
        if severity in {"critical", "high"} and not recommendations:
            recommendations.append(
                DefenseRecommendation(
                    action_type=DefenseActionType.ADD_FIREWALL_RULE,
                    target="affected-host",
                    priority=1,
                    rationale=(
                        f"High-severity finding ({severity}) with no specific vector keywords — "
                        "add a restrictive firewall rule as a precautionary measure"
                    ),
                )
            )

        return recommendations

    def _save_brief(self, brief: DefenseBrief) -> None:
        """Write the defense brief to ``workspace/defense-brief.json``."""
        brief_path = self.workspace / "defense-brief.json"
        try:
            brief_path.write_text(
                brief.model_dump_json(indent=2),
                encoding="utf-8",
            )
            log.debug("Defense brief written to %s", brief_path)
        except OSError as exc:
            log.error("Failed to write defense brief: %s", exc)

    def _load_verification_result(self, finding_ref: str) -> VerificationResult | None:
        """Load ``workspace/verification-{finding_ref}.json`` if it exists."""
        result_path = self.workspace / f"verification-{finding_ref}.json"
        if not result_path.exists():
            log.debug("Verification result not found: %s", result_path)
            return None

        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return VerificationResult.model_validate(data)
        except (OSError, ValueError) as exc:
            log.error("Failed to load verification result %s: %s", result_path, exc)
            return None

    def _save_state(self) -> None:
        """Persist current :class:`OrchestratorState` to ``workspace/.vaccine-state.json``."""
        try:
            self._state_path.write_text(
                self.state.model_dump_json(indent=2),
                encoding="utf-8",
            )
            log.debug("Orchestrator state saved to %s", self._state_path)
        except OSError as exc:
            log.error("Failed to save orchestrator state: %s", exc)

    def _load_state(self) -> OrchestratorState | None:
        """Load persisted :class:`OrchestratorState` from disk for resuming an interrupted run."""
        if not self._state_path.exists():
            return None

        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            state = OrchestratorState.model_validate(data)
            log.info(
                "Resumed orchestrator state from %s (iteration %d)",
                self._state_path,
                state.iteration,
            )
            return state
        except (OSError, ValueError) as exc:
            log.error("Failed to load orchestrator state from %s: %s", self._state_path, exc)
            return None


# ── Convenience entry point ────────────────────────────────────────────────────


async def run_vaccine_loop(
    workspace: str | Path,
    max_iterations: int = 10,
) -> OrchestratorState:
    """Entry point for the vaccine orchestration loop.

    Creates a fresh :class:`OrchestratorState`, builds a :class:`VaccineOrchestrator`,
    and runs the full attack↔defend↔verify cycle.

    Args:
        workspace: Path to the engagement workspace directory.
        max_iterations: Maximum number of loop iterations before stopping.

    Returns:
        The final :class:`OrchestratorState` after the loop completes.
    """
    workspace = Path(workspace)
    state = OrchestratorState(max_iterations=max_iterations)
    orchestrator = VaccineOrchestrator(workspace, state)
    return await orchestrator.run()
