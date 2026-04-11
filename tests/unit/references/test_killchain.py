"""Tests for the kill-chain phase → tool mapper."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.killchain import (
    load_entries,
    lookup,
    normalize_phase,
    suggest,
)


class TestNormalizePhase:
    def test_direct_match(self) -> None:
        assert normalize_phase("recon") == "recon"
        assert normalize_phase("command and control") == "command-and-control"

    def test_aliases(self) -> None:
        assert normalize_phase("c2") == "command-and-control"
        assert normalize_phase("Privilege Escalation") == "privilege-escalation"
        assert normalize_phase("Credential Access") == "credential-access"
        assert normalize_phase("lateral") == "lateral-movement"

    def test_unknown_phase_slugified(self) -> None:
        assert normalize_phase("Custom Weird Phase") == "custom-weird-phase"


class TestFallbackYaml:
    def test_loads_without_cache(self, tmp_path: Path) -> None:
        entries = load_entries(root=tmp_path)
        assert len(entries) > 30  # Committed YAML has plenty
        assert any(e.name == "nmap" for e in entries)
        assert all(e.source == "fallback" for e in entries)

    def test_phases_normalized(self, tmp_path: Path) -> None:
        entries = load_entries(root=tmp_path)
        phases = {e.phase for e in entries}
        assert "recon" in phases
        assert "credential-access" in phases
        assert "lateral-movement" in phases


class TestLookup:
    def test_recon_phase(self, tmp_path: Path) -> None:
        hits = lookup("recon", root=tmp_path)
        names = {h.name for h in hits}
        assert "nmap" in names
        assert "subfinder" in names

    def test_alias_resolution(self, tmp_path: Path) -> None:
        hits = lookup("c2", root=tmp_path)
        names = {h.name for h in hits}
        assert any(n.lower() in {"sliver", "mythic", "havoc"} for n in names)

    def test_limit_respected(self, tmp_path: Path) -> None:
        hits = lookup("recon", limit=3, root=tmp_path)
        assert len(hits) <= 3


class TestSuggest:
    def test_keyword_match(self, tmp_path: Path) -> None:
        hits = suggest("dump kerberos tickets", root=tmp_path)
        assert len(hits) > 0

    def test_empty_returns_empty(self, tmp_path: Path) -> None:
        assert suggest("", root=tmp_path) == []

    def test_single_word_too_short_ignored(self, tmp_path: Path) -> None:
        # terms <= 2 chars are dropped
        assert suggest("a b", root=tmp_path) == []


class TestUpstreamParse:
    def test_readme_overlay(self, tmp_path: Path) -> None:
        repo = tmp_path / "redteam-tools"
        repo.mkdir(parents=True)
        (repo / "README.md").write_text(
            "# RedTeam-Tools\n\n"
            "## Recon\n\n"
            "- [customreconthing](https://example.com/crt) — does recon stuff\n"
            "\n"
            "## Privilege Escalation\n\n"
            "- [weirdprivesc](https://example.com/wpe) — escalates weirdly\n",
            encoding="utf-8",
        )
        entries = load_entries(root=tmp_path)
        names = {e.name for e in entries}
        assert "customreconthing" in names
        assert "weirdprivesc" in names
        custom = next(e for e in entries if e.name == "customreconthing")
        assert custom.phase == "recon"
        assert custom.source == "redteam-tools"
