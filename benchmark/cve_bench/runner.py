"""CVE-Bench runner (live + dry-run shared loop).

Loads challenges, dispatches each to a swappable agent callable, scores
the returned evidence, and (optionally) streams JSONL. Live mode requires
the Decepticon stack + LLM credentials — see ``_default_agent``. Dry-run
mode passes ``dry_run.mock_agent`` instead.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from benchmark.cve_bench.loader import CVEBenchChallenge, load_all
from benchmark.cve_bench.scorer import Verdict, score

AgentFn = Callable[[CVEBenchChallenge], dict[str, Any]]


@dataclass
class RunnerConfig:
    fixtures_dir: Path | None = None
    variants: tuple[str, ...] = ("zero_day", "one_day")
    cve_filter: tuple[str, ...] = ()  # empty => all
    output_jsonl: Path | None = None
    mode: str = "live"


def _default_agent(_challenge: CVEBenchChallenge) -> dict[str, Any]:
    """Live-mode placeholder. Out of sprint scope.

    Full wiring will dispatch to ``benchmark.runner`` / ``benchmark.harness``
    with a CVE-Bench-shaped engagement spec and collect agent evidence
    (HTTP/SQL/admin/outbound). Requires the Decepticon stack online and LLM
    credentials — see ``benchmark/cve_bench/README.md`` §"Full run, live mode".
    """
    raise NotImplementedError(
        "Live CVE-Bench runner requires Decepticon stack + LLM credentials. "
        "Use benchmark.cve_bench.dry_run for the offline harness demo."
    )


def run_one(challenge: CVEBenchChallenge, agent: AgentFn, mode: str = "live") -> Verdict:
    start = time.monotonic()
    error: str | None = None
    evidence: dict[str, Any] = {}
    try:
        evidence = agent(challenge)
    except Exception as exc:  # pragma: no cover — surfaced via Verdict.error
        error = f"{type(exc).__name__}: {exc}"
    return score(
        challenge,
        evidence,
        duration_seconds=time.monotonic() - start,
        error=error,
        mode=mode,
    )


def run_batch(cfg: RunnerConfig, agent: AgentFn | None = None) -> list[Verdict]:
    challenges = load_all(cfg.fixtures_dir, variants=cfg.variants)
    if cfg.cve_filter:
        keep = set(cfg.cve_filter)
        challenges = [c for c in challenges if c.cve_id in keep]
    fn: AgentFn = agent or _default_agent
    verdicts: list[Verdict] = []
    handle = None
    if cfg.output_jsonl is not None:
        cfg.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        # Truncate: one batch run produces one artefact. Append would
        # duplicate verdicts when a dated dry-run file is regenerated.
        handle = cfg.output_jsonl.open("w", encoding="utf-8")
    try:
        for ch in challenges:
            v = run_one(ch, fn, mode=cfg.mode)
            verdicts.append(v)
            if handle is not None:
                handle.write(json.dumps(v.to_dict(), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    finally:
        if handle is not None:
            handle.close()
    return verdicts
