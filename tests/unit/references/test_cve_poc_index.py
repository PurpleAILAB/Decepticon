"""Tests for CVE → PoC index."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.cve_poc_index import (
    PoCIndex,
    build_index,
    load_index,
    lookup_poc,
    save_index,
)


def _build_trickest_cache(root: Path) -> Path:
    repo = root / "trickest-cve"
    year = repo / "2021"
    year.mkdir(parents=True)
    (year / "CVE-2021-44228.md").write_text(
        "### CVE-2021-44228\n\n"
        "Log4Shell — Apache log4j2 RCE via JNDI lookup.\n\n"
        "#### PoCs\n\n"
        "- https://github.com/kozmer/log4j-shell-poc\n"
        "- https://github.com/tangxiaofeng7/CVE-2021-44228-Apache-Log4j-Rce\n"
        "- https://example.com/dup.\n",
        encoding="utf-8",
    )
    (year / "CVE-2021-44228.md").write_text(
        (year / "CVE-2021-44228.md").read_text(encoding="utf-8")
        + "\nanother https://github.com/kozmer/log4j-shell-poc mention\n",
        encoding="utf-8",
    )
    (year / "CVE-2021-41773.md").write_text(
        "Apache 2.4.49 path traversal.\n\nhttps://github.com/blasty/CVE-2021-41773",
        encoding="utf-8",
    )
    # Non-CVE year directories should be ignored
    (repo / "README.md").write_text("index", encoding="utf-8")
    return repo


def _build_mrxn_cache(root: Path) -> Path:
    repo = root / "penetration-testing-poc"
    sub = repo / "log4j"
    sub.mkdir(parents=True)
    (sub / "CVE-2021-44228_exploit.py").write_text(
        "# Exploit for CVE-2021-44228\nimport sys\n", encoding="utf-8"
    )
    (sub / "notes.md").write_text(
        "See also CVE-2021-41773 https://attacker.example.com/notes.html",
        encoding="utf-8",
    )
    return repo


class TestPoCIndexCore:
    def test_add_and_lookup(self) -> None:
        idx = PoCIndex()
        idx.add("cve-2024-1234", "https://a.example")
        idx.add("CVE-2024-1234", "https://a.example")  # dedup
        idx.add("CVE-2024-1234", "https://b.example")
        assert idx.lookup("CVE-2024-1234") == ["https://a.example", "https://b.example"]
        assert idx.lookup("cve-2024-1234") == ["https://a.example", "https://b.example"]

    def test_to_dict_shape(self) -> None:
        idx = PoCIndex()
        idx.add("CVE-2024-1", "https://x")
        d = idx.to_dict()
        assert d["count"] == 1
        assert d["entries"]["CVE-2024-1"] == ["https://x"]


class TestBuildIndex:
    def test_absent_caches(self, tmp_path: Path) -> None:
        idx = build_index(root=tmp_path)
        assert idx.size() == 0

    def test_trickest_only(self, tmp_path: Path) -> None:
        _build_trickest_cache(tmp_path)
        idx = build_index(root=tmp_path)
        urls = idx.lookup("CVE-2021-44228")
        assert any("kozmer" in u for u in urls)
        assert len(urls) >= 2

    def test_mrxn_only(self, tmp_path: Path) -> None:
        _build_mrxn_cache(tmp_path)
        idx = build_index(root=tmp_path)
        urls = idx.lookup("CVE-2021-44228")
        assert any(u.startswith("file://") for u in urls)

    def test_both_merged(self, tmp_path: Path) -> None:
        _build_trickest_cache(tmp_path)
        _build_mrxn_cache(tmp_path)
        idx = build_index(root=tmp_path)
        assert idx.size() >= 2
        assert idx.lookup("CVE-2021-41773")
        assert idx.lookup("CVE-2021-44228")


class TestPersist:
    def test_save_and_load(self, tmp_path: Path) -> None:
        _build_trickest_cache(tmp_path)
        idx = build_index(root=tmp_path)
        save_index(idx, root=tmp_path)
        loaded = load_index(root=tmp_path)
        assert loaded.lookup("CVE-2021-44228") == idx.lookup("CVE-2021-44228")

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        # No trickest cache → no index file
        idx = load_index(root=tmp_path)
        assert idx.size() == 0


class TestLookupHelper:
    def test_lookup_poc_no_cache(self, tmp_path: Path) -> None:
        assert lookup_poc("CVE-2020-1234", root=tmp_path) == []

    def test_lookup_poc_builds_on_demand(self, tmp_path: Path) -> None:
        _build_trickest_cache(tmp_path)
        # lookup_poc should fall back to build_index when no persisted file
        urls = lookup_poc("CVE-2021-44228", root=tmp_path)
        assert len(urls) >= 2
