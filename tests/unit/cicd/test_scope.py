"""Tests for diff-scope resolution against real git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from decepticon.cicd.scope import DiffScope, DiffScopeError, resolve_diff_scope


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _run(["git", "init", "-q", "-b", "main"], r)
    _run(["git", "config", "user.email", "t@e.com"], r)
    _run(["git", "config", "user.name", "T"], r)
    (r / "a.py").write_text("print('a')\n")
    (r / "keep.py").write_text("print('keep')\n")
    _run(["git", "add", "."], r)
    _run(["git", "commit", "-q", "-m", "base"], r)
    return r


def test_resolve_scope_on_feature_branch(repo: Path):
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "b.py").write_text("print('b')\n")
    (repo / "a.py").write_text("print('a modified')\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "feat changes"], repo)

    scope = resolve_diff_scope(base="main", head="HEAD", repo_path=repo)
    assert isinstance(scope, DiffScope)
    assert scope.changed_files == ["a.py", "b.py"]
    assert "keep.py" not in scope.changed_files
    assert not scope.is_empty


def test_scope_excludes_deletions(repo: Path):
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "keep.py").unlink()
    (repo / "c.py").write_text("print('c')\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "del + add"], repo)

    scope = resolve_diff_scope(base="main", repo_path=repo)
    assert "c.py" in scope.changed_files
    assert "keep.py" not in scope.changed_files  # deletions excluded


def test_scope_uses_merge_base_not_raw_diff(repo: Path):
    """A branch forked before main advanced only reports its own delta."""
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "feat.py").write_text("print('feat')\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "feat"], repo)

    # main advances independently
    _run(["git", "checkout", "-q", "main"], repo)
    (repo / "main-only.py").write_text("print('main')\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "main advance"], repo)

    _run(["git", "checkout", "-q", "feat"], repo)
    scope = resolve_diff_scope(base="main", head="feat", repo_path=repo)
    # Only the branch's own file — main-only.py is on the other side of
    # the merge base and must not be attributed to this PR.
    assert scope.changed_files == ["feat.py"]
    assert "main-only.py" not in scope.changed_files


def test_scope_empty_when_no_changes(repo: Path):
    _run(["git", "checkout", "-q", "-b", "noop"], repo)
    scope = resolve_diff_scope(base="main", head="HEAD", repo_path=repo)
    assert scope.is_empty
    assert scope.changed_files == []


def test_scope_filter_by_suffix(repo: Path):
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "x.py").write_text("1\n")
    (repo / "y.md").write_text("doc\n")
    (repo / "z.ts").write_text("1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "mixed"], repo)

    scope = resolve_diff_scope(base="main", repo_path=repo)
    py_only = scope.filter(suffixes=(".py",))
    assert py_only == ["x.py"]
    code = scope.filter(suffixes=(".py", ".ts"))
    assert sorted(code) == ["x.py", "z.ts"]
    assert len(scope.filter()) == 3


def test_scope_env_fallback(repo: Path, monkeypatch):
    monkeypatch.setenv("DECEPTICON_DIFF_BASE", "main")
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "n.py").write_text("1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "n"], repo)
    scope = resolve_diff_scope(repo_path=repo)  # no explicit base
    assert scope.base == "main"
    assert scope.changed_files == ["n.py"]


def test_scope_bad_base_raises(repo: Path):
    with pytest.raises(DiffScopeError, match="merge-base"):
        resolve_diff_scope(base="does-not-exist", repo_path=repo)


def test_scope_non_repo_raises(tmp_path: Path):
    notrepo = tmp_path / "plain"
    notrepo.mkdir()
    with pytest.raises(DiffScopeError, match="not inside a git repo"):
        resolve_diff_scope(base="main", repo_path=notrepo)


def test_scope_to_dict_roundtrips(repo: Path):
    _run(["git", "checkout", "-q", "-b", "feat"], repo)
    (repo / "d.py").write_text("1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "d"], repo)
    d = resolve_diff_scope(base="main", repo_path=repo).to_dict()
    assert d["count"] == 1
    assert d["changed_files"] == ["d.py"]
    assert d["base"] == "main"
