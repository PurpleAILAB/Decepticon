"""Path-based inference of whether a SKILL.md describes an offensive skill.

Replaces the v0.1 spec's ``metadata.kind`` check. The frontmatter field
is dead in production (4/251 files), so we infer "offensive" from the
file path: anything under ``/skills/<source>/reporting/`` or
``/skills/<source>/analyst/`` is non-offensive; everything else is
offensive.
"""

from __future__ import annotations

import re

# Match "...skills/<source>/(reporting|analyst)/..." where <source> is
# one path segment (typically "standard" or "plugins/<plugin>").
_NON_OFFENSIVE_RE = re.compile(
    r"(?:^|/)skills/[^/]+(?:/[^/]+)*/(?:reporting|analyst)/",
)


def is_offensive_path(path: str) -> bool:
    """Return True if the SKILL.md path indicates an offensive skill."""
    return _NON_OFFENSIVE_RE.search(path) is None
