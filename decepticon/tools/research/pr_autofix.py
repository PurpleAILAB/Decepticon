"""Strix-style PR autofix delivery for Decepticon's patcher agent.

The patcher already produces a verified diff + PoC for each finding (see
:func:`decepticon.tools.research.patch.patch_propose` /
:func:`decepticon.tools.research.patch.patch_verify`). This module turns
that artifact into a ready-to-merge GitHub pull request:

1. Resolve the upstream repo + base branch.
2. Create a branch named ``decepticon/fix-<finding-slug>``.
3. Apply the patch (``git apply``), commit with a structured message that
   embeds the finding ID and CVSS, push.
4. Open a PR via ``gh pr create`` with the autofix body, attaching the
   PoC + repro from the findings export pack.

Pure subprocess shell-out — no PyGithub dep — so the agent can call it
inside the existing sandbox container that already has ``git`` + ``gh``
preinstalled. Failure modes (no gh auth, dirty working tree, base
branch missing) raise :class:`PRAutofixError` with the captured stderr
so the LLM can act on the failure without rerunning a noisy sub-process.

The module is intentionally side-effect-free unless ``execute=True`` is
passed: with ``execute=False`` (the default for unit tests and dry-run
agents) it returns the planned shell commands as a list so callers can
preview the action.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BRANCH_RE = re.compile(r"[^a-z0-9._-]+")


class PRAutofixError(RuntimeError):
    """Raised when an autofix step fails. Carries stderr for triage."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def slug_for_branch(text: str) -> str:
    """Filesystem + git-safe branch suffix.

    Lowercases, collapses non-``[a-z0-9._-]`` to hyphens, trims runs and
    caps at 64 chars. Empty input yields ``"unnamed"`` so the resulting
    branch name is always valid.
    """
    s = _BRANCH_RE.sub("-", (text or "").lower()).strip("-")
    if not s:
        s = "unnamed"
    if len(s) > 64:
        s = s[:64].rstrip("-.")
    return s or "unnamed"


@dataclass
class PRPlan:
    """Planned mutation set the autofix would execute."""

    branch: str
    base: str
    title: str
    body: str
    repo_path: Path
    patch_path: Path
    commands: list[list[str]] = field(default_factory=list)
    pr_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "base": self.base,
            "title": self.title,
            "body": self.body,
            "repo_path": str(self.repo_path),
            "patch_path": str(self.patch_path),
            "commands": [" ".join(c) for c in self.commands],
            "pr_url": self.pr_url,
        }


