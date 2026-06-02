"""DetectionFeedbackMiddleware — the Red-vs-Blue learning loop.

Closes the adaptive half of the Offensive Vaccine (docs/features/blue-cell.md
§"Adaptive feedback loop"). Blue Cell records ``DetectionFired`` nodes when the
agent's own activity trips a detection rule; this orchestrator-side hook reads
those nodes before each planning iteration and, when a technique was caught
fast (low MTTD), does two things:

1. Injects a ``<system-reminder>`` naming the rule/technique/MTTD and telling
   the agent its signatures are being watched — switch to a stealthier
   approach.
2. Escalates the in-progress OPPLAN objective's OPSEC posture toward
   ``careful`` (escalate-only — it never loosens a posture the operator set
   stricter), so the next delegation runs quieter.

It is deliberately best-effort: a graph-read blip or an unexpected state shape
returns ``None`` rather than crashing the model step, and with no Blue Cell
activity (no ``DetectionFired`` nodes) it is a silent no-op, so adding it to
the default orchestrator stack changes nothing until the defensive loop runs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections import OrderedDict
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from decepticon.tools.research._state import _load
from decepticon_core.types.engagement import ObjectiveStatus, OpsecLevel
from decepticon_core.types.kg import NodeKind

log = logging.getLogger(__name__)

# OPSEC postures from loudest to stealthiest. Escalation moves rightward only.
_OPSEC_ORDER: tuple[OpsecLevel, ...] = (
    OpsecLevel.LOUD,
    OpsecLevel.STANDARD,
    OpsecLevel.CAREFUL,
    OpsecLevel.QUIET,
    OpsecLevel.SILENT,
)

# Bound the surfaced-detection set so a long engagement can't grow it without
# limit; FIFO eviction (a re-surfaced detection after eviction is acceptable).
_SURFACED_MAX = 4096

_DEFAULT_THRESHOLD = 5.0


def _opsec_rank(value: object) -> int:
    """Index of an OPSEC posture in the loud→stealth order; STANDARD if unknown."""
    try:
        return _OPSEC_ORDER.index(OpsecLevel(value))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return _OPSEC_ORDER.index(OpsecLevel.STANDARD)


class DetectionFeedbackMiddleware(AgentMiddleware):
    """Warn the agent and stiffen OPSEC when Blue Cell catches it fast."""

    def __init__(
        self,
        *,
        mttd_threshold: float = _DEFAULT_THRESHOLD,
        target_opsec: OpsecLevel = OpsecLevel.CAREFUL,
    ) -> None:
        super().__init__()
        self._threshold = mttd_threshold
        self._target_opsec = target_opsec
        self._surfaced: OrderedDict[str, bool] = OrderedDict()
        self._lock = threading.Lock()

    def _fast_unsurfaced(self) -> list[dict[str, object]]:
        """Fast DetectionFired props not yet surfaced; marks them surfaced."""
        try:
            graph, _ = _load()
        except Exception as exc:  # noqa: BLE001 — best-effort; no graph → no-op
            log.debug("detection feedback: graph load failed: %s", exc)
            return []

        candidates: list[tuple[str, dict[str, Any]]] = []
        for node in graph.by_kind(NodeKind.DETECTION_FIRED):
            mttd = node.props.get("mttd_seconds")
            if mttd is None:
                continue
            try:
                if float(mttd) <= self._threshold:
                    candidates.append((node.id, dict(node.props)))
            except (TypeError, ValueError):
                continue

        with self._lock:
            fresh = [(nid, props) for nid, props in candidates if nid not in self._surfaced]
            for nid, _props in fresh:
                self._surfaced[nid] = True
            while len(self._surfaced) > _SURFACED_MAX:
                self._surfaced.popitem(last=False)
        return [props for _nid, props in fresh]

    def _reminder(self, detections: list[dict[str, Any]]) -> str:
        lines = []
        for props in sorted(detections, key=lambda p: float(p.get("mttd_seconds", 0.0) or 0.0)):
            mttd = float(props.get("mttd_seconds", 0.0) or 0.0)
            techniques = ", ".join(str(t) for t in (props.get("mitre") or [])) or "?"
            title = props.get("rule_title") or props.get("rule_id") or "detection"
            lines.append(
                f"  • {title} fired in {mttd:.1f}s on {techniques} (rule {props.get('rule_id', '?')})"
            )
        return (
            "<system-reminder>\n"
            "Blue Cell caught your activity quickly. These detections fired on the "
            "engagement's own telemetry:\n\n"
            + "\n".join(lines)
            + "\n\nThose technique signatures are being watched. Switch to a stealthier "
            "approach: slow your timing, evade the matched signatures, pick alternative "
            "tooling, and do not re-run the burned techniques. Downgrade the active "
            "objective's OPSEC posture (toward `careful`/`quiet`) via the OPPLAN tools "
            "before delegating the next step.\n"
            "</system-reminder>"
        )

    def _escalate_opsec(self, objectives: object) -> list[dict[str, Any]] | None:
        """Bump the in-progress objective's opsec toward the target. None if unchanged."""
        if not isinstance(objectives, list) or not objectives:
            return None
        target_rank = _opsec_rank(self._target_opsec)
        updated: list[dict[str, Any]] = []
        changed = False
        for objective in objectives:
            entry = dict(objective) if isinstance(objective, dict) else objective
            if (
                isinstance(entry, dict)
                and entry.get("status") == ObjectiveStatus.IN_PROGRESS.value
                and _opsec_rank(entry.get("opsec")) < target_rank
            ):
                entry["opsec"] = self._target_opsec.value
                changed = True
            updated.append(entry)
        return updated if changed else None

    def _build_update(self, state: object) -> dict | None:
        detections = self._fast_unsurfaced()
        if not detections:
            return None
        update: dict = {"messages": [HumanMessage(content=self._reminder(detections))]}
        objectives = state.get("objectives") if isinstance(state, dict) else None
        escalated = self._escalate_opsec(objectives)
        if escalated is not None:
            update["objectives"] = escalated
        return update

    def before_model(self, state, runtime):  # type: ignore[override]
        try:
            return self._build_update(state)
        except Exception:  # noqa: BLE001 — never crash the model step
            log.warning("detection feedback middleware failed", exc_info=True)
            return None

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        return await asyncio.to_thread(self.before_model, state, runtime)


def detection_mttd_threshold() -> float:
    """Read the fast-detection MTTD threshold (seconds) from the environment."""
    try:
        return float(os.environ.get("DECEPTICON_DETECTION_MTTD_THRESHOLD", _DEFAULT_THRESHOLD))
    except ValueError:
        return _DEFAULT_THRESHOLD
