"""HackerOne disclosed-report corpus indexer.

Parses the markdown tables inside a cached clone of
``reddelexc/hackerone-reports`` and yields ``BugReport`` rows that the
analyst agent can query for prior art.

The upstream repo ships a family of ``tops_by_*.md`` files — each is a
pre-sorted markdown table of disclosed reports:

    tops_by_bounty.md    — sorted by bounty amount descending
    tops_by_cwe.md       — grouped by CWE identifier
    tops_by_program.md   — grouped by program name
    tops_by_severity.md  — grouped by severity
    tops_by_upvotes.md   — sorted by upvotes

The file layout and column order change occasionally upstream, so this
parser is **column-agnostic**: for each table row it extracts the
first markdown link as ``(title, url)``, then runs per-field detectors
(``$`` for bounty, ``CWE-NNNN`` for CWE, severity keywords) over the
remaining cells. Cells that don't match anything are preserved as
``extras``.

Callers get a ``list[BugReport]`` that they can filter in memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decepticon.tools.references.fetch import cache_path

REPO_SLUG = "hackerone-reports"

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOUNTY = re.compile(r"\$\s*([0-9][0-9,\.]*)")
_CWE = re.compile(r"CWE-(\d+)", re.IGNORECASE)
_SEVERITY_WORDS = {
    "critical",
    "high",
    "medium",
    "low",
    "informational",
    "none",
}


@dataclass
class BugReport:
    """A single disclosed HackerOne report row."""

    title: str = ""
    url: str = ""
    cwe: str = ""
    severity: str = ""
    bounty: float = 0.0
    program: str = ""
    source_file: str = ""
    extras: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "cwe": self.cwe,
            "severity": self.severity,
            "bounty": self.bounty,
            "program": self.program,
            "source_file": self.source_file,
            "extras": list(self.extras),
        }


def _parse_bounty(cell: str) -> float:
    m = _BOUNTY.search(cell)
    if not m:
        return 0.0
    raw = m.group(1).replace(",", "").rstrip(".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _parse_severity(cell: str) -> str:
    low = cell.strip().lower()
    if low in _SEVERITY_WORDS:
        return low
    for word in _SEVERITY_WORDS:
        if re.search(rf"\b{word}\b", low):
            return word
    return ""


def _parse_cwe(cell: str) -> str:
    m = _CWE.search(cell)
    if not m:
        return ""
    return f"CWE-{m.group(1)}"


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row into cells without breaking link bracketing."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    inner = stripped[1:-1]
    cells: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in inner:
        if ch in "[(":
            depth += 1
            buf.append(ch)
        elif ch in "])":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "|" and depth == 0:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _is_header_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def _parse_row(cells: list[str], source_file: str, program_hint: str) -> BugReport | None:
    if not cells:
        return None
    report = BugReport(source_file=source_file, program=program_hint)
    matched_cells: set[int] = set()
    # First pass — find the first markdown link for title + URL.
    for i, cell in enumerate(cells):
        m = _MD_LINK.search(cell)
        if m:
            report.title = m.group(1).strip()
            report.url = m.group(2).strip()
            matched_cells.add(i)
            break
    # Second pass — per-cell detectors. A cell may match multiple.
    for i, cell in enumerate(cells):
        if not cell:
            continue
        bounty = _parse_bounty(cell)
        if bounty > 0 and report.bounty == 0.0:
            report.bounty = bounty
            matched_cells.add(i)
        cwe = _parse_cwe(cell)
        if cwe and not report.cwe:
            report.cwe = cwe
            matched_cells.add(i)
        sev = _parse_severity(cell)
        if sev and not report.severity:
            report.severity = sev
            matched_cells.add(i)
    # Anything unmatched → extras (useful context like reporter name)
    for i, cell in enumerate(cells):
        if i in matched_cells or not cell:
            continue
        report.extras.append(cell)
    if not report.title and not report.url and not report.cwe:
        return None
    return report


def parse_tops_file(path: Path) -> list[BugReport]:
    """Parse a single ``tops_by_*.md`` file into BugReport rows."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    reports: list[BugReport] = []
    current_program = ""
    in_table = False
    header_seen = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("## "):
            # Section header — often the program name in tops_by_program.md
            current_program = line[3:].strip()
            in_table = False
            header_seen = False
            continue
        if line.startswith("# "):
            current_program = ""
            in_table = False
            header_seen = False
            continue
        cells = _split_table_row(line)
        if not cells:
            in_table = False
            header_seen = False
            continue
        if not header_seen:
            header_seen = True
            in_table = True
            continue
        if _is_header_separator(cells):
            continue
        if not in_table:
            continue
        row = _parse_row(cells, source_file=path.name, program_hint=current_program)
        if row is not None:
            reports.append(row)
    return reports


