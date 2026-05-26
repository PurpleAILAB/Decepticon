#!/usr/bin/env python3
"""Parse and deduplicate subdomain results from multiple tools.

Usage:
    python parse_subdomains.py recon/subfinder.txt recon/amass.txt
    python parse_subdomains.py recon/*.txt --output recon/all_subs.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_subdomains(text: str) -> set[str]:
    """Extract valid subdomains from text using regex."""
    pattern = r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}"
    return {m.lower() for m in re.findall(pattern, text)}


def main():
    parser = argparse.ArgumentParser(description="Parse and deduplicate subdomains")
    parser.add_argument("files", nargs="+", help="Input files containing subdomains")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("-d", "--domain", help="Filter to this root domain only")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    all_subs: set[str] = set()
    source_map: dict[str, list[str]] = {}

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"[WARN] File not found: {filepath}", file=sys.stderr)
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        subs = extract_subdomains(text)
        all_subs.update(subs)
        source_map[path.name] = sorted(subs)

    # Filter by root domain if specified
    if args.domain:
        root = args.domain.lower().lstrip(".")
        all_subs = {s for s in all_subs if s.endswith(root)}

    sorted_subs = sorted(all_subs)

    if args.json:
        output = json.dumps(
            {
                "total": len(sorted_subs),
                "subdomains": sorted_subs,
                "sources": {k: len(v) for k, v in source_map.items()},
            },
            indent=2,
        )
    else:
        output = "\n".join(sorted_subs)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"[+] {len(sorted_subs)} unique subdomains written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
