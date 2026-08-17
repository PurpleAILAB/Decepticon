# CVE-Bench harness for Decepticon

Sibling to `benchmark/` XBOW provider; targets
[CVE-Bench](https://github.com/uiuc-kang-lab/cve-bench)
([leaderboard](https://cvebench.com/),
[paper](https://arxiv.org/abs/2503.17332)) — 40 critical CVEs, two
variants (`zero_day`, `one_day`), 8 win conditions per attempt.

**Live status:** the harness dispatches an already-provisioned CVE-Bench target
through the configured Decepticon LangGraph assistant and scores only the
structured workspace evidence it writes. Target lifecycle and credentials remain
owned by the upstream CVE-Bench operator.

## Layout

```
benchmark/cve_bench/
├── loader.py    parse upstream CVE-*.yml → CVEBenchChallenge
├── scorer.py    8 win-condition predicates → Verdict
├── runner.py    load → agent callable → score → JSONL
├── live.py      LangGraph dispatch + strict workspace evidence ingestion
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

## Full run, live mode

Start the Decepticon stack and an upstream CVE-Bench target set first. The live
runner does not provision targets and never guesses evaluator facts from agent
text; it accepts only ``cve-bench-evidence.json`` written in the challenge
workspace.

```bash
export CVE_BENCH_LANGGRAPH_URL=http://localhost:2024
export CVE_BENCH_ASSISTANT_ID=decepticon
uv run python -m benchmark.cve_bench.live \
  --fixtures-dir ../cve-bench/src/critical/metadata \
  --variant one_day \
  --output benchmark/results/cve-bench/live-one-day.jsonl
```

The agent receives the pinned target metadata and must write one JSON evidence
object. Unknown fields fail the run; the scorer remains the authority for all
eight win conditions. Use separate runs for `zero_day` and `one_day`.

## Leaderboard submission

Per [cvebench.com](https://cvebench.com/), submissions go as PRs to
`uiuc-kang-lab/cve-bench` with Inspect logs. We mirror the 8 conditions
1:1 in `scorer.py` — pass criteria are not invented locally.

## References

- Upstream README & schema:
  <https://github.com/uiuc-kang-lab/cve-bench> (retrieved 2026-06-11)
- Leaderboard: <https://cvebench.com/>
- Paper: Zhu et al., ICML 2025 spotlight, arXiv:2503.17332
