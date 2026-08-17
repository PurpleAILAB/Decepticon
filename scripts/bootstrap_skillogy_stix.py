"""Download and verify the MITRE STIX input required by Skillogy builds."""

from __future__ import annotations

import argparse
from pathlib import Path

from decepticon.skillogy.builder.stix_bootstrap import ensure_stix_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the pinned MITRE ATT&CK Enterprise STIX v19.1 bundle."
    )
    parser.add_argument("--out", type=Path, default=None, help="Override the cached output path.")
    args = parser.parse_args(argv)
    path = ensure_stix_bundle(args.out)
    print(f"verified MITRE STIX bundle: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
