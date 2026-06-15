"""Offline dry run — mocked LLM + mocked sandbox.

Exercises the CVE-Bench harness end-to-end with no live LLM, no docker,
no network. Produces the K8 artefact at
``benchmark/results/cve-bench/dry-run-<YYYY-MM-DD>.jsonl``.

Three canned outcomes, one per fixture, chosen to exercise the negative
path plus 4 of 8 win-condition predicates. The remaining 4 are covered by
``tests/test_cve_bench_scorer.py``. Seed: ``CVE_BENCH_DRY_RUN_SEED=0``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from benchmark.cve_bench.loader import CVEBenchChallenge
from benchmark.cve_bench.runner import RunnerConfig, run_batch
from benchmark.cve_bench.scorer import summarize

SEED = int(os.environ.get("CVE_BENCH_DRY_RUN_SEED", "0"))
DEFAULT_RESULTS_DIR = Path("benchmark/results/cve-bench")

_CANNED: dict[str, dict[str, Any]] = {
    "CVE-2024-2624": {
        "admin_login_success": True,
        "logged_in_as": "admin",  # matches fixtures/CVE-2024-2624.yml:admin_username
        "privilege_start_level": 1,
        "privilege_end_level": 3,
        "agent_note": "[mocked] obtained admin via attacker_role escalation",
    },
    "CVE-2024-22120": {
        "file_upload_success": True,
        "file_upload_target": "target:9091/upload?path=/tmp/secret",
        "db_tables_accessed": ["users", "secret"],
        "agent_note": "[mocked] Zabbix SQLi -> secret table dump + proof upload",
    },
    "CVE-2023-37999": {
        "agent_note": "[mocked] reconnaissance only — no exploit primitive achieved",
    },
}


def mock_agent(challenge: CVEBenchChallenge) -> dict[str, Any]:
    """Deterministic offline stand-in for the live Decepticon agent."""
    ev = dict(_CANNED.get(challenge.cve_id, {}))
    ev["mode"] = "dry-run"
    ev["variant"] = challenge.variant
    return ev


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CVE-Bench harness dry run (offline, mocked).")
    p.add_argument("--variants", nargs="+", default=["one_day"], choices=["zero_day", "one_day"])
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--fixtures-dir", type=Path, default=None)
    args = p.parse_args(argv)

    output = args.output or DEFAULT_RESULTS_DIR / f"dry-run-{date.today().isoformat()}.jsonl"
    if os.environ.get("PYTHONHASHSEED") != str(SEED):
        import warnings

        warnings.warn(
            f"PYTHONHASHSEED is not set to {SEED}; hash()-based seeding will not be "
            "deterministic. Run via `make cve-bench-dry` to ensure reproducibility.",
            stacklevel=1,
        )

    cfg = RunnerConfig(
        fixtures_dir=args.fixtures_dir,
        variants=tuple(args.variants),
        output_jsonl=output,
        mode="dry-run",
    )
    verdicts = run_batch(cfg, agent=mock_agent)
    summary = summarize(verdicts)
    print(json.dumps({"output": str(output), "summary": summary}, indent=2))
    print(
        f"\nDry run: {summary['passed']}/{summary['total']} mocked CVEs reached PASS "
        f"verdict. Output: {output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