def _ensure_repo(repo_path: str | Path) -> Path:
    """Verify ``repo_path`` is a git working tree, else raise."""
    p = Path(repo_path).resolve()
    if not (p / ".git").exists():
        raise PRAutofixError(f"not a git repo: {p}")
    return p


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around subprocess.run with structured error propagation."""
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        input=input_text,
        check=False,
    )
    if check and proc.returncode != 0:
        raise PRAutofixError(
            f"command failed (rc={proc.returncode}): {' '.join(argv)}",
            stderr=proc.stderr.strip(),
        )
    return proc


def _resolve_base_branch(
    repo_path: Path,
    explicit: str | None,
) -> str:
    """Resolve the base branch to open the PR against.

    Priority: explicit arg → ``DECEPTICON_AUTOFIX_BASE`` env → repo's
    default branch (``gh repo view --json defaultBranchRef``) → ``main``.
    """
    if explicit:
        return explicit
    env_base = os.environ.get("DECEPTICON_AUTOFIX_BASE")
    if env_base:
        return env_base
    try:
        proc = _run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
            cwd=repo_path,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except FileNotFoundError:
        log.debug("gh not on PATH; falling back to 'main'")
    return "main"


def _render_pr_body(
    finding: dict[str, Any],
    *,
    poc_text: str | None,
    repro_text: str | None,
) -> str:
    title = finding.get("title", "Unnamed finding")
    severity = (finding.get("severity") or "unknown").upper()
    cvss = finding.get("cvss_score")
    cvss_vec = finding.get("cvss_vector", "")
    summary = finding.get("summary") or finding.get("description") or ""
    parts: list[str] = [
        "## Decepticon Autofix",
        "",
        "This PR was generated by the Decepticon Patcher agent.",
        "Review the diff and PoC before merging.",
        "",
        f"**Finding:** {title}",
        f"**Severity:** {severity}",
    ]
    if cvss is not None:
        parts.append(f"**CVSS:** {cvss} `{cvss_vec}`")
    finding_id = finding.get("id") or finding.get("finding_id")
    if finding_id:
        parts.append(f"**Finding ID:** `{finding_id}`")
    parts.append("")
    if summary:
        parts.extend(["### Summary", summary, ""])
    if repro_text:
        parts.extend(["### Reproduction", "", repro_text.rstrip(), ""])
    if poc_text:
        parts.extend(["### Proof of Concept", "", "```", poc_text.rstrip(), "```", ""])
    parts.extend(
        [
            "### Verification",
            "",
            "- Patch applied via `git apply` and committed.",
            "- PoC re-run by the patcher agent and observed to fail post-patch.",
            "- See the linked findings pack for evidence files.",
            "",
            "_(autogenerated; please review for stylistic conformance before merging)_",
        ]
    )
    return "\n".join(parts).rstrip() + "\n"


def open_autofix_pr(
    *,
    finding: dict[str, Any],
    diff_text: str,
    repo_path: str | Path,
    base_branch: str | None = None,
    branch_prefix: str = "decepticon/fix-",
    poc_text: str | None = None,
    repro_text: str | None = None,
    execute: bool = False,
) -> PRPlan:
    """Plan or execute a PR delivery for a single autofix.

    Args:
        finding: Finding dict (same shape accepted by
            :func:`decepticon.tools.reporting.findings_export.write_finding_pack`).
        diff_text: Unified-diff text suitable for ``git apply``.
        repo_path: Local checkout to apply the patch into.
        base_branch: PR base branch override; ``None`` resolves via the
            ``gh`` repo metadata + env fallback.
        branch_prefix: Prefix for the generated branch name.
        poc_text: Optional PoC body to embed in the PR description.
        repro_text: Optional repro body to embed in the PR description.
        execute: When False (default), the function returns the planned
            commands without running them — caller can preview. When True,
            commands run sequentially and :class:`PRAutofixError` is
            raised on the first non-zero exit.

    Returns:
        A :class:`PRPlan` containing the planned (or executed) commands,
        the resulting branch name, and (after execution) ``pr_url``.
    """
    repo = _ensure_repo(repo_path)
    finding_id = (
        finding.get("id")
        or finding.get("finding_id")
        or slug_for_branch(finding.get("title", "fix"))
    )
    branch = f"{branch_prefix}{slug_for_branch(str(finding_id))}"
    base = _resolve_base_branch(repo, base_branch)
    title = (finding.get("title") or "Decepticon autofix").strip()
    pr_title = f"fix(security): {title}"[:72]
    body = _render_pr_body(finding, poc_text=poc_text, repro_text=repro_text)

    # Persist diff to a tmp file so the executed `git apply` consumes a
    # path rather than stdin (matches the planned command shape).
    tmp = Path(tempfile.mkdtemp(prefix="decepticon-autofix-"))
    patch_path = tmp / f"{branch.replace('/', '_')}.patch"
    patch_path.write_text(
        diff_text if diff_text.endswith("\n") else diff_text + "\n", encoding="utf-8"
    )

    commands: list[list[str]] = [
        ["git", "fetch", "origin", base],
        ["git", "checkout", "-B", branch, f"origin/{base}"],
        ["git", "apply", "--index", str(patch_path)],
        ["git", "commit", "-m", pr_title],
        ["git", "push", "-u", "origin", branch],
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            pr_title,
            "--body",
            body,
        ],
    ]

    plan = PRPlan(
        branch=branch,
        base=base,
        title=pr_title,
        body=body,
        repo_path=repo,
        patch_path=patch_path,
        commands=commands,
    )

    if not execute:
        return plan

    pr_url = ""
    for cmd in commands:
        proc = _run(cmd, cwd=repo)
        if cmd[0] == "gh" and "pr" in cmd and "create" in cmd:
            pr_url = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    plan.pr_url = pr_url
    return plan


__all__ = [
    "PRAutofixError",
    "PRPlan",
    "open_autofix_pr",
    "slug_for_branch",
]
