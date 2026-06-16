"""Fuzzing harness generation and crash triage package.

Pure-Python implementations that run without any fuzzer installed:

- ``harness`` — AFL++ / libFuzzer C harness source + compile/run command generator
- ``triage``  — ASAN / signal crash-output parser with exploitability classification

The agent escalates to real fuzzers via bash (afl-fuzz, honggfuzz,
clang -fsanitize=fuzzer) — this package is the harness factory and the
first-pass crash classifier.
"""

from __future__ import annotations

from decepticon.tools.fuzzing.harness import FuzzTarget, HarnessConfig, generate_harness
from decepticon.tools.fuzzing.triage import CrashAnalysis, triage_crash

__all__ = [
    "CrashAnalysis",
    "FuzzTarget",
    "HarnessConfig",
    "generate_harness",
    "triage_crash",
]
