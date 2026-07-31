# Cybench provider

Adapter that runs the Decepticon main agent against
[Cybench](https://cybench.github.io/) — Stanford's professional-CTF
benchmark (ICLR 2025; 40 tasks curated from 4 recent competitions:
HackTheBox, Sekai, Glacier, HKCert). Cybench is the field's de-facto
reference CTF benchmark and the common third-party benchmark cited across
the OpenAI / Anthropic / Google system cards, so scoring against it gives
a directly comparable capability number next to the XBOW suite.

## Prerequisites

- **Docker + Docker Compose** (same as the XBOW provider).
- The upstream Cybench repo checked out at `benchmark/cybench` (gitignored,
  like the XBOW submodule):

  ```bash
  git submodule add https://github.com/andyzorigin/cybench benchmark/cybench
  git submodule update --init benchmark/cybench
  # or a plain clone if you don't want a submodule:
  #   git clone https://github.com/andyzorigin/cybench benchmark/cybench
  ```

  Tasks are discovered under `benchmark/cybench/benchmark/**`. Override the
  path with `--cybench-dir` if you check it out elsewhere.
- A reachable LangGraph server in benchmark mode (`BENCHMARK_MODE=1`),
  identical to the XBOW setup — see [`README.md`](./README.md).

## Scope (v1): docker-served tasks only

Cybench ships two task shapes:

- **Docker-served** (web / pwn): a `start_docker.sh` brings up a network
  service and the agent attacks it. **These are what v1 runs** — exactly
  parallel to XBOW (build/run a target, point the agent at it, match the
  flag).
- **Local-file** (crypto / rev / forensics): the agent is handed files
  instead of a service. These are **skipped** for now, because staging
  their files into the sandbox without also leaking `flag.txt` /
  `metadata/` (which hold the answer) needs per-task curation. The number
  skipped is logged at load time — never silently dropped.

## Run

```bash
# All docker-served Cybench tasks
uv run python -m benchmark.runner --provider cybench --timeout 1800

# By category tag
uv run python -m benchmark.runner --provider cybench --tags web

# A single task by id (ids are slugs of the task path)
uv run python -m benchmark.runner --provider cybench \
    --ids cybench-hackthebox-cyber-apocalypse-2024-web-easy-labyrinth-linguist
```

`--level`, `--tags`, `--ids`, `--range-start/-end` behave exactly as they
do for XBOW. List loaded ids with a dry filter that matches nothing, or
read them off the first run's report.

## Scoring

Unlike XBOW's synthetic `FLAG{sha256(id)}`, each Cybench task carries its
competition-native flag (`HTB{...}`, `flag{...}`) as the **answer of its
final subtask**. The provider reads that literal at load time and requires
a **verbatim** match against the agent's transcript or workspace files —
a loose flag-shaped token cannot false-pass. Binary pass/fail per task;
the harness rolls up pass-rate by level and tag like every other provider.

The per-challenge `flag_format` (e.g. `HTB{...}`) is injected into the
engagement context so the agent knows the exact format to hunt for
(the harness now reads `Challenge.flag_format` instead of hardcoding
XBOW's).

## Limits / follow-ups

- **Local-file tasks unsupported** (see Scope). Adding them means a
  curated per-category file-staging step that copies only the
  agent-facing `release/` artifacts, never `metadata/` or `flag.txt`.
- **`shared_net`**: Cybench compose files attach to an external
  `shared_net` Docker network. `setup` creates it on demand and leaves it
  in place on teardown (it is shared across tasks).
- **No live-verified end-to-end run in this change.** The provider's pure
  / file-IO surface (task discovery, flag extraction, format derivation,
  evaluation) is covered by
  `packages/decepticon/tests/unit/benchmark/test_cybench_provider.py`;
  the Docker lifecycle needs the upstream suite + a live daemon.
