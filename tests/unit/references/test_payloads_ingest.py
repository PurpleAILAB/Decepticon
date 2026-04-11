"""Tests for PayloadsAllTheThings ingestion."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.payloads import BUNDLED_PAYLOADS
from decepticon.tools.references.payloads_ingest import (
    classify_dir,
    iter_ingested_payloads,
    merged_payloads,
    search_merged,
)


def _build_fake_cache(root: Path) -> Path:
    """Lay out a minimal PayloadsAllTheThings clone for tests."""
    repo = root / "payloads-all-the-things"
    sqli = repo / "SQL Injection" / "Intruder"
    sqli.mkdir(parents=True)
    (sqli / "mysql.txt").write_text(
        "# header comment\n' OR 1=1-- -\n' UNION SELECT null,null-- -\n\n' AND SLEEP(5)-- -\n",
        encoding="utf-8",
    )
    (repo / "SQL Injection" / "README.md").write_text("# SQLi methodology\n", encoding="utf-8")

    ssrf = repo / "Server Side Request Forgery" / "Intruder"
    ssrf.mkdir(parents=True)
    (ssrf / "bypass.txt").write_text(
        "http://127.0.0.1/\nhttp://localhost/admin\nhttp://0.0.0.0/\n",
        encoding="utf-8",
    )

    # Folder that should be skipped
    skip = repo / "Methodology and Resources"
    skip.mkdir(parents=True)
    (skip / "note.md").write_text("ignored\n", encoding="utf-8")

    # Unknown folder — should slugify instead of skip
    novel = repo / "Novel Class" / "Intruder"
    novel.mkdir(parents=True)
    (novel / "a.txt").write_text("payload-xyz\n", encoding="utf-8")

    return repo


class TestClassifyDir:
    def test_known_folder(self) -> None:
        assert classify_dir("SQL Injection") == "sqli"
        assert classify_dir("SSRF") == "ssrf"
        assert classify_dir("XSS Injection") == "xss"
        assert classify_dir("Insecure Deserialization") == "deser"

    def test_skip_folder(self) -> None:
        assert classify_dir("Methodology and Resources") is None
        assert classify_dir(".git") is None

    def test_unknown_folder_slugified(self) -> None:
        assert classify_dir("Some Brand New Class") == "some-brand-new-class"


class TestIterIngested:
    def test_absent_cache_returns_empty(self, tmp_path: Path) -> None:
        assert iter_ingested_payloads(root=tmp_path) == []

    def test_walks_cache(self, tmp_path: Path) -> None:
        _build_fake_cache(tmp_path)
        rows = iter_ingested_payloads(root=tmp_path)
        classes = {r.vuln_class for r in rows}
        assert "sqli" in classes
        assert "ssrf" in classes
        assert "novel-class" in classes
        # Methodology folder skipped
        assert "methodology-and-resources" not in classes

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        _build_fake_cache(tmp_path)
        rows = iter_ingested_payloads(root=tmp_path)
        sqli = [r for r in rows if r.vuln_class == "sqli"]
        # Comment header + README marker both excluded from payloads
        assert not any("header comment" in r.payload for r in sqli)
        # README is still present as a methodology marker
        assert any("methodology" in r.title.lower() for r in sqli)

    def test_per_file_limit_respected(self, tmp_path: Path) -> None:
        repo = tmp_path / "payloads-all-the-things" / "XSS" / "Intruder"
        repo.mkdir(parents=True)
        (repo / "big.txt").write_text("\n".join(f"<script>a{i}</script>" for i in range(500)))
        rows = iter_ingested_payloads(root=tmp_path, per_file_limit=10)
        xss = [r for r in rows if r.vuln_class == "xss"]
        assert len(xss) <= 10


class TestMergedPayloads:
    def test_bundled_included(self, tmp_path: Path) -> None:
        merged = merged_payloads(root=tmp_path)
        bundled_count = len(BUNDLED_PAYLOADS)
        assert len(merged) >= bundled_count

    def test_merge_adds_ingested(self, tmp_path: Path) -> None:
        _build_fake_cache(tmp_path)
        merged = merged_payloads(root=tmp_path)
        assert len(merged) > len(BUNDLED_PAYLOADS)

    def test_dedup_same_payload(self, tmp_path: Path) -> None:
        repo = tmp_path / "payloads-all-the-things" / "XSS" / "Intruder"
        repo.mkdir(parents=True)
        # Inject a payload that is already in BUNDLED_PAYLOADS
        (repo / "dup.txt").write_text("<script>alert(document.domain)</script>\n")
        merged = merged_payloads(root=tmp_path)
        dups = [p for p in merged if p.payload == "<script>alert(document.domain)</script>"]
        assert len(dups) == 1


class TestSearchMerged:
    def test_filter_by_class(self, tmp_path: Path) -> None:
        _build_fake_cache(tmp_path)
        hits = search_merged(vuln_class="ssrf", root=tmp_path)
        assert all(h.vuln_class == "ssrf" for h in hits)

    def test_filter_by_keyword(self, tmp_path: Path) -> None:
        _build_fake_cache(tmp_path)
        hits = search_merged(vuln_class="ssrf", keyword="127", root=tmp_path)
        assert len(hits) >= 1
        assert all("127" in (h.title + h.payload + h.notes) for h in hits)
