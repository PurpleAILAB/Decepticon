"""Command-line entry: scan a skill corpus, print a report, exit 0/1.

Two modes:

- ``warn`` (default during Phase 0 cleanup): prints all violations and
  exits ``0``. CI uses this until the corpus is clean.
- ``strict``: prints all violations and exits ``1`` if any are found.
  CI switches to this after Phase 0 completes.
"""

from __future__ import annotations

import argparse
import enum
import sys
from dataclasses import dataclass
from pathlib import Path

from decepticon.skill_audit.rules import RuleId, Violation, validate_skill_file


class ExitCode(enum.IntEnum):
    OK = 0
    VIOLATIONS_FOUND = 1
    USAGE_ERROR = 2


@dataclass(frozen=True)
class CorpusReport:
    """Result of scanning a corpus root."""

    files_scanned: int
    violations: list[Violation]


def scan_corpus(root: Path) -> CorpusReport:
    """Walk every ``SKILL.md`` under ``root`` and collect violations.

    Per-file rules run via ``validate_skill_file``. Corpus-level rules
    (currently only ``R-duplicate-name``) run after the walk so they
    can see every frontmatter at once.
    """
    files_scanned = 0
    violations: list[Violation] = []
    # name → [paths] for R-duplicate-name. The graph builder MERGEs
    # :Skill nodes on this field; non-unique names silently collapse
    # rows in Neo4j and lose skills from the live catalog.
    name_index: dict[str, list[str]] = {}
    for skill_md in sorted(root.rglob("SKILL.md")):
        files_scanned += 1
        text = skill_md.read_text(encoding="utf-8")
        violations.extend(validate_skill_file(str(skill_md), text))
        # Index the frontmatter name without re-parsing (cheap regex).
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "---":
                break
            if stripped.startswith("name:"):
                name = stripped.split(":", 1)[1].strip().strip("'\"")
                if name:
                    name_index.setdefault(name, []).append(str(skill_md))
                break
    for name, paths in sorted(name_index.items()):
        if len(paths) > 1:
            for p in paths:
                violations.append(
                    Violation(
                        p,
                        RuleId.DUPLICATE_NAME,
                        f"frontmatter name {name!r} also appears in: "
                        + ", ".join(other for other in paths if other != p),
                    )
                )
    return CorpusReport(files_scanned=files_scanned, violations=violations)


def _format_report(report: CorpusReport) -> str:
    """Human-readable report. One line per violation, summary at the end."""
    lines = [f"{v.rule_id.value} {v.path}: {v.detail}" for v in report.violations]
    lines.append(f"-- {report.files_scanned} files scanned, {len(report.violations)} violations")
    return "\n".join(lines)


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m decepticon.skill_audit",
        description="Validate SKILL.md frontmatter against the canonical schema.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("packages/decepticon/decepticon/skills"),
        help="Corpus root to scan (defaults to the packaged skills tree).",
    )
    parser.add_argument(
        "--mode",
        choices=("warn", "strict"),
        default="warn",
        help="warn: exit 0 even with violations. strict: exit 1 on any.",
    )
    return parser


def main(argv: list[str] | None = None) -> ExitCode:
    args = _build_argparser().parse_args(argv)
    if not args.root.exists():
        print(f"error: --root {args.root} does not exist", file=sys.stderr)
        return ExitCode.USAGE_ERROR
    report = scan_corpus(args.root)
    print(_format_report(report))
    if args.mode == "strict" and report.violations:
        return ExitCode.VIOLATIONS_FOUND
    return ExitCode.OK
