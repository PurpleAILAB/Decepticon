"""Language inventory — count files + LOC per language under a tree.

Used by the CPG Analyst to budget the rest of the analysis: if Python
dominates with 50 files and JS has 2, we joern-cli the Python and
tree-sitter the JS.

Uses extension-based detection — fast, no shebang sniffing. Good enough
for the agent's budgeting decisions; the parser modules verify language
when they actually parse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Mapping ext → canonical language tag. Add new languages here + a
# matching dictionary file under dictionaries/{lang}.yaml.
_EXT_TO_LANG: dict[str, str] = {
    # Python
    ".py": "python", ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    # Go
    ".go": "go",
    # Java / Kotlin
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    # C / C++
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    # Rust
    ".rs": "rust",
    # Ruby
    ".rb": "ruby", ".rake": "ruby",
    # PHP
    ".php": "php", ".phtml": "php",
    # C#
    ".cs": "csharp",
    # Smart contracts (handed off to contract_auditor — recorded here)
    ".sol": "solidity",
    ".move": "move",
    ".cairo": "cairo",
    ".vy": "vyper",
    # IaC (handed off to cloud_hunter — recorded here)
    ".tf": "terraform",
    ".tfvars": "terraform",
}

# Default vendored directories to skip. Engagement scope decides whether
# to include these; flip ``skip_vendored=False`` to scan them.
_VENDORED_DIRS = frozenset({
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "__pycache__",
    ".git",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "third_party",
    "third-party",
    "external",
})


@dataclass
class LanguageStats:
    """Per-language stats produced by inventory."""

    lang: str
    file_count: int = 0
    loc: int = 0
    files: list[str] = field(default_factory=list)
    primary: bool = False

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "file_count": self.file_count,
            "loc": self.loc,
            "primary": self.primary,
            "sample_files": self.files[:10],
        }


def _count_loc(path: Path) -> int:
    """Cheap LOC counter — blank-line and comment stripping is left to
    parser tools. Good-enough for budgeting."""
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def cpg_inventory_languages(
    root: str | Path,
    *,
    skip_vendored: bool = True,
    max_files: int = 50_000,
) -> dict[str, dict]:
    """Walk ``root`` and tally files + LOC per language.

    Args:
        root: directory to walk
        skip_vendored: skip common dep/build dirs (node_modules, .git, ...)
        max_files: hard cap on files walked (safety bound)

    Returns:
        ``{lang: {file_count, loc, primary, sample_files}, ...}`` sorted
        by descending file_count. The language with the most files is
        marked ``primary=True``.
    """
    root = Path(root)
    stats: dict[str, LanguageStats] = {}
    seen = 0

    for dirpath, dirnames, filenames in os.walk(root):
        if skip_vendored:
            dirnames[:] = [d for d in dirnames if d not in _VENDORED_DIRS and not d.startswith(".")]
        for fn in filenames:
            seen += 1
            if seen > max_files:
                break
            ext = os.path.splitext(fn)[1].lower()
            lang = _EXT_TO_LANG.get(ext)
            if not lang:
                continue
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            entry = stats.setdefault(lang, LanguageStats(lang=lang))
            entry.file_count += 1
            entry.loc += _count_loc(p)
            if len(entry.files) < 10:
                entry.files.append(rel)
        if seen > max_files:
            break

    if not stats:
        return {}

    primary_lang = max(stats.values(), key=lambda s: s.file_count).lang
    stats[primary_lang].primary = True

    return {
        lang: stats[lang].to_dict()
        for lang in sorted(stats.keys(), key=lambda k: -stats[k].file_count)
    }


__all__ = ["LanguageStats", "cpg_inventory_languages"]
