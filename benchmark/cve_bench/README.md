# CVE-Bench harness for Decepticon

Sibling to `benchmark/` XBOW provider; targets
[CVE-Bench](https://github.com/uiuc-kang-lab/cve-bench)
([leaderboard](https://cvebench.com/),
[paper](https://arxiv.org/abs/2503.17332)) — 40 critical CVEs, two
variants (`zero_day`, `one_day`), 8 win conditions per attempt.

**Sprint S5 status:** harness + offline dry run landed. Live 40 × 2 run
gated on Decepticon stack + LLM credentials (out of sprint scope). See
[`benchmark/results/cve-bench/README.md`](../results/cve-bench/README.md).

## Layout

```
benchmark/cve_bench/
├── loader.py    parse upstream CVE-*.yml → CVEBenchChallenge
├── scorer.py    8 win-condition predicates → Verdict
├── runner.py    load → agent callable → score → JSONL
├── dry_run.py   mocked LLM + sandbox, deterministic (seed=0)
└── fixtures/    CVE-2023-37999, CVE-2024-22120, CVE-2024-2624
                 (snapshotted 2026-06-11 from upstream/src/critical/metadata)
```

## Dry run (offline, mocked)

```bash
make cve-bench-dry
# == CVE_BENCH_DRY_RUN_SEED=0 PYTHONHASHSEED=0 \
#       uv run python -m benchmark.cve_bench.dry_run
```

Loads 3 fixtures as `one_day`, runs the deterministic `mock_agent` (no
LLM/docker/network), scores each against the 8 conditions
(`scorer.WIN_CONDITIONS`, verbatim from upstream README §Overview),
streams JSONL to `benchmark/results/cve-bench/dry-run-<YYYY-MM-DD>.jsonl`.

## Full run, live mode (out of scope)

`runner.py::_default_agent` raises `NotImplementedError`. Wire it by
replacing the agent callable handed to `run_batch` with one that
dispatches to `benchmark.runner.run_challenge` and returns CVE-Bench
evidence (HTTP/SQL/admin/outbound). Requires: stack online, LiteLLM
credentials, `uiuc-kang-lab/cve-bench` clone with docker images reachable.

For 40 CVEs, point `--fixtures-dir` at `<cve-bench>/src/critical/metadata`.

## Leaderboard submission

Per [cvebench.com](https://cvebench.com/), submissions go as PRs to
`uiuc-kang-lab/cve-bench` with Inspect logs. We mirror the 8 conditions
1:1 in `scorer.py` — pass criteria are not invented locally.

## References

- Upstream README & schema:
  <https://github.com/uiuc-kang-lab/cve-bench> (retrieved 2026-06-11)
- Leaderboard: <https://cvebench.com/>
- Paper: Zhu et al., ICML 2025 spotlight, arXiv:2503.17332
