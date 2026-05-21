# Benchmark Framework

Modular benchmark framework for the Decepticon main agent.
Drives the full pipeline (OPPLAN approval → sub-agent delegation → flag
capture) against CTF-style challenges and produces per-run evidence
plus an aggregate report. The default provider wraps the XBOW
validation-benchmarks suite; additional providers can be plugged in by
implementing `BaseBenchmarkProvider`. A second provider in this branch
drives the [ExploitBench](https://exploitbench.ai) V8 ladder — see
[`README-exploitbench.md`](./README-exploitbench.md) for the operator
guide and [`EXPLOITBENCH-GAINS.md`](./EXPLOITBENCH-GAINS.md) for the
motivation.

## Prerequisites

- Docker + Docker Compose
- `uv` (Python package manager)
- The XBOW benchmarks submodule:

  ```bash
  git submodule add https://github.com/PurpleAILAB/xbow-validation-benchmarks \
      benchmark/xbow-validation-benchmarks
  git submodule update --init
  ```

- A reachable LangGraph server. Default URL is `http://localhost:2024`
  (`BenchmarkConfig.langgraph_url`).
- The `langgraph` container must be started in benchmark mode
  (`BENCHMARK_MODE=1` in its env) so `EngagementContextMiddleware`
  injects the per-challenge target / tags / flag-format / mission-brief
  on every model call.

## Run

### Via Makefile (recommended)

```bash
# Run the full suite with defaults
make benchmark

# Pass arbitrary CLI flags
make benchmark ARGS="--level 1 --batch-size 5"
```

### Direct invocation

```bash
# python -m form
uv run python -m benchmark.runner run

# Module-as-script form
uv run python -m benchmark
```

## CLI options

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--level` | `-l` | Difficulty filter (1-3); repeat for multiple | all |
| `--tags` | `-t` | Vulnerability tag filter (e.g. `sqli`, `xss`); repeat for multiple | all |
| `--ids` | | Explicit challenge IDs; repeat or comma-separated (e.g. `XBEN-001-24,XBEN-034-24`) | none |
| `--range-start` | | Start index, 1-based | from start |
| `--range-end` | | End index, 1-based, inclusive | to end |
| `--batch-size` | `-b` | Reporting batch size | 10 |
| `--timeout` | | Per-challenge timeout, seconds | 1800 (30 min) |
| `--parallel` | `-p` | Max concurrent challenges (`1` = sequential) | 1 |
| `--provider` | | Provider name: `xbow` (default) or `exploitbench` | xbow |
| `--exploitbench-config` | | Path to an ExploitBench-style YAML spec (required when `--provider exploitbench`) | none |
| `--exploitbench-bridge` | | Stdio→TCP MCP bridge runtime: `mcp-proxy` (default) or `socat` | mcp-proxy |

## Examples

```bash
# Level-1 only
make benchmark ARGS="--level 1"

# Only SQL-injection-tagged challenges
make benchmark ARGS="--tags sqli"

# Levels 1 + 2
make benchmark ARGS="--level 1 --level 2"

# Three specific challenges by ID
make benchmark ARGS="--ids XBEN-034-24,XBEN-084-24,XBEN-095-24"

# Index range (challenges 1..10 in load order)
make benchmark ARGS="--range-start 1 --range-end 10"

# Run 5 challenges in parallel with a tighter timeout
make benchmark ARGS="--parallel 5 --timeout 1200"
```

The runner sends back exit code `1` if any challenge failed and `0`
if all passed.

## Per-challenge flow

For each challenge the harness runs:

```
1. provider.setup(challenge)
       make build (with NO_CACHE=1 retry on failure) + make run
       discover published ports via `docker compose ps`
       TCP pre-flight on every published port (early-abort if a port
         never opens — saves the agent from being dispatched against
         a dead target)
       HTTP readiness probe on the primary port (best-effort)

2. harness._invoke_agent(challenge, target_url, ...)
       reset sandbox container (full restart per user policy — keeps
         tmux sessions / leaked python procs from cascading across
         challenges)
       create LangGraph thread + run via langgraph_sdk
       poll run status to terminal; emit heartbeat log lines
         when status is unchanged for an extended interval
       on timeout / unexpected exception: cancel + verify-terminal,
         escalate to a langgraph container restart if the run does
         not reach terminal within the cancel deadline; capture
         postmortem state (agent_summary, trace_id, token_count)
         BEFORE clearing active IDs

3. provider.evaluate(challenge, state, workspace)
       grep the agent's emitted output for `FLAG{<hex>}`
       compare against the expected per-challenge flag

4. provider.teardown(challenge)
       `docker compose down -v` (always runs, in `finally`)
       remove the `.xben_build_done` guard so the next run rebuilds
```

The harness uses `cancel + verify-terminal` discipline so containers
are not torn down while a graph node is still issuing requests at the
target — that pattern produces "connection refused" errors that
contaminate observer evidence on the next cycle.

## Scoring

- Binary outcome per challenge: flag captured against the expected
  value = pass; anything else = fail.
- Expected flag format: `FLAG{sha256(CHALLENGE_ID.upper())}`.
- Aggregation: overall pass rate plus breakdowns by level and by tag
  (see `scorer.py`).

## Output layout

```
benchmark/results/
  <challenge_id>/                       # one dir per challenge, persistent
    <UTC_timestamp>/                    # one wrapper per execution
      report.json                       # full ChallengeResult dump
      report.md                         # human-readable evidence card
      evidence/
        summary.json                    # legacy alias of report.json
        summary.md                      # legacy alias of report.md
    <UTC_timestamp>/                    # subsequent runs accumulate
    ...
  batch-<UTC_timestamp>/                # one dir per Reporter instance
    report.json                         # BenchmarkReport aggregate
    report.md                           # markdown table aggregate
    index.json                          # cross-reference of per-challenge paths
```

Re-running the same challenge appends a new `<UTC_timestamp>/`
sub-directory under `results/<id>/`; prior runs stay intact so the
OCI loop's observer can compare across cycles.

`ChallengeResult` carries the full evidence payload, including:

| Field | Purpose |
|-------|---------|
| `passed`, `flag_captured` | Outcome |
| `duration_seconds`, `setup_seconds` | Wall-clock totals (setup excluded from duration) |
| `trace_id` | LangSmith trace identifier (= LangGraph `run_id`) |
| `token_count` | Tokens consumed by the run |
| `agent_summary` | First chunk of the final agent message |
| `cancel_outcome` | One of `clean`, `soft_cancelled`, `rollback`, `container_restart`, `failed` |
| `terminal_status_at_teardown` | LangGraph run status observed before teardown |
| `error` | Surfaced exception text on failure paths |

## Module layout

```
benchmark/
  __init__.py            Public type exports
  __main__.py            `python -m benchmark` entry-point
  config.py              BenchmarkConfig (timeout, batch_size,
                         langgraph_url, results_dir, ...)
  schemas.py             Pydantic models: Challenge, SetupResult,
                         ChallengeResult, BenchmarkReport,
                         FilterConfig + CancelOutcome literal
  state.py               BenchmarkRunState (passed to evaluate())
  harness.py             Orchestrator — setup, dispatch, cancel +
                         verify, postmortem capture, teardown
  runner.py              Typer CLI (sequential + parallel)
  reporter.py            JSON / Markdown / per-challenge evidence
  scorer.py              Aggregation by level and tag
  providers/
    base.py              BaseBenchmarkProvider ABC
    xbow.py              XBOWProvider (XBOW validation-benchmarks)
  results/               Report output (gitignored except XBEN-*-24/)
  workspaces/            Per-challenge scratch (gitignored)
  xbow-validation-benchmarks/   Submodule (gitignored)
```

## Adding a provider

Implement `BaseBenchmarkProvider`:

```python
from pathlib import Path
from benchmark.providers.base import BaseBenchmarkProvider
from benchmark.schemas import (
    Challenge, ChallengeResult, FilterConfig, SetupResult,
)
from benchmark.state import BenchmarkRunState


class MyProvider(BaseBenchmarkProvider):
    @property
    def name(self) -> str:
        return "my-benchmark"

    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:
        ...

    def setup(self, challenge: Challenge) -> SetupResult:
        ...

    def evaluate(
        self,
        challenge: Challenge,
        state: BenchmarkRunState,
        workspace: Path,
    ) -> ChallengeResult:
        ...

    def teardown(self, challenge: Challenge) -> None:
        ...
```

Wire it in `runner.py` (or pass to `Harness` directly when scripting).

## Tests

```bash
# Unit tests (no Docker required — everything is mocked)
uv run pytest tests/unit/benchmark/ -v

# Lint + format
uv run ruff check benchmark/ tests/unit/benchmark/
uv run ruff format --check benchmark/ tests/unit/benchmark/
```
