"""Tests for the AllAboutBugBounty methodology retriever."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.methodology import (
    classes_present,
    classify_filename,
    load_chapters,
    lookup,
)


def _build_cache(root: Path) -> Path:
    repo = root / "all-about-bug-bounty"
    repo.mkdir(parents=True)
    (repo / "SSRF.md").write_text(
        "# SSRF Methodology\n\nStep 1: identify URL fetching endpoints.\nStep 2: try metadata URLs.\n",
        encoding="utf-8",
    )
    (repo / "IDOR.md").write_text(
        "# IDOR\n\nLook for predictable IDs in URLs and JSON.\n",
        encoding="utf-8",
    )
    (repo / "Account Takeover.md").write_text(
        "# ATO chapter\n\nCheck password reset tokens.\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("root readme", encoding="utf-8")
    return repo


class TestClassifyFilename:
    def test_known(self) -> None:
        assert classify_filename("SSRF.md") == "ssrf"
        assert classify_filename("IDOR.md") == "idor"
        assert classify_filename("Account Takeover.md") == "ato"

    def test_unknown_slugified(self) -> None:
        assert classify_filename("New Cool Bug Class.md") == "new-cool-bug-class"


class TestLoadChapters:
    def test_absent_cache(self, tmp_path: Path) -> None:
        assert load_chapters(root=tmp_path) == []

    def test_walks_cache(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        chapters = load_chapters(root=tmp_path)
        classes = {c.vuln_class for c in chapters}
        assert "ssrf" in classes
        assert "idor" in classes
        assert "ato" in classes

    def test_skips_readme(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        chapters = load_chapters(root=tmp_path)
        assert not any(c.title.lower() == "readme" for c in chapters)


class TestLookup:
    def test_lookup_by_class(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = lookup("ssrf", root=tmp_path)
        assert len(hits) == 1
        assert "metadata" in hits[0]["excerpt"].lower()

    def test_lookup_by_title_fragment(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = lookup("account takeover", root=tmp_path)
        assert len(hits) == 1

    def test_empty_when_no_match(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        assert lookup("not-a-real-class", root=tmp_path) == []

    def test_excerpt_truncation(self, tmp_path: Path) -> None:
        repo = tmp_path / "all-about-bug-bounty"
        repo.mkdir(parents=True)
        (repo / "SQL Injection.md").write_text("X" * 5000, encoding="utf-8")
        hits = lookup("sqli", excerpt_chars=100, root=tmp_path)
        assert "[truncated]" in hits[0]["excerpt"]


class TestClassesPresent:
    def test_absent(self, tmp_path: Path) -> None:
        assert classes_present(root=tmp_path) == []

    def test_sorted(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        classes = classes_present(root=tmp_path)
        assert classes == sorted(classes)
