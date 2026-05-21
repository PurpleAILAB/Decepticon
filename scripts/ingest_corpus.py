#!/usr/bin/env python3
"""Drift detector for the vendored payload corpus.

Walks ``skills/_corpus/payloads/`` (PayloadsAllTheThings submodule),
hashes each top-level vuln-class README.md, and maintains
``skills/_corpus/.manifest.json`` mapping ``<vuln-class>`` →
``{sha256, last_seen_commit, mapped_skill_path}``.

Re-running prints ``STALE | NEW | UNCHANGED | MISSING_LEAF`` per class so
CI can fail or open an issue when:
  * Upstream content drifted (sha changed) for a class already mapped to a
    Decepticon leaf — the leaf may need a refresh.
  * A new vuln-class directory appeared upstream without a Decepticon
    mapping yet (``NEW``).
  * The Decepticon leaf path referenced in the manifest no longer exists
    on disk (``MISSING_LEAF``).

Idempotent, pure-Python (stdlib only), <5s runtime on a 14MB submodule.

Usage::

    python3 scripts/ingest_corpus.py            # update manifest in place
    python3 scripts/ingest_corpus.py --report   # don't write, print diff
    python3 scripts/ingest_corpus.py --check    # exit non-zero if any drift

Designed for CI integration; safe to run on every push.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "skills" / "_corpus" / "payloads"
MANIFEST_PATH = REPO_ROOT / "skills" / "_corpus" / ".manifest.json"

# vuln-class directory names that DO NOT have a Decepticon leaf mapping yet —
# refreshing the manifest will mark these NEW. Use this as a placeholder for
# the leaves we want to write next (see TODO comments in each).
DEFAULT_MAPPINGS: dict[str, str] = {
    # Already-populated Decepticon leaves (matching upstream classes)
    "SQL Injection": "skills/exploit/web/sqli.md",
    "XSS Injection": "skills/exploit/web/xss.md",
    "XXE Injection": "skills/exploit/web/xxe.md",
    "Server Side Request Forgery": "skills/exploit/web/ssrf.md",
    "Server Side Template Injection": "skills/exploit/web/ssti.md",
    "Command Injection": "skills/exploit/web/command-injection.md",
    "CRLF Injection": "skills/exploit/web/crlf.md",
    "File Inclusion": "skills/exploit/web/lfi.md",
    "Race Condition": "skills/exploit/web/race-condition.md",
    "Request Smuggling": "skills/exploit/web/smuggling.md",
    "Insecure Deserialization": "skills/exploit/web/deserialization.md",
    "GraphQL Injection": "skills/exploit/web/graphql.md",
    "Upload Insecure Files": "skills/exploit/web/file-upload.md",
    "Prototype Pollution": "skills/analyst/prototype-pollution.md",
    "Prompt Injection": "skills/analyst/prompt-injection.md",
    # Newly-added Decepticon leaves (this PR populates these mappings)
    "JSON Web Token": "skills/exploit/web/jwt/SKILL.md",
    "OAuth Misconfiguration": "skills/exploit/web/oauth/SKILL.md",
    "SAML Injection": "skills/exploit/web/saml/SKILL.md",
    "Web Cache Deception": "skills/exploit/web/cache-deception/SKILL.md",
    "NoSQL Injection": "skills/exploit/web/nosqli/SKILL.md",
    "LDAP Injection": "skills/exploit/web/ldapi/SKILL.md",
    "XPATH Injection": "skills/exploit/web/xpath-xslt/SKILL.md",
    "XSLT Injection": "skills/exploit/web/xpath-xslt/SKILL.md",
    "Open Redirect": "skills/exploit/web/open-redirect/SKILL.md",
    "Mass Assignment": "skills/exploit/web/mass-assignment/SKILL.md",
    "ORM Leak": "skills/exploit/web/mass-assignment/SKILL.md",
    "DOM Clobbering": "skills/exploit/web/dom-clobbering/SKILL.md",
    "XS-Leak": "skills/exploit/web/xs-leaks/SKILL.md",
    "Account Takeover": "skills/exploit/web/ato-methodology/SKILL.md",
    "Reverse Proxy Misconfigurations": "skills/exploit/web/proxy-misconfig/SKILL.md",
    "Dependency Confusion": "skills/exploit/supplychain/dep-confusion/SKILL.md",
    "CSS Injection": "skills/exploit/web/css-injection/SKILL.md",
    "Tabnabbing": "skills/exploit/web/open-redirect/SKILL.md",
}


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def current_submodule_sha() -> str:
    """Return the commit SHA the PayloadsAllTheThings submodule is pinned to."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=CORPUS_ROOT,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def scan_corpus() -> dict[str, dict[str, str]]:
    """Walk corpus, return {class_name: {sha256, readme_relpath}}."""
    classes: dict[str, dict[str, str]] = {}
    if not CORPUS_ROOT.is_dir():
        print(
            f"error: corpus root {CORPUS_ROOT} not found; run `git submodule update --init` first",
            file=sys.stderr,
        )
        sys.exit(2)
    for entry in sorted(CORPUS_ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        readme = entry / "README.md"
        if not readme.is_file():
            continue
        classes[entry.name] = {
            "sha256": sha256_file(readme),
            "readme_relpath": readme.relative_to(REPO_ROOT).as_posix(),
        }
    return classes


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"submodule_sha": "unknown", "classes": {}}
    return json.loads(MANIFEST_PATH.read_text())


