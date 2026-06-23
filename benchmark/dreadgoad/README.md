# DreadGOAD Benchmark Runner

Drives any LangGraph-registered agent through an Active Directory attack
range on AWS, captures per-run evidence (LangSmith trace, OPPLAN,
findings, workspace tarball, cost breakdown), and writes a per-agent
grid summary.

The lab is built and torn down by the upstream
[DreadGOAD](https://github.com/dreadnode/DreadGOAD) Go CLI; the runner
talks to the agent over the LangGraph SDK and to the sandbox container
over `docker exec` / `docker cp`. There is no downstream-only code path —
every config + provider + harness file under `benchmark/dreadgoad/`
runs as-is against an OSS Decepticon stack started with `make dev`.

## Prerequisites

1. **DreadGOAD CLI** built locally:

   ```bash
   git clone https://github.com/dreadnode/DreadGOAD
   cd DreadGOAD
   ansible-galaxy collection install -r ansible/requirements.yml
   go build -o cli/dreadgoad ./cli
   ```

   Export `DREADGOAD_CLI_PATH` to the absolute path of the built
   binary (default `./cli/dreadgoad`). If you bring up the lab out
   of band, set `DREADGOAD_BENCH_REUSE=1` plus the
   `DREADGOAD_BENCH_DC_URL` / `DREADGOAD_BENCH_DOMAIN` /
   `DREADGOAD_BENCH_SEED_USER` / `DREADGOAD_BENCH_SEED_PASS` env vars
   and the harness will skip provision/destroy.

2. **AWS credentials** with permissions to run the DreadGOAD Terraform
   modules (`aws configure`).

3. **A reachable LangGraph server** with the agent you want to drive
   already registered. The default config points at the OSS main
   agent (`decepticon`) on `http://localhost:2024` — start it with
   `make dev` from the repository root. Override via the `langgraph_url`
   field in the config YAML.

4. **(Optional) LiteLLM proxy** for cost attribution. Set
   `LITELLM_MASTER_KEY` if you want the runner to populate
   `cost_total_usd` from `/spend/logs`; otherwise the cost report
   records `time_window_unavailable` and the run still completes.

## Quick start

```bash
# Smoke a single agent against a fresh lab.
python3 -m benchmark.dreadgoad run \
    --config benchmark/dreadgoad/configs/apt29.yaml \
    --rounds 1
```

Outputs land under `benchmark/dreadgoad/results/<agent_id>/<UTC-ts>/`:

- `metadata.json` — run-level evidence (LangSmith trace id, timing,
  cost breakdown, lab provisioning info, agent activity counters)
- `scorecard.md` — human-readable single-run summary
- `measurement.json` — raw measurement-callback record pulled from the
  sandbox
- `opplan.json` / `timeline.jsonl` / `findings/` — workspace artifacts
- `workspace.tar.gz` — full `/workspace/<engagement>/` archive

A per-agent `grid-summary.md` is regenerated at the top of every
`results/<agent_id>/` directory after each grid run.

Exit codes:

- `0` — every scenario completed (`status == "completed"`)
- `1` — at least one scenario failed or timed out
- `2` — runner-level error (lab provision failed, LangGraph
  unreachable, …)

## Configs included

| Config | Personas × Rounds = Runs | `lab_mode` | Est. cloud cost |
|---|---|---|---|
| `apt28.yaml` / `apt29.yaml` / `apt41.yaml` / `apt44.yaml` / `lazarus.yaml` | 1 × 1 = 1 | isolated | $5–10 |
| `apt-grid-15runs.yaml` | 5 × 3 = 15 | isolated | $50–100 |
| `apt-shared-lab-grid.yaml` | 4 × 3 = 12 | shared | $5–10 |

Every shipped config defaults its `agents:` list to `decepticon` —
edit the YAML (or override on the CLI with `--agents <id1> <id2> …`)
to point at the LangGraph `assistant_id` of whatever agent you want
to drive against the lab.

## Lab lifecycle (`lab_mode`)

- **`isolated`** (default) — every scenario gets a fresh lab via
  `provider.provision`/`teardown`. AD state cannot leak between
  scenarios; cloud cost scales linearly with `rounds × len(agents)`.
- **`shared`** — the runner provisions ONE lab via
  `provider.provision_grid` before any scenario runs, every scenario
  reuses that `ProvisionResult`, and `provider.teardown_grid` is
  called once after the whole grid (even on grid-level failure).
  Workspaces remain isolated under `/workspace/<scenario.name>`; AD
  state does NOT. Cloud cost ≈ one lab.

Destructive techniques (T1485 data destruction, T1561.002 disk wipe,
etc.) corrupt sibling-scenario measurements when run in `shared` mode
— prefer `isolated` for those grids and gate the relevant T-codes
through `extra_opplan_concessions` (see `configs/apt44.yaml`).

## Cleanup

If a grid is interrupted, leftover AWS resources can be released
with the upstream CLI directly:

```bash
./cli/dreadgoad destroy --variant-id <id>
```

The `variant_id` for each scenario is recorded under
`results/<agent_id>/<UTC-ts>/metadata.json` (`lab.variant_id`) and
in `state.json` at the root of the results dir.

## Known gap — outer-timeout teardown

When a scenario exceeds `timeout_per_run_seconds`, the outer
`asyncio.wait_for` cancels `run_one` mid-execution. The inner
`finally: provider.teardown(provision)` block may not complete
before cancellation, which means the AWS lab can leak.

After any grid run that includes timed-out scenarios:

1. Inspect `results/state.json` for `variant_id` values on
   `status="timeout"` results.
2. For each leaked variant: `./cli/dreadgoad destroy --variant-id <id>`.
3. Cross-check `aws ec2 describe-instances` for any orphaned hosts.

## See also

- https://github.com/dreadnode/DreadGOAD — upstream lab + Go CLI
- `benchmark/README.md` — the other benchmark runner (XBOW / MHBench
  / ExploitBench) shipping in this repository
