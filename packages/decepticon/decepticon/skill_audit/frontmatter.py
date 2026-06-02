"""SKILL.md YAML frontmatter parsing.

The corpus uses a leading ``---`` delimited YAML block followed by the
markdown body. This module isolates the parse so the validator can
report ``FrontmatterParseError`` per-file rather than crashing the
whole run on one bad file.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*(?:\n(.*))?\Z",
    re.DOTALL,
)


class FrontmatterParseError(ValueError):
    """Raised when a SKILL.md has no frontmatter or malformed YAML."""


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter_dict, body).

    The frontmatter dict is the raw YAML mapping; nested ``metadata``
    stays nested. The body is the markdown after the closing ``---``,
    with no leading newline.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise FrontmatterParseError("no YAML frontmatter block found")
    raw_yaml, raw_body = match.group(1), match.group(2) or ""
    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise FrontmatterParseError(f"YAML parse failed: {exc}") from exc
    if parsed is None:
        return {}, raw_body
    if not isinstance(parsed, dict):
        raise FrontmatterParseError(
            f"frontmatter must be a YAML mapping, got {type(parsed).__name__}"
        )
    return parsed, raw_body
