"""One-shot reference cache hydration.

Clones (or ``git pull``s) every reference repo that an indexer under
``decepticon/references/`` knows how to parse. Safe to call multiple
times — ``ensure_cached`` does a fast-forward pull when the clone is
already present.

Usage::

    from decepticon.tools.references.hydrate import hydrate_all
    hydrate_all()

or as a one-liner::

    python -m decepticon.references.hydrate

The six source slugs are the ones the Tier 1 indexers depend on. Extra
catalogued repos (pentestgpt, shannon, excalibur, etc.) are **not**
hydrated here — they are reference-only and have no structured
indexer, so cloning them would just burn disk.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.tools.references.cve_poc_index import (
    MRXN_SLUG,
    TRICKEST_SLUG,
    build_index,
    invalidate_cache,
    save_index,
)
from decepticon.tools.references.fetch import ReferenceCache, ensure_cached
from decepticon.tools.references.h1_corpus import invalidate_corpus_cache
from decepticon.tools.references.killchain import invalidate_entries_cache
from decepticon.tools.references.methodology import invalidate_chapters_cache
from decepticon.tools.references.oneliners import invalidate_recipes_cache
from decepticon.tools.references.payloads_ingest import invalidate_merged_cache

#: Reference repos with structured indexers attached. Order matches
#: execution order in ``hydrate_all``.
INDEXED_SLUGS: tuple[str, ...] = (
    "payloads-all-the-things",
    TRICKEST_SLUG,
    MRXN_SLUG,
    "hackerone-reports",
    "book-of-secret-knowledge",
    "redteam-tools",
    "all-about-bug-bounty",
)


@dataclass
class HydrationResult:
    slug: str
    ok: bool
    present: bool
    size_bytes: int
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "ok": self.ok,
            "present": self.present,
            "size_bytes": self.size_bytes,
            "error": self.error,
        }


def _hydrate_one(slug: str, root: Path | None) -> HydrationResult:
    try:
        status: ReferenceCache = ensure_cached(slug, root=root)
    except Exception as e:  # pragma: no cover — ensure_cached is defensive
        return HydrationResult(slug=slug, ok=False, present=False, size_bytes=0, error=str(e))
    return HydrationResult(
        slug=slug,
        ok=status.present,
        present=status.present,
        size_bytes=status.size_bytes,
    )


def hydrate_all(
    *,
    root: Path | None = None,
    slugs: tuple[str, ...] | None = None,
    rebuild_poc_index: bool = True,
) -> list[HydrationResult]:
    """Clone / update every indexed reference repo.

    After the clones land, optionally rebuild the CVE→PoC JSON index.
    Returns one ``HydrationResult`` per slug so callers can report
    progress.
    """
    targets = slugs if slugs is not None else INDEXED_SLUGS
    results = [_hydrate_one(slug, root) for slug in targets]
    # Re-hydration invalidates every per-corpus memo so subsequent
    # lookups refresh from disk.
    invalidate_corpus_cache()
    invalidate_entries_cache()
    invalidate_chapters_cache()
    invalidate_recipes_cache()
    invalidate_merged_cache()
    if rebuild_poc_index:
        poc_touched = any(r.slug in {TRICKEST_SLUG, MRXN_SLUG} and r.present for r in results)
        if poc_touched:
            invalidate_cache()
            try:
                index = build_index(root=root)
                if index.size() > 0:
                    save_index(index, root=root)
            except OSError:
                pass  # skip unparseable entries
    return results


def format_report(results: list[HydrationResult]) -> str:
    lines = ["Reference cache hydration:"]
    for r in results:
        mark = "OK " if r.ok else "ERR"
        size_mb = r.size_bytes / (1024 * 1024)
        extra = f" — {r.error}" if r.error else ""
        lines.append(f"  [{mark}] {r.slug:<26} {size_mb:>8.1f} MB{extra}")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    results = hydrate_all()
    print(format_report(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv[1:]))


__all__ = [
    "HydrationResult",
    "INDEXED_SLUGS",
    "format_report",
    "hydrate_all",
]
