"""Tests for HackerOne disclosed-report corpus indexer."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.h1_corpus import (
    BugReport,
    load_corpus,
    parse_tops_file,
    search,
)

_TOPS_BY_BOUNTY = """# Top reports by bounty

| Title | Program | Bounty | Severity | CWE |
|-------|---------|--------|----------|-----|
| [SSRF on api.example.com](https://hackerone.com/reports/11111) | Example | $20,000 | critical | CWE-918 |
| [IDOR on profile endpoint](https://hackerone.com/reports/22222) | Example | $5,000 | high | CWE-639 |
| [Self-XSS on blog](https://hackerone.com/reports/33333) | Blog | $100 | low | CWE-79 |
"""

_TOPS_BY_CWE = """# Top reports by CWE

## CWE-918 — Server-Side Request Forgery

| Title | Program | Bounty |
|-------|---------|--------|
| [SSRF on api.example.com](https://hackerone.com/reports/11111) | Example | $20,000 |

## CWE-79 — Cross-Site Scripting

| Title | Program | Bounty |
|-------|---------|--------|
| [Self-XSS on blog](https://hackerone.com/reports/33333) | Blog | $100 |
"""


def _build_cache(root: Path) -> Path:
    repo = root / "hackerone-reports"
    repo.mkdir(parents=True)
    (repo / "tops_by_bounty.md").write_text(_TOPS_BY_BOUNTY, encoding="utf-8")
    (repo / "tops_by_cwe.md").write_text(_TOPS_BY_CWE, encoding="utf-8")
    return repo


class TestParseTopsFile:
    def test_parses_bounty_table(self, tmp_path: Path) -> None:
        repo = _build_cache(tmp_path)
        rows = parse_tops_file(repo / "tops_by_bounty.md")
        assert len(rows) == 3
        ssrf = next(r for r in rows if "SSRF" in r.title)
        assert ssrf.url == "https://hackerone.com/reports/11111"
        assert ssrf.bounty == 20000.0
        assert ssrf.severity == "critical"
        assert ssrf.cwe == "CWE-918"

    def test_parses_cwe_file_with_sections(self, tmp_path: Path) -> None:
        repo = _build_cache(tmp_path)
        rows = parse_tops_file(repo / "tops_by_cwe.md")
        assert len(rows) == 2


class TestLoadCorpus:
    def test_absent_cache(self, tmp_path: Path) -> None:
        assert load_corpus(root=tmp_path) == []

    def test_dedups_across_files(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        corpus = load_corpus(root=tmp_path)
        urls = [r.url for r in corpus]
        assert len(urls) == len(set(urls))
        assert "https://hackerone.com/reports/11111" in urls


class TestSearch:
    def test_filter_by_cwe(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search(cwe="CWE-918", root=tmp_path)
        assert len(hits) == 1
        assert hits[0].title == "SSRF on api.example.com"

    def test_filter_by_min_bounty(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search(min_bounty=1000, root=tmp_path)
        assert all(r.bounty >= 1000 for r in hits)
        # Sorted descending by bounty when min_bounty > 0
        bounties = [r.bounty for r in hits]
        assert bounties == sorted(bounties, reverse=True)

    def test_filter_by_severity(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search(severity="low", root=tmp_path)
        assert len(hits) == 1
        assert hits[0].severity == "low"

    def test_filter_by_keyword(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search(keyword="ssrf", root=tmp_path)
        assert any("SSRF" in r.title for r in hits)

    def test_cwe_normalisation(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search(cwe="918", root=tmp_path)
        assert len(hits) == 1

    def test_in_memory_corpus(self) -> None:
        reports = [
            BugReport(title="A", url="u1", cwe="CWE-79", bounty=500),
            BugReport(title="B", url="u2", cwe="CWE-918", bounty=2000),
        ]
        hits = search(reports=reports, min_bounty=1000)
        assert len(hits) == 1
        assert hits[0].cwe == "CWE-918"
