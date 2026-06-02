"""``python -m decepticon.skillogy.builder`` — assemble the full
graph from seeds + SKILL.md + MITRE STIX and emit ``skills.cypher``.

Default paths point at the in-tree corpus. The STIX bundle is required
because Phase 1a's IMPLEMENTS edges only resolve when their target
``:Technique`` nodes exist. Use ``--no-mitre`` to emit a skills-only
dump for fast local iteration.
"""

from __future__ import annotations

import argparse
import enum
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from decepticon.skillogy.builder.emit import emit_cypher
from decepticon.skillogy.builder.mitre_stix import emit_mitre_records
from decepticon.skillogy.builder.model import Edge, Node
from decepticon.skillogy.builder.seeds_to_graph import emit_all_seed_records
from decepticon.skillogy.builder.skills import emit_skill_records


class ExitCode(enum.IntEnum):
    OK = 0
    DIFF_FOUND = 1
    USAGE_ERROR = 2


def _git_head() -> str:
    """Return the current git HEAD, empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return ""


def build_graph(
    *,
    skills_root: Path,
    stix_bundle: Path | None,
    commit_sha: str,
    built_at: datetime,
) -> tuple[list[Node], list[Edge]]:
    """Run every emit pass and return the combined node/edge lists."""
    nodes: list[Node] = []
    edges: list[Edge] = []

    seed_nodes, seed_edges = emit_all_seed_records()
    nodes.extend(seed_nodes)
    edges.extend(seed_edges)

    if stix_bundle is not None:
        mitre_nodes, mitre_edges = emit_mitre_records(stix_bundle)
        nodes.extend(mitre_nodes)
        edges.extend(mitre_edges)

    skill_nodes, skill_edges = emit_skill_records(
        skills_root, commit_sha=commit_sha, built_at=built_at
    )
    nodes.extend(skill_nodes)
    edges.extend(skill_edges)

    return nodes, edges


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m decepticon.skillogy.builder",
        description="Compile SKILL.md + seeds + MITRE STIX into skills.cypher.",
    )
    parser.add_argument(
        "--skills-root",
        type=Path,
        default=Path("packages/decepticon/decepticon/skills"),
        help="Corpus root to scan.",
    )
    parser.add_argument(
        "--stix-bundle",
        type=Path,
        default=Path(
            os.environ.get(
                "SKILLOGY_STIX_BUNDLE",
                str(Path.home() / ".cache/skillogy/mitre/enterprise-attack-19.1.json"),
            )
        ),
        help=(
            "Path to a pinned MITRE ATT&CK Enterprise STIX 2.1 bundle. "
            "Default reads $SKILLOGY_STIX_BUNDLE or ~/.cache/skillogy/mitre/enterprise-attack-19.1.json."
        ),
    )
    parser.add_argument(
        "--no-mitre",
        action="store_true",
        help="Skip the MITRE STIX importer (skills-only dump for fast iteration).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("packages/decepticon/decepticon/skills/.graph/skills.cypher"),
        help="Output Cypher dump path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the on-disk dump differs from the built output (no write).",
    )
    parser.add_argument(
        "--frozen-built-at",
        action="store_true",
        help=(
            "Use a fixed built_at timestamp (1970-01-01T00:00:00+00:00) so the dump "
            "is byte-identical across CI runs. Required for --check."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> ExitCode:
    args = _build_argparser().parse_args(argv)
    if not args.skills_root.exists():
        print(f"error: --skills-root {args.skills_root} does not exist", file=sys.stderr)
        return ExitCode.USAGE_ERROR

    stix_bundle: Path | None
    if args.no_mitre:
        stix_bundle = None
    else:
        if not args.stix_bundle.exists():
            print(
                f"error: --stix-bundle {args.stix_bundle} does not exist; "
                f"download it from github.com/mitre-attack/attack-stix-data or pass --no-mitre",
                file=sys.stderr,
            )
            return ExitCode.USAGE_ERROR
        stix_bundle = args.stix_bundle

    built_at = (
        datetime(1970, 1, 1, tzinfo=timezone.utc)
        if args.frozen_built_at or args.check
        else datetime.now(timezone.utc)
    )
    commit_sha = "" if args.check or args.frozen_built_at else _git_head()

    nodes, edges = build_graph(
        skills_root=args.skills_root,
        stix_bundle=stix_bundle,
        commit_sha=commit_sha,
        built_at=built_at,
    )
    text = emit_cypher(nodes, edges)

    if args.check:
        if not args.out.exists():
            print(f"error: --check but {args.out} does not exist", file=sys.stderr)
            return ExitCode.DIFF_FOUND
        existing = args.out.read_text(encoding="utf-8")
        if existing == text:
            print(f"OK: {args.out} matches build output ({len(nodes)} nodes, {len(edges)} edges)")
            return ExitCode.OK
        print(
            f"DIFF: {args.out} differs from build output. "
            f"Run `python -m decepticon.skillogy.builder` to regenerate.",
            file=sys.stderr,
        )
        return ExitCode.DIFF_FOUND

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(text)} bytes, {len(nodes)} nodes, {len(edges)} edges)")
    return ExitCode.OK
