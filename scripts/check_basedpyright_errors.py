"""Parse a basedpyright JSON report and fail iff there are error-level diagnostics.

Warnings and information are reported as a count but do not fail the gate —
the codebase carries pre-existing warnings on langchain dynamic interfaces
that are tracked but non-blocking. The error-count is ratcheted up over time.

Usage:
    uv run basedpyright --outputjson > bp.json
    uv run python scripts/check_basedpyright_errors.py bp.json

Exits 0 if no errors, 1 if any error-level diagnostic is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <bp.json>", file=sys.stderr)
        return 2

    bp_path = Path(argv[1])
    if not bp_path.exists():
        print(f"basedpyright JSON not found: {bp_path}", file=sys.stderr)
        return 2

    data = json.loads(bp_path.read_text())
    summary = data["summary"]
    print(
        f"basedpyright: {summary['errorCount']} errors, "
        f"{summary['warningCount']} warnings, "
        f"{summary['informationCount']} info"
    )

    if not summary["errorCount"]:
        return 0

    print()
    print("=== error-level diagnostics ===")
    for diag in data.get("generalDiagnostics", []):
        if diag.get("severity") != "error":
            continue
        loc = diag.get("range", {}).get("start", {})
        line = loc.get("line", 0)
        if isinstance(line, int):
            line += 1
        print(f"  {diag.get('file', '?')}:{line}")
        print(f"    {diag.get('message', '')}")
        if diag.get("rule"):
            print(f"    rule: {diag['rule']}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
