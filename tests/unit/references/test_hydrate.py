"""Tests for the hydration helper.

We don't hit the network — we call the internal helper with a
monkey-patched ``ensure_cached`` that just creates a fake clone
directory so the rest of the pipeline (reporting, PoC index rebuild)
exercises its real code paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from decepticon.tools.references import hydrate
from decepticon.tools.references.fetch import ReferenceCache


@pytest.fixture
def patched_ensure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    calls: list[str] = []

    def fake_ensure(slug: str, **_: Any) -> ReferenceCache:
        calls.append(slug)
        path = tmp_path / slug
        path.mkdir(parents=True, exist_ok=True)
        (path / "README.md").write_text(f"fake {slug}", encoding="utf-8")
        return ReferenceCache(
            slug=slug,
            url=f"https://example.com/{slug}",
            path=path,
            present=True,
            size_bytes=128,
        )

    monkeypatch.setattr(hydrate, "ensure_cached", fake_ensure)
    return calls


class TestHydrateAll:
    def test_covers_all_indexed_slugs(self, patched_ensure: list[str], tmp_path: Path) -> None:
        results = hydrate.hydrate_all(root=tmp_path, rebuild_poc_index=False)
        assert {r.slug for r in results} == set(hydrate.INDEXED_SLUGS)
        assert all(r.ok for r in results)
        assert patched_ensure == list(hydrate.INDEXED_SLUGS)

    def test_format_report_non_empty(self, patched_ensure: list[str], tmp_path: Path) -> None:
        results = hydrate.hydrate_all(root=tmp_path, rebuild_poc_index=False)
        report = hydrate.format_report(results)
        assert "hackerone-reports" in report
        assert "OK" in report

    def test_slug_subset(self, patched_ensure: list[str], tmp_path: Path) -> None:
        results = hydrate.hydrate_all(
            root=tmp_path,
            slugs=("hackerone-reports",),
            rebuild_poc_index=False,
        )
        assert len(results) == 1
        assert results[0].slug == "hackerone-reports"
