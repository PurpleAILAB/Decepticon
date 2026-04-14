"""CVE → public PoC link index.

Reads the cached ``trickest/cve`` repo (per-CVE markdown files grouped
by year) plus the secondary mirror ``Mr-xn/Penetration_Testing_POC``
and builds a single ``{cve_id: [poc_url, ...]}`` map.

The built index is persisted to a JSON file next to the trickest cache
so subsequent lookups skip the walk. Regenerate with ``build_index()``
or by deleting the cache file.

Callers use:

    from decepticon.tools.references.cve_poc_index import lookup_poc
    urls = lookup_poc("CVE-2021-44228")

The function is safe to call when the cache is absent — it returns an
empty list instead of raising.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decepticon.tools.references.fetch import cache_path

TRICKEST_SLUG = "trickest-cve"
MRXN_SLUG = "penetration-testing-poc"

_CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+", re.IGNORECASE)
_INDEX_FILENAME = "poc_index.json"


@dataclass
class PoCIndex:
    """In-memory map of CVE ID to a de-duplicated list of PoC URLs.

    The public ``entries`` attribute is a ``{cve_id: [urls]}`` mapping
    that preserves insertion order (stable across serialisation). For
    O(1) membership checks during bulk ingestion we maintain a parallel
    ``_seen`` ``{cve_id: set[url]}`` — a heavily-PoC'd CVE like
    Log4Shell can carry 100+ URLs, and ``url in list`` on every call
    dominates ``build_index`` wall time without it.
    """

    entries: dict[str, list[str]] = field(default_factory=dict)
    _seen: dict[str, set[str]] = field(default_factory=dict, repr=False, compare=False)

    def add(self, cve_id: str, url: str) -> None:
        key = cve_id.upper()
        bucket = self.entries.get(key)
        if bucket is None:
            bucket = []
            self.entries[key] = bucket
            self._seen[key] = set()
        seen = self._seen.setdefault(key, set(bucket))
        if url in seen:
            return
        bucket.append(url)
        seen.add(url)

    def lookup(self, cve_id: str) -> list[str]:
        return list(self.entries.get(cve_id.upper(), ()))

    def size(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.size(),
            "entries": self.entries,
        }


def _iter_trickest_files(repo: Path) -> list[Path]:
    """Return every ``CVE-*.md`` file under year-numbered directories."""
    if not repo.is_dir():
        return []
    files: list[Path] = []
    for year_dir in sorted(repo.iterdir()):
        if not year_dir.is_dir():
            continue
        if not re.fullmatch(r"\d{4}", year_dir.name):
            continue
        files.extend(sorted(year_dir.glob("CVE-*.md")))
    return files


def _extract_cve_id(path: Path, text: str) -> str | None:
    stem = path.stem.upper()
    if _CVE_ID_RE.fullmatch(stem):
        return stem
    m = _CVE_ID_RE.search(text)
    return m.group(0).upper() if m else None


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _ingest_trickest(repo: Path, index: PoCIndex) -> int:
    added = 0
    for path in _iter_trickest_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cve_id = _extract_cve_id(path, text)
        if not cve_id:
            continue
        for url in _extract_urls(text):
            before = len(index.entries.get(cve_id, ()))
            index.add(cve_id, url)
            if len(index.entries[cve_id]) > before:
                added += 1
    return added


#: Skip files larger than this many bytes when scanning the Mr-xn
#: mirror. Keeps an unbounded upstream repo from blowing up the walk.
_MAX_SCAN_SIZE = 512 * 1024  # 512 KB is plenty for a PoC script


def _ingest_mrxn(repo: Path, index: PoCIndex) -> int:
    """Scan filenames and markdown in the Mr-xn mirror for CVE IDs + URLs.

    Walks the repo without following symlinks: an upstream symlink
    pointing outside the cache root would otherwise let a compromised
    upstream repo leak host paths into the index and, via
    ``cve_poc_lookup``, into the agent context.
    """
    if not repo.is_dir() or repo.is_symlink():
        return 0
    try:
        repo_real = repo.resolve(strict=False)
    except OSError:
        return 0
    added = 0
    for path in repo.rglob("*"):
        try:
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            # Ensure the resolved path is still inside the cache root —
            # otherwise we'd happily read /etc/shadow if someone
            # swapped in a symlink between rglob() and is_file().
            real = path.resolve(strict=False)
            real.relative_to(repo_real)
        except (OSError, ValueError):
            continue
        suffix = path.suffix.lower()
        if suffix not in {".md", ".txt", ".py"}:
            # Avoid blowing up on huge binary/sample files
            continue
        try:
            if path.stat().st_size > _MAX_SCAN_SIZE:
                continue
        except OSError:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name_ids = _CVE_ID_RE.findall(path.name)
        body_ids = _CVE_ID_RE.findall(text)
        ids = {i.upper() for i in (name_ids + body_ids)}
        if not ids:
            continue
        try:
            rel = str(path.relative_to(repo))
        except ValueError:
            continue
        url = f"file://{rel}"
        for cve_id in ids:
            before = len(index.entries.get(cve_id, ()))
            index.add(cve_id, url)
            if len(index.entries[cve_id]) > before:
                added += 1
        for url in _extract_urls(text):
            for cve_id in ids:
                before = len(index.entries.get(cve_id, ()))
                index.add(cve_id, url)
                if len(index.entries[cve_id]) > before:
                    added += 1
    return added


def build_index(*, root: Path | None = None) -> PoCIndex:
    """Walk both caches and return a fresh ``PoCIndex``."""
    index = PoCIndex()
    trickest = cache_path(TRICKEST_SLUG, root=root)
    mrxn = cache_path(MRXN_SLUG, root=root)
    _ingest_trickest(trickest, index)
    _ingest_mrxn(mrxn, index)
    return index


def _index_file(root: Path | None) -> Path:
    trickest = cache_path(TRICKEST_SLUG, root=root)
    return trickest.parent / _INDEX_FILENAME


def save_index(index: PoCIndex, *, root: Path | None = None) -> Path:
    path = _index_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # Compact form (no indent, no spaces) — this file is machine-read,
    # can reach 20-50 MB on a fully-hydrated trickest clone, and is
    # loaded on every process startup. Dropping indent cuts the file
    # size ~40% and the parse time proportionally.
    tmp.write_text(
        json.dumps(
            index.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_index(*, root: Path | None = None) -> PoCIndex:
    """Load persisted index if present; otherwise return empty ``PoCIndex``.

    Empty is the **safe default** — lookups quietly return no hits.
    """
    path = _index_file(root)
    if not path.is_file():
        return PoCIndex()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PoCIndex()
    raw = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return PoCIndex()
    index = PoCIndex()
    for k, v in raw.items():
        if isinstance(v, list):
            for url in v:
                if isinstance(url, str):
                    index.add(str(k), url)
    return index


# ── Process-level cache ────────────────────────────────────────────────
#
# The persisted PoC index can be tens of MB. Reloading it on every
# ``lookup_poc`` call dominates CVE lookup latency. We memoize the
# PoCIndex for the life of the process, keyed by the resolved index
# file path. When the file's mtime changes we reload — that way
# ``references_hydrate`` picks up changes without a process restart.

_index_cache: dict[Path, tuple[float, PoCIndex]] = {}


def _cached_index(root: Path | None) -> PoCIndex:
    path = _index_file(root)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    entry = _index_cache.get(path)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    index = load_index(root=root)
    if index.size() == 0:
        # Try a live build in case the cache was hydrated but not
        # indexed yet. Store even an empty-after-build to avoid
        # re-walking on every call.
        index = build_index(root=root)
        if index.size() > 0:
            try:
                save_index(index, root=root)
                mtime = path.stat().st_mtime
            except OSError:
                pass  # malformed entry — skip
    _index_cache[path] = (mtime, index)
    return index


def invalidate_cache() -> None:
    """Drop the cached PoCIndex (tests / post-hydrate)."""
    _index_cache.clear()


def lookup_poc(cve_id: str, *, root: Path | None = None) -> list[str]:
    """Convenience lookup that reads the persisted index lazily.

    Falls back to an on-the-fly build of the trickest cache if no
    persisted index exists yet. Returns ``[]`` when neither cache is
    present. The loaded index is memoized per-process so subsequent
    lookups skip the JSON parse.
    """
    return _cached_index(root).lookup(cve_id)


__all__ = [
    "MRXN_SLUG",
    "PoCIndex",
    "TRICKEST_SLUG",
    "build_index",
    "invalidate_cache",
    "load_index",
    "lookup_poc",
    "save_index",
]
