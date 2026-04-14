"""Tests for the references package: catalog, payloads, fetch, tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from decepticon.tools.references import fetch as fetch_mod
from decepticon.tools.references.catalog import (
    REFERENCES,
    references_by_category,
    references_for_topic,
    suggest_for_finding,
)
from decepticon.tools.references.fetch import (
    cache_path,
    cache_status,
    ensure_cached,
    search_cache,
)
from decepticon.tools.references.payloads import (
    BUNDLED_PAYLOADS,
    payloads_by_class,
    search_payloads,
)


class TestCatalog:
    def test_references_contain_all_user_links(self) -> None:
        slugs = {r.slug for r in REFERENCES}
        expected_min = {
            "hackerone-reports",
            "payloads-all-the-things",
            "book-of-secret-knowledge",
            "pentagi",
            "pentestgpt",
            "redteam-tools",
            "trickest-cve",
            "penetration-testing-poc",
            "all-about-bug-bounty",
            "shannon",
            "strix",
            "hexstrike-ai",
            "neurosploit",
            "excalibur",
        }
        missing = expected_min - slugs
        assert not missing, f"missing catalog slugs: {missing}"

    def test_categories_populated(self) -> None:
        cats = {r.category for r in REFERENCES}
        for required in (
            "report-corpus",
            "payload-library",
            "cheat-sheet",
            "reference-agent",
            "tool-index",
            "cve-poc",
            "methodology",
        ):
            assert required in cats

    def test_references_by_category_filter(self) -> None:
        refs = references_by_category("cve-poc")
        assert all(r.category == "cve-poc" for r in refs)
        assert len(refs) >= 2

    def test_references_for_topic(self) -> None:
        assert any(r.slug == "all-about-bug-bounty" for r in references_for_topic("idor"))

    def test_suggest_returns_non_empty(self) -> None:
        picks = suggest_for_finding(vuln_class="sqli")
        slugs = [r.slug for r in picks]
        assert "payloads-all-the-things" in slugs
        assert "hackerone-reports" in slugs


class TestBundledPayloads:
    def test_known_classes_present(self) -> None:
        classes = {p.vuln_class for p in BUNDLED_PAYLOADS}
        for c in (
            "sqli",
            "ssrf",
            "xss",
            "ssti",
            "deser",
            "rce",
            "xxe",
            "idor",
            "jwt",
            "oauth",
            "lfi",
            "proto-pollution",
            "cmdi",
            "graphql",
            "prompt-injection",
        ):
            assert c in classes, f"missing class {c}"

    def test_payloads_by_class(self) -> None:
        hits = payloads_by_class("ssrf")
        assert len(hits) >= 3

    def test_search_payloads_keyword(self) -> None:
        hits = search_payloads(vuln_class="ssrf", keyword="imds")
        assert len(hits) >= 1
        assert all("imds" in (p.title + p.payload + p.notes).lower() for p in hits)

    def test_search_payloads_class_only(self) -> None:
        hits = search_payloads(vuln_class="jwt")
        assert len(hits) >= 3


class TestFetchCache:
    def test_cache_path_resolves(self, tmp_path: Path) -> None:
        p = cache_path("hackerone-reports", root=tmp_path)
        assert p == tmp_path / "hackerone-reports"

    def test_cache_status_missing(self, tmp_path: Path) -> None:
        status = cache_status("hackerone-reports", root=tmp_path)
        assert status.present is False
        assert status.size_bytes == 0

    def test_cache_status_present(self, tmp_path: Path) -> None:
        target = tmp_path / "hackerone-reports"
        target.mkdir(parents=True)
        (target / "README.md").write_text("hello world", encoding="utf-8")
        status = cache_status("hackerone-reports", root=tmp_path)
        assert status.present is True
        assert status.size_bytes >= len("hello world")

    def test_ensure_cached_dry_run(self, tmp_path: Path) -> None:
        # run=False — no network, just computes the projected path
        status = ensure_cached("hackerone-reports", root=tmp_path, run=False)
        assert status.slug == "hackerone-reports"
        assert status.present is False  # not actually cloned

    def test_unknown_slug_raises(self) -> None:
        with pytest.raises(KeyError):
            cache_path("does-not-exist")

    def test_search_cache_passes_pattern_after_double_dash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "hackerone-reports"
        repo.mkdir(parents=True)
        (repo / "README.md").write_text("hello\n", encoding="utf-8")

        captured: dict[str, list[str]] = {}

        def fake_run(
            cmd: list[str],
            *,
            capture_output: bool,
            timeout: int,
            text: bool,
            errors: str,
        ) -> SimpleNamespace:
            captured["cmd"] = cmd
            return SimpleNamespace(stdout="")

        monkeypatch.setattr(fetch_mod, "_which", lambda binary: binary == "rg")
        monkeypatch.setattr(fetch_mod.subprocess, "run", fake_run)

        assert search_cache("hackerone-reports", "--hidden", root=tmp_path) == []
        assert captured["cmd"] == [
            "rg",
            "-n",
            "--max-count",
            "3",
            "--",
            "--hidden",
            str(repo),
        ]
