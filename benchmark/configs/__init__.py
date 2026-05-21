"""ExploitBench-style YAML configs for the Decepticon benchmark runner.

Each file in this directory is a thin port of an upstream
``exploitbench/benchmarks/*.yaml`` config, restricted to the fields the
Decepticon harness consumes (``benchmark_id``, ``envs``, ``seeds``,
``init_prompt``, ``init_prompt_hint``). Anything else upstream — model
dispatch, nudge schedules, cost caps, budget knobs — is intentionally
not modeled and is silently dropped by ``ExploitBenchProvider._load_spec``.
"""
