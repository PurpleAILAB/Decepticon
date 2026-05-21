"""Tests for the PR autofix delivery."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from decepticon.tools.research.pr_autofix import (
    PRAutofixError,
    PRPlan,
    open_autofix_pr,
    slug_for_branch,
)

# ── slug_for_branch ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Reflected XSS in /search", "reflected-xss-in-search"),
        ("CVE-2026-12345", "cve-2026-12345"),
        ("v1.2.3", "v1.2.3"),
        ("path with /slashes/", "path-with-slashes"),
        ("", "unnamed"),
        ("---", "unnamed"),
        ("a" * 100, "a" * 64),
    ],
    ids=["typical", "cve", "version", "slashes", "empty", "dashes-only", "long"],
)
def test_slug_for_branch(raw, expected):
    assert slug_for_branch(raw) == expected


# ── helpers ──────────────────────────────────────────────────────


def _init_repo(tmp_path: Path) -> Path:
    """Initialise a real local git repo so the planner can resolve paths."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "vuln.py").write_text("def login(p): return p == 'admin'\n")
    subprocess.run(["git", "add", "vuln.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


_FINDING = {
    "id": "F-001",
    "title": "Auth bypass: weak password compare",
    "severity": "high",
    "cvss_score": 7.4,
    "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
    "summary": "Login accepts hardcoded admin string.",
}

_DIFF = """\
diff --git a/vuln.py b/vuln.py
index 0000000..1111111 100644
--- a/vuln.py
+++ b/vuln.py
@@ -1 +1 @@
-def login(p): return p == 'admin'
+def login(p): return False  # disabled
"""


# ── plan-only path (no execute) ──────────────────────────────────


def test_plan_returns_pr_plan(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
        execute=False,
    )
    assert isinstance(plan, PRPlan)
    assert plan.branch == "decepticon/fix-f-001"
    assert plan.base == "main"
    assert plan.title.startswith("fix(security): Auth bypass")
    assert plan.repo_path == repo


def test_plan_writes_patch_to_disk(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
        execute=False,
    )
    assert plan.patch_path.exists()
    body = plan.patch_path.read_text()
    assert body.startswith("diff --git a/vuln.py")
    assert body.endswith("\n")


def test_plan_does_not_mutate_repo(tmp_path):
    repo = _init_repo(tmp_path)
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
        execute=False,
    )
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_before == head_after
    branches = subprocess.run(
        ["git", "branch"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "decepticon/fix-f-001" not in branches


def test_plan_commands_in_expected_order(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(finding=_FINDING, diff_text=_DIFF, repo_path=repo, base_branch="main")
    cmd_strs = [" ".join(c) for c in plan.commands]
    assert cmd_strs[0].startswith("git fetch origin main")
    assert cmd_strs[1].startswith("git checkout -B decepticon/fix-f-001")
    assert cmd_strs[2].startswith("git apply --index")
    assert cmd_strs[3].startswith("git commit -m fix(security)")
    assert cmd_strs[4].startswith("git push -u origin decepticon/fix-f-001")
    assert cmd_strs[5].startswith("gh pr create --base main")


def test_plan_to_dict_serialises_all_fields(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
    )
    info = plan.to_dict()
    assert info["branch"] == "decepticon/fix-f-001"
    assert info["base"] == "main"
    assert "git apply" in " ".join(info["commands"])


def test_plan_uses_explicit_base(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="develop",
    )
    assert plan.base == "develop"


def test_plan_env_base_used_when_no_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("DECEPTICON_AUTOFIX_BASE", "release/1.x")
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch=None,
    )
    assert plan.base == "release/1.x"


# ── PR body composition ─────────────────────────────────────────


def test_pr_body_includes_finding_metadata(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
        poc_text="curl -X POST /login -d 'admin'",
        repro_text="1. POST /login\n2. Observe 200 with admin session",
    )
    body = plan.body
    assert "Auth bypass" in body
    assert "**Severity:** HIGH" in body
    assert "CVSS:** 7.4" in body
    assert "F-001" in body
    assert "POST /login" in body
    assert "curl -X POST /login" in body


def test_pr_body_skips_optional_sections(tmp_path):
    repo = _init_repo(tmp_path)
    plan = open_autofix_pr(
        finding={"id": "F-x", "title": "X", "severity": "low"},
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
    )
    body = plan.body
    assert "### Reproduction" not in body
    assert "### Proof of Concept" not in body
    assert "### Verification" in body  # always included


def test_pr_title_capped_at_72_chars(tmp_path):
    repo = _init_repo(tmp_path)
    long_title = "A" * 200
    plan = open_autofix_pr(
        finding={"id": "F-y", "title": long_title, "severity": "high"},
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
    )
    assert len(plan.title) <= 72


# ── error paths ─────────────────────────────────────────────────


def test_plan_rejects_non_git_directory(tmp_path):
    notrepo = tmp_path / "notrepo"
    notrepo.mkdir()
    with pytest.raises(PRAutofixError, match="not a git repo"):
        open_autofix_pr(
            finding=_FINDING,
            diff_text=_DIFF,
            repo_path=notrepo,
        )


# ── execute path (uses real git, fakes gh) ──────────────────────


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: fake `gh` is a bash script and PATH uses ':' separator",
)
def test_execute_applies_patch_and_pushes_to_local_remote(tmp_path, monkeypatch):
    """End-to-end execution against a local origin + a fake `gh` script.

    Validates the autofix actually applies the diff, commits it under the
    expected branch, and "creates" a PR (the fake gh records the call and
    prints a stub URL the planner captures into ``pr_url``).
    """
    # Set up bare origin so `git push` can target it without a network.
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = _init_repo(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo, check=True)

    # Fake gh script writes to a log so we can assert it was called.
    fake_gh_dir = tmp_path / "bin"
    fake_gh_dir.mkdir()
    log_path = tmp_path / "gh.log"
    fake_gh = fake_gh_dir / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> {log_path}\n'
        'echo "https://github.com/example/repo/pull/42"\n'
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_gh_dir}:{__import__('os').environ['PATH']}")

    plan = open_autofix_pr(
        finding=_FINDING,
        diff_text=_DIFF,
        repo_path=repo,
        base_branch="main",
        execute=True,
    )
    # PR URL captured from fake gh stdout
    assert plan.pr_url == "https://github.com/example/repo/pull/42"
    # Branch exists on origin
    out = subprocess.run(
        ["git", "ls-remote", str(origin), "decepticon/fix-f-001"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "decepticon/fix-f-001" in out
    # Working tree carries the patched line on the new branch
    head_file = subprocess.run(
        ["git", "show", "decepticon/fix-f-001:vuln.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "return False" in head_file
    # Fake gh was actually invoked
    assert log_path.exists()
    assert "pr create" in log_path.read_text()


def test_execute_propagates_git_apply_failure(tmp_path):
    repo = _init_repo(tmp_path)
    bad_diff = "diff --git a/missing.py b/missing.py\n@@ broken @@\n"
    with pytest.raises(PRAutofixError) as exc:
        open_autofix_pr(
            finding=_FINDING,
            diff_text=bad_diff,
            repo_path=repo,
            base_branch="main",
            execute=True,
        )
    assert "command failed" in str(exc.value)
