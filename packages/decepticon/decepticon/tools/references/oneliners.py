"""Shell one-liner / recipe corpus.

Chunks the cached ``trimstray/the-book-of-secret-knowledge`` repo into
topical ``Recipe`` rows — each a snippet with a heading path, optional
description, and the command block itself.

The upstream repo stores its content mostly in one massive
``README.md`` with a deep heading hierarchy; additional notes live in
sibling ``.md`` files under ``sections/`` (layout varies). This module
walks any ``*.md`` file it finds, splits on heading markers, and
captures the nearest fenced code block as the command.

Lookups are plain substring over the heading chain + description, so
callers can say ``oneliner_search("tcpdump")`` or
``oneliner_search("ssh tunnel")`` and get the best matches back.

When the cache is absent, all functions return an empty list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.tools.references.fetch import cache_path

REPO_SLUG = "book-of-secret-knowledge"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*```")


@dataclass
class Recipe:
    """One extracted command / snippet with its heading path."""

    topic: str
    headings: tuple[str, ...]
    description: str
    command: str
    source_file: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "headings": list(self.headings),
            "description": self.description,
            "command": self.command,
            "source_file": self.source_file,
            "line": self.line,
        }


def _parse_markdown(path: Path, text: str) -> list[Recipe]:
    """Walk one markdown file and yield every heading → code-block pair."""
    recipes: list[Recipe] = []
    lines = text.splitlines()
    stack: list[str] = []  # Active heading chain, indexed by depth-1
    description_buf: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING.match(line)
        if heading:
            depth = len(heading.group(1))
            title = heading.group(2).strip()
            # Trim stack to depth-1 and push this heading.
            del stack[depth - 1 :]
            stack.append(title)
            description_buf = []
            i += 1
            continue
        if _FENCE.match(line):
            # Capture until closing fence.
            start = i
            i += 1
            buf: list[str] = []
            while i < len(lines) and not _FENCE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # consume closing fence
            command = "\n".join(buf).strip()
            if not command or not stack:
                description_buf = []
                continue
            description = " ".join(description_buf).strip()[:400]
            topic = stack[-1]
            recipes.append(
                Recipe(
                    topic=topic,
                    headings=tuple(stack),
                    description=description,
                    command=command,
                    source_file=path.name,
                    line=start + 1,
                )
            )
            description_buf = []
            continue
        # Non-heading, non-fence → paragraph text becomes description
        stripped = line.strip()
        if stripped and not stripped.startswith(("|", ">", "-", "*", "```")):
            description_buf.append(stripped)
        else:
            # Table / quote / list row: keep short fragments
            if stripped and len(stripped) < 200:
                description_buf.append(stripped)
        i += 1
    return recipes


_recipes_cache: dict[tuple[Path, int], tuple[float, list[Recipe]]] = {}


def _compute_recipes(root: Path | None, limit: int) -> list[Recipe]:
    repo = cache_path(REPO_SLUG, root=root)
    if not repo.is_dir():
        return []
    recipes: list[Recipe] = []
    for md in sorted(repo.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        recipes.extend(_parse_markdown(md, text))
        if len(recipes) >= limit:
            break
    return recipes[:limit]


def load_recipes(*, root: Path | None = None, limit: int = 4000) -> list[Recipe]:
    """Walk the cached book-of-secret-knowledge repo for recipes.

    Memoized per-process by (cache-root, repo mtime, limit). Walking
    600+ markdown files on every ``oneliner_search`` call is wasted
    I/O — re-hydration invalidates the cache via directory mtime.
    """
    repo = cache_path(REPO_SLUG, root=root)
    key = (repo, limit)
    try:
        mtime = repo.stat().st_mtime if repo.exists() else -1.0
    except OSError:
        mtime = -1.0
    entry = _recipes_cache.get(key)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    recipes = _compute_recipes(root, limit)
    _recipes_cache[key] = (mtime, recipes)
    return recipes


def invalidate_recipes_cache() -> None:
    _recipes_cache.clear()


def search(
    topic: str,
    *,
    limit: int = 15,
    recipes: list[Recipe] | None = None,
    root: Path | None = None,
) -> list[Recipe]:
    """Return recipes whose heading chain / description match ``topic``.

    Ranking is dumb-but-fast: count how many query terms hit the
    heading chain + description, break ties by how early in the chain
    the hit is.
    """
    if not topic:
        return []
    terms = [t for t in re.split(r"\s+", topic.lower()) if t]
    if not terms:
        return []
    corpus = recipes if recipes is not None else load_recipes(root=root)
    scored: list[tuple[int, int, Recipe]] = []
    for r in corpus:
        haystack = " ".join(r.headings).lower() + " " + r.description.lower()
        hits = sum(1 for term in terms if term in haystack)
        if hits == 0:
            continue
        # Heading-chain depth bonus — earlier hits score higher
        chain_lower = [h.lower() for h in r.headings]
        depth_bonus = 0
        for term in terms:
            for depth, chunk in enumerate(chain_lower):
                if term in chunk:
                    depth_bonus += max(0, 10 - depth)
                    break
        scored.append((hits, depth_bonus, r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:limit]]


__all__ = ["REPO_SLUG", "Recipe", "load_recipes", "search"]
