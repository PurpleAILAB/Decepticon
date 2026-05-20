"""VaccineWriter — programmatic stage-transition API for the Offensive Vaccine pipeline.

The VaccineMiddleware (read-only watcher) emits *advisories* when findings
are ready for the next stage. But to actually flip ``validated → patched
→ defended → shipped`` flags, somebody has to write back to the finding
JSON file. Previously that was the responsibility of each sub-agent
(verifier/patcher/defender) hand-crafting a filesystem write via the
generic ``write_file`` tool. That's brittle:

- Race conditions on read-modify-write
- No schema enforcement
- Easy to forget ``stage_at`` timestamps
- No structured fields capture (diff, commit_sha, rule_path, pr_url)

This module provides ``VaccineWriter`` — a thin wrapper over the same
backend the VaccineMiddleware already uses, exposing typed transition
methods. Sub-agent tools and the orchestrator both get the same writer
instance, so transitions are observable + atomic.

Usage from a tool (e.g. inside ``patcher.py``)::

    from decepticon.middleware.vaccine_writer import VaccineWriter

    writer = VaccineWriter(backend=sandbox)
    writer.mark_patched(
        finding_id="FIND-001",
        diff_path="/workspace/patches/FIND-001.diff",
        commit_sha="abc1234",
        patch_verify_result="pass",
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from decepticon.middleware.vaccine import _DEFAULT_FINDINGS_DIR


# Schema field names — keep aligned w/ VaccineMiddleware._next_stage()
_STAGE_FLAGS = ("validated", "patched", "defended", "shipped")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TransitionResult:
    """Outcome of a stage transition write."""

    ok: bool
    finding_id: str
    stage: str
    error: str | None = None
    written: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


class VaccineWriter:
    """Atomic stage-transition writes for Vaccine findings.

    Args:
        backend: Filesystem backend (e.g. ``DockerSandbox``) implementing
            ``read(path)`` and ``write(path, content)`` per the
            deepagents backend protocol.
        findings_dir: Sandbox directory where ``FIND-NNN.json`` files
            live. Default ``/workspace/findings``.

    Methods:
        mark_validated(finding_id, **fields)
        mark_patched(finding_id, **fields)
        mark_defended(finding_id, **fields)
        mark_shipped(finding_id, **fields)
        get(finding_id) -> dict | None
        create(finding_id, **fields) -> TransitionResult
    """

    def __init__(
        self,
        *,
        backend: Any,
        findings_dir: str = _DEFAULT_FINDINGS_DIR,
    ) -> None:
        self._backend = backend
        self._findings_dir = findings_dir.rstrip("/")

    # ── paths ─────────────────────────────────────────────────────────

    def _path(self, finding_id: str) -> str:
        # Allow callers to pass either "FIND-001" or "FIND-001.json"
        stem = finding_id[:-5] if finding_id.endswith(".json") else finding_id
        return f"{self._findings_dir}/{stem}.json"

    # ── primitive read/write ──────────────────────────────────────────

    def get(self, finding_id: str) -> dict | None:
        """Return the current finding JSON, or None if missing/corrupt."""
        path = self._path(finding_id)
        try:
            res = self._backend.read(path)
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

    def _put(self, finding_id: str, doc: dict) -> bool:
        path = self._path(finding_id)
        body = json.dumps(doc, indent=2, sort_keys=True, default=str)
        try:
            res = self._backend.write(path, body)
        except Exception:
            return False
        return not getattr(res, "error", None)

    # ── transition primitives ─────────────────────────────────────────

    def create(self, finding_id: str, **fields: Any) -> TransitionResult:
        """Create a new finding doc. Idempotent — if already present, returns ok=False."""
        existing = self.get(finding_id)
        if existing is not None:
            return TransitionResult(
                ok=False,
                finding_id=finding_id,
                stage="create",
                error="already exists",
                written=existing,
            )
        doc: dict[str, Any] = {
            "vuln_id": finding_id,
            "created_at": _utc_now_iso(),
        }
        for flag in _STAGE_FLAGS:
            doc[flag] = False
        doc.update(fields)
        if not self._put(finding_id, doc):
            return TransitionResult(
                ok=False,
                finding_id=finding_id,
                stage="create",
                error="backend write failed",
            )
        return TransitionResult(ok=True, finding_id=finding_id, stage="create", written=doc)

    def _transition(self, finding_id: str, stage: str, **fields: Any) -> TransitionResult:
        if stage not in _STAGE_FLAGS:
            return TransitionResult(
                ok=False,
                finding_id=finding_id,
                stage=stage,
                error=f"unknown stage: {stage!r}",
            )
        doc = self.get(finding_id)
        if doc is None:
            # Auto-create on first transition. Patcher might fire before
            # the finding was formally created — be permissive.
            doc = {
                "vuln_id": finding_id,
                "created_at": _utc_now_iso(),
            }
            for flag in _STAGE_FLAGS:
                doc[flag] = False
        # Idempotent — already at this stage = no-op success
        if doc.get(stage):
            doc.update(fields)
            self._put(finding_id, doc)
            return TransitionResult(
                ok=True,
                finding_id=finding_id,
                stage=stage,
                error="already at this stage (no-op merge)",
                written=doc,
            )
        doc[stage] = True
        doc[f"{stage}_at"] = _utc_now_iso()
        doc.update(fields)
        if not self._put(finding_id, doc):
            return TransitionResult(
                ok=False,
                finding_id=finding_id,
                stage=stage,
                error="backend write failed",
            )
        return TransitionResult(ok=True, finding_id=finding_id, stage=stage, written=doc)

    # ── public typed transitions ──────────────────────────────────────

    def mark_validated(self, finding_id: str, **fields: Any) -> TransitionResult:
        """Verifier hook: validated PoC, ready for patcher."""
        return self._transition(finding_id, "validated", **fields)

    def mark_patched(self, finding_id: str, **fields: Any) -> TransitionResult:
        """Patcher hook: code fix landed locally + ``patch_verify`` passed."""
        return self._transition(finding_id, "patched", **fields)

    def mark_defended(self, finding_id: str, **fields: Any) -> TransitionResult:
        """Defender hook: detection rule written + ``defense_verify`` fired."""
        return self._transition(finding_id, "defended", **fields)

    def mark_shipped(
        self,
        finding_id: str,
        *,
        patch_pr_url: str | None = None,
        detection_pr_url: str | None = None,
        **fields: Any,
    ) -> TransitionResult:
        """Ship hook: both upstream PRs (code + detection) opened.

        Args:
            finding_id: e.g. ``FIND-001``
            patch_pr_url: URL of the code-fix PR (from
                ``github_pr_from_patcher``)
            detection_pr_url: URL of the detection-rule PR (from
                ``github_pr_from_defender``)
            **fields: any additional metadata to merge into the doc.
        """
        if patch_pr_url:
            fields.setdefault("patch_pr_url", patch_pr_url)
        if detection_pr_url:
            fields.setdefault("detection_pr_url", detection_pr_url)
        return self._transition(finding_id, "shipped", **fields)


__all__ = ["VaccineWriter", "TransitionResult"]
