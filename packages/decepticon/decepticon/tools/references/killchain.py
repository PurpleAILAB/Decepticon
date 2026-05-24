"""Kill-chain phase → tool mapper.

Two data sources, merged transparently:

1. **Committed fallback YAML** — ``killchain.yaml`` shipped alongside
   this module. A small curated set of ~80 tools grouped by MITRE
   ATT&CK tactic so the agent always has a baseline map without a
   clone.
2. **Upstream parse** — the cached clone of ``A-poc/RedTeam-Tools``
   README is scanned for markdown tool tables and merged on top.

Phases are normalized to the MITRE ATT&CK tactic vocabulary:

    recon | weaponization | delivery | exploitation |
    persistence | privilege-escalation | defense-evasion |
    credential-access | discovery | lateral-movement |
    collection | command-and-control | exfiltration | impact

Unrecognized upstream headings are kept as-is so the data is not
silently lost — they sort last in ``lookup()`` output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.tools.references.fetch import cache_path

REPO_SLUG = "redteam-tools"

_FALLBACK_FILE = Path(__file__).parent / "killchain.yaml"

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

_PHASE_ALIASES: dict[str, str] = {
    "reconnaissance": "recon",
    "recon": "recon",
    "osint": "recon",
    "scanning": "recon",
    "enumeration": "recon",
    "weaponization": "weaponization",
    "initial access": "delivery",
    "delivery": "delivery",
    "exploitation": "exploitation",
    "exploit": "exploitation",
    "persistence": "persistence",
    "privilege escalation": "privilege-escalation",
    "priv esc": "privilege-escalation",
    "privesc": "privilege-escalation",
    "defense evasion": "defense-evasion",
    "evasion": "defense-evasion",
    "credential access": "credential-access",
    "credential dumping": "credential-access",
    "password cracking": "credential-access",
    "credentials": "credential-access",
    "discovery": "discovery",
    "internal recon": "discovery",
    "lateral movement": "lateral-movement",
    "lateral": "lateral-movement",
    "pivoting": "lateral-movement",
    "collection": "collection",
    "command and control": "command-and-control",
    "c2": "command-and-control",
    "command & control": "command-and-control",
    "exfiltration": "exfiltration",
    "exfil": "exfiltration",
    "impact": "impact",
    "post exploitation": "persistence",
}


@dataclass
class ToolEntry:
    """One tool → phase mapping row."""

    name: str
    phase: str
    description: str = ""
    url: str = ""
    source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phase": self.phase,
            "description": self.description,
            "url": self.url,
            "source": self.source,
        }


_CANONICAL_PHASES: frozenset[str] = frozenset(
    {
        "recon",
        "weaponization",
        "delivery",
        "exploitation",
        "persistence",
        "privilege-escalation",
        "defense-evasion",
        "credential-access",
        "discovery",
        "lateral-movement",
        "collection",
        "command-and-control",
        "exfiltration",
        "impact",
        "misc",
    }
)


def normalize_phase(raw: str) -> str:
    """Fold any heading variant into the canonical phase slug."""
    if raw in _CANONICAL_PHASES:
        return raw
    lowered = raw.strip().lower()
    if lowered in _CANONICAL_PHASES:
        return lowered
    # Hyphenated canonical form like "credential-access"
    if lowered.replace("-", " ") in _PHASE_ALIASES:
        return _PHASE_ALIASES[lowered.replace("-", " ")]
    key = re.sub(r"[^a-z0-9 &]", "", lowered).strip()
    key = re.sub(r"\s+", " ", key)
    if key in _PHASE_ALIASES:
        return _PHASE_ALIASES[key]
    for alias, canonical in _PHASE_ALIASES.items():
        if alias in key:
            return canonical
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "misc"


def _load_yaml_fallback() -> list[ToolEntry]:
    """Parse the committed ``killchain.yaml``.

    Uses a tiny hand-rolled YAML reader so the package has no new
    third-party dependency. The format is strict:

        - name: nmap
          phase: recon
          description: Port scanner
          url: https://nmap.org
    """
    if not _FALLBACK_FILE.is_file():
        return []
    try:
        raw = _FALLBACK_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[ToolEntry] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current.get("name"):
                entries.append(
                    ToolEntry(
                        name=current.get("name", ""),
                        phase=normalize_phase(current.get("phase", "")),
                        description=current.get("description", ""),
                        url=current.get("url", ""),
                        source="fallback",
                    )
                )
            current = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        current[key.strip()] = value.strip().strip('"').strip("'")
    if current.get("name"):
        entries.append(
            ToolEntry(
                name=current.get("name", ""),
                phase=normalize_phase(current.get("phase", "")),
                description=current.get("description", ""),
                url=current.get("url", ""),
                source="fallback",
            )
        )
    return entries


def _parse_readme(repo: Path) -> list[ToolEntry]:
    readme = repo / "README.md"
    if not readme.is_file():
        return []
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries: list[ToolEntry] = []
    heading_stack: list[str] = []
    for raw in text.splitlines():
        heading = _HEADING.match(raw)
        if heading:
            depth = len(heading.group(1))
            title = heading.group(2).strip()
            del heading_stack[depth - 1 :]
            heading_stack.append(title)
            continue
        # Tool rows show up either as bullet-list links or markdown
        # table rows with a name + description.
        stripped = raw.strip()
        if not stripped:
            continue
        link = _MD_LINK.search(stripped)
        if not link:
            continue
        name = link.group(1).strip()
        url = link.group(2).strip()
        if not name or not url.startswith("http"):
            continue
        # Phase = closest heading mapped to a known tactic.
        phase = "misc"
        for heading_text in reversed(heading_stack):
            candidate = normalize_phase(heading_text)
            if candidate in _CANONICAL_PHASES and candidate != "misc":
                phase = candidate
                break
        # Description = the text after the link in the same line.
        rest = stripped[link.end() :].lstrip(" -:|")
        description = rest[:200]
        entries.append(
            ToolEntry(
                name=name,
                phase=phase,
                description=description,
                url=url,
                source="redteam-tools",
            )
        )
    return entries


_entries_cache: dict[Path, tuple[float, list[ToolEntry]]] = {}


def _compute_entries(root: Path | None) -> list[ToolEntry]:
    merged: dict[tuple[str, str], ToolEntry] = {}
    for entry in _load_yaml_fallback():
        merged[(entry.name.lower(), entry.phase)] = entry
    repo = cache_path(REPO_SLUG, root=root)
    if repo.is_dir():
        for entry in _parse_readme(repo):
            key = (entry.name.lower(), entry.phase)
            if key not in merged:
                merged[key] = entry
    return list(merged.values())


def load_entries(*, root: Path | None = None) -> list[ToolEntry]:
    """Return the merged entry list: fallback YAML + cached upstream parse.

    Memoized per-process keyed by the RedTeam-Tools cache mtime.
    """
    repo = cache_path(REPO_SLUG, root=root)
    try:
        mtime = repo.stat().st_mtime if repo.exists() else -1.0
    except OSError:
        mtime = -1.0
    entry = _entries_cache.get(repo)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    entries = _compute_entries(root)
    _entries_cache[repo] = (mtime, entries)
    return entries


def invalidate_entries_cache() -> None:
    _entries_cache.clear()


def lookup(
    phase: str,
    *,
    limit: int = 25,
    entries: list[ToolEntry] | None = None,
    root: Path | None = None,
) -> list[ToolEntry]:
    """Return tools for the requested phase (normalized)."""
    target = normalize_phase(phase)
    pool = entries if entries is not None else load_entries(root=root)
    hits = [e for e in pool if e.phase == target]
    # Sort fallback entries first (they're curated), then alphabetical
    hits.sort(key=lambda e: (e.source != "fallback", e.name.lower()))
    return hits[:limit]


def suggest(
    objective: str,
    *,
    limit: int = 10,
    entries: list[ToolEntry] | None = None,
    root: Path | None = None,
) -> list[ToolEntry]:
    """Keyword-match an objective description against tool names + descriptions."""
    if not objective:
        return []
    terms = [t for t in re.split(r"\s+", objective.lower()) if len(t) > 2]
    if not terms:
        return []
    pool = entries if entries is not None else load_entries(root=root)
    scored: list[tuple[int, ToolEntry]] = []
    for entry in pool:
        haystack = f"{entry.name} {entry.description} {entry.phase}".lower()
        hits = sum(1 for term in terms if term in haystack)
        if hits:
            scored.append((hits, entry))
    scored.sort(key=lambda x: (x[0], x[1].source != "fallback"), reverse=True)
    return [e for _, e in scored[:limit]]


__all__ = [
    "REPO_SLUG",
    "ToolEntry",
    "load_entries",
    "lookup",
    "normalize_phase",
    "suggest",
]
