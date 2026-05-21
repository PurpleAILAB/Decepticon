"""Diff-scope resolution — match Strix's ``--scope-mode diff``.

Given a base ref (``origin/main`` by default) the resolver computes the
set of files a branch changed relative to the merge base. The engagement
can then restrict static analysis to those paths so a PR scan is fast and
only flags regressions the PR itself introduced.

Pure ``git`` shell-out — no GitPython. Works in detached-HEAD CI
checkouts as long as ``fetch-depth: 0`` (full history) was used, which
the bundled GitHub Action documents.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class DiffScopeError(RuntimeError):
    """Raised when the diff scope cannot be resolved (bad ref, shallow clone)."""


@dataclass
class DiffScope:
    """Resolved diff scope for a PR-style run."""

    base: str
    head: str
    merge_base: str
    changed_files: list[str] = field(default_factory=list)
    repo_root: Path = field(default_factory=lambda: Path("."))

    @property
    def is_empty(self) -> bool:
        return not self.changed_files

    def filter(self, *, suffixes: tuple[str, ...] | None = None) -> list[str]:
        """Return changed files, optionally restricted to given suffixes."""
        if suffixes is None:
            return list(self.changed_files)
        return [f for f in self.changed_files if f.endswith(suffixes)]

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "head": self.head,
            "merge_base": self.merge_base,
            "changed_files": list(self.changed_files),
            "repo_root": str(self.repo_root),
            "count": len(self.changed_files),
        }


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise DiffScopeError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def _resolve_repo_root(start: str | Path) -> Path:
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=Path(start))
    except DiffScopeError as exc:
        raise DiffScopeError(f"not inside a git repo: {start}") from exc
    return Path(root)


def resolve_diff_scope(
    *,
    base: str | None = None,
    head: str = "HEAD",
    repo_path: str | Path = ".",
) -> DiffScope:
    """Compute the set of files changed between ``base`` and ``head``.

    Args:
        base: Base ref to diff against. ``None`` falls back to
            ``$DECEPTICON_DIFF_BASE`` then ``origin/main``.
        head: Head ref (default ``HEAD``).
        repo_path: Any path inside the target repo.

    Returns:
        A :class:`DiffScope`. ``changed_files`` are repo-root-relative
        POSIX paths, sorted, with deletions excluded (a deleted file has
        nothing to scan).

    Raises:
        DiffScopeError: bad ref, shallow clone without the base, or not a
            git repo.
    """
    base = base or os.environ.get("DECEPTICON_DIFF_BASE") or "origin/main"
    root = _resolve_repo_root(repo_path)

    # Resolve the merge base so a long-lived branch doesn't surface every
    # change that landed on main since it forked — only the branch's own
    # delta. ``--fork-point`` falls back to plain merge-base when reflog
    # data is unavailable (typical in CI checkouts).
    try:
        merge_base = _git(["merge-base", base, head], cwd=root)
    except DiffScopeError as exc:
        raise DiffScopeError(
            f"could not find merge-base of {base!r} and {head!r} — "
            "ensure the CI checkout used fetch-depth: 0 (full history)"
        ) from exc

    raw = _git(
        ["diff", "--name-only", "--diff-filter=d", f"{merge_base}..{head}"],
        cwd=root,
    )
    files = sorted(line.strip() for line in raw.splitlines() if line.strip())
    return DiffScope(
        base=base,
        head=head,
        merge_base=merge_base,
        changed_files=files,
        repo_root=root,
    )


__all__ = ["DiffScope", "DiffScopeError", "resolve_diff_scope"]
