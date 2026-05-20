"""VaccineMiddleware — auto-dispatch Patcher → Defender → PR on validated findings.

Implements the orchestration glue for the Offensive Vaccine loop documented
in ``docs/offensive-vaccine.md``. The Vaccine pipeline is:

    Scanner → Detector → Verifier → Patcher → Defender → github_pr_create

Each stage is an existing agent. This middleware automates the *dispatch*
between stages so the orchestrator doesn't need explicit instructions to
"now run the defender on FIND-NNN" — it sees a state transition and
fires the next stage automatically.

State transitions watched:
- ``validated=true`` (set by Verifier) but ``patched != true`` → orchestrator
  should dispatch ``task("patcher", ...)`` for that finding
- ``patched=true`` (set by Patcher) but ``defended != true`` → dispatch
  ``task("defender", ...)`` for that finding
- ``defended=true`` (set by Defender) but ``shipped != true`` → dispatch
  ``github_pr_from_patcher`` + ``github_pr_from_defender`` (or hand to a
  reporting sub-agent)

The middleware does NOT emit tool calls directly — that's not the
``AgentMiddleware`` API. It injects a ``<system-reminder>`` HumanMessage
identifying the finding(s) that need next-stage dispatch. The
orchestrator (decepticon agent prompt) is responsible for executing the
dispatch via ``task()`` on its next turn.

This keeps the implementation:
1. Pure addition (no breaking changes to existing agents)
2. Compatible w/ the existing OPPLANMiddleware (which is the
   authoritative state-transition recorder)
3. Inspectable — the reminder messages are visible in trace logs

Hook: ``before_model`` — runs every turn, so newly-validated findings
get advisory on the very next inference.

Tuning knobs:
- ``poll_path``: filesystem path (in sandbox) to read for finding state.
  Default is ``/workspace/findings/`` where Decepticon writes
  ``FIND-NNN.json`` per the existing pipeline.
- ``cooldown_turns``: avoid re-emitting the same dispatch advisory for
  the same finding repeatedly. Default 5.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage


# Default path inside the sandbox where the verifier/patcher/defender
# write their per-finding state. Override via constructor.
_DEFAULT_FINDINGS_DIR = "/workspace/findings"


class VaccineMiddleware(AgentMiddleware):
    """Auto-dispatch next-stage advisories for the Offensive Vaccine pipeline.

    Args:
        backend: Filesystem backend (e.g. DockerSandbox) used to read
            finding state files. Must implement ``ls(dir)`` and
            ``read(path)`` returning the same shape as deepagents' backend
            protocol.
        findings_dir: Directory in the sandbox where per-finding JSON
            state files live. Default ``/workspace/findings/``.
        cooldown_turns: Turns to suppress re-advisory for the same
            finding's same next-stage. Default 5.
    """

    def __init__(
        self,
        *,
        backend: object,
        findings_dir: str = _DEFAULT_FINDINGS_DIR,
        cooldown_turns: int = 5,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._findings_dir = findings_dir.rstrip("/")
        self._cooldown = cooldown_turns
        # (finding_id, next_stage) -> last-advised turn
        self._last_advised: dict[tuple[str, str], int] = {}
        self._turn = 0
        self._writer = None

    @property
    def writer(self):
        """Atomic stage-transition writer sharing this middleware's backend.

        Sub-agent tools call ``mw.writer.mark_patched(finding_id, ...)``
        instead of hand-writing JSON via the generic ``write_file`` tool,
        so flag transitions land in the same finding files this watcher
        is scanning. See ``decepticon.middleware.vaccine_writer.VaccineWriter``.
        """
        if self._writer is None:
            from decepticon.middleware.vaccine_writer import VaccineWriter
            self._writer = VaccineWriter(
                backend=self._backend,
                findings_dir=self._findings_dir,
            )
        return self._writer

    # ── finding-state scan ─────────────────────────────────────────────

    def _list_finding_files(self) -> list[str]:
        try:
            res = self._backend.ls(self._findings_dir)  # type: ignore[attr-defined]
        except Exception:
            return []
        if getattr(res, "error", None):
            return []
        names: list[str] = []
        for attr in ("entries", "files", "items"):
            cand = getattr(res, attr, None)
            if isinstance(cand, list):
                names = [str(n) for n in cand]
                break
        if not names:
            data = getattr(res, "file_data", None)
            if isinstance(data, dict):
                names = [str(n) for n in data.get("entries", [])]
        return [n for n in names if n.endswith(".json")]

    def _read_finding(self, filename: str) -> dict | None:
        path = f"{self._findings_dir}/{filename}"
        try:
            res = self._backend.read(path)  # type: ignore[attr-defined]
        except Exception:
            return None
        if getattr(res, "error", None):
            return None
        data = getattr(res, "file_data", None)
        if not data:
            return None
        content = data.get("content", "")
        if isinstance(content, list):
            content = "\n".join(content)
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None

    def _next_stage(self, finding: dict) -> str | None:
        """Determine which Vaccine stage should be dispatched next.

        Returns the stage name (``patcher``, ``defender``, ``ship``) or
        None if the finding is either incomplete (no validation yet) or
        terminal (already shipped).
        """
        if not finding.get("validated"):
            return None
        if not finding.get("patched"):
            return "patcher"
        if not finding.get("defended"):
            return "defender"
        if not finding.get("shipped"):
            return "ship"
        return None  # terminal

    # ── advisory builder ────────────────────────────────────────────────

    def _stage_instruction(self, stage: str, finding_id: str) -> list[str]:
        if stage == "patcher":
            return [
                f"VACCINE: finding `{finding_id}` is validated but not patched.",
                "Next action: dispatch `task(\"patcher\", ...)` with the finding's",
                "vuln_id, evidence excerpts from the verifier, and the workspace path.",
                "Patcher will produce a minimal diff + run `patch_verify` against",
                "the original PoC. On verified, finding's `patched` flag flips true.",
            ]
        if stage == "defender":
            return [
                f"VACCINE: finding `{finding_id}` is patched but not defended.",
                "Next action: dispatch `task(\"defender\", ...)` with the finding's",
                "vuln_id, PoC command, and bug class.",
                "Defender writes a sigma / snort / semgrep / falco rule that fires",
                "on the original PoC + does not fire on legit traffic.",
                "On defense_verify=fired, finding's `defended` flag flips true.",
            ]
        if stage == "ship":
            return [
                f"VACCINE: finding `{finding_id}` is patched + defended but not shipped.",
                "Next action: call `github_pr_from_patcher(...)` to land the code fix",
                "upstream + `github_pr_from_defender(...)` to land the detection rule.",
                "Both helpers in `decepticon.tools.reporting.github_pr_create`.",
                "On both PRs opened, mark `shipped=true` in the finding file.",
            ]
        return []

    def _build_message(self, pending: list[tuple[str, str]]) -> dict:
        lines = ["<system-reminder>"]
        lines.append("VACCINE pipeline — pending next-stage dispatches:")
        lines.append("")
        for finding_id, stage in pending:
            lines.extend(self._stage_instruction(stage, finding_id))
            lines.append("")
        lines.append(
            "Dispatch the most-recently-completed-stage finding first "
            "(LIFO) so the pipeline drains incrementally. Do NOT batch "
            "multiple dispatches in one turn — each sub-agent's evidence "
            "writes need to be observed before the next stage runs."
        )
        lines.append("</system-reminder>")
        return {"messages": [HumanMessage(content="\n".join(lines))]}

    # ── middleware hooks ────────────────────────────────────────────────

    def _scan_and_advise(self) -> dict | None:
        self._turn += 1
        files = self._list_finding_files()
        pending: list[tuple[str, str]] = []
        for fname in files:
            data = self._read_finding(fname)
            if not data:
                continue
            stage = self._next_stage(data)
            if not stage:
                continue
            finding_id = str(data.get("vuln_id") or data.get("key") or PurePosixPath(fname).stem)
            key = (finding_id, stage)
            last = self._last_advised.get(key)
            if last is not None and (self._turn - last) < self._cooldown:
                continue
            pending.append((finding_id, stage))
            self._last_advised[key] = self._turn
        if not pending:
            return None
        return self._build_message(pending)

    def before_model(self, state, runtime):  # type: ignore[override]
        return self._scan_and_advise()

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        # Backend reads MAY be sync subprocess calls — caller's choice.
        # Decepticon's DockerSandbox.read is sync; if a future backend is
        # async, override this method.
        return self._scan_and_advise()


__all__ = ["VaccineMiddleware"]
