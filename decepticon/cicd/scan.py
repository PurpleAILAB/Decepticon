"""Headless CI scan gate — ``python -m decepticon.cicd.scan``.

Mirrors Strix's ``strix -n`` semantic: resolve the diff scope, point the
engagement at it (left to the launcher / Docker stack in a real run),
then evaluate the findings artifact and **exit non-zero when in-scope
findings at or above the fail threshold exist**. A non-zero exit is what
blocks the PR merge in a CI gate.

Designed to run in two modes:

* ``--check-only`` — resolve + print the diff scope and validate the
  findings file shape without failing the build on findings. Used by
  Decepticon's own CI to smoke-test the gate logic without the Docker
  stack.
* default — full gate: read ``--findings`` JSON, count findings that
  touch a changed file at/above ``--fail-on`` severity, exit ``1`` if
  any, ``0`` otherwise.

Findings file schema (the same dict shape
:func:`decepticon.tools.reporting.findings_export.write_finding_pack`
consumes)::

    [
      {"id": "...", "severity": "high", "title": "...",
       "file": "decepticon/foo.py"},   # or props.file / props.path
      ...
    ]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from decepticon.cicd.scope import DiffScopeError, resolve_diff_scope

_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _finding_path(finding: dict[str, Any]) -> str:
    """Extract the file a finding points at, tolerating shape variants."""
    for key in ("file", "path", "affected_file"):
        if finding.get(key):
            return str(finding[key])
    props = finding.get("props")
    if isinstance(props, dict):
        for key in ("file", "path", "affected_file"):
            if props.get(key):
                return str(props[key])
    return ""


def _finding_severity(finding: dict[str, Any]) -> str:
    sev = finding.get("severity")
    if not sev and isinstance(finding.get("props"), dict):
        sev = finding["props"].get("severity")
    return str(sev or "info").lower()


def load_findings(path: str | Path) -> list[dict[str, Any]]:
    """Load + validate a findings JSON file. Returns a list of dicts.

    Raises ``ValueError`` on malformed input so the gate fails loudly
    rather than silently passing a broken artifact.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"findings file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"findings file is not valid JSON: {exc}") from exc
    if isinstance(data, dict) and "findings" in data:
        data = data["findings"]
    if not isinstance(data, list):
        raise ValueError("findings file must be a JSON list or {'findings': [...]}")
    return [f for f in data if isinstance(f, dict)]


def evaluate_gate(
    findings: list[dict[str, Any]],
    changed_files: list[str],
    *,
    fail_on: str = "low",
    scope_to_diff: bool = True,
) -> dict[str, Any]:
    """Decide pass/fail for the CI gate.

    Args:
        findings: Parsed findings list.
        changed_files: Repo-relative paths the PR touched.
        fail_on: Minimum severity that fails the build.
        scope_to_diff: When True, only findings whose file is in
            ``changed_files`` count. When False, every finding counts
            (full-repo scan mode).

    Returns:
        ``{"failed": bool, "blocking": [...], "ignored": [...],
        "threshold": "..."}``.
    """
    threshold = _SEVERITY_ORDER.get(fail_on.lower(), 1)
    changed = set(changed_files)
    blocking: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for f in findings:
        sev_rank = _SEVERITY_ORDER.get(_finding_severity(f), 0)
        in_scope = (not scope_to_diff) or (_finding_path(f) in changed)
        if sev_rank >= threshold and in_scope:
            blocking.append(f)
        else:
            ignored.append(f)
    return {
        "failed": bool(blocking),
        "blocking": blocking,
        "ignored": ignored,
        "threshold": fail_on.lower(),
        "scoped": scope_to_diff,
    }


def _print_report(scope_dict: dict[str, Any], gate: dict[str, Any]) -> None:
    print("── Decepticon CI scan ──────────────────────────────")
    print(f"base={scope_dict['base']}  head={scope_dict['head']}")
    print(f"changed files: {scope_dict['count']}")
    for f in scope_dict["changed_files"][:25]:
        print(f"  · {f}")
    if scope_dict["count"] > 25:
        print(f"  … +{scope_dict['count'] - 25} more")
    print(
        f"gate: threshold={gate['threshold']} scoped={gate['scoped']} "
        f"blocking={len(gate['blocking'])} ignored={len(gate['ignored'])}"
    )
    for b in gate["blocking"]:
        sev = _finding_severity(b).upper()
        print(f"  ✗ [{sev}] {b.get('title', b.get('id', '?'))} ({_finding_path(b) or 'n/a'})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="decepticon-scan",
        description="Headless CI scan gate (Strix -n parity).",
    )
    p.add_argument("--diff-base", default=None, help="Base ref (default origin/main).")
    p.add_argument("--head", default="HEAD", help="Head ref (default HEAD).")
    p.add_argument("--repo", default=".", help="Path inside the target repo.")
    p.add_argument(
        "--findings",
        default=None,
        help="Findings JSON produced by the engagement. Omit with --check-only.",
    )
    p.add_argument(
        "--fail-on",
        default="low",
        choices=sorted(_SEVERITY_ORDER),
        help="Minimum severity that fails the build (default low).",
    )
    p.add_argument(
        "--no-scope",
        action="store_true",
        help="Count every finding, not just those touching changed files.",
    )
    p.add_argument(
        "--check-only",
        action="store_true",
        help="Resolve + print scope and validate findings shape; never fail on findings.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns the process exit code (0 pass, 1 gate fail, 2 error)."""
    # The report uses box-drawing glyphs; force UTF-8 so it does not crash on
    # consoles with a legacy code page (e.g. cp1252 on Windows).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        scope = resolve_diff_scope(
            base=args.diff_base,
            head=args.head,
            repo_path=args.repo,
        )
    except DiffScopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    findings: list[dict[str, Any]] = []
    if args.findings:
        try:
            findings = load_findings(args.findings)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    elif not args.check_only:
        print(
            "error: --findings is required unless --check-only is set",
            file=sys.stderr,
        )
        return 2

    gate = evaluate_gate(
        findings,
        scope.changed_files,
        fail_on=args.fail_on,
        scope_to_diff=not args.no_scope,
    )
    _print_report(scope.to_dict(), gate)

    if args.check_only:
        print("check-only: gate not enforced")
        return 0
    if gate["failed"]:
        print(f"\nGATE FAILED — {len(gate['blocking'])} blocking finding(s)")
        return 1
    print("\nGATE PASSED — no blocking findings in scope")
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess in tests
    raise SystemExit(main())
