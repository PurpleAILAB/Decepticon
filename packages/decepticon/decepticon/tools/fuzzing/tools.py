"""LangChain @tool wrappers for the fuzzing package."""

from __future__ import annotations

import json
import shutil
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.fuzzing.harness import HarnessConfig, generate_harness
from decepticon.tools.fuzzing.triage import triage_crash


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def fuzz_generate_harness(
    target_library: str,
    target_function: str,
    input_type: str = "stdin",
    extra_cflags: str = "",
    extra_ldflags: str = "",
) -> str:
    """Generate an AFL++ / libFuzzer C harness for a target library function.

    Returns JSON with harness_source, compile_cmd, run_cmd, sanitizer_flags.
    """
    config = HarnessConfig(
        target_library=target_library,
        target_function=target_function,
        input_type=input_type,
        extra_cflags=extra_cflags,
        extra_ldflags=extra_ldflags,
    )
    return _json(generate_harness(config).to_dict())


@tool
def fuzz_triage_crash(crash_output: str, binary_path: str = "") -> str:
    """Triage a fuzzer crash from ASAN / signal output and rate exploitability.

    Returns JSON with crash_type, severity, faulting_address, stack_frames,
    asan_summary, exploitability_notes.
    """
    return _json(triage_crash(crash_output, binary_path).to_dict())


@tool
def fuzz_status() -> str:
    """Report which fuzzers / sanitizers are available on PATH."""
    backends = ["afl-fuzz", "afl-clang-fast", "honggfuzz", "clang", "clang++", "gcc"]
    return _json({name: bool(shutil.which(name)) for name in backends})


FUZZING_TOOLS = [fuzz_generate_harness, fuzz_triage_crash, fuzz_status]
