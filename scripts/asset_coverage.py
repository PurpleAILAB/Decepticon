#!/usr/bin/env python3
"""Print the asset-type coverage report. Run via ``make asset-coverage``.

Exit 0 for the report; exit 1 only if the catalog fails an internal
integrity invariant (count != 75), so CI can wire it as a guard.
"""

from __future__ import annotations

import sys

from decepticon_core.types import asset_types as at


def main() -> int:
    entries = at.all()
    if len(entries) != 75:
        print(f"INTEGRITY ERROR: expected 75 entries, found {len(entries)}", file=sys.stderr)
        return 1

    summary = at.coverage_summary()
    print("Asset-type coverage")
    print("===================")
    print(f"  covered: {summary['covered']:>3}")
    print(f"  partial: {summary['partial']:>3}")
    print(f"  gap:     {summary['gap']:>3}")
    print(f"  total:   {len(entries):>3}")
    print()
    for status in ("gap", "partial"):
        rows = [a for a in entries if a.coverage == status]
        if rows:
            print(f"{status.upper()} ({len(rows)}):")
            for a in sorted(rows, key=lambda x: x.number):
                print(
                    f"  #{a.number:<3} {a.id:<22} {a.category:<20} -> {', '.join(a.agents) or '(none)'}"
                )
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
