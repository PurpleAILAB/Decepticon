"""No-Site-Name rule checker for the open-web engine.

The engine must stay site-agnostic: target knowledge (which host, which CSS
selector, which referer) enters ONLY at runtime via the tool's arguments, never
hardcoded in ``decepticon/sandbox_web/**`` or ``waf_profiles.yaml``. A hardcoded
host would bias the generic fetch chain toward one target and, worse for a
RoE-gated red-team tool, smuggle an out-of-band destination past scope review.

Run as a CI gate / locally::

    python -m decepticon.sandbox_web.bias_check
    python -m decepticon.sandbox_web.bias_check --strict   # also scan docstrings

Exit 0 if clean, 1 if violations found.

Derived from ``fivetaku/insane-search`` (MIT), ``engine/bias_check.py``.

What is allowed (NOT a violation):
  * WAF *product* names (akamai, cloudflare, datadome, …) — the whole point.
  * Generic/neutral hosts in ``URL_ALLOWLIST`` (example.com, localhost, the
    google.com referer strategy, httpbin test endpoint).
  * A line tagged ``# NOTE-BIAS-OK`` / ``# EXAMPLE-ONLY``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Bare URL / domain matcher — flags hardcoded site hosts in engine code.
URL_PATTERN = re.compile(
    r"https?://[\w.-]+|[\w-]+\.(?:com|net|org|co\.kr|kr|io|dev|ai)\b",
    re.IGNORECASE,
)

# Generic / neutral hosts allowed anywhere — provably unrelated to any target
# preference (examples, stdlib docs, the neutral google referer, test endpoints).
URL_ALLOWLIST = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "127.0.0.1",
    # Tool/doc sources cited in comments.
    "curl.se",
    "playwright.dev",
    "nodejs.org",
    "npmjs.com",
    # Neutral off-site referer strategy target.
    "www.google.com",
    "google.com",
    # Generic HTTP test endpoint for transport tests.
    "httpbin.org",
}

# Comment markers that exempt a line (human-reviewed explanation).
COMMENT_OK_MARKERS = {
    ".py": ("# NOTE-BIAS-OK", "# EXAMPLE-ONLY"),
    ".yaml": ("# NOTE-BIAS-OK", "# EXAMPLE-ONLY"),
    ".yml": ("# NOTE-BIAS-OK", "# EXAMPLE-ONLY"),
}

# Files exempted entirely (full match against path relative to the scan root).
EXPLICIT_ALLOW_FILES = {
    "bias_check.py",  # self-exempt: this file names the patterns it forbids
}

EXCLUDED_DIR_NAMES = {"__pycache__", ".git", ".venv", "dist", "build", "node_modules"}

SCANNED_SUFFIXES = (".py", ".yaml", ".yml")


def _line_is_exempt(line: str, ext: str) -> bool:
    return any(m in line for m in COMMENT_OK_MARKERS.get(ext, ()))


def _scan_file(path: Path, root: Path) -> list[str]:
    rel = path.relative_to(root)
    if path.name in EXPLICIT_ALLOW_FILES:
        return []
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"{rel}:0 — read error: {exc}"]

    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_is_exempt(line, ext):
            continue
        for match in URL_PATTERN.finditer(line):
            host = match.group(0).lower().split("//", 1)[-1].split("/", 1)[0]
            if host in URL_ALLOWLIST:
                continue
            if host.endswith(".example.com") or host.endswith(".example.org"):
                continue
            violations.append(f"{rel}:{lineno} — hardcoded host `{host}` in: {line.strip()[:120]}")
            break
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="No-Site-Name rule check for sandbox_web")
    parser.add_argument(
        "--root",
        default=None,
        help="Engine root. Defaults to the directory containing this file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="(reserved) also scan docstrings strictly — currently identical scan",
    )
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).parent

    violations: list[str] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            scanned += 1
            violations.extend(_scan_file(p, root))

    print(f"[bias-check] scanned {scanned} files under {root}")
    if violations:
        print(f"[bias-check] FAIL — {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        print()
        print("Fix: remove the hardcoded host (target knowledge belongs at runtime),")
        print("or tag the line '# NOTE-BIAS-OK' if it is a genuine non-site reference.")
        return 1

    print("[bias-check] OK — clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
