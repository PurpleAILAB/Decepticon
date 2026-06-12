"""``decepticon-cli zip`` - package and restore engagement workspaces.

An engagement's durable state lives under ``<workspace>/engagements/<id>/``
(``events.jsonl``, persisted knowledge graphs, planning documents, the RoE
audit ledger). Operators need to hand a finished engagement to a teammate,
archive it off the runner, or move it between hosts. This command turns that
directory into a single portable ZIP and restores it on the far side.

Subcommands
-----------
- ``export`` — zip ``<workspace>/engagements/<id>/`` into a ``.zip`` file.
  Archive entries are stored under a top-level ``<id>/`` prefix so the file
  is self-describing and round-trips cleanly through ``import``.
- ``import`` — restore an exported ZIP back under a workspace's
  ``engagements/`` directory, then verify every archived file landed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2


def _default_workspace() -> Path | None:
    value = os.environ.get("DECEPTICON_ENGAGEMENT_WORKSPACE")
    return Path(value) if value else None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="decepticon-cli zip",
        description="Package and restore Decepticon engagement workspaces.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    export = sub.add_parser(
        "export",
        help="Zip an engagement directory into a portable .zip archive.",
    )
    export.add_argument(
        "engagement_id",
        help="Engagement identifier; the directory <workspace>/engagements/<id> is archived.",
    )
    export.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help=(
            "Workspace root containing the engagements/ directory. "
            "Defaults to $DECEPTICON_ENGAGEMENT_WORKSPACE."
        ),
    )
    export.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Destination path for the .zip archive.",
    )

    imp = sub.add_parser(
        "import",
        help="Restore an exported engagement .zip under a workspace.",
    )
    imp.add_argument(
        "archive",
        type=Path,
        help="Path to an engagement .zip produced by `zip export`.",
    )
    imp.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help=(
            "Workspace root to restore into; the engagement lands under "
            "<workspace>/engagements/<id>. Defaults to $DECEPTICON_ENGAGEMENT_WORKSPACE."
        ),
    )
    imp.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing engagement directory instead of failing.",
    )
    return p


def _resolve_workspace(arg_value: Path | None) -> Path | None:
    return arg_value if arg_value is not None else _default_workspace()


def export_engagement(engagement_id: str, workspace: Path, output: Path) -> int:
    """Zip ``<workspace>/engagements/<engagement_id>/`` into ``output``.

    Archive entries are stored relative to ``engagements/`` so the top-level
    directory inside the ZIP is ``<engagement_id>/``. Returns the number of
    files written.
    """
    source = workspace / "engagements" / engagement_id
    if not source.is_dir():
        raise FileNotFoundError(f"engagement directory not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    base = source.parent  # <workspace>/engagements
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            arcname = path.relative_to(base).as_posix()
            if path.is_dir():
                # Preserve empty directories explicitly.
                if not any(path.iterdir()):
                    zf.writestr(arcname + "/", "")
                continue
            zf.write(path, arcname)
            count += 1
    return count


def _safe_members(zf: zipfile.ZipFile, dest_root: Path) -> tuple[set[str], list[zipfile.ZipInfo]]:
    """Validate archive entries and return (engagement_ids, members).

    Rejects absolute paths, ``..`` traversal and symlink entries so a malicious
    archive cannot escape ``dest_root`` or plant links pointing outside it.
    Returns the set of top-level engagement ids found.
    """
    dest_resolved = dest_root.resolve()
    engagement_ids: set[str] = set()
    members: list[zipfile.ZipInfo] = []
    for info in zf.infolist():
        name = info.filename
        parts = Path(name).parts
        if not parts:
            continue
        if Path(name).is_absolute() or ".." in parts:
            raise ValueError(f"unsafe path in archive: {name}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"symlink entry not allowed in archive: {name}")
        target = (dest_root / name).resolve()
        if target != dest_resolved and not target.is_relative_to(dest_resolved):
            raise ValueError(f"path escapes destination: {name}")
        engagement_ids.add(parts[0])
        members.append(info)
    return engagement_ids, members


def import_engagement(archive: Path, workspace: Path, force: bool = False) -> tuple[str, int]:
    """Restore ``archive`` under ``<workspace>/engagements/``.

    Returns ``(engagement_id, files_restored)``. Verifies every archived
    regular file exists on disk after extraction. Refuses to clobber an
    existing engagement unless ``force`` is set, in which case the existing
    directory is removed first so the restore is a clean replacement rather
    than a merge with stale files.
    """
    if not archive.is_file():
        raise FileNotFoundError(f"archive not found: {archive}")
    if not zipfile.is_zipfile(archive):
        raise ValueError(f"not a valid ZIP archive: {archive}")

    dest_root = workspace / "engagements"
    dest_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zf:
        engagement_ids, members = _safe_members(zf, dest_root)
        if len(engagement_ids) != 1:
            raise ValueError(
                f"archive must contain exactly one engagement, found: {sorted(engagement_ids)}"
            )
        (engagement_id,) = tuple(engagement_ids)

        existing = dest_root / engagement_id
        if existing.exists() or existing.is_symlink():
            if not force:
                raise ValueError(
                    f"engagement already exists: {existing} (use --force to overwrite)"
                )
            if existing.is_dir() and not existing.is_symlink():
                shutil.rmtree(existing)
            else:
                existing.unlink()

        restored = 0
        for info in members:
            zf.extract(info, dest_root)
            if info.is_dir():
                continue
            extracted = dest_root / info.filename
            if not extracted.is_file():
                raise RuntimeError(f"restore verification failed for: {info.filename}")
            restored += 1
    return engagement_id, restored


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    workspace = _resolve_workspace(args.workspace)
    if workspace is None:
        print(
            "error: workspace not set; pass --workspace or $DECEPTICON_ENGAGEMENT_WORKSPACE",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if args.command == "export":
        try:
            count = export_engagement(args.engagement_id, workspace, args.output)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"exported {count} file(s) from engagement {args.engagement_id} to {args.output}")
        return EXIT_OK

    if args.command == "import":
        try:
            engagement_id, restored = import_engagement(args.archive, workspace, args.force)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        dest = workspace / "engagements" / engagement_id
        print(f"imported engagement {engagement_id} ({restored} file(s)) to {dest}")
        return EXIT_OK

    return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