def write_manifest(data: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def diff_and_classify(
    prior: dict, current_classes: dict[str, dict[str, str]]
) -> tuple[dict, list[tuple[str, str, str]]]:
    """Compare prior manifest to current scan.

    Returns (new_manifest, drift_rows). Each drift_row is a tuple of
    (status, class_name, mapped_leaf_or_dash). Status ∈ {STALE, NEW,
    UNCHANGED, MISSING_LEAF}.
    """
    new_classes: dict[str, dict[str, str]] = {}
    drift: list[tuple[str, str, str]] = []
    prior_classes: dict[str, dict[str, str]] = prior.get("classes", {})

    for name, scan in current_classes.items():
        mapped = DEFAULT_MAPPINGS.get(name, prior_classes.get(name, {}).get("mapped_leaf", ""))
        leaf_present = bool(mapped) and (REPO_ROOT / mapped).is_file()

        if name not in prior_classes:
            status = "NEW"
        elif prior_classes[name].get("sha256") != scan["sha256"]:
            status = "STALE"
        elif mapped and not leaf_present:
            status = "MISSING_LEAF"
        else:
            status = "UNCHANGED"

        drift.append((status, name, mapped or "-"))
        new_classes[name] = {
            "sha256": scan["sha256"],
            "readme_relpath": scan["readme_relpath"],
            "mapped_leaf": mapped,
        }

    new_manifest = {
        "submodule_sha": current_submodule_sha(),
        "classes": new_classes,
    }
    return new_manifest, drift


def print_drift(rows: list[tuple[str, str, str]]) -> None:
    # Sort by status (NEW first, then STALE, then MISSING_LEAF, then UNCHANGED)
    order = {"NEW": 0, "STALE": 1, "MISSING_LEAF": 2, "UNCHANGED": 3}
    rows = sorted(rows, key=lambda r: (order.get(r[0], 4), r[1]))
    counts = {}
    for status, name, leaf in rows:
        counts[status] = counts.get(status, 0) + 1
        if status != "UNCHANGED":
            print(f"{status:14s} {name:42s} → {leaf}")
    print()
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"summary: {summary} ({sum(counts.values())} classes total)")


def main() -> int:
    # The drift table uses non-ASCII glyphs; force UTF-8 so it does not crash
    # on consoles with a legacy code page (e.g. cp1252 on Windows).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="print drift only, don't write manifest")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if NEW, STALE, or MISSING_LEAF detected (for CI gating)",
    )
    args = ap.parse_args()

    prior = load_manifest()
    current = scan_corpus()
    new_manifest, drift = diff_and_classify(prior, current)
    print_drift(drift)

    if not args.report:
        write_manifest(new_manifest)
        print(f"\nwrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")

    if args.check:
        bad = [r for r in drift if r[0] in ("NEW", "STALE", "MISSING_LEAF")]
        if bad:
            print(f"\nfailing: {len(bad)} class(es) need attention", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
