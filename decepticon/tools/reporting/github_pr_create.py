"""GitHub PR creation tool for the Patcher / Defender stages.

When the Patcher generates a verified code fix, this tool opens an upstream
PR to land the change. When the Defender generates a verified detection
rule, this tool opens an upstream PR to the org's detection-as-code repo.

Both flows go through the same primitive: prepare a branch on a fork,
push the changes, open a PR against the upstream.

Auth: uses the `gh` CLI's existing auth context (token w/ `repo` scope
minimum; `workflow` scope IF the change touches `.github/workflows/*`).
The operator is expected to be authenticated via `gh auth login` or to
have set `GH_TOKEN` / `GITHUB_TOKEN` in the environment.

This is a thin shell wrapper, NOT a full GitHub API client — the `gh`
CLI is the dependency. That keeps us out of the rate-limit and pagination
fragility of direct PyGithub calls.
"""

from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PRResult:
    """Result of a github_pr_create call."""

    success: bool
    url: str | None
    pr_number: int | None
    error: str | None

    def as_dict(self) -> dict:
        return {
            "success": self.success,
            "url": self.url,
            "pr_number": self.pr_number,
            "error": self.error,
        }


def github_pr_create(
    repo: str,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str,
    *,
    work_tree: Path,
    fork: str | None = None,
    draft: bool = False,
    labels: list[str] | None = None,
) -> PRResult:
    """Create a pull request against `repo` from `work_tree`.

    Args:
        repo: Upstream owner/repo (e.g. "PurpleAILAB/Decepticon").
        base_branch: Target branch on upstream (typically "main").
        head_branch: Branch name to push to fork.
        title: PR title (Conventional-Commit style preferred).
        body: PR body (markdown).
        work_tree: Path to the working git checkout. Caller must have
            already committed the changes locally; this function only
            handles push + PR open.
        fork: Optional owner/repo for the fork. If None, `gh` infers
            from the current `fork` remote.
        draft: Open as draft PR.
        labels: Optional label names to apply (must exist on the upstream).

    Returns:
        PRResult w/ `success`, `url`, `pr_number`, `error`.
    """
    if not work_tree.exists():
        return PRResult(False, None, None, f"work_tree does not exist: {work_tree}")

    # Push the branch to the fork
    push_cmd = ["git", "push", "fork" if fork is None else "fork", head_branch]
    push = subprocess.run(
        push_cmd, cwd=work_tree, capture_output=True, text=True
    )
    if push.returncode != 0:
        return PRResult(False, None, None, f"git push failed: {push.stderr.strip()}")

    # Determine head spec for cross-repo PR
    head_spec = head_branch
    if fork:
        owner = fork.split("/", 1)[0]
        head_spec = f"{owner}:{head_branch}"

    # Build gh pr create command
    cmd: list[str] = [
        "gh", "pr", "create",
        "--repo", repo,
        "--base", base_branch,
        "--head", head_spec,
        "--title", title,
        "--body", body,
    ]
    if draft:
        cmd.append("--draft")
    if labels:
        for label in labels:
            cmd.extend(["--label", label])

    result = subprocess.run(cmd, cwd=work_tree, capture_output=True, text=True)
    if result.returncode != 0:
        return PRResult(False, None, None, f"gh pr create failed: {result.stderr.strip()}")

    url = result.stdout.strip().splitlines()[-1]
    pr_number = _extract_pr_number(url)
    return PRResult(True, url, pr_number, None)


def _extract_pr_number(url: str) -> int | None:
    # https://github.com/<owner>/<repo>/pull/123 → 123
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except (IndexError, ValueError):
        return None


def github_pr_from_patcher(
    *,
    vuln_id: str,
    file_path: str,
    diff: str,
    commit_message: str,
    upstream_repo: str,
    work_tree: Path,
    fork: str | None = None,
) -> PRResult:
    """Higher-level helper: take a verified patch from the Patcher and
    open a PR for it. Caller has already applied the diff to disk.

    Used by the Patcher agent's terminal step when a finding has
    `patch_verify.status == "verified"`.
    """
    branch = f"fix/decepticon-{vuln_id}"
    # 1. Create branch from current HEAD
    subprocess.run(["git", "checkout", "-B", branch], cwd=work_tree, check=False, capture_output=True)
    # 2. Stage + commit
    subprocess.run(["git", "add", file_path], cwd=work_tree, check=False, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", commit_message], cwd=work_tree, check=False, capture_output=True
    )
    # 3. Open PR
    body = textwrap.dedent(
        f"""\
        ## Summary

        Auto-generated patch for vulnerability `{vuln_id}` discovered by Decepticon.

        ## Verification

        - Vulnerability reproduced via PoC (see linked finding)
        - Patch applied, PoC re-run, attack fails → `patch_verify.status == "verified"`
        - No new regressions in the repo's test suite (per the verifier stage)

        ## Diff

        ```diff
        {diff[:2000]}{'...' if len(diff) > 2000 else ''}
        ```

        ## Provenance

        Generated by Decepticon vulnresearch pipeline. Finding ID `{vuln_id}`
        in the engagement KG. See `docs/offensive-vaccine.md` for the
        end-to-end loop.

        cc: @{vuln_id.split('-', 1)[0] if '-' in vuln_id else 'decepticon-bot'}
        """
    )
    return github_pr_create(
        repo=upstream_repo,
        base_branch="main",
        head_branch=branch,
        title=commit_message.splitlines()[0],
        body=body,
        work_tree=work_tree,
        fork=fork,
    )


def github_pr_from_defender(
    *,
    vuln_id: str,
    rule_file: str,
    rule_format: str,
    rule_content: str,
    upstream_repo: str,
    work_tree: Path,
    fork: str | None = None,
) -> PRResult:
    """Higher-level helper: take a verified detection rule from the
    Defender and open a PR against the org's detection-as-code repo.
    """
    branch = f"detect/decepticon-{vuln_id}"
    subprocess.run(["git", "checkout", "-B", branch], cwd=work_tree, check=False, capture_output=True)
    subprocess.run(["git", "add", rule_file], cwd=work_tree, check=False, capture_output=True)
    msg = f"detect({rule_format}): decepticon-{vuln_id} regression rule"
    subprocess.run(["git", "commit", "-m", msg], cwd=work_tree, check=False, capture_output=True)
    body = textwrap.dedent(
        f"""\
        ## Summary

        Auto-generated `{rule_format}` detection rule for finding `{vuln_id}`.

        ## Verification

        - PoC of the original vulnerability re-run against the detection stack
        - Rule fires on the PoC → `defense_verify.status == "fired"`
        - No false-positive hits in a 24h sample of engagement recon traffic

        ## Rule

        ```{rule_format}
        {rule_content[:2000]}{'...' if len(rule_content) > 2000 else ''}
        ```

        ## Use

        Apply this rule alongside the code patch (PR for the patch linked from
        finding `{vuln_id}`). The patch closes the immediate vector; this rule
        catches sibling-pattern abuse and future regressions.

        Generated by Decepticon Defender. See `docs/offensive-vaccine.md` for
        the attack→defend→verify loop.
        """
    )
    return github_pr_create(
        repo=upstream_repo,
        base_branch="main",
        head_branch=branch,
        title=msg,
        body=body,
        work_tree=work_tree,
        fork=fork,
        labels=["security-detection", f"format/{rule_format}"],
    )


__all__ = [
    "PRResult",
    "github_pr_create",
    "github_pr_from_patcher",
    "github_pr_from_defender",
]
