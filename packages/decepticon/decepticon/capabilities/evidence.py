"""Evidence validation independent of a graph backend.

The validator is deliberately pure: agents may produce evidence in a sandbox,
but promotion decisions are based on immutable captured output and an explicit
negative control rather than model confidence or exit status alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceValidation:
    """Outcome of comparing a positive proof with its baseline control."""

    validated: bool
    success_matches: tuple[str, ...] = ()
    negative_matches: tuple[str, ...] = ()
    noise_matches: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        if self.validated:
            return "positive evidence matched while the baseline did not"
        return "; ".join(self.errors) or "evidence did not meet the promotion contract"


def _compile_patterns(patterns: list[str], label: str) -> tuple[list[re.Pattern[str]], list[str]]:
    compiled: list[re.Pattern[str]] = []
    errors: list[str] = []
    for index, pattern in enumerate(patterns):
        if not isinstance(pattern, str) or not pattern.strip():
            errors.append(f"{label}[{index}] must be a non-empty regex")
            continue
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE | re.DOTALL))
        except re.error as exc:
            errors.append(f"{label}[{index}] is invalid: {exc}")
    return compiled, errors


def validate_evidence(
    success_output: str,
    negative_output: str,
    *,
    success_patterns: list[str],
    negative_patterns: list[str],
) -> EvidenceValidation:
    """Validate a captured proof and negative control.

    At least one success pattern must occur in the positive output, at least
    one baseline pattern must occur in the negative output, and *none* of the
    success patterns may occur in the negative output.  Invalid regexes are
    rejected instead of silently downgraded to substring matching.
    """
    positive, positive_errors = _compile_patterns(success_patterns, "success_patterns")
    baseline, baseline_errors = _compile_patterns(negative_patterns, "negative_patterns")
    errors = [*positive_errors, *baseline_errors]
    if not positive:
        errors.append("at least one success pattern is required")
    if not baseline:
        errors.append("at least one negative-control pattern is required")
    if errors:
        return EvidenceValidation(validated=False, errors=tuple(errors))

    success_matches = tuple(
        pattern.pattern for pattern in positive if pattern.search(success_output)
    )
    negative_matches = tuple(
        pattern.pattern for pattern in baseline if pattern.search(negative_output)
    )
    noise_matches = tuple(
        pattern.pattern for pattern in positive if pattern.search(negative_output)
    )
    if not success_matches:
        errors.append("positive evidence did not match a success pattern")
    if not negative_matches:
        errors.append("negative control did not match a baseline pattern")
    if noise_matches:
        errors.append("negative control also matched a success pattern")
    return EvidenceValidation(
        validated=not errors,
        success_matches=success_matches,
        negative_matches=negative_matches,
        noise_matches=noise_matches,
        errors=tuple(errors),
    )


def _within_workspace(workspace: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("evidence paths must be workspace-relative")
    root = workspace.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence path escapes the workspace") from exc
    return resolved


def validate_evidence_files(
    workspace: Path,
    *,
    success_path: str,
    negative_path: str,
    success_patterns: list[str],
    negative_patterns: list[str],
) -> EvidenceValidation:
    """Load two workspace-relative evidence files and validate their signals."""
    errors: list[str] = []
    try:
        success_file = _within_workspace(workspace, success_path)
        negative_file = _within_workspace(workspace, negative_path)
    except ValueError as exc:
        return EvidenceValidation(validated=False, errors=(str(exc),))
    if success_file == negative_file:
        return EvidenceValidation(
            validated=False,
            errors=("positive evidence and negative control must be distinct files",),
        )
    for label, path in (("positive evidence", success_file), ("negative control", negative_file)):
        if not path.is_file():
            errors.append(f"{label} file does not exist: {path.name}")
    if errors:
        return EvidenceValidation(validated=False, errors=tuple(errors))
    return validate_evidence(
        success_file.read_text(encoding="utf-8", errors="replace"),
        negative_file.read_text(encoding="utf-8", errors="replace"),
        success_patterns=success_patterns,
        negative_patterns=negative_patterns,
    )