_corpus_cache: dict[Path, tuple[float, list[BugReport]]] = {}


def _compute_corpus(root: Path | None) -> list[BugReport]:
    repo = cache_path(REPO_SLUG, root=root)
    if not repo.is_dir():
        return []
    files: list[Path] = []
    for name in (
        "tops_by_bounty.md",
        "tops_by_cwe.md",
        "tops_by_program.md",
        "tops_by_severity.md",
        "tops_by_upvotes.md",
    ):
        p = repo / name
        if p.is_file():
            files.append(p)
    if not files:
        files = sorted(repo.glob("tops_*.md"))
    reports: list[BugReport] = []
    seen: set[str] = set()
    for f in files:
        for r in parse_tops_file(f):
            key = r.url or f"{r.title}|{r.cwe}|{r.source_file}"
            if key in seen:
                continue
            seen.add(key)
            reports.append(r)
    return reports


def load_corpus(*, root: Path | None = None) -> list[BugReport]:
    """Walk the cached repo and return every BugReport row.

    Memoized per-process by (cache-root, repo mtime). Re-hydrating the
    upstream clone invalidates the cache via directory mtime change.
    """
    repo = cache_path(REPO_SLUG, root=root)
    try:
        mtime = repo.stat().st_mtime if repo.exists() else -1.0
    except OSError:
        mtime = -1.0
    entry = _corpus_cache.get(repo)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    corpus = _compute_corpus(root)
    _corpus_cache[repo] = (mtime, corpus)
    return corpus


def invalidate_corpus_cache() -> None:
    """Drop the process-level corpus cache (tests / post-hydrate)."""
    _corpus_cache.clear()


def search(
    reports: list[BugReport] | None = None,
    *,
    cwe: str | None = None,
    keyword: str | None = None,
    program: str | None = None,
    min_bounty: float = 0.0,
    severity: str | None = None,
    limit: int = 20,
    root: Path | None = None,
) -> list[BugReport]:
    """Filter the H1 corpus in memory.

    If ``reports`` is omitted, the full corpus is loaded from the
    cached repo on each call — fine for interactive agent usage since
    the corpus is a few thousand rows.
    """
    corpus = reports if reports is not None else load_corpus(root=root)
    needle = keyword.lower() if keyword else None
    cwe_norm = ""
    if cwe:
        m = _CWE.search(cwe)
        if m:
            cwe_norm = f"CWE-{m.group(1)}"
        elif cwe.strip().isdigit():
            cwe_norm = f"CWE-{cwe.strip()}"
        else:
            cwe_norm = cwe.upper()
    severity_norm = severity.lower() if severity else None
    program_norm = program.lower() if program else None
    out: list[BugReport] = []
    for r in corpus:
        if cwe_norm and r.cwe.upper() != cwe_norm.upper():
            continue
        if severity_norm and r.severity.lower() != severity_norm:
            continue
        if program_norm and program_norm not in r.program.lower():
            continue
        if r.bounty < min_bounty:
            continue
        if needle and needle not in (r.title + " " + r.url + " " + " ".join(r.extras)).lower():
            continue
        out.append(r)
        if len(out) >= limit:
            break
    # Sort by bounty descending when bounty filter active — otherwise
    # keep upstream order so the caller can reason about sort lineage.
    if min_bounty > 0 or (not needle and not cwe_norm and not severity_norm and not program_norm):
        out.sort(key=lambda r: r.bounty, reverse=True)
    return out


__all__ = [
    "BugReport",
    "REPO_SLUG",
    "load_corpus",
    "parse_tops_file",
    "search",
]
