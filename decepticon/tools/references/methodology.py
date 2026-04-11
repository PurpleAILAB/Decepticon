"""AllAboutBugBounty chapter retriever.

Walks a cached clone of ``daffainfo/AllAboutBugBounty`` and indexes
each per-vuln-class chapter (plain markdown files at the repo root)
into ``Chapter`` rows. Unlike ``h1_corpus``, we expose **raw markdown
retrieval** — the agent gets the chapter text itself so it can read
the methodology in context rather than matching structured fields.

Typical upstream layout:

    AllAboutBugBounty/
      SSRF.md
      IDOR.md
      Account Takeover.md
      OAuth Misconfiguration.md
      ...

File basenames are folded into Decepticon vuln_class slugs via a small
alias table; unknown filenames get slugified defaults so new chapters
surface automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.tools.references.fetch import cache_path

REPO_SLUG = "all-about-bug-bounty"

_FILE_TO_CLASS: dict[str, str] = {
    "ssrf": "ssrf",
    "server side request forgery": "ssrf",
    "idor": "idor",
    "insecure direct object reference": "idor",
    "account takeover": "ato",
    "authentication bypass": "auth-bypass",
    "2fa bypass": "2fa-bypass",
    "broken link hijacking": "blh",
    "business logic error": "biz-logic",
    "cache poisoning": "cache-poisoning",
    "clickjacking": "clickjacking",
    "cors misconfiguration": "cors",
    "crlf injection": "crlf",
    "csrf": "csrf",
    "csv injection": "csv-injection",
    "file inclusion": "lfi",
    "directory traversal": "lfi",
    "exposed source code": "source-exposure",
    "host header injection": "host-header",
    "jwt": "jwt",
    "no rate limiting": "rate-limit",
    "oauth misconfiguration": "oauth",
    "open redirect": "open-redirect",
    "parameter pollution": "hpp",
    "race condition": "race",
    "rce": "rce",
    "remote code execution": "rce",
    "sql injection": "sqli",
    "ssti": "ssti",
    "subdomain takeover": "subdomain-takeover",
    "unrestricted file upload": "file-upload",
    "xss": "xss",
    "xxe": "xxe",
    "graphql": "graphql",
    "prototype pollution": "proto-pollution",
}


@dataclass
class Chapter:
    """A single methodology chapter with its raw markdown body."""

    vuln_class: str
    title: str
    path: str
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "vuln_class": self.vuln_class,
            "title": self.title,
            "path": self.path,
            "body": self.body,
        }

    def excerpt(self, limit: int = 1800) -> str:
        if len(self.body) <= limit:
            return self.body
        return self.body[:limit] + "\n\n…[truncated]"


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def classify_filename(name: str) -> str:
    """Map a markdown filename to a Decepticon vuln_class slug."""
    key = Path(name).stem.lower().strip()
    if key in _FILE_TO_CLASS:
        return _FILE_TO_CLASS[key]
    for alias, canonical in _FILE_TO_CLASS.items():
        if alias in key:
            return canonical
    return _slugify(key)


_chapters_cache: dict[Path, tuple[float, list[Chapter]]] = {}


def _compute_chapters(root: Path | None) -> list[Chapter]:
    repo = cache_path(REPO_SLUG, root=root)
    if not repo.is_dir():
        return []
    chapters: list[Chapter] = []
    for md in sorted(repo.rglob("*.md")):
        rel = md.relative_to(repo)
        if md.name.lower() in {"readme.md", "contributing.md", "code_of_conduct.md"}:
            continue
        try:
            body = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chapters.append(
            Chapter(
                vuln_class=classify_filename(md.name),
                title=md.stem,
                path=str(rel),
                body=body,
            )
        )
    return chapters


def load_chapters(*, root: Path | None = None) -> list[Chapter]:
    """Walk the cached repo and return every top-level chapter.

    Memoized per-process by (cache-root, repo mtime). Re-hydrating
    the clone invalidates the cache via directory mtime change.
    """
    repo = cache_path(REPO_SLUG, root=root)
    try:
        mtime = repo.stat().st_mtime if repo.exists() else -1.0
    except OSError:
        mtime = -1.0
    entry = _chapters_cache.get(repo)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    chapters = _compute_chapters(root)
    _chapters_cache[repo] = (mtime, chapters)
    return chapters


def invalidate_chapters_cache() -> None:
    _chapters_cache.clear()


def lookup(
    vuln_class: str,
    *,
    chapters: list[Chapter] | None = None,
    root: Path | None = None,
    excerpt_chars: int = 1800,
) -> list[dict[str, Any]]:
    """Return every chapter whose slug matches the requested class."""
    target = vuln_class.lower().strip()
    pool = chapters if chapters is not None else load_chapters(root=root)
    hits = [c for c in pool if c.vuln_class == target or target in c.title.lower()]
    return [
        {
            "vuln_class": c.vuln_class,
            "title": c.title,
            "path": c.path,
            "excerpt": c.excerpt(excerpt_chars),
        }
        for c in hits
    ]


def classes_present(*, root: Path | None = None) -> list[str]:
    """List the distinct vuln classes found in the cached repo."""
    return sorted({c.vuln_class for c in load_chapters(root=root)})


__all__ = [
    "Chapter",
    "REPO_SLUG",
    "classes_present",
    "classify_filename",
    "load_chapters",
    "lookup",
]
