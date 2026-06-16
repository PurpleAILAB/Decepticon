"""Fuzzing harness generation for AFL++ and libFuzzer.

Pure-Python: emits C harness source plus the compile / run commands the
agent can drop on disk and execute via bash. No subprocess calls here —
generation only. ASAN/UBSAN sanitizer flags are always included.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_SANITIZER_FLAGS = "-fsanitize=address,undefined -fno-omit-frame-pointer"


@dataclass
class HarnessConfig:
    """Inputs for ``generate_harness``."""

    target_library: str
    target_function: str
    input_type: str = "stdin"  # file | stdin | buffer
    compiler: str = "afl-clang-fast"
    extra_cflags: str = ""
    extra_ldflags: str = ""


@dataclass
class FuzzTarget:
    """Generated harness plus the commands to build and run it."""

    harness_source: str
    compile_cmd: str
    run_cmd: str
    sanitizer_flags: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_source": self.harness_source,
            "compile_cmd": self.compile_cmd,
            "run_cmd": self.run_cmd,
            "sanitizer_flags": self.sanitizer_flags,
        }


def _is_libfuzzer(compiler: str) -> bool:
    return "afl" not in compiler


def _libfuzzer_source(fn: str) -> str:
    return f"""#include <stdint.h>
#include <stddef.h>

/* Target under test. */
extern void {fn}(const uint8_t *data, size_t size);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {{
    if (data == NULL || size == 0) return 0;
    {fn}(data, size);
    return 0;
}}
"""


def _afl_source(fn: str, input_type: str) -> str:
    if input_type == "file":
        reader = """    if (argc < 2) return 1;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 1;
    size_t size = fread(buf, 1, sizeof(buf), f);
    fclose(f);"""
    else:  # stdin (default) and buffer both read from stdin under AFL
        reader = "    size_t size = fread(buf, 1, sizeof(buf), stdin);"

    return f"""#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* Target under test. */
extern void {fn}(const uint8_t *data, size_t size);

#ifndef MAX_INPUT
#define MAX_INPUT (1 << 20)
#endif

int main(int argc, char **argv) {{
    static uint8_t buf[MAX_INPUT];
{reader}
    if (size == 0) return 0;
    {fn}(buf, size);
    return 0;
}}
"""


def generate_harness(config: HarnessConfig) -> FuzzTarget:
    """Generate a C fuzzing harness and its build / run commands.

    libFuzzer (any non-AFL compiler) gets ``LLVMFuzzerTestOneInput``;
    AFL++ gets a ``main`` that reads from stdin or a file argument.
    """
    fn = config.target_function
    harness_file = "harness.c"
    out_bin = "fuzz_target"

    cflags = _SANITIZER_FLAGS
    if config.extra_cflags:
        cflags = f"{cflags} {config.extra_cflags}"
    ldflags = config.extra_ldflags

    if _is_libfuzzer(config.compiler):
        source = _libfuzzer_source(fn)
        cflags = f"{cflags} -fsanitize=fuzzer"
        compile_cmd = (
            f"{config.compiler} {cflags} {harness_file} "
            f"-l{config.target_library} {ldflags} -o {out_bin}".replace("  ", " ").strip()
        )
        run_cmd = f"./{out_bin} -max_len=4096 corpus/"
    else:
        source = _afl_source(fn, config.input_type)
        compile_cmd = (
            f"{config.compiler} {cflags} {harness_file} "
            f"-l{config.target_library} {ldflags} -o {out_bin}".replace("  ", " ").strip()
        )
        if config.input_type == "file":
            run_cmd = f"afl-fuzz -i corpus/ -o findings/ -- ./{out_bin} @@"
        else:
            run_cmd = f"afl-fuzz -i corpus/ -o findings/ -- ./{out_bin}"

    return FuzzTarget(
        harness_source=source,
        compile_cmd=compile_cmd,
        run_cmd=run_cmd,
        sanitizer_flags=_SANITIZER_FLAGS,
    )
